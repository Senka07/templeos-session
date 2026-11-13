#!/usr/bin/env python3
"""O servico org.freedesktop.ScreenSaver da sessao TempleOS.

O original nao tem protetor de tela nem bloqueio: a tela fica sempre acesa.
Este processo existe por dois motivos de fora do TempleOS:

1. Inibir. Firefox, Chromium, VLC, OBS e companhia pedem Inhibit() pelo D-Bus
   enquanto passam um video. Sem ninguem com esse nome no barramento o pedido
   falha calado. Aqui ele vira XScreenSaverSuspend(): o servidor X para de
   contar o tempo parado e nao apaga o monitor (DPMS) enquanto houver pedido.
   Isso so faz diferenca com TEMPLEOS_TELA_ACESA=0 ou com o item 2 ligado.

2. Bloquear depois de N minutos parado (TEMPLEOS_BLOQUEIO_MIN no sessao.conf;
   0 ou vazio desliga, que e o padrao). Quem conta o tempo e o proprio
   servidor X: XSetScreenSaver(N*60) e este processo se registra como o
   "protetor externo" (XScreenSaverSetAttributes com uma janela InputOnly de
   1x1). Quando o tempo acaba, o X mapeia essa janela invisivel no lugar de
   apagar a tela e manda um ScreenSaverNotify; aqui o protetor e desligado na
   hora (XForceScreenSaver Reset) e o trava entra. Contar no servidor, e nao
   num relogio proprio, faz valer tambem o XScreenSaverSuspend que jogos SDL
   e o mpv pedem direto ao X, sem passar pelo D-Bus.

A tela bloqueada e a selecao _TEMPLEOS_TRAVA (ver trava/trava.c). O XFixes
avisa quando ela muda de dono, e isso vira o sinal ActiveChanged.

Pedidos de inibicao morrem com o processo que pediu: um navegador que caiu no
meio do video nao deixa a tela acesa para sempre.
"""
import ctypes, os, signal, sys, time
from ctypes import c_int, c_uint, c_ulong, c_void_p, POINTER, Structure, byref
import gi
from gi.repository import Gio, GLib
try:
    gi.require_version('GLibUnix', '2.0')
    from gi.repository import GLibUnix
except (ImportError, ValueError):
    GLibUnix = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x11, deus, bloqueio
from x11 import DPY, RAIZ
from texto import RAIZ as RAIZ_REPO

NOME = 'org.freedesktop.ScreenSaver'
# Firefox e o xdg-screensaver usam /ScreenSaver; Chromium e GLib, o caminho longo
CAMINHOS = ('/org/freedesktop/ScreenSaver', '/ScreenSaver')
INTERFACE = '''<node><interface name="org.freedesktop.ScreenSaver">
  <method name="Inhibit">
    <arg type="s" direction="in"/><arg type="s" direction="in"/>
    <arg type="u" direction="out"/>
  </method>
  <method name="UnInhibit"><arg type="u" direction="in"/></method>
  <method name="Lock"/>
  <method name="SimulateUserActivity"/>
  <method name="GetActive"><arg type="b" direction="out"/></method>
  <method name="SetActive">
    <arg type="b" direction="in"/><arg type="b" direction="out"/>
  </method>
  <method name="GetActiveTime"><arg type="u" direction="out"/></method>
  <method name="GetSessionIdleTime"><arg type="u" direction="out"/></method>
  <signal name="ActiveChanged"><arg type="b"/></signal>
</interface></node>'''

# --- MIT-SCREEN-SAVER (libXss) e XFixes, via ctypes ---------------------------
try:
    xss = ctypes.CDLL('libXss.so.1')
except OSError:
    sys.exit('protetor: sem libXss (pacote libxss), nada de inibir nem de bloquear parado')
xf = ctypes.CDLL('libXfixes.so.3')  # vem com o GTK 3

class XScreenSaverInfo(Structure):
    _fields_ = [('window', c_ulong), ('state', c_int), ('kind', c_int),
                ('til_or_since', c_ulong), ('idle', c_ulong), ('eventMask', c_ulong)]

class XScreenSaverNotifyEvent(Structure):
    _fields_ = [('type', c_int), ('serial', c_ulong), ('send_event', c_int),
                ('display', c_void_p), ('window', c_ulong), ('root', c_ulong),
                ('state', c_int), ('kind', c_int), ('forced', c_int), ('time', c_ulong)]

def _f(lib, nome, res, args):
    fn = getattr(lib, nome)
    fn.restype, fn.argtypes = res, args

_f(xss, 'XScreenSaverQueryExtension', c_int, [c_void_p, POINTER(c_int), POINTER(c_int)])
_f(xss, 'XScreenSaverSelectInput', None, [c_void_p, c_ulong, c_ulong])
_f(xss, 'XScreenSaverSetAttributes', None, [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint,
                                            c_uint, c_int, c_uint, c_void_p, c_ulong, c_void_p])
