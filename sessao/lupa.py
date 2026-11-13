#!/usr/bin/env python3
"""Zoom da tela inteira, o Ctrl+Alt+Z do original (Adam/Gr/GrEnd.HC).

Como no TempleOS:
- o fator dobra a cada Ctrl+Alt+Z e cai pela metade com Ctrl+Alt+Shift+Z, de 1
  a 8 (GR_SCRN_ZOOM_MAX em Adam/Gr/GrGlbls.HC); em 1 o zoom acaba;
- a vista centraliza no mouse e so pula quando ele chega a 8 pixels da borda
  da tela ampliada (o teste de WinMsUpdate em Adam/Win.HC), e o canto esquerdo
  da vista anda de 8 em 8 pixels (GrFixZoomScale em Adam/Gr/GrScrn.HC);
- o mouse continua mexendo na tela de verdade: so a imagem e ampliada.

No X11 isso vira uma janela por cima de tudo que nao pega mouse nem teclado
(a regiao de entrada dela e vazia, entao o clique cai na janela de baixo). A
imagem vem das janelas, nao da tela: com um compositor cada janela de topo tem
uma pixmap so dela (extensao Composite), e o servidor amplia e empilha essas
pixmaps na nossa janela (extensao Render, filtro "nearest", pixel duro). Ler a
tela daria um espelho infinito, porque a tela ja inclui a nossa janela.

O cursor de verdade fica escondido enquanto o zoom esta ligado (XFixes) e o
desenhado e o mesmo, ampliado, como no original, em que o cursor e pintado na
tela antes do zoom.

Comandos pela entrada padrao, uma linha cada: "+" dobra, "-" divide. O
atalhos.py e quem escreve; se ele morrer, a entrada fecha e o zoom acaba junto.
Uso direto, para testar: python3 lupa.py [fator inicial]
"""
import ctypes, os, select, signal, sys, time
from ctypes import (c_char_p, c_int, c_long, c_short, c_uint, c_ulong, c_ushort,
                    c_void_p, POINTER, Structure, byref)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x11 import x11, DPY, RAIZ, atomo

ZOOM_MAX = 8
QUADROS = 60          # por segundo; o original desenha a 30, mas aqui o cursor
                      # tambem e nosso, e a 30 ele parece arrastado
BORDA = 8             # px da tela ampliada que fazem a vista pular

xr = ctypes.CDLL('libXrender.so.1')
xc = ctypes.CDLL('libXcomposite.so.1')
xf = ctypes.CDLL('libXfixes.so.3')

class XWindowAttributes(Structure):
    _fields_ = [('x', c_int), ('y', c_int), ('width', c_int), ('height', c_int),
                ('border_width', c_int), ('depth', c_int), ('visual', c_void_p),
                ('root', c_ulong), ('class_', c_int), ('bit_gravity', c_int),
                ('win_gravity', c_int), ('backing_store', c_int),
                ('backing_planes', c_ulong), ('backing_pixel', c_ulong),
                ('save_under', c_int), ('colormap', c_ulong), ('map_installed', c_int),
                ('map_state', c_int), ('all_event_masks', c_long),
                ('your_event_mask', c_long), ('do_not_propagate_mask', c_long),
                ('override_redirect', c_int), ('screen', c_void_p)]

class XSetWindowAttributes(Structure):
    _fields_ = [('background_pixmap', c_ulong), ('background_pixel', c_ulong),
                ('border_pixmap', c_ulong), ('border_pixel', c_ulong),
                ('bit_gravity', c_int), ('win_gravity', c_int), ('backing_store', c_int),
                ('backing_planes', c_ulong), ('backing_pixel', c_ulong),
                ('save_under', c_int), ('event_mask', c_long),
                ('do_not_propagate_mask', c_long), ('override_redirect', c_int),
                ('colormap', c_ulong), ('cursor', c_ulong)]

