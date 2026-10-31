#!/usr/bin/env python3
"""Gera o tema xfwm4 "TempleOS" a partir dos glifos de dados/fonte8x8.json.

A moldura do TempleOS e texto: TextBorder() (Adam/Gr/GrTextBase.HC) desenha a
borda com os caracteres 2-13 da fonte, e a borda da janela em foco usa os de
linha dupla (solid = task==sys_focus_task, Adam/Gr/GrScrn.HC). Por isso cada
peca aqui e um glifo de 8x8 ampliado 2x, em azul claro sobre branco
(border_attr da unidade C:).

A barra de titulo segue DocBorderNew() (Adam/DolDoc/DocTerm.HC): "MENU" colado
no canto esquerdo, titulo invertido no centro, "[X]" colado no canto direito.
No xfwm4 o "MENU" e o botao de menu da janela e o "[X]" o de fechar.

Uso: gerar-tema.py [diretorio-de-temas]   (padrao: build/themes)
"""
import json, os, sys
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'build', 'themes'),
                    'TempleOS', 'xfwm4')
GLIFOS = json.load(open(os.path.join(RAIZ, 'dados', 'fonte8x8.json')))
E = 2            # escala: 640x480 do original vira 1280x960
C = 8 * E        # lado de uma celula de texto
BRANCO, AZUL, AZUL_CLARO = (255, 255, 255), (0, 0, 170), (85, 85, 255)

def celula(ch, fg=AZUL_CLARO, bg=BRANCO):
    im = Image.new('RGB', (C, C), bg)
    v = GLIFOS[ch]
    for y in range(8):
        for x in range(8):
            if (v >> (8 * y + x)) & 1:
                im.paste(fg, (x * E, y * E, x * E + E, y * E + E))
    return im

def texto(s, fg=AZUL_CLARO, bg=BRANCO):
    im = Image.new('RGB', (C * len(s), C), bg)
    for i, ch in enumerate(s.encode('latin1')):
        im.paste(celula(ch, fg, bg), (i * C, 0))
    return im

def xpm(im, nome):
    im = im.convert('RGB')
    cores = sorted(c for _, c in im.getcolors())
    sim = {c: '.#abcdefghijklmnopqrstuvwxyz'[i] for i, c in enumerate(cores)}
    w, h = im.size
    linhas = ['"%d %d %d 1",' % (w, h, len(cores))]
    linhas += ['"%s c #%02X%02X%02X",' % (sim[c], *c) for c in cores]
    px = im.load()
    linhas += ['"%s"%s' % (''.join(sim[px[x, y]] for x in range(w)), ',' if y < h - 1 else '')
               for y in range(h)]
    open(os.path.join(DEST, nome + '.xpm'), 'w').write(
        '/* XPM */\nstatic char * %s[] = {\n%s\n};\n' % (nome.replace('-', '_'), '\n'.join(linhas)))

os.makedirs(DEST, exist_ok=True)
# (horizontal, vertical, sup-esq, sup-dir, inf-esq, inf-dir): +1 = linha dupla
BORDAS = {'active': (3, 5, 7, 9, 11, 13), 'inactive': (2, 4, 6, 8, 10, 12)}
for estado, (h, v, se, sd, ie, id_) in BORDAS.items():
    xpm(celula(se), 'top-left-' + estado)
    xpm(celula(sd), 'top-right-' + estado)
    xpm(celula(ie), 'bottom-left-' + estado)
    xpm(celula(id_), 'bottom-right-' + estado)
    xpm(celula(h), 'bottom-' + estado)
    xpm(celula(v), 'left-' + estado)
    xpm(celula(v), 'right-' + estado)
    for n in (1, 2, 4, 5):
        xpm(celula(h), 'title-%d-%s' % (n, estado))
    xpm(Image.new('RGB', (C, C), AZUL_CLARO), 'title-3-' + estado)  # fundo do titulo invertido
    # Botoes: MENU sempre invertido (no original ele pisca), [X] normal;
    # pressionado inverte, que e o unico retorno visual que faz sentido aqui.
    for sufixo in ('', '-prelight'):
        xpm(texto('MENU', BRANCO, AZUL_CLARO), 'menu-%s%s' % (estado, sufixo))
        xpm(texto('[X]'), 'close-%s%s' % (estado, sufixo))
    # Botoes que o TempleOS nao tem: so a linha da borda, caso alguem os ponha no layout.
    for b in ('hide', 'maximize', 'maximize-toggled', 'shade', 'shade-toggled',
              'stick', 'stick-toggled'):
        for sufixo in ('', '-prelight', '-pressed'):
            xpm(celula(h), '%s-%s%s' % (b, estado, sufixo))
