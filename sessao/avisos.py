#!/usr/bin/env python3
"""Notificacoes da sessao TempleOS: o servico org.freedesktop.Notifications.

Sem isto o D-Bus proprio da sessao ativa o xfce4-notifyd, sem tema. Cada aviso e
um documento DolDoc no canto superior direito: moldura de glifos, nome do app
como titulo, resumo em vermelho e corpo em azul, os botoes das acoes em $BT.

Clicar em qualquer lugar fecha e dispara a acao "default", se houver. Enquanto a
tela esta bloqueada (selecao _TEMPLEOS_TRAVA, ver trava/trava.c) os avisos ficam
na fila: o texto deles nao deve aparecer na tela de quem nao destravou.
"""
import html, os, re, sys, textwrap, unicodedata, warnings
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x11
from doc import Doc, trecho, botao
from texto import C, BLUE, RED, WHITE, LTBLUE, escreve

NOME = 'org.freedesktop.Notifications'
CAMINHO = '/org/freedesktop/Notifications'
INTERFACE = '''<node><interface name="org.freedesktop.Notifications">
  <method name="GetCapabilities"><arg type="as" direction="out"/></method>
  <method name="Notify">
    <arg type="s"/><arg type="u"/><arg type="s"/><arg type="s"/><arg type="s"/>
    <arg type="as"/><arg type="a{sv}"/><arg type="i"/>
    <arg type="u" direction="out"/>
  </method>
  <method name="CloseNotification"><arg type="u"/></method>
  <method name="GetServerInformation">
    <arg type="s" direction="out"/><arg type="s" direction="out"/>
    <arg type="s" direction="out"/><arg type="s" direction="out"/>
  </method>
  <signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
  <signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
</interface></node>'''

COLS = 46
INTERNAS = COLS - 4          # colunas de texto: moldura e um espaco de cada lado
MAX_CORPO = 6                # linhas
MAX_NA_TELA = 5
MAX_NA_FILA = 20
PADRAO_MS = 8000
EXPIROU, DISPENSOU, PEDIRAM = 1, 2, 3   # motivos de NotificationClosed
# glifos de moldura em linha simples (ver BORDAS em xfwm4/gerar-tema.py)
H, V, SE, SD, IE, ID = '\x02', '\x04', '\x06', '\x08', '\x0a', '\x0c'

def cp437(s):
    """Unicode para o que escreve() desenha: a metade de cima da fonte e CP437.

    O que nao existe nela perde o acento (a CP437 nao tem til, por exemplo) e o
    que nem assim existe, como emoji, sai do texto.
    """
    r = []
    for ch in s:
        if ord(ch) < 32 or ord(ch) == 127:
            continue
        for tentativa in (ch, unicodedata.normalize('NFKD', ch)[:1]):
            try:
                r.append(tentativa.encode('cp437').decode('latin1'))
                break
            except UnicodeEncodeError:
                pass
    return ''.join(r)

def sem_marcacao(s):
    # Nao anunciamos body-markup, mas alguns apps mandam mesmo assim
    return html.unescape(re.sub(r'<[^>]+>', '', s))

def quebra(s, largura, maximo):
    linhas = []
    for par in s.split('\n'):
        linhas += textwrap.wrap(cp437(par), largura) or ['']
    while linhas and not linhas[-1]:
        linhas.pop()
    if len(linhas) > maximo:
        linhas = linhas[:maximo]
        linhas[-1] = linhas[-1][:largura - 3] + '...'
    return linhas

def tamanho_tela():
    # o XScreen, que o RandR atualiza na hora (ver o comentario no fundo.py)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        t = Gdk.Screen.get_default()
        return t.get_width(), t.get_height()

def tela_bloqueada():
    return x11.x11.XGetSelectionOwner(x11.DPY, x11.atomo('_TEMPLEOS_TRAVA')) != 0