class XVisualInfo(Structure):
    _fields_ = [('visual', c_void_p), ('visualid', c_ulong), ('screen', c_int),
                ('depth', c_int), ('class_', c_int), ('red_mask', c_ulong),
                ('green_mask', c_ulong), ('blue_mask', c_ulong),
                ('colormap_size', c_int), ('bits_per_rgb', c_int)]

class XFixesCursorImage(Structure):
    _fields_ = [('x', c_short), ('y', c_short), ('width', c_ushort), ('height', c_ushort),
                ('xhot', c_ushort), ('yhot', c_ushort), ('cursor_serial', c_ulong),
                ('pixels', POINTER(c_ulong)), ('atom', c_ulong), ('name', c_char_p)]

class XRenderColor(Structure):
    _fields_ = [('red', c_ushort), ('green', c_ushort), ('blue', c_ushort),
                ('alpha', c_ushort)]

class XTransform(Structure):
    _fields_ = [('matrix', (c_int * 3) * 3)]   # XFixed: ponto fixo 16.16

def _f(lib, nome, res, args):
    fn = getattr(lib, nome)
    fn.restype, fn.argtypes = res, args

_f(x11, 'XGetWindowAttributes', c_int, [c_void_p, c_ulong, POINTER(XWindowAttributes)])
_f(x11, 'XQueryTree', c_int, [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                              POINTER(POINTER(c_ulong)), POINTER(c_uint)])
_f(x11, 'XQueryPointer', c_int, [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_ulong),
                                 POINTER(c_int), POINTER(c_int), POINTER(c_int),
                                 POINTER(c_int), POINTER(c_uint)])
_f(x11, 'XDefaultVisual', c_void_p, [c_void_p, c_int])
_f(x11, 'XDefaultDepth', c_int, [c_void_p, c_int])
_f(x11, 'XCreateWindow', c_ulong, [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint, c_uint,
                                   c_int, c_uint, c_void_p, c_ulong,
                                   POINTER(XSetWindowAttributes)])
_f(x11, 'XMapRaised', c_int, [c_void_p, c_ulong])
_f(x11, 'XRaiseWindow', c_int, [c_void_p, c_ulong])
_f(x11, 'XMoveResizeWindow', c_int, [c_void_p, c_ulong, c_int, c_int, c_uint, c_uint])
_f(x11, 'XDestroyWindow', c_int, [c_void_p, c_ulong])
_f(x11, 'XCreatePixmap', c_ulong, [c_void_p, c_ulong, c_uint, c_uint, c_uint])
_f(x11, 'XFreePixmap', c_int, [c_void_p, c_ulong])
_f(x11, 'XCreateGC', c_void_p, [c_void_p, c_ulong, c_ulong, c_void_p])
_f(x11, 'XFreeGC', c_int, [c_void_p, c_void_p])
_f(x11, 'XMatchVisualInfo', c_int, [c_void_p, c_int, c_int, c_int, POINTER(XVisualInfo)])
_f(x11, 'XCreateImage', c_void_p, [c_void_p, c_void_p, c_uint, c_int, c_int, c_void_p,
                                   c_uint, c_uint, c_int, c_int])
_f(x11, 'XPutImage', c_int, [c_void_p, c_ulong, c_void_p, c_void_p, c_int, c_int, c_int,
                             c_int, c_uint, c_uint])
_f(x11, 'XStoreName', c_int, [c_void_p, c_ulong, c_char_p])
_f(xr, 'XRenderFindVisualFormat', c_void_p, [c_void_p, c_void_p])
_f(xr, 'XRenderFindStandardFormat', c_void_p, [c_void_p, c_int])
_f(xr, 'XRenderCreatePicture', c_ulong, [c_void_p, c_ulong, c_void_p, c_ulong, c_void_p])
_f(xr, 'XRenderFreePicture', None, [c_void_p, c_ulong])
_f(xr, 'XRenderSetPictureTransform', None, [c_void_p, c_ulong, POINTER(XTransform)])
_f(xr, 'XRenderSetPictureFilter', None, [c_void_p, c_ulong, c_char_p, c_void_p, c_int])
_f(xr, 'XRenderComposite', None, [c_void_p, c_int, c_ulong, c_ulong, c_ulong, c_int, c_int,
                                  c_int, c_int, c_int, c_int, c_uint, c_uint])