xpm(texto('MENU'), 'menu-pressed')
xpm(texto('[X]', BRANCO, AZUL_CLARO), 'close-pressed')

open(os.path.join(DEST, 'themerc'), 'w').write('''\
# Gerado por xfwm4/gerar-tema.py -- nao editar a mao.
active_text_color=#FFFFFF
inactive_text_color=#FFFFFF
title_shadow_active=false
title_shadow_inactive=false
button_offset=0
button_spacing=0
full_width_title=false
title_horizontal_offset=0
title_vertical_offset_active=0
title_vertical_offset_inactive=0
maximized_offset=0
''')

# GTK3 so para os processos da sessao (xfwm4 e fundo.py recebem GTK_THEME=TempleOS;
# os apps nao): menu da janela, lista do Alt+Tab e dialogos do proprio xfwm4.
# Por isso os seletores podem ser genericos. A moldura dupla imita o glifo de
# linha dupla a 2x (tracos de 2px com 2px de vao).
GTK = os.path.join(os.path.dirname(DEST), 'gtk-3.0')
os.makedirs(GTK, exist_ok=True)
# O GtkCheckMenuItem usa a largura do marcador tambem como altura minima da
# linha, entao o "[X]" do DolDoc (48px) deixava cada item com 56px. Fica o
# glifo de visto (0xFB) numa celula so.
def icone(ch):
    im = celula(ch, AZUL, BRANCO).convert('RGBA')
    im.putalpha(celula(ch, (255, 255, 255), (0, 0, 0)).convert('L'))
    return im
icone(0xFB).save(os.path.join(GTK, 'marcado.png'))
icone(ord(' ')).save(os.path.join(GTK, 'desmarcado.png'))
icone(ord('>')).save(os.path.join(GTK, 'seta.png'))
open(os.path.join(GTK, 'gtk.css'), 'w').write('''\
/* Gerado por xfwm4/gerar-tema.py -- nao editar a mao. */
/* O CSS embutido do Alt+Tab do xfwm4 usa estas cores. */
@define-color theme_bg_color #FFFFFF;
@define-color theme_fg_color #0000AA;
@define-color theme_selected_bg_color #5555FF;
@define-color theme_selected_fg_color #FFFFFF;
* {
  all: unset;
  font: 12pt "Temple Std";
  -gtk-icon-style: regular;
}
/* cor so nas raizes: com "all: unset" o color volta a herdar, e o rotulo de
   um item selecionado fica branco junto com o item */
window, menu, .menu, .context-menu, popover, tooltip {
  background-color: #FFFFFF;
  color: #0000AA;
}
menu, .menu, .context-menu, tooltip, .xfwm-tabwin {
  border: 6px double #5555FF;
}
menu { padding: 6px 0; }
#xfwm-tabwin { border: 6px double #5555FF; border-radius: 0; padding: 0; background-color: #FFFFFF; }
#xfwm-tabwin button { background-color: #FFFFFF; color: #0000AA; }
#xfwm-tabwin button:hover, #xfwm-tabwin button:checked, #xfwm-tabwin button:focus,
#xfwm-tabwin button:selected { background-color: #5555FF; color: #FFFFFF; }
menuitem, button, label { padding: 0 16px; min-height: 16px; }
menuitem:hover, row:selected, *:selected {
  background-color: #5555FF;
  color: #FFFFFF;
}
menuitem:disabled, label:disabled { color: #AAAAAA; }
separator { min-height: 2px; margin: 7px 0; background-color: #5555FF; }
check, radio {
  min-width: 16px; min-height: 16px;
  -gtk-icon-source: url("desmarcado.png");
}
check:checked, radio:checked { -gtk-icon-source: url("marcado.png"); }
menuitem arrow { min-width: 16px; min-height: 16px; -gtk-icon-source: url("seta.png"); }
''')
print('tema em', os.path.dirname(DEST))