class Aviso(Doc):
    def __init__(self, central, ident, dados):
        super().__init__(dados['app'] or 'Notification', COLS, 3, x=0, y=0)
        self.central, self.ident, self.dados, self.timer = central, ident, dados, None
        critico = dados['critico']
        # Janela gerenciada do tipo notificacao: fica acima das outras sem
        # receber foco, sem barra de titulo do xfwm4 e fora do Alt+Tab.
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_decorated(False)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)

        titulo = ' %s ' % cp437(dados['app'] or 'Notification')[:COLS - 10]
        topo = [trecho(SE + H, LTBLUE), trecho(titulo, WHITE, fundo=RED if critico else LTBLUE),
                trecho(H * (COLS - 6 - len(titulo)), LTBLUE),
                trecho('[X]', LTBLUE, lambda: central.fecha(self, DISPENSOU)), trecho(SD, LTBLUE)]
        linhas = [topo]
        for l in quebra(dados['titulo'], INTERNAS, 2):
            linhas.append([trecho('  ' + l, RED)])
        for l in quebra(dados['corpo'], INTERNAS, MAX_CORPO):
            linhas.append([trecho('  ' + l)])
        acoes = dados['acoes'][:3]
        if acoes:
            linha = [trecho(' ')]
            for chave, rotulo in acoes:
                linha += [botao(cp437(rotulo)[:11],
                                lambda c=chave: central.aciona(self, c)), trecho(' ')]
            linhas += [[], linha, []]
        linhas.append([trecho(IE + H * (COLS - 2) + ID, LTBLUE)])
        self.conteudo = linhas
        self.linhas = len(linhas)
        self.ao_clicar = lambda: central.aciona(self, 'default')
        self.set_default_size(COLS * C, self.linhas * C)
        self.set_size_request(COLS * C, self.linhas * C)

    def desenha(self, w, cr):
        super().desenha(w, cr)
        for lin in range(1, self.linhas - 1):  # os lados, depois dos botoes e do texto
            escreve(cr, 0, lin, V, LTBLUE, WHITE)
            escreve(cr, COLS - 1, lin, V, LTBLUE, WHITE)
        return True