_f(xss, 'XScreenSaverUnsetAttributes', None, [c_void_p, c_ulong])
_f(xss, 'XScreenSaverSuspend', None, [c_void_p, c_int])
_f(xss, 'XScreenSaverQueryInfo', c_int, [c_void_p, c_ulong, POINTER(XScreenSaverInfo)])
_f(xf, 'XFixesQueryExtension', c_int, [c_void_p, POINTER(c_int), POINTER(c_int)])
_f(xf, 'XFixesSelectSelectionInput', None, [c_void_p, c_ulong, c_ulong, c_ulong])
_f(x11.x11, 'XSetScreenSaver', c_int, [c_void_p, c_int, c_int, c_int, c_int])
_f(x11.x11, 'XGetScreenSaver', c_int, [c_void_p, POINTER(c_int), POINTER(c_int),
                                       POINTER(c_int), POINTER(c_int)])
_f(x11.x11, 'XForceScreenSaver', c_int, [c_void_p, c_int])

SCREEN_SAVER_ON = 1
SCREEN_SAVER_RESET = 0
NOTIFY_MASK = 1                     # ScreenSaverNotifyMask
INPUT_ONLY = 2                      # classe de janela
COPY_FROM_PARENT = 0
SELECAO_MUDOU = 1 | 2 | 4           # SetSelectionOwner | WindowDestroy | ClientClose

def ambiente():
    env = dict(os.environ)
    env.pop('GTK_THEME', None)
    env['TEMPLEOS_RAIZ'] = RAIZ_REPO
    return env

def segundos():
    """TEMPLEOS_BLOQUEIO_MIN em segundos. Aceita fracao: 0.1 da 6 s, para testar."""
    try:
        return max(0, round(float(os.environ.get('TEMPLEOS_BLOQUEIO_MIN') or 0) * 60))
    except ValueError:
        print('protetor: TEMPLEOS_BLOQUEIO_MIN nao e um numero, bloqueio desligado',
              file=sys.stderr)
        return 0

