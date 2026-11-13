#!/usr/bin/env python3
"""Grade do mouse, o Ctrl+Alt+G do original (Adam/Win.HC).

No TempleOS o Ctrl+Alt+G abre um formulario com a struct CGridGlbls
(Kernel/KernelA.HH) e o Ctrl+Alt+Shift+G volta tudo ao padrao (GridInit em
Kernel/SerialDev/Mouse.HC). O formulario mora no atalhos.py; este processo faz
o que os campos pedem:

- Show Grid: linhas pretas de x_offset em x_offset, de x em x (DrawWinGrid);
- Show Coordinates: "(xxx,yyy)" em preto, 10 colunas antes da borda direita,
  na 4a linha de texto (WinFinalUpdate);
- Snap Grid: o mouse so para nos pontos da grade. O original guarda a posicao
  "de verdade" (ms.presnap) e mostra a arredondada (ms.pos); aqui a de verdade
  fica em self.pre e o ponteiro e levado para a arredondada com XWarpPointer;
- XSpeed/YSpeed: multiplicam o movimento do mouse (ms_grid.x_speed).

Os numeros estao em pixels do TempleOS: a sessao desenha tudo a 2x (texto.E),
entao uma grade de 8 tem 16 pixels de tela, a mesma celula do texto das
janelas, e as coordenadas vao ate 639 numa tela de 1280.

A janela e transparente (visual ARGB, o compositor mistura) e nao pega mouse
nem teclado (regiao de entrada vazia). Sem compositor nao ha transparencia: a
janela vira preta e recortada so no formato das linhas (extensao Shape).

Configuracao pela entrada padrao, um JSON por linha (o atalhos.py escreve).
Quando a entrada fecha, o processo sai. Teste a mao:
  echo '{"show": true, "coord": true}' | python3 grade.py     (sai na hora)
  (echo '{"snap": true, "show": true}'; sleep 10) | python3 grade.py
"""
import ctypes, json, math, os, signal, sys, time
from ctypes import c_char_p, c_int, c_ubyte, c_uint, c_ulong, c_void_p, POINTER, Structure, byref
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib
try:
    from gi.repository import GLibUnix
except ImportError:            # PyGObject antigo
    GLibUnix = None
import cairo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x11
from x11 import DPY, RAIZ
from texto import E, C, GLIFOS
from lupa import XWindowAttributes, tamanho_tela

# GridInit: tudo desligado, grade de 8, sem deslocamento, velocidade 1
PADRAO = dict(snap=False, show=False, coord=False, x=8.0, y=8.0,
              x_offset=0.0, y_offset=0.0, x_speed=1.0, y_speed=1.0)
INTERVALO = 1 / 250             # s entre dois tratamentos do mouse
NOME_LUPA = b'TempleOS zoom'   # a janela do lupa.py fica por cima desta

xi = ctypes.CDLL('libXi.so.6')

class XIEventMask(Structure):
    _fields_ = [('deviceid', c_int), ('mask_len', c_int), ('mask', POINTER(c_ubyte))]

def _f(lib, nome, res, args):
    fn = getattr(lib, nome)
    fn.restype, fn.argtypes = res, args

_f(x11.x11, 'XQueryPointer', c_int, [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                                     POINTER(c_int), POINTER(c_int), POINTER(c_int),
                                     POINTER(c_int), POINTER(c_uint)])
_f(x11.x11, 'XWarpPointer', c_int, [c_void_p, c_ulong, c_ulong, c_int, c_int, c_uint, c_uint,
                                    c_int, c_int])
_f(x11.x11, 'XQueryTree', c_int, [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                                  POINTER(POINTER(c_ulong)), POINTER(c_uint)])
_f(x11.x11, 'XFetchName', c_int, [c_void_p, c_ulong, POINTER(c_char_p)])
_f(x11.x11, 'XGetWindowAttributes', c_int, [c_void_p, c_ulong, POINTER(XWindowAttributes)])
_f(x11.x11, 'XRaiseWindow', c_int, [c_void_p, c_ulong])
_f(x11.x11, 'XQueryExtension', c_int, [c_void_p, c_char_p, POINTER(c_int), POINTER(c_int),
                                       POINTER(c_int)])
