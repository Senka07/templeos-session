#!/usr/bin/env python3
"""Ponte do org.freedesktop.systemd1 para o D-Bus proprio da sessao.

A sessao roda em `dbus-run-session` (ver sessao.sh) para o xfconfd ler as
configuracoes dela. O systemd --user, porem, so esta no barramento do usuario
($XDG_RUNTIME_DIR/bus). Quem procura por ele no barramento da sessao recebe
"Process org.freedesktop.systemd1 exited with status 1": o dbus-daemon acha o
.service do nome, que e um /bin/false de mentira, e tenta ativar. Acontece com
`systemd-run --user --wait` (e --pty, --pipe, --shell), `flatpak run` criando o
scope de cada app, e qualquer programa que fale com o systemd pelo D-Bus.

Esta ponte e dona do nome no barramento da sessao e repassa:
  chamadas  a mensagem inteira (corpo, descritores de arquivo, flags) vai para o
            systemd de verdade, e a resposta volta para quem chamou;
  sinais    tudo o que o systemd emite (JobRemoved, PropertiesChanged...) e
            emitido de novo aqui, que e o que o systemd-run --wait espera ouvir.

Uma conta a mais: com AddRef=true no StartTransientUnit (o systemd-run --wait
usa) a unidade fica presa a quem pediu, para ninguem perder o resultado dela.
Quem pediu, para o systemd, e a ponte, que vive a sessao toda. Por isso, quando
o cliente de verdade sai do barramento da sessao, a ponte chama UnrefUnit.

TEMPLEOS_BARRAMENTO_USUARIO troca o endereco do barramento do usuario.
"""
import os, sys
from gi.repository import Gio, GLib

NOME = 'org.freedesktop.systemd1'
GERENTE = '/org/freedesktop/systemd1'
INT_GERENTE = 'org.freedesktop.systemd1.Manager'

