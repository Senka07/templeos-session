#!/usr/bin/env python3
"""Gera a fonte do TempleOS a partir de Kernel/FontStd.HC.

Saidas (em dados/ e fonte/):
  dados/fonte8x8.json  os 256 glifos como inteiros de 64 bits (linha 0 no byte
                       baixo, pixel x no bit x) -- e o que os apps da sessao usam
                       para desenhar texto pixel a pixel, sem passar por FreeType.
  dados/fonte8x8-extra.json  os caracteres que a CP437 nao tem (ã, Á, aspas
                       curvas...), no mesmo formato, pelo codigo Unicode em hexa.
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
    if c == 0xff:
        # Na CP437 o 0xFF e o espaco sem quebra (U+00A0), mas no TempleOS e um
        # quadrado cheio: o "1.7 MiB" do Thunar e o "10 kB" de outros apps
        # saiam com um bloco no lugar do espaco. O U+00A0 ganha o glifo do
        # espaco, logo abaixo.
        return None
    if c >= 0x80:
        return ord(bytes([c]).decode('cp437'))
    return None

def contorno(v):
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
    return pen.glyph()

# --- Os caracteres que a CP437 nao tem ------------------------------------
# Terry nunca quis UTF ("We do not want UTF, just 8-bit characters", em
# Doc/Demands.DD), entao a tabela dele para no que a CP437 tem: falta o ã, o õ e
# quase toda maiuscula acentuada. Sem eles o xfwm4, o kitty e o Thunar buscavam
# esses caracteres em outra fonte, de outro tamanho, no meio da palavra.
# Nada aqui e desenho livre: a letra e a do proprio TempleOS e os acentos
# seguem o que a fonte ja faz no É e no Ñ.

def linhas_de(ch):
    """As 8 linhas (bit x = pixel x) do glifo de um caractere da CP437."""
    v = glifos[ch.encode('cp437')[0]]
    return [(v >> (8 * y)) & 0xff for y in range(8)]

def bits(s):
    return sum(1 << x for x, c in enumerate(s) if c == '#')

def valor(linhas):
    return sum(r << (8 * y) for y, r in enumerate(linhas))

def comprime(linhas, n=5):
    """Maiuscula de 7 linhas em 5, para caber o acento em cima.

    Sai sempre uma linha igual a vizinha, a mais perto do meio: as hastes
    encurtam e as barras (a do A, a do E) ficam. E o que a VGA fazia no Ä/Ö.
    """
    linhas = linhas[:7]
    while len(linhas) > n:
        meio = (len(linhas) - 1) / 2
        repetidas = [i for i in range(1, len(linhas)) if linhas[i] == linhas[i - 1]]
        i = min(repetidas, key=lambda i: abs(i - meio)) if repetidas else len(linhas) // 2
        del linhas[i]
    return linhas

# Acentos nas linhas 0 e 1. Agudo, grave e trema ficam numa linha so com uma
# vazia embaixo, como no É e no Ñ originais; til e circunflexo precisam das duas
# para terem forma, e encostam na letra como no â e no ê da CP437.
ACENTOS = {
    'agudo': ['....##..', '........'],
    'grave': ['..##....', '........'],
    'trema': ['.##..##.', '........'],
    'circ':  ['...##...', '..#..#..'],
    'til':   ['..##..#.', '.#..##..'],
}

def maiuscula(base, acento):
    return valor([bits(r) for r in ACENTOS[acento]] + comprime(linhas_de(base)) + [0])

def minuscula(base, acento):
    # nas minusculas as linhas 0 e 1 ja estao livres
    return valor([bits(r) for r in ACENTOS[acento]] + linhas_de(base)[2:])

def desenho(*linhas):
    return valor([bits(r) for r in linhas] + [0] * (8 - len(linhas)))

extras = {}
for base, letras in (('A', 'À:grave Á:agudo Â:circ Ã:til'),
                     ('E', 'È:grave Ê:circ Ë:trema'),
                     ('I', 'Ì:grave Í:agudo Î:circ Ï:trema'),
                     ('O', 'Ò:grave Ó:agudo Ô:circ Õ:til'),
                     ('U', 'Ù:grave Ú:agudo Û:circ'),
                     ('Y', 'Ý:agudo Ÿ:trema')):
    for par in letras.split():
        ch, acento = par.split(':')
        extras[ch] = maiuscula(base, acento)
extras['ã'] = minuscula('a', 'til')
extras['õ'] = minuscula('o', 'til')
extras['ý'] = minuscula('y', 'agudo')
extras['—'] = desenho('........', '........', '........', '########')
extras['…'] = desenho('........', '........', '........', '........', '........',
                      '##.##.##', '##.##.##')
extras['•'] = desenho('........', '........', '...##...', '..####..', '..####..', '...##...')
extras['€'] = desenho('...####.', '..##....', '######..', '..##....', '######..', '..##....',
                      '...####.')
extras['×'] = desenho('........', '.##..##.', '..####..', '...##...', '..####..', '.##..##.')
# Aspas curvas, apostrofo tipografico e os tracos menores viram os retos que
# a fonte ja tem: a 8x8 nao ha pixel para a curva.
for ch, igual in (("‘’‚‛′", "'"), ('“”„‟″', '"'), ('‐‑‒–−', '-')):
    for c in ch:
        extras[c] = glifos[ord(igual)]
extras['\xa0'] = glifos[ord(' ')]  # ver unicode_de()

json.dump({'%04X' % ord(ch): v for ch, v in sorted(extras.items())},
          open(os.path.join(RAIZ, 'dados', 'fonte8x8-extra.json'), 'w'), indent=0)

nomes, cmap, contornos = ['.notdef'], {}, {}
pen = TTGlyphPen(None)
contornos['.notdef'] = pen.glyph()
por_valor = {}  # glifos iguais (as aspas curvas e as retas) dividem o contorno
for c, v in enumerate(glifos):
    u = unicode_de(c)
    if u is None:
        continue
    nome = 'uni%04X' % u
    nomes.append(nome); cmap[u] = nome; contornos[nome] = contorno(v)
    por_valor.setdefault(v, nome)
for ch, v in extras.items():
    if v in por_valor:
        cmap[ord(ch)] = por_valor[v]
        continue
    nome = 'uni%04X' % ord(ch)
    nomes.append(nome); cmap[ord(ch)] = nome; contornos[nome] = contorno(v)
    por_valor[v] = nome

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
print('ok: %d glifos, %d caracteres (%d fora da CP437)' % (len(nomes) - 1, len(cmap), len(extras)))