_f(xr, 'XRenderFillRectangle', None, [c_void_p, c_int, c_ulong, POINTER(XRenderColor),
                                      c_int, c_int, c_uint, c_uint])
_f(xc, 'XCompositeNameWindowPixmap', c_ulong, [c_void_p, c_ulong])
_f(xc, 'XCompositeRedirectSubwindows', None, [c_void_p, c_ulong, c_int])
_f(xc, 'XCompositeUnredirectSubwindows', None, [c_void_p, c_ulong, c_int])
_f(xf, 'XFixesHideCursor', None, [c_void_p, c_ulong])
_f(xf, 'XFixesShowCursor', None, [c_void_p, c_ulong])
_f(xf, 'XFixesGetCursorImage', POINTER(XFixesCursorImage), [c_void_p])
_f(xf, 'XFixesCreateRegion', c_ulong, [c_void_p, c_void_p, c_int])
_f(xf, 'XFixesDestroyRegion', None, [c_void_p, c_ulong])
_f(xf, 'XFixesSetWindowShapeRegion', None, [c_void_p, c_ulong, c_int, c_int, c_int, c_ulong])

OP_SRC, OP_OVER = 1, 3
VISIVEL, SO_ENTRADA = 2, 2          # map_state IsViewable, class InputOnly
SHAPE_ENTRADA = 2                   # ShapeInput
REDIRECT_AUTOMATICO = 0
PICT_ARGB32 = 0                     # PictStandardARGB32

def transforma(pict, z):
    """A Render pergunta 'que pixel da origem vai neste destino?': origem = destino/z."""
    t = XTransform()
    t.matrix[0][0] = t.matrix[1][1] = 65536 // z
    t.matrix[2][2] = 65536
    xr.XRenderSetPictureTransform(DPY, pict, byref(t))
    xr.XRenderSetPictureFilter(DPY, pict, b'nearest', None, 0)

def tamanho_tela():
    a = XWindowAttributes()
    x11.XGetWindowAttributes(DPY, RAIZ, byref(a))
    return a.width, a.height

