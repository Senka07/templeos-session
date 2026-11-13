"""Texto do TempleOS desenhado direto dos glifos de dados/fonte8x8.json.

Sem FreeType no caminho: cada glifo vira uma superficie cairo de 16x16
(8x8 ampliado 2x) por par de cores, guardada em cache. A tela e uma grade de
celulas, como o text_base do original.
"""
import json, os, unicodedata
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
# Os caracteres que a CP437 nao tem (ã, Á...; ver fonte/gerar-fonte.py) entram
# depois dos 256 originais. EXTRA leva o caractere ao indice dele em GLIFOS.
EXTRA = {}
try:
    _extra = json.load(open(os.path.join(RAIZ, 'dados', 'fonte8x8-extra.json')))
except FileNotFoundError:
    _extra = {}
for _hexa, _v in _extra.items():
    EXTRA[chr(int(_hexa, 16))] = chr(len(GLIFOS))
    GLIFOS.append(_v)
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

def para_glifos(s):
    """Texto Unicode para indices de GLIFOS, um caractere por glifo.

    A metade de cima da fonte segue a CP437 (o é e o ç estao la, mas em outro
    numero que no Latin-1); depois vem a tabela extra. O que nao existe em
    nenhuma das duas perde o acento, e o que nem assim existe, como emoji, sai.
    """
    r = []
    for ch in s:
        if ord(ch) < 32 or ord(ch) == 127:
            continue
        for tentativa in (ch, unicodedata.normalize('NFKD', ch)[:1]):
            if tentativa in EXTRA:
                r.append(EXTRA[tentativa])
                break
            try:
                r.append(tentativa.encode('cp437').decode('latin1'))
                break
            except UnicodeEncodeError:
                pass
    return ''.join(r)

def escreve(cr, col, lin, s, fg, bg):
    """Escreve s a partir da celula (col, lin).

    Cada caractere de s ja e o indice do glifo (ver para_glifos): assim os de
    moldura, como o '\x02', passam direto. Indice que nao existe vira '?'.
    """
    for i, ch in enumerate(s):
        n = ord(ch) if ord(ch) < len(GLIFOS) else ord('?')
        cr.set_source_surface(_glifo(n, fg, bg), (col + i) * C, lin * C)
        cr.paint()