class Central:
    def __init__(self):
        self.ativos, self.fila, self.proximo = [], [], 1
        self.conexao = None
        self.no = Gio.DBusNodeInfo.new_for_xml(INTERFACE).interfaces[0]
        tela = Gdk.Screen.get_default()
        tela.connect('size-changed', self.tela_mudou)
        tela.connect('monitors-changed', self.tela_mudou)
        GLib.timeout_add_seconds(1, self.confere_fila)
        # A sessao sobe isto antes de todo app. Com a sessao no ar, fica na espera
        # do nome e o assume quando o dono atual (o xfce4-notifyd) sair.
        Gio.bus_own_name(Gio.BusType.SESSION, NOME, Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
                         self.barramento, None, None)

    # ------------------------------------------------------------ D-Bus
    def barramento(self, conexao, _nome):
        self.conexao = conexao
        conexao.register_object(CAMINHO, self.no, self.chamada, None, None)

    def chamada(self, _con, _rem, _cam, _int, metodo, params, inv):
        try:
            if metodo == 'Notify':
                inv.return_value(GLib.Variant('(u)', (self.notify(params),)))
            elif metodo == 'CloseNotification':
                self.close(params.unpack()[0])
                inv.return_value(None)
            elif metodo == 'GetCapabilities':
                inv.return_value(GLib.Variant('(as)', (['body', 'actions'],)))
            elif metodo == 'GetServerInformation':
                inv.return_value(GLib.Variant('(ssss)', ('avisos', 'TempleOS', '1.0', '1.2')))
            else:
                inv.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod', metodo)
        except Exception as e:  # um app mandar lixo nao derruba o servico
            print('avisos:', e, file=sys.stderr)
            inv.return_dbus_error('org.freedesktop.DBus.Error.Failed', str(e))

    def emite(self, sinal, tipo, valores):
        if self.conexao:
            self.conexao.emit_signal(None, CAMINHO, NOME, sinal, GLib.Variant(tipo, valores))

    def notify(self, params):
        # Campo a campo: desempacotar os hints inteiros copiaria o image-data
        campo = lambda i: params.get_child_value(i).unpack()
        troca = campo(1)
        acoes_v = campo(5)
        urg = params.get_child_value(6).lookup_value('urgency', GLib.VariantType('y'))
        critico = urg is not None and urg.get_byte() == 2
        dados = dict(
            app=campo(0), titulo=sem_marcacao(campo(3)), corpo=sem_marcacao(campo(4)),
            acoes=[(c, r) for c, r in zip(acoes_v[::2], acoes_v[1::2]) if c != 'default'],
            tem_padrao='default' in acoes_v[::2], critico=critico, expira=campo(7))
        ident = troca or self.proximo
        if not troca:
            self.proximo += 1
        self.mostra_ou_enfileira(ident, dados)
        return ident

    def close(self, ident):
        for a in self.ativos:
            if a.ident == ident:
                self.fecha(a, PEDIRAM)
                return
        for item in self.fila:
            if item[0] == ident:
                self.fila.remove(item)
                self.emite('NotificationClosed', '(uu)', (ident, PEDIRAM))
                return

    # ------------------------------------------------------------ pilha
    def mostra_ou_enfileira(self, ident, dados):
        for item in self.fila:
            if item[0] == ident:  # replaces_id de quem ainda esta na fila
                self.fila[self.fila.index(item)] = (ident, dados)
                return
        for a in self.ativos:
            if a.ident == ident:
                i = self.ativos.index(a)
                self.desliga(a)
                self.ativos[i] = self.cria(ident, dados)
                self.arranja()
                return
        self.fila.append((ident, dados))
        while len(self.fila) > MAX_NA_FILA:
            velho = self.fila.pop(0)
            self.emite('NotificationClosed', '(uu)', (velho[0], EXPIROU))
        self.puxa()

    def cria(self, ident, dados):
        a = Aviso(self, ident, dados)
        a.show_all()
        expira = dados['expira']
        if expira < 0:
            expira = 0 if dados['critico'] else PADRAO_MS
        if expira:
            a.timer = GLib.timeout_add(expira, self.expirou, a)
        return a

    def expirou(self, a):
        a.timer = None
        self.fecha(a, EXPIROU)
        return False

    def desliga(self, a):
        if a.timer:
            GLib.source_remove(a.timer)
            a.timer = None
        a.destroy()

    def fecha(self, a, motivo):
        if a not in self.ativos:
            return
        self.ativos.remove(a)
        self.desliga(a)
        self.emite('NotificationClosed', '(uu)', (a.ident, motivo))
        self.arranja()
        self.puxa()

    def aciona(self, a, chave):
        if a not in self.ativos:
            return
        if chave != 'default' or a.dados['tem_padrao']:
            self.emite('ActionInvoked', '(us)', (a.ident, chave))
        self.fecha(a, DISPENSOU)

    def puxa(self):
        if tela_bloqueada():
            return
        _, h = tamanho_tela()
        while self.fila and len(self.ativos) < MAX_NA_TELA:
            usado = 2 * C + sum((a.linhas + 1) * C for a in self.ativos)
            ident, dados = self.fila[0]
            a = self.cria(ident, dados)
            if self.ativos and usado + a.linhas * C > h:  # espera abrir espaco
                self.desliga(a)
                break
            self.fila.pop(0)
            self.ativos.append(a)
        self.arranja()

    def arranja(self):
        w, _ = tamanho_tela()
        y = 2 * C  # logo abaixo da linha de status
        for a in self.ativos:
            a.move(w - COLS * C - C, y)
            y += (a.linhas + 1) * C

    def confere_fila(self):
        if self.fila:
            self.puxa()
        return True

    def tela_mudou(self, *_):
        GLib.timeout_add(300, lambda: self.arranja() or False)

if __name__ == '__main__':
    Central()
    Gtk.main()