class Protetor:
    def __init__(self):
        self.oraculo = deus.Oraculo()
        self.inibidores = {}        # cookie -> (remetente, app, motivo)
        self.proximo = 1
        self.suspenso = False
        self.bloqueada = bloqueio.bloqueada()
        self.desde = time.monotonic() if self.bloqueada else 0
        self.pediu_em = 0           # evita dois trava seguidos antes do 1o pegar a selecao
        self.conexao = None
        self.registros = []

        ev, err = c_int(), c_int()
        if not xss.XScreenSaverQueryExtension(DPY, byref(ev), byref(err)):
            sys.exit('protetor: o servidor X nao tem MIT-SCREEN-SAVER')
        self.ev_protetor = ev.value
        xf.XFixesQueryExtension(DPY, byref(ev), byref(err))
        self.ev_fixes = ev.value
        xf.XFixesSelectSelectionInput(DPY, RAIZ, x11.atomo('_TEMPLEOS_TRAVA'), SELECAO_MUDOU)

        # guarda o que estava antes (o sessao.sh pode ter feito "xset s off")
        self.antes = [c_int() for _ in range(4)]
        x11.x11.XGetScreenSaver(DPY, *(byref(v) for v in self.antes))
        self.seg = segundos()
        if self.seg:
            t, i, blank, expo = (v.value for v in self.antes)
            x11.x11.XSetScreenSaver(DPY, self.seg, 0, blank, expo)
            # protetor externo: o X mapeia esta janela em vez de apagar a tela
            xss.XScreenSaverSetAttributes(DPY, RAIZ, 0, 0, 1, 1, 0, 0, INPUT_ONLY,
                                          None, 0, None)
            xss.XScreenSaverSelectInput(DPY, RAIZ, NOTIFY_MASK)
        x11.x11.XFlush(DPY)
        GLib.io_add_watch(x11.x11.XConnectionNumber(DPY), GLib.IO_IN, self.eventos)

    def encerra(self):
        if self.seg:
            xss.XScreenSaverUnsetAttributes(DPY, RAIZ)
            x11.x11.XSetScreenSaver(DPY, *(v.value for v in self.antes))
        x11.x11.XSync(DPY, False)   # o Suspend some sozinho com a conexao

    # --- X ---------------------------------------------------------------
    def eventos(self, *_):
        ev = x11.XEvent()
        while x11.x11.XPending(DPY):
            x11.x11.XNextEvent(DPY, byref(ev))
            if ev.type == self.ev_protetor:
                n = ctypes.cast(byref(ev), POINTER(XScreenSaverNotifyEvent)).contents
                if n.state == SCREEN_SAVER_ON:
                    self.parado()
            elif ev.type == self.ev_fixes:
                self.confere_trava()
        return True

    def parado(self):
        """O X contou TEMPLEOS_BLOQUEIO_MIN minutos sem teclado nem mouse."""
        x11.x11.XForceScreenSaver(DPY, SCREEN_SAVER_RESET)
        x11.x11.XFlush(DPY)
        # Inibido nao deveria chegar aqui (Suspend). Bloqueada, o X continua
        # contando na tela do trava: so desliga o protetor de novo.
        if self.inibidores or bloqueio.bloqueada():
            return
        print('protetor: %d s parado, bloqueando' % self.seg, file=sys.stderr)
        self.bloqueia()

    def bloqueia(self):
        if bloqueio.bloqueada() or time.monotonic() - self.pediu_em < 5:
            return
        self.pediu_em = time.monotonic()
        bloqueio.bloqueia(self.oraculo, ambiente())

    def confere_trava(self):
        agora = bloqueio.bloqueada()
        if agora == self.bloqueada:
            return
        self.bloqueada = agora
        self.desde = time.monotonic() if agora else 0
        for caminho in CAMINHOS:
            self.conexao.emit_signal(None, caminho, NOME, 'ActiveChanged',
                                     GLib.Variant('(b)', (agora,)))

    def suspende(self):
        quer = bool(self.inibidores)
        if quer != self.suspenso:
            xss.XScreenSaverSuspend(DPY, quer)
            x11.x11.XFlush(DPY)
            self.suspenso = quer

    def ocioso(self):
        info = XScreenSaverInfo()
        xss.XScreenSaverQueryInfo(DPY, RAIZ, byref(info))
        return info.idle // 1000

    # --- D-Bus -----------------------------------------------------------
    def chamada(self, con, remetente, caminho, iface, metodo, args, pedido):
        a = args.unpack()
        r = None
        if metodo == 'Inhibit':
            cookie = self.proximo
            self.proximo += 1
            self.inibidores[cookie] = (remetente, a[0], a[1])
            print('protetor: inibido por %s (%s): %s' % (a[0], remetente, a[1]), file=sys.stderr)
            self.suspende()
            r = GLib.Variant('(u)', (cookie,))
        elif metodo == 'UnInhibit':
            dono = self.inibidores.get(a[0])
            if dono and dono[0] == remetente:
                del self.inibidores[a[0]]
                print('protetor: %s liberou' % dono[1], file=sys.stderr)
                self.suspende()
        elif metodo == 'Lock':
            self.bloqueia()
        elif metodo == 'SimulateUserActivity':
            x11.x11.XForceScreenSaver(DPY, SCREEN_SAVER_RESET)
            x11.x11.XFlush(DPY)
        elif metodo == 'GetActive':
            r = GLib.Variant('(b)', (self.bloqueada,))
        elif metodo == 'SetActive':
            # ligar = bloquear; desligar a tela bloqueada so com a senha
            if a[0]:
                self.bloqueia()
            r = GLib.Variant('(b)', (bool(a[0]),))
        elif metodo == 'GetActiveTime':
            s = int(time.monotonic() - self.desde) if self.bloqueada else 0
            r = GLib.Variant('(u)', (s,))
        elif metodo == 'GetSessionIdleTime':
            r = GLib.Variant('(u)', (self.ocioso(),))
        pedido.return_value(r)

    def dono_mudou(self, con, remetente, caminho, iface, sinal, args):
        nome, velho, novo = args.unpack()
        if novo or not nome.startswith(':'):
            return
        mortos = [c for c, (quem, *_) in self.inibidores.items() if quem == nome]
        for c in mortos:
            print('protetor: %s saiu sem liberar' % self.inibidores.pop(c)[1], file=sys.stderr)
        if mortos:
            self.suspende()

    def no_barramento(self, con, nome):
        self.conexao = con
        info = Gio.DBusNodeInfo.new_for_xml(INTERFACE).interfaces[0]
        for caminho in CAMINHOS:
            self.registros.append(con.register_object(caminho, info, self.chamada))
        con.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
                             'NameOwnerChanged', '/org/freedesktop/DBus', None,
                             Gio.DBusSignalFlags.NONE, self.dono_mudou)

def main():
    p = Protetor()
    laco = GLib.MainLoop()
    def perdeu(con, nome):
        # excecao num callback do GLib nao encerra o processo: sai pelo laco
        print('protetor: outro processo ja tem %s' % NOME, file=sys.stderr)
        laco.quit()
    Gio.bus_own_name(Gio.BusType.SESSION, NOME, Gio.BusNameOwnerFlags.NONE,
                     p.no_barramento, None, perdeu)
    sinal = GLibUnix.signal_add if GLibUnix else GLib.unix_signal_add
    for s in (signal.SIGTERM, signal.SIGINT):
        sinal(GLib.PRIORITY_DEFAULT, s, laco.quit)
    try:
        laco.run()
    finally:
        p.encerra()

if __name__ == '__main__':
    main()