_f(xi, 'XIQueryVersion', c_int, [c_void_p, POINTER(c_int), POINTER(c_int)])
_f(xi, 'XISelectEvents', c_int, [c_void_p, c_ulong, POINTER(XIEventMask), c_int])

XI_RAW_MOTION = 17
XI_TODOS_MESTRES = 1            # XIAllMasterDevices
GENERIC_EVENT = 35
VISIVEL = 2                     # map_state IsViewable

def arvore(j):
    """(pai, filhos de baixo para cima) de uma janela."""
    r, p, filhos, n = c_ulong(), c_ulong(), POINTER(c_ulong)(), c_uint()
    if not x11.x11.XQueryTree(DPY, j, byref(r), byref(p), byref(filhos), byref(n)):
        return None, []
    lista = filhos[:n.value]
    if filhos:
        x11.x11.XFree(filhos)
    return p.value, lista

def de_topo(j):
    """A janela filha da raiz que contem j: a moldura que o WM pos em volta."""
    while j:
        pai, _ = arvore(j)
        if pai == RAIZ or not pai:
            return j
        j = pai
    return 0

def ponteiro():
    r, f = c_ulong(), c_ulong()
    x, y, wx, wy, m = c_int(), c_int(), c_int(), c_int(), c_uint()
    x11.x11.XQueryPointer(DPY, RAIZ, byref(r), byref(f), byref(x), byref(y),
                          byref(wx), byref(wy), byref(m))
    return x.value, y.value

def escuta_movimento():
    """XInput2 RawMotion na raiz: um evento a cada movimento do mouse fisico,
    mesmo com outro programa segurando o ponteiro. So serve de despertador;
    a posicao vem do XQueryPointer."""
    op, ev, err = c_int(), c_int(), c_int()
    if not x11.x11.XQueryExtension(DPY, b'XInputExtension', byref(op), byref(ev), byref(err)):
        return False
    maior, menor = c_int(2), c_int(2)
    if xi.XIQueryVersion(DPY, byref(maior), byref(menor)) != 0:
        return False
    bits = (c_ubyte * 3)()
    bits[XI_RAW_MOTION >> 3] |= 1 << (XI_RAW_MOTION & 7)
    m = XIEventMask(XI_TODOS_MESTRES, 3, bits)
    xi.XISelectEvents(DPY, RAIZ, byref(m), 1)
    x11.x11.XFlush(DPY)
    return True