class Lupa:
    def __init__(self, z):
        self.z = 1
        self.visual = x11.XDefaultVisual(DPY, 0)
        self.prof = x11.XDefaultDepth(DPY, 0)
        self.formato = xr.XRenderFindVisualFormat(DPY, self.visual)
        self.w, self.h = tamanho_tela()
        at = XSetWindowAttributes()
        at.background_pixmap = 0        # None: o X nao apaga a janela antes de nos
        at.override_redirect = 1        # o WM nao a enquadra nem a move
        self.janela = x11.XCreateWindow(DPY, RAIZ, 0, 0, self.w, self.h, 0, self.prof, 1,
                                        self.visual, 1 | (1 << 9), byref(at))
        x11.XStoreName(DPY, self.janela, b'TempleOS zoom')
        vazia = xf.XFixesCreateRegion(DPY, None, 0)
        xf.XFixesSetWindowShapeRegion(DPY, self.janela, SHAPE_ENTRADA, 0, 0, vazia)
        xf.XFixesDestroyRegion(DPY, vazia)
        self.pict_janela = xr.XRenderCreatePicture(DPY, self.janela, self.formato, 0, None)
        self.fundo = self.pict_fundo = 0
        self.refaz_fundo()
        # Sem compositor as janelas nao tem pixmap propria; o redirecionamento
        # automatico cria uma sem mudar nada na tela (o servidor continua pintando)
        self.redirecionou = not x11.XGetSelectionOwner(DPY, atomo('_NET_WM_CM_S0'))
        if self.redirecionou:
            xc.XCompositeRedirectSubwindows(DPY, RAIZ, REDIRECT_AUTOMATICO)
        self.cursor_serial = None
        self.cursor = None
        v = XVisualInfo()
        self.visual32 = v.visual if x11.XMatchVisualInfo(DPY, 0, 32, 4, byref(v)) else None
        xf.XFixesHideCursor(DPY, RAIZ)
        x11.XMapRaised(DPY, self.janela)
        self.mouse()
        self.escala(z)

    def refaz_fundo(self):
        # Desenha-se num buffer e so o quadro pronto vai para a janela, sem piscar
        if self.fundo:
            xr.XRenderFreePicture(DPY, self.pict_fundo)
            x11.XFreePixmap(DPY, self.fundo)
        self.fundo = x11.XCreatePixmap(DPY, RAIZ, self.w, self.h, self.prof)
        self.pict_fundo = xr.XRenderCreatePicture(DPY, self.fundo, self.formato, 0, None)

    def mouse(self):
        r, f = c_ulong(), c_ulong()
        x, y, wx, wy, m = c_int(), c_int(), c_int(), c_int(), c_uint()
        x11.XQueryPointer(DPY, RAIZ, byref(r), byref(f), byref(x), byref(y),
                          byref(wx), byref(wy), byref(m))
        self.mx, self.my = x.value, y.value

    def centraliza(self):
        # GrScaleZoom + GrFixZoomScale
        z = self.z
        self.sx = max(0, min(self.mx - (self.w >> 1) // z, self.w - self.w // z)) & ~7
        self.sy = max(0, min(self.my - (self.h >> 1) // z, self.h - self.h // z))

    def escala(self, fator):
        self.z = max(1, min(ZOOM_MAX, int(self.z * fator)))
        self.centraliza()

    def segue_mouse(self):
        # WinMsUpdate: so pula quando o mouse encosta na borda da vista
        dx = (self.mx - self.sx) * self.z
        dy = (self.my - self.sy) * self.z
        if not (BORDA <= dx < self.w - BORDA) or not (BORDA <= dy < self.h - BORDA):
            self.centraliza()

    def janelas(self):
        r, p, filhos, n = c_ulong(), c_ulong(), POINTER(c_ulong)(), c_uint()
        if not x11.XQueryTree(DPY, RAIZ, byref(r), byref(p), byref(filhos), byref(n)):
            return []
        lista = filhos[:n.value]
        if filhos:
            x11.XFree(filhos)
        return lista  # de baixo para cima

    def desenha_janela(self, j):
        a = XWindowAttributes()
        if not x11.XGetWindowAttributes(DPY, j, byref(a)):
            return
        if a.map_state != VISIVEL or a.class_ == SO_ENTRADA:
            return
        z, b = self.z, a.border_width
        x0, y0 = a.x, a.y
        larg, alt = a.width + 2 * b, a.height + 2 * b
        # o retangulo dela na tela ampliada, cortado pela tela
        dx0, dy0 = max(0, (x0 - self.sx) * z), max(0, (y0 - self.sy) * z)
        dx1 = min(self.w, (x0 + larg - self.sx) * z)
        dy1 = min(self.h, (y0 + alt - self.sy) * z)
        if dx1 <= dx0 or dy1 <= dy0:
            return
        pix = xc.XCompositeNameWindowPixmap(DPY, j)
        if not pix:
            return
        fmt = xr.XRenderFindVisualFormat(DPY, a.visual)
        pict = xr.XRenderCreatePicture(DPY, pix, fmt, 0, None)
        transforma(pict, z)
        # origem = (src + i) / z, e queremos (dx0 + i) / z + sx - x0
        xr.XRenderComposite(DPY, OP_OVER, pict, 0, self.pict_fundo,
                            dx0 + (self.sx - x0) * z, dy0 + (self.sy - y0) * z, 0, 0,
                            dx0, dy0, dx1 - dx0, dy1 - dy0)
        xr.XRenderFreePicture(DPY, pict)
        x11.XFreePixmap(DPY, pix)

    def atualiza_cursor(self):
        img = xf.XFixesGetCursorImage(DPY)
        if not img:
            return
        c = img.contents
        if c.cursor_serial != self.cursor_serial and self.visual32:
            if self.cursor:
                xr.XRenderFreePicture(DPY, self.cursor[0])
                x11.XFreePixmap(DPY, self.cursor[1])
            w, h = c.width, c.height
            # os pixels vem em unsigned long (64 bits aqui), ARGB pre-multiplicado
            dados = (ctypes.c_uint32 * (w * h))(*(p & 0xffffffff for p in c.pixels[:w * h]))
            pix = x11.XCreatePixmap(DPY, RAIZ, w, h, 32)
            gc = x11.XCreateGC(DPY, pix, 0, None)
            im = x11.XCreateImage(DPY, self.visual32, 32, 2, 0, dados, w, h, 32, 0)
            x11.XPutImage(DPY, pix, gc, im, 0, 0, 0, 0, w, h)
            ctypes.cast(im, POINTER(c_void_p))[2] = None  # data: e nosso, nao da Xlib
            x11.XFree(im)
            x11.XFreeGC(DPY, gc)
            pict = xr.XRenderCreatePicture(DPY, pix,
                                           xr.XRenderFindStandardFormat(DPY, PICT_ARGB32), 0, None)
            self.cursor = (pict, pix, w, h, c.xhot, c.yhot)
            self.cursor_serial = c.cursor_serial
        x11.XFree(img)

    def desenha_cursor(self):
        if not self.cursor:
            return
        pict, _pix, w, h, hx, hy = self.cursor
        z = self.z
        transforma(pict, z)
        x, y = (self.mx - hx - self.sx) * z, (self.my - hy - self.sy) * z
        xr.XRenderComposite(DPY, OP_OVER, pict, 0, self.pict_fundo, 0, 0, 0, 0,
                            x, y, w * z, h * z)

    def quadro(self):
        w, h = tamanho_tela()
        if (w, h) != (self.w, self.h):  # mudou a resolucao
            self.w, self.h = w, h
            x11.XMoveResizeWindow(DPY, self.janela, 0, 0, w, h)
            self.refaz_fundo()
            self.centraliza()
        self.mouse()
        self.segue_mouse()
        preto = XRenderColor(0, 0, 0, 0xffff)
        xr.XRenderFillRectangle(DPY, OP_SRC, self.pict_fundo, byref(preto), 0, 0, w, h)
        lista = self.janelas()
        for j in lista:
            if j != self.janela:
                self.desenha_janela(j)
        self.atualiza_cursor()
        self.desenha_cursor()
        xr.XRenderComposite(DPY, OP_SRC, self.pict_fundo, 0, self.pict_janela,
                            0, 0, 0, 0, 0, 0, w, h)
        # Menus e avisos abertos depois nascem por cima: volta para o topo
        if lista and lista[-1] != self.janela:
            x11.XRaiseWindow(DPY, self.janela)
        x11.XFlush(DPY)

    def fecha(self):
        xf.XFixesShowCursor(DPY, RAIZ)
        if self.redirecionou:
            xc.XCompositeUnredirectSubwindows(DPY, RAIZ, REDIRECT_AUTOMATICO)
        x11.XDestroyWindow(DPY, self.janela)
        x11.XSync(DPY, False)

def main():
    z = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    # kill tambem passa pelo finally. Mesmo sem isso o cursor voltaria: o X
    # esconde o cursor so enquanto o cliente que pediu esta conectado.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    lupa = Lupa(z)
    entrada = sys.stdin.fileno()
    lendo = not os.isatty(entrada)
    passo = 1 / QUADROS
    try:
        while lupa.z > 1:
            inicio = time.monotonic()
            lupa.quadro()
            resta = max(0, passo - (time.monotonic() - inicio))
            if not lendo:
                time.sleep(resta)
                continue
            pronto, _, _ = select.select([entrada], [], [], resta)
            if pronto:
                dados = os.read(entrada, 64)
                if not dados:       # o atalhos.py fechou: acabou
                    break
                for ch in dados.decode(errors='ignore'):
                    if ch == '+':
                        lupa.escala(2)
                    elif ch == '-':
                        lupa.escala(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        lupa.fecha()

if __name__ == '__main__':
    main()