def endereco_usuario():
    end = os.environ.get('TEMPLEOS_BARRAMENTO_USUARIO')
    if end is None:
        run = os.environ.get('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())
        end = 'unix:path=' + os.path.join(run, 'bus')
    return end if end not in ('', '0') else None

def pede_addref(msg):
    """Nome da unidade, se a mensagem e um StartTransientUnit com AddRef=true."""
    if msg.get_interface() != INT_GERENTE or msg.get_member() != 'StartTransientUnit':
        return None
    corpo = msg.get_body()
    if corpo is None or corpo.get_type_string() != '(ssa(sv)a(sa(sv)))':
        return None
    props = corpo.get_child_value(2)
    for i in range(props.n_children()):
        nome, valor = props.get_child_value(i).unpack()
        if nome == 'AddRef' and valor is True:
            return corpo.get_child_value(0).get_string()
    return None

class Ponte:
    def __init__(self, sessao, usuario):
        self.sessao, self.usuario = sessao, usuario
        self.refs = {}   # nome unico do cliente na sessao -> unidades com AddRef
        usuario.signal_subscribe(NOME, None, None, None, None, Gio.DBusSignalFlags.NONE,
                                 self.sinal)
        sessao.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
                                'NameOwnerChanged', '/org/freedesktop/DBus', None,
                                Gio.DBusSignalFlags.NONE, self.dono_mudou)
        # O filtro roda na thread do GDBus, antes de qualquer tratamento: as
        # chamadas para a ponte nao chegam a virar "UnknownMethod".
        sessao.add_filter(self.filtro)
        usuario.connect('closed', self.caiu)
        sessao.connect('closed', self.caiu)

    def caiu(self, *_):
        print('ponte-systemd: barramento fechou, saindo', file=sys.stderr)
        os._exit(0)

    def filtro(self, _con, msg, entrando):
        if entrando and msg.get_message_type() == Gio.DBusMessageType.METHOD_CALL:
            GLib.idle_add(self.repassa, msg)
            return None
        return msg

    def repassa(self, msg):
        ida = Gio.DBusMessage.new_method_call(NOME, msg.get_path(), msg.get_interface(),
                                              msg.get_member())
        ida.set_flags(msg.get_flags())
        corpo = msg.get_body()
        if corpo is not None:
            ida.set_body(corpo)
        fds = msg.get_unix_fd_list()
        if fds is not None:
            ida.set_unix_fd_list(fds)
        unidade = pede_addref(msg)
        try:
            # sem limite de tempo: o systemd-run --wait so recebe a resposta no fim
            self.usuario.send_message_with_reply(
                ida, Gio.DBusSendMessageFlags.NONE, GLib.MAXINT32, None,
                self.respondeu, (msg, unidade))
        except GLib.Error as e:
            self.erro(msg, 'org.freedesktop.DBus.Error.Failed', e.message)
        return False

    def respondeu(self, con, res, dados):
        msg, unidade = dados
        try:
            volta = con.send_message_with_reply_finish(res)
        except GLib.Error as e:
            self.erro(msg, 'org.freedesktop.DBus.Error.NoReply', e.message)
            return
        if msg.get_flags() & Gio.DBusMessageFlags.NO_REPLY_EXPECTED:
            return
        if volta.get_message_type() == Gio.DBusMessageType.ERROR:
            corpo = volta.get_body()
            texto = corpo.get_child_value(0).get_string() if (
                corpo is not None and corpo.get_type_string().startswith('(s')) else ''
            self.erro(msg, volta.get_error_name(), texto)
            return
        r = Gio.DBusMessage.new_method_reply(msg)
        corpo = volta.get_body()
        if corpo is not None:
            r.set_body(corpo)
        if volta.get_unix_fd_list() is not None:
            r.set_unix_fd_list(volta.get_unix_fd_list())
        if unidade:
            self.refs.setdefault(msg.get_sender(), set()).add(unidade)
        self.envia(r)

    def erro(self, msg, nome, texto):
        if not msg.get_flags() & Gio.DBusMessageFlags.NO_REPLY_EXPECTED:
            self.envia(Gio.DBusMessage.new_method_error_literal(msg, nome, texto))

    def envia(self, r):
        try:
            self.sessao.send_message(r, Gio.DBusSendMessageFlags.NONE)
        except GLib.Error as e:
            print('ponte-systemd:', e.message, file=sys.stderr)

    def sinal(self, _con, _rem, caminho, interface, membro, params):
        try:
            self.sessao.emit_signal(None, caminho, interface, membro, params)
        except GLib.Error as e:
            print('ponte-systemd:', e.message, file=sys.stderr)

    def dono_mudou(self, _con, _rem, _cam, _int, _sinal, params):
        nome, _velho, novo = params.unpack()
        if novo or nome not in self.refs:
            return
        for unidade in self.refs.pop(nome):
            self.usuario.call(NOME, GERENTE, INT_GERENTE, 'UnrefUnit',
                              GLib.Variant('(s)', (unidade,)), None,
                              Gio.DBusCallFlags.NONE, -1, None, None)

def main():
    end = endereco_usuario()
    if not end:
        return
    sessao = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    if sessao.get_unique_name() is None:
        return
    # Mesmo barramento (a sessao sem dbus-run-session): o systemd ja esta la.
    if os.environ.get('DBUS_SESSION_BUS_ADDRESS', '').split(',')[0] == end.split(',')[0]:
        return
    try:
        usuario = Gio.DBusConnection.new_for_address_sync(
            end, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    except GLib.Error as e:
        print('ponte-systemd: barramento do usuario:', e.message, file=sys.stderr)
        return
    Ponte(sessao, usuario)
    laco = GLib.MainLoop()
    Gio.bus_own_name_on_connection(sessao, NOME, Gio.BusNameOwnerFlags.NONE, None,
                                   lambda *_: laco.quit())
    laco.run()

if __name__ == '__main__':
    main()