def numero(v, padrao, minimo=None, maximo=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return padrao
    if not math.isfinite(v):
        return padrao
    if minimo is not None:
        v = max(minimo, v)
    if maximo is not None:
        v = min(maximo, v)
    return v

def limpa(cfg):
    """Os valores do formulario, com o que travaria a sessao barrado: grade
    de 0 seria um laco infinito no desenho e velocidade 0 prende o mouse."""
    c = dict(PADRAO)
    for k in ('snap', 'show', 'coord'):
        c[k] = bool(cfg.get(k, False))
    for k in ('x', 'y'):
        c[k] = numero(cfg.get(k), PADRAO[k], 1, 4096)
    for k in ('x_offset', 'y_offset'):
        c[k] = numero(cfg.get(k), 0.0, -4096, 4096)
    for k in ('x_speed', 'y_speed'):
        c[k] = numero(cfg.get(k), 1.0, 0.1, 10)
    return c

class Grade:
    def __init__(self):
        self.cfg = dict(PADRAO)
        self.janela = None
        self.texto = ''
        self.nomes = {}            # xid -> WM_NAME, para achar a janela do lupa
        self.formulario = 0        # xid do Grid do atalhos.py aberto
        self.buraco = None         # (x, y, w, h) da moldura dele: ali nao ha grade
        self.pre = None            # posicao sem arredondar (ms.presnap)
        self.ultimo = None         # onde deixamos o ponteiro
        self.agendado = 0
        self.ultima_vez = 0.0
        tela = Gdk.Screen.get_default()
        tela.connect('size-changed', lambda *_: self.refaz_janela())
        tela.connect('composited-changed', lambda *_: self.refaz_janela())
        if not escuta_movimento():
            # sem XInput2, olha o mouse 60 vezes por segundo
            GLib.timeout_add(16, lambda: self.moveu() or True)
        GLib.io_add_watch(x11.x11.XConnectionNumber(DPY), GLib.IO_IN, self.eventos)
        GLib.timeout_add(250, self.fica_por_cima)

    # ------------------------------------------------------------ configuracao
    def configura(self, cfg):
        if set(cfg) == {'formulario'}:
            # Com o formulario aberto a grade nao sobe por cima dele: as linhas
            # cortariam as letras (no original o texto cai certinho na grade de 8)
            antes, self.formulario = self.formulario, int(cfg['formulario'] or 0)
            if self.formulario and not antes:
                # rapido enquanto ele esta aberto, para o buraco seguir o arrastar
                GLib.timeout_add(50, self.acompanha_formulario)
            self.acompanha_formulario()
            return
        antes = self.cfg
        self.cfg = limpa(cfg)
        if self.controla() and not (self.pre is not None and self.controla(antes)):
            x, y = ponteiro()
            self.pre, self.ultimo = [float(x), float(y)], (x, y)
        if not self.controla():
            self.pre = self.ultimo = None
        visuais = ('show', 'coord', 'x', 'y', 'x_offset', 'y_offset')
        if self.janela is None or any(antes[k] != self.cfg[k] for k in visuais):
            self.refaz_janela()
        self.moveu()

    def controla(self, cfg=None):
        """Se este processo precisa mexer no ponteiro: encaixe ou velocidade."""
        c = cfg if cfg is not None else self.cfg
        return c['snap'] or c['x_speed'] != 1 or c['y_speed'] != 1

    # ------------------------------------------------------------ mouse
    def eventos(self, *_):
        ev = x11.XEvent()
        mexeu = False
        while x11.x11.XPending(DPY):
            x11.x11.XNextEvent(DPY, byref(ev))
            mexeu = mexeu or ev.type == GENERIC_EVENT
        if mexeu:
            self.agenda()
        return True

    def agenda(self):
        """Um mouse de 1000 Hz manda 1000 eventos por segundo; tratar cada um
        em Python custaria um bom pedaco de um nucleo. Ate 250 por segundo e o
        que vier no meio fica para o proximo."""
        if self.agendado:
            return
        falta = self.ultima_vez + INTERVALO - time.monotonic()
        if falta <= 0:
            self.trata()
        else:
            self.agendado = GLib.timeout_add(max(1, int(falta * 1000)), self.trata)

    def trata(self):
        self.agendado = 0
        self.ultima_vez = time.monotonic()
        self.moveu()
        return False

    def moveu(self):
        if self.controla() and self.pre is not None:
            self.encaixa()
        if self.cfg['coord'] and self.janela:
            self.atualiza_coordenadas()

    def encaixa(self):
        """O ms.presnap -> ms.pos de Kernel/SerialDev/Mouse.HC.

        O quanto o mouse andou desde o ultimo encaixe vai para self.pre,
        multiplicado pela velocidade; o ponteiro vai para o ponto da grade
        abaixo de self.pre. O XWarpPointer e relativo (do ponto atual) para
        nao perder um movimento que chegue entre a leitura e a escrita.
        """
        c, w, h = self.cfg, *self.tamanho()
        x, y = ponteiro()
        ux, uy = self.ultimo
        self.pre[0] = min(max(self.pre[0] + (x - ux) * c['x_speed'], 0), w - 1)
        self.pre[1] = min(max(self.pre[1] + (y - uy) * c['y_speed'], 0), h - 1)
        if c['snap']:
            gx, gy = c['x'] * E, c['y'] * E
            ax = math.floor(self.pre[0] / gx) * gx + c['x_offset'] * E
            ay = math.floor(self.pre[1] / gy) * gy + c['y_offset'] * E
        else:
            ax, ay = self.pre
        ax = min(max(int(round(ax)), 0), w - 1)
        ay = min(max(int(round(ay)), 0), h - 1)
        if (ax, ay) != (x, y):
            x11.x11.XWarpPointer(DPY, 0, 0, 0, 0, 0, 0, ax - x, ay - y)
            x11.x11.XFlush(DPY)
        self.ultimo = (ax, ay)

    # ------------------------------------------------------------ janela
    def tamanho(self):
        return tamanho_tela()   # da raiz pelo X: o GDK demora a ver a resolucao nova

    def refaz_janela(self):
        """Visual e formato dependem do compositor; mais simples refazer tudo."""
        if self.janela:
            self.janela.destroy()
            self.janela = None
        if not (self.cfg['show'] or self.cfg['coord']):
            return
        tela = Gdk.Screen.get_default()
        j = Gtk.Window(type=Gtk.WindowType.POPUP)   # override_redirect: o WM nao toca
        j.set_title('TempleOS grid')
        self.argb = tela.is_composited() and tela.get_rgba_visual() is not None
        if self.argb:
            j.set_visual(tela.get_rgba_visual())
        j.set_app_paintable(True)
        w, h = self.tamanho()
        j.move(0, 0)
        j.set_default_size(w, h)
        j.connect('draw', self.desenha)
        j.realize()
        j.input_shape_combine_region(cairo.Region())   # cliques atravessam
        self.janela = j
        self.texto = self.coordenadas() if self.cfg['coord'] else ''
        if not self.argb:
            self.recorta()
        j.show()
        self.fica_por_cima()

    def linhas(self):
        """Os retangulos das linhas da grade, como DrawWinGrid: de offset em
        diante (a esquerda do offset nao ha linha, igual ao original)."""
        if not self.cfg['show']:
            return []
        c, (w, h) = self.cfg, self.tamanho()
        r = []
        for passo, inicio, total, vertical in ((c['x'] * E, c['x_offset'] * E, w, True),
                                               (c['y'] * E, c['y_offset'] * E, h, False)):
            d = inicio
            if d < 0:
                d += math.ceil(-d / passo) * passo
            while d < total:
                p = int(round(d))
                r.append((p, 0, E, h) if vertical else (0, p, w, E))
                d += passo
        return r

    def coordenadas(self):
        x, y = ponteiro()
        return '(%03d,%03d)' % (x // E, y // E)

    def lugar_texto(self):
        w, _ = self.tamanho()
        return w - 10 * C, 3 * C       # GR_WIDTH-FONT_WIDTH*10, FONT_HEIGHT*3

    def pixels_texto(self):
        """Os pixels acesos do texto, cada um um quadrado E x E."""
        if not self.texto:
            return []
        x0, y0 = self.lugar_texto()
        r = []
        for i, ch in enumerate(self.texto):
            v = GLIFOS[ord(ch)]
            for y in range(8):
                for x in range(8):
                    if v >> (8 * y + x) & 1:
                        r.append((x0 + (i * 8 + x) * E, y0 + y * E, E, E))
        return r

    def recorta(self):
        """Sem compositor: a janela e preta e so existe onde ha linha ou letra."""
        reg = cairo.Region()
        for x, y, w, h in self.linhas() + self.pixels_texto():
            reg.union(cairo.RectangleInt(x, y, w, h))
        if self.buraco:
            reg.subtract(cairo.RectangleInt(*self.buraco))
        self.janela.shape_combine_region(reg)

    def desenha(self, _w, cr):
        if self.argb:
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgb(0, 0, 0)          # dc->color=BLACK, grade e texto
        if not self.argb:
            cr.paint()
            return True
        if self.buraco:
            w, h = self.tamanho()
            cr.rectangle(0, 0, w, h)
            cr.rectangle(*self.buraco)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.clip()
            cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        for x, y, w, h in self.linhas() + self.pixels_texto():
            cr.rectangle(x, y, w, h)
        cr.fill()
        return True

    def atualiza_coordenadas(self):
        t = self.coordenadas()
        if t == self.texto:
            return
        self.texto = t
        if self.argb:
            x, y = self.lugar_texto()
            self.janela.queue_draw_area(x, y, 10 * C, C)
        else:
            self.recorta()

    def fica_por_cima(self):
        """Menus e janelas novas nascem por cima: subir de novo, mas sem passar
        da janela do zoom, que amplia esta junto com o resto."""
        if not self.janela or not self.janela.get_window():
            return True
        self.acompanha_formulario()
        eu = self.janela.get_window().get_xid()
        _, lista = arvore(RAIZ)
        if eu not in lista:
            return True
        lupa, acima = None, False
        for j in lista[lista.index(eu) + 1:]:
            if self.nome(j) == NOME_LUPA:
                lupa = j
                continue
            a = XWindowAttributes()
            if x11.x11.XGetWindowAttributes(DPY, j, byref(a)) and a.map_state == VISIVEL:
                acima = True
        if acima:
            x11.x11.XRaiseWindow(DPY, eu)
            if lupa:
                x11.x11.XRaiseWindow(DPY, lupa)
            x11.x11.XFlush(DPY)
            self.janela.queue_draw()
        return True

    def acompanha_formulario(self):
        """Com o formulario aberto a grade tem um buraco do tamanho dele: as
        linhas cortariam as letras (no original o texto das janelas cai certinho
        na grade de 8, aqui nao). Por baixo dele na pilha nao serve: o compositor
        do xfwm4 continua pintando a grade por cima ate a moldura se mexer."""
        buraco = None
        if self.formulario:
            moldura = de_topo(self.formulario)
            a = XWindowAttributes()
            if (moldura and x11.x11.XGetWindowAttributes(DPY, moldura, byref(a))
                    and a.map_state == VISIVEL):
                b = a.border_width
                buraco = (a.x, a.y, a.width + 2 * b, a.height + 2 * b)
        if buraco != self.buraco and self.janela:
            self.buraco = buraco
            if self.argb:
                self.janela.queue_draw()
            else:
                self.recorta()
        return bool(self.formulario)

    def nome(self, j):
        if j not in self.nomes:
            s = c_char_p()
            self.nomes[j] = s.value if x11.x11.XFetchName(DPY, j, byref(s)) and s.value else b''
            if s.value:
                x11.x11.XFree(ctypes.cast(s, c_void_p))
        return self.nomes[j]

def main():
    grade = Grade()
    entrada = sys.stdin.fileno()
    sobra = [b'']

    def le(*_):
        dados = os.read(entrada, 4096)
        if not dados:            # o atalhos.py fechou (ou morreu): acabou
            Gtk.main_quit()
            return False
        sobra[0] += dados
        *linhas, sobra[0] = sobra[0].split(b'\n')
        for l in linhas:
            if l.strip():
                try:
                    grade.configura(json.loads(l))
                except ValueError as e:
                    print('grade: linha invalida:', e, file=sys.stderr)
        return True

    GLib.io_add_watch(entrada, GLib.IO_IN | GLib.IO_HUP, le)
    sinal = GLibUnix.signal_add if GLibUnix else GLib.unix_signal_add
    sinal(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    sinal(GLib.PRIORITY_DEFAULT, signal.SIGINT, Gtk.main_quit)
    Gtk.main()

if __name__ == '__main__':
    main()
