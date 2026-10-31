"""Texto do TempleOS desenhado direto dos glifos de dados/fonte8x8.json.

Sem FreeType no caminho: cada glifo vira uma superficie cairo de 16x16
(8x8 ampliado 2x) por par de cores, guardada em cache. A tela e uma grade de
celulas, como o text_base do original.
"""
import json, os
import cairo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E = 2
C = 8 * E

# Kernel: BLACK BLUE GREEN CYAN RED PURPLE BROWN LTGRAY DKGRAY LTBLUE LTGREEN
# LTCYAN LTRED LTPURPLE YELLOW WHITE (gr_palette_std em Adam/Gr/GrPalette.HC)
PALETA = ['000000', '0000AA', '00AA00', '00AAAA', 'AA0000', 'AA00AA', 'AA5500', 'AAAAAA',
          '555555', '5555FF', '55FF55', '55FFFF', 'FF5555', 'FF55FF', 'FFFF55', 'FFFFFF']
(BLACK, BLUE, GREEN, CYAN, RED, PURPLE, BROWN, LTGRAY,
 DKGRAY, LTBLUE, LTGREEN, LTCYAN, LTRED, LTPURPLE, YELLOW, WHITE) = range(16)

GLIFOS = json.load(open(os.path.join(RAIZ, 'dados', 'fonte8x8.json')))
_cache = {}

def rgb(cor):
    h = PALETA[cor]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

def _glifo(ch, fg, bg):
    chave = (ch, fg, bg)
    s = _cache.get(chave)
    if s is None:
        s = cairo.ImageSurface(cairo.FORMAT_RGB24, C, C)
        stride = s.get_stride()
        buf = s.get_data()
        cores = [bytes.fromhex(PALETA[c])[::-1] + b'\0' for c in (bg, fg)]  # BGRx
        v = GLIFOS[ch]
        for y in range(C):
            for x in range(C):
                o = y * stride + x * 4
                buf[o:o + 4] = cores[(v >> (8 * (y // E) + x // E)) & 1]
        s.mark_dirty()
        _cache[chave] = s
    return s

def escreve(cr, col, lin, s, fg, bg):
    """Escreve s a partir da celula (col, lin). Caracteres fora de latin-1 viram '?'."""
    for i, ch in enumerate(s.encode('latin1', 'replace')):
        cr.set_source_surface(_glifo(ch, fg, bg), (col + i) * C, lin * C)
        cr.paint()
