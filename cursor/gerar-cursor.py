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
# Precisa ter TODOS os nomes que algum app pede: o que faltar aqui a libXcursor
# vai buscar no tema "default" (~/.icons/default, que costuma ser outro tema).
# Era assim que a mao do Okular (openhand/pointing_hand do Qt) escapava.
# Os nomes do Qt saem de qxcbcursor.cpp; os hashes sao os nomes antigos.
ESPERA = ['wait', 'watch', 'progress', 'left_ptr_watch', 'half-busy',
          '0426c94ea35c87780ff01dc239897213', '00000000000000020006000e7e9ffc3f',
          '08e8e1c95fe2fc01f976f1e063a24ccd', '3ecb610c1bf2410f44200f48c40d3599']
SETA = ['default', 'arrow', 'top_left_arrow', 'left_arrow', 'up_arrow', 'pointer', 'hand',
        'hand1', 'hand2', 'pointing_hand', 'openhand', 'closedhand', 'grab', 'grabbing',
        'dnd-none', 'dnd-ask', 'link', 'text', 'xterm', 'ibeam',
        'crosshair', 'cross', 'tcross', 'cross_reverse', 'diamond_cross', 'color-picker',
        'move', 'fleur', 'size_all', 'help', 'whats_this', 'question_arrow', 'left_ptr_help',
        'not-allowed', 'no-drop', 'forbidden', 'crossed_circle', 'circle', 'context-menu',
        'cell', 'plus', 'copy', 'alias', 'all-scroll', 'all-resize',
        'col-resize', 'row-resize', 'split_h', 'split_v', 'n-resize', 's-resize', 'e-resize',
        'w-resize', 'ne-resize', 'nw-resize', 'se-resize', 'sw-resize', 'ew-resize', 'ns-resize',
        'nesw-resize', 'nwse-resize', 'size_hor', 'size_ver', 'size_bdiag', 'size_fdiag',
        'h_double_arrow', 'v_double_arrow', 'double_arrow', 'fd_double_arrow', 'bd_double_arrow',
        'sb_h_double_arrow', 'sb_v_double_arrow', 'sb_up_arrow', 'sb_down_arrow',
        'sb_left_arrow', 'sb_right_arrow', 'top_side', 'bottom_side', 'left_side', 'right_side',
        'top_left_corner', 'top_right_corner', 'bottom_left_corner', 'bottom_right_corner',
        'ul_angle', 'ur_angle', 'll_angle', 'lr_angle', 'top_tee', 'bottom_tee', 'left_tee',
        'right_tee', 'X_cursor', 'pirate', 'dnd-move', 'dnd-copy', 'dnd-link', 'vertical-text',
        'zoom-in', 'zoom-out', 'pencil', 'right_ptr', 'center_ptr', 'draft', 'dotbox',
        'target', 'icon', 'draped_box', 'left-ptr',
        'e29285e634086352946a0e7090d73106', '5aca4d189052212118709018842178c0',
        '9d800788f1b08800ae810202380a0822', '208530c400c041818281048008011002',
        '03b6e0fcb3499374a867c041f52298f0', '5c6cd98b3f3ebcb1f9c7f1c204630408',
        'd9ce0ab605698f320427677b458ad60b', '00008160000006810000408080010102',
        '028006030e0e7ebffc7f7070c0600140', '50585d75b494802d0151028115016902',
        'fcf1c3c7cd4491d801f1e1c78f100000', '38c5dff7c7b8962045400281044508d2',
        'c7088f0f3e6c8088236ef8e1e3e70000', '2870a09082c103050810ffdffffe0204',
        'c07385c7190e701020ff7ffffd08103c', '043a9f68147c53184671403ffa811cc5',
        '14fef782d02440884392942c11205230', '1081e37283d90000800003c07f3ef6bf',
        '6407b0e94181790501fd1e167b474872', '640fb0e74195791501fd1ed57b41487f',
        'a2a266d0498c3104214a47bd64ab0fc8', 'b66166c04f8c3109214a4fbd64a50fc8',
        '4498f0e0c1937ffe01fd06f973665830', '9081237383d90e509aa00f00170e968f',
        'fcf21c00b30f7e3f83fe0dfd12e71cff']
# Invisiveis de proposito (video em tela cheia esconde o ponteiro): nunca viram seta.
INVISIVEIS = {'blank', 'none'}

# E o que mais os outros temas instalados tiverem: qualquer um deles pode ser o
# "default" da vez. Rodar de novo depois de instalar um tema de cursor novo.
def nomes_instalados():
    pastas = os.environ.get('XCURSOR_PATH', '').split(':') if os.environ.get('XCURSOR_PATH') else [
        os.path.expanduser('~/.local/share/icons'), os.path.expanduser('~/.icons'),
        '/usr/share/icons', '/usr/share/pixmaps']
    achados = {}
    for pasta in pastas:
        if not os.path.isdir(pasta):
            continue
        for tema in os.listdir(pasta):
            cur = os.path.join(pasta, tema, 'cursors')
            if tema == 'TempleOS' or not os.path.isdir(cur):
                continue
            for n in os.listdir(cur):
                if n in achados or n in INVISIVEIS or n.startswith('.'):
                    continue
                alvo = os.path.basename(os.path.realpath(os.path.join(cur, n)))
                achados[n] = 'watch' if (n in ESPERA or alvo in ESPERA) else 'left_ptr'
    return achados

extras = nomes_instalados()
SETA = sorted((set(SETA) | {n for n, a in extras.items() if a == 'left_ptr'}) - set(ESPERA) - {'left_ptr'})
ESPERA = sorted((set(ESPERA) | {n for n, a in extras.items() if a == 'watch'}) - {'watch'})
for alvo, nomes in (('left_ptr', SETA), ('watch', ESPERA)):
    for n in nomes:
        p = os.path.join(DEST, 'cursors', n)
        if os.path.lexists(p):
            os.remove(p)
        os.symlink(alvo, p)
open(os.path.join(DEST, 'index.theme'), 'w').write(
    '[Icon Theme]\nName=TempleOS\nComment=Ponteiro do TempleOS (DrawStdMs) a 2x\n')
print('cursor em', DEST)
