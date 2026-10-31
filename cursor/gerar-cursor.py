#!/usr/bin/env python3
"""Gera o tema de cursor "TempleOS" (Xcursor) a partir do desenho do original.

DrawStdMs() (Adam/Gr/GrComposites.HC) chama GrArrow3(x+8,y+8 -> x,y): uma
diagonal de 9 pixels com as duas linhas da ponta, de 5 pixels cada (w=2.75).
O original desenha em XOR, entao a seta fica preta no branco e amarela no azul;
o Xcursor nao faz XOR, e a aproximacao e a seta preta com contorno branco.
DrawWaitMs() vira o cursor de espera: circulo vermelho cortado.
Tudo a 2x, como o resto da sessao.

Uso: gerar-cursor.py [diretorio-de-icones]   (padrao: build/icons)
"""
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'build', 'icons'),
                    'TempleOS')
E = 2
PRETO, BRANCO, LTRED, RED = (0, 0, 0, 255), (255, 255, 255, 255), (255, 85, 85, 255), (170, 0, 0, 255)

def seta():
    pontos = {(i, i) for i in range(9)} | {(0, i) for i in range(5)} | {(i, 0) for i in range(5)}
    im = Image.new('RGBA', ((9 + 2) * E, (9 + 2) * E), (0, 0, 0, 0))
    for x, y in pontos:  # contorno: os 8 vizinhos de cada pixel da seta
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                im.paste(BRANCO, ((x + 1 + dx) * E, (y + 1 + dy) * E, (x + 2 + dx) * E, (y + 2 + dy) * E))
    for x, y in pontos:
        im.paste(PRETO, ((x + 1) * E, (y + 1) * E, (x + 2) * E, (y + 2) * E))
    return im, (E, E)

def espera():
    t = 17
    im = Image.new('RGBA', (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((1, 1, 15, 15), outline=LTRED, width=3)
    d.line((2, 14, 14, 2), fill=LTRED, width=3)
    d.ellipse((1, 1, 15, 15), outline=RED, width=1)
    d.line((2, 14, 14, 2), fill=RED, width=1)
    return im.resize((t * E, t * E), Image.NEAREST), (t * E // 2, t * E // 2)

os.makedirs(os.path.join(DEST, 'cursors'), exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    for nome, (im, (hx, hy)) in (('left_ptr', seta()), ('watch', espera())):
        png = os.path.join(tmp, nome + '.png')
        im.save(png)
        cfg = os.path.join(tmp, nome + '.cfg')
        open(cfg, 'w').write('%d %d %d %s\n' % (im.width, hx, hy, png))
        subprocess.run(['xcursorgen', cfg, os.path.join(DEST, 'cursors', nome)], check=True)

# O TempleOS tem um ponteiro so: todos os nomes viram a seta, menos os de espera.
ESPERA = ['wait', 'progress', 'left_ptr_watch', 'half-busy']
SETA = ['default', 'arrow', 'top_left_arrow', 'pointer', 'hand1', 'hand2', 'text', 'xterm',
        'ibeam', 'crosshair', 'cross', 'move', 'fleur', 'grab', 'grabbing', 'help',
        'question_arrow', 'not-allowed', 'context-menu', 'cell', 'copy', 'alias', 'all-scroll',
        'col-resize', 'row-resize', 'n-resize', 's-resize', 'e-resize', 'w-resize', 'ne-resize',
        'nw-resize', 'se-resize', 'sw-resize', 'ew-resize', 'ns-resize', 'nesw-resize',
        'nwse-resize', 'size_hor', 'size_ver', 'size_bdiag', 'size_fdiag', 'sb_h_double_arrow',
        'sb_v_double_arrow', 'top_side', 'bottom_side', 'left_side', 'right_side',
        'top_left_corner', 'top_right_corner', 'bottom_left_corner', 'bottom_right_corner',
        'X_cursor', 'pirate', 'dnd-move', 'dnd-copy', 'dnd-link', 'vertical-text', 'zoom-in',
        'zoom-out', 'pencil', 'right_ptr', 'center_ptr']
for alvo, nomes in (('left_ptr', SETA), ('watch', ESPERA)):
    for n in nomes:
        p = os.path.join(DEST, 'cursors', n)
        if os.path.lexists(p):
            os.remove(p)
        os.symlink(alvo, p)
open(os.path.join(DEST, 'index.theme'), 'w').write(
    '[Icon Theme]\nName=TempleOS\nComment=Ponteiro do TempleOS (DrawStdMs) a 2x\n')
print('cursor em', DEST)
