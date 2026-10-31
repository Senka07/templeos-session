#!/usr/bin/env python3
"""Gera a fonte do TempleOS a partir de Kernel/FontStd.HC.

Saidas (em dados/ e fonte/):
  dados/fonte8x8.json  os 256 glifos como inteiros de 64 bits (linha 0 no byte
                       baixo, pixel x no bit x) -- e o que os apps da sessao usam
                       para desenhar texto pixel a pixel, sem passar por FreeType.
  fonte/TempleStd.ttf  a mesma fonte em contornos de pixel, para o xfwm4 e o kitty.
                       Cada pixel da fonte vale 128 unidades num em de 1024, entao
                       a 16px (12pt a 96 DPI) cada pixel da fonte vira 2x2 na tela.

O mapeamento para Unicode segue a CP437, que e o que a metade de cima da tabela
do TempleOS reproduz; assim as molduras de caixa do Unicode (usadas por htop,
mc etc.) caem nos glifos de borda originais.
"""
import json, os, re, sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, 'iso-extraida', 'Kernel', 'FontStd.HC')
PX, ASC, DESC = 128, 7, 1  # unidades por pixel; linhas acima/abaixo da base

texto = open(SRC, 'rb').read().decode('latin1')
glifos = [int(h, 16) for h in re.findall(r'0x([0-9A-F]{16})', texto)][:256]
assert len(glifos) == 256

os.makedirs(os.path.join(RAIZ, 'dados'), exist_ok=True)
json.dump(glifos, open(os.path.join(RAIZ, 'dados', 'fonte8x8.json'), 'w'))

def unicode_de(c):
    if 0x20 <= c < 0x7f:
        return c
    if c == 0x7f:
        return 0x2302
    if c >= 0x80:
        return ord(bytes([c]).decode('cp437'))
    return None

nomes, cmap, contornos = ['.notdef'], {}, {}
pen = TTGlyphPen(None)
contornos['.notdef'] = pen.glyph()
for c, v in enumerate(glifos):
    u = unicode_de(c)
    if u is None:
        continue
    nome = 'uni%04X' % u
    pen = TTGlyphPen(None)
    for y in range(8):
        linha = (v >> (8 * y)) & 0xff
        x = 0
        while x < 8:  # um retangulo por trecho continuo da linha
            if linha >> x & 1:
                x0 = x
                while x < 8 and linha >> x & 1:
                    x += 1
                topo, base = (ASC - y) * PX, (ASC - y - 1) * PX
                pen.moveTo((x0 * PX, base)); pen.lineTo((x0 * PX, topo))
                pen.lineTo((x * PX, topo)); pen.lineTo((x * PX, base)); pen.closePath()
            else:
                x += 1
    nomes.append(nome); cmap[u] = nome; contornos[nome] = pen.glyph()

fb = FontBuilder(8 * PX, isTTF=True)
fb.setupGlyphOrder(nomes)
fb.setupCharacterMap(cmap)
fb.setupGlyf(contornos)
fb.setupHorizontalMetrics({n: (8 * PX, 0) for n in nomes})
fb.setupHorizontalHeader(ascent=ASC * PX, descent=-DESC * PX)
fb.setupNameTable({'familyName': 'Temple Std', 'styleName': 'Regular',
                   'psName': 'TempleStd-Regular',
                   'copyright': 'Glifos de Kernel/FontStd.HC do TempleOS (dominio publico)'})
fb.setupOS2(sTypoAscender=ASC * PX, sTypoDescender=-DESC * PX, sTypoLineGap=0,
            usWinAscent=ASC * PX, usWinDescent=DESC * PX, xAvgCharWidth=8 * PX)
fb.font['OS/2'].panose.bFamilyType = 2
fb.font['OS/2'].panose.bProportion = 9  # monoespacada
fb.setupPost(isFixedPitch=1)
fb.save(os.path.join(RAIZ, 'fonte', 'TempleStd.ttf'))
print('ok: %d glifos' % (len(nomes) - 1))
