#!/usr/bin/env python3
"""Gera o tema GTK3 "TempleOS-Thunar": o Thunar com a cara do TempleOS.

Diferente do tema "TempleOS" (so menus e Alt+Tab do xfwm4), este cobre uma
janela de app inteira: barra de menus, ferramentas, campo do caminho, lista de
locais, a vista dos arquivos, dialogos de copia e de propriedades. Quem aplica
e o tema-app.so (ver tema-app.c), so no processo do Thunar da sessao.

Cores e formas do original:
- fundo branco, texto azul (BLUE), linhas e selecao em azul claro (LTBLUE),
  como nos documentos DolDoc e no FileMgr (Adam/ABlkDev/FileMgr.HC);
- selecao e item sob o mouse invertidos, que e o cursor do DolDoc;
- linha simples = normal, linha dupla = em foco, como nas molduras
  (TextBorder em Adam/Gr/GrTextBase.HC);
- cabecalhos em roxo (PURPLE), como o "File Manager" do FileMgr;
- fonte 8x8 em tamanho real (8px) e nada arredondado, sem sombra nem degrade;
- icones simbolicos (de uma cor so), que pegam o azul do texto.

Uso: gerar-tema.py [diretorio-de-temas]   (padrao: build/themes)
"""
import json, os, sys
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'build', 'themes'),
                    'TempleOS-Thunar', 'gtk-3.0')
GLIFOS = json.load(open(os.path.join(RAIZ, 'dados', 'fonte8x8.json')))
E = 2
C = 8 * E
AZUL, BRANCO = (0, 0, 170), (255, 255, 255)

def glifo(ch, cor):
    """Um caractere da fonte a 2x, so os pontos acesos (fundo transparente)."""
    im = Image.new('RGBA', (C, C), (0, 0, 0, 0))
    v = GLIFOS[ch]
    for y in range(8):
        for x in range(8):
            if (v >> (8 * y + x)) & 1:
                im.paste(cor + (255,), (x * E, y * E, x * E + E, y * E + E))
    return im

os.makedirs(DEST, exist_ok=True)
# nome -> caractere; cada um sai em azul e em branco (para item selecionado)
ICONES = {
    'visto': 0xFB,       # caixa marcada
    'ponto': 0xFE,       # radio marcado: o quadradinho do original
    'mais': ord('+'),    # expandir pasta na arvore
    'menos': ord('-'),   # recolher
    'seta': ord('>'),    # submenu
}
for nome, ch in ICONES.items():
    glifo(ch, AZUL).save(os.path.join(DEST, nome + '.png'))
    glifo(ch, BRANCO).save(os.path.join(DEST, nome + '-sel.png'))

open(os.path.join(DEST, 'gtk.css'), 'w').write('''\
/* Gerado por thunar/gerar-tema.py -- nao editar a mao. */
@define-color azul #0000AA;
@define-color azul_claro #5555FF;
@define-color roxo #AA00AA;
@define-color cinza #AAAAAA;
@define-color branco #FFFFFF;

/* nomes que o GTK e alguns widgets procuram */
@define-color theme_bg_color @branco;
@define-color theme_fg_color @azul;
@define-color theme_base_color @branco;
@define-color theme_text_color @azul;
@define-color theme_selected_bg_color @azul_claro;
@define-color theme_selected_fg_color @branco;
@define-color insensitive_fg_color @cinza;
@define-color borders @azul_claro;
/* o Thunar pinta a selecao com estas quando a vista nao tem o foco (menu
   aberto, foco no campo do caminho); sem elas o nome ficava branco no branco */
@define-color theme_unfocused_bg_color @branco;
@define-color theme_unfocused_fg_color @azul;
@define-color theme_unfocused_base_color @branco;
@define-color theme_unfocused_text_color @azul;
@define-color theme_unfocused_selected_bg_color @azul_claro;
@define-color theme_unfocused_selected_fg_color @branco;

@keyframes gira { to { -gtk-icon-transform: rotate(1turn); } }

* {
  all: unset;
  font: 8px "Temple Std";  /* 1 ponto da fonte = 1 pixel; so 8px e 16px saem nitidos */
  -gtk-icon-style: symbolic;
  caret-color: @azul;
  -gtk-secondary-caret-color: @azul_claro;
}

/* ---- raizes ---- */
window, dialog, messagedialog, .background, popover, viewport, textview text {
  background-color: @branco;
  color: @azul;
}
*:disabled { color: @cinza; }
selection, *:selected, entry selection, label selection, textview text selection {
  background-color: @azul_claro;
  color: @branco;
}
headerbar {
  background-color: @azul_claro;
  color: @branco;
  min-height: 24px;
  padding: 0 8px;
}
headerbar button { border-color: transparent; color: @branco; }
headerbar button:hover { background-color: @branco; color: @azul_claro; }
.dialog-action-area, .dialog-action-box { padding: 8px; }
.dialog-action-area button, .dialog-action-box button { margin-left: 8px; }

/* ---- menus (mesmo desenho do tema da sessao) ---- */
menubar { border-bottom: 2px solid @azul_claro; }
menubar > menuitem { padding: 2px 16px; }
menu, .menu, .context-menu, tooltip {
  background-color: @branco;
  color: @azul;
  border: 6px double @azul_claro;
}
menu { padding: 6px 0; }
menuitem { padding: 0 16px; min-height: 20px; }
menuitem:hover, menubar > menuitem:hover {
  background-color: @azul_claro;
  color: @branco;
}
/* O atalho (Ctrl+Z...) fica com a cor herdada do rotulo: com cor propria o
   GTK 3 deixava de desenha-lo fora do item sob o mouse. */
menu separator { min-height: 2px; margin: 7px 0; background-color: @azul_claro; }
menuitem arrow { min-width: 16px; min-height: 16px; -gtk-icon-source: url("seta.png"); }
menuitem:hover arrow { -gtk-icon-source: url("seta-sel.png"); }
menuitem check, menuitem radio { margin-right: 8px; }
tooltip { padding: 2px 8px; }

/* ---- barra de ferramentas ---- */
toolbar {
  padding: 2px 8px;
  border-bottom: 2px solid @azul_claro;
}
toolbar separator { min-width: 2px; margin: 4px 8px; background-color: @azul_claro; }
toolbar button { padding: 2px; border-color: transparent; }
toolbar toolitem { margin: 0 4px; }

/* ---- botoes: linha simples; o padrao do dialogo ganha a linha dupla ---- */
button {
  padding: 4px 12px;
  min-height: 16px;
  min-width: 16px;
  border: 2px solid @azul_claro;
  background-color: @branco;
  color: @azul;
}
button.flat, button.image-button.flat, notebook tab button, .path-bar button {
  border-color: transparent;
}
button.image-button { padding: 4px; }
button:hover, button:active, button:checked {
  background-color: @azul_claro;
  color: @branco;
}
button:disabled { color: @cinza; border-color: @cinza; }
button.flat:disabled { border-color: transparent; }
/* Linha dupla = 6px "double" (2 de linha, 2 de vao, 2 de linha), com 4px a
   menos de padding para o botao nao mudar de tamanho. Nada de box-shadow: o
   ~/.config/gtk-3.0/gtk.css do Retro-Moe zera o box-shadow em todo app. */
button.default, button.suggested-action, button:focus:not(.flat) {
  border: 6px double @azul_claro;
  padding: 0 8px;
}
button.image-button:focus:not(.flat) { padding: 0; }

/* ---- campos de texto: linha simples, dupla quando em foco ---- */
entry, spinbutton:not(.vertical) {
  min-height: 20px;
  padding: 4px 10px;
  border: 2px solid @azul_claro;
  background-color: @branco;
  color: @azul;
}
spinbutton:not(.vertical) entry { border: none; padding: 0; min-height: 0; }
spinbutton:not(.vertical) button { border: none; border-left: 2px solid @azul_claro; }
entry:focus, spinbutton:focus {
  border: 6px double @azul_claro;
  padding: 0 6px;
}
entry:disabled { border-color: @cinza; }
entry image { margin: 0 4px; }
entry progress { border-bottom: 2px solid @azul_claro; }

/* ---- caixas de marcar ---- */
check, radio {
  min-width: 16px;
  min-height: 16px;
  border: 2px solid @azul_claro;
  background-color: @branco;
  margin-right: 8px;
  -gtk-icon-source: none;
}
check:checked { -gtk-icon-source: url("visto.png"); }
radio:checked { -gtk-icon-source: url("ponto.png"); }
menuitem:hover check:checked { -gtk-icon-source: url("visto-sel.png"); }
menuitem:hover radio:checked { -gtk-icon-source: url("ponto-sel.png"); }
menuitem:hover check, menuitem:hover radio { background-color: @azul_claro; border-color: @branco; }
check:disabled, radio:disabled { border-color: @cinza; }
switch {
  min-width: 48px;
  min-height: 16px;
  border: 2px solid @azul_claro;
  padding: 2px;
  color: transparent;
}
switch slider { min-width: 16px; min-height: 16px; background-color: @cinza; }
switch:checked slider { background-color: @azul_claro; }

/* ---- listas e a vista dos arquivos ---- */
.view, treeview, iconview, list, textview {
  background-color: @branco;
  color: @azul;
}
.view:selected, treeview:selected, iconview:selected, row:selected,
.view:selected:focus, treeview:selected:focus {
  background-color: @azul_claro;
  color: @branco;
}
row { padding: 2px 8px; }
treeview.view { -GtkTreeView-horizontal-separator: 8; -GtkTreeView-vertical-separator: 4; }
treeview.view header button {
  padding: 2px 8px;
  border: none;
  border-bottom: 2px solid @azul_claro;
  color: @roxo;
}
treeview.view header button:hover { background-color: @azul_claro; color: @branco; }
treeview.view header button:not(:last-child) { border-right: 2px solid @azul_claro; }
treeview.view header button arrow { min-width: 16px; min-height: 16px; -gtk-icon-source: none; }
treeview.view expander {
  min-width: 16px;
  min-height: 16px;
  -gtk-icon-source: url("mais.png");
}
treeview.view expander:checked { -gtk-icon-source: url("menos.png"); }
treeview.view expander:selected { -gtk-icon-source: url("mais-sel.png"); }
treeview.view expander:checked:selected { -gtk-icon-source: url("menos-sel.png"); }
treeview.view.separator { min-height: 2px; color: @azul_claro; }
treeview.view:drop(active) { border: 2px solid @azul_claro; }
.view rubberband, treeview rubberband, rubberband {
  border: 2px solid @azul_claro;
  background-color: alpha(@azul_claro, 0.25);
}
.sidebar, .shortcuts-pane treeview { background-color: @branco; }

/* ---- divisorias, rolagem, abas ---- */
paned > separator {
  min-width: 2px;
  min-height: 2px;
  background-color: @azul_claro;
  -gtk-icon-source: none;
}
/* sem os botoes de seta nas pontas (o padrao do GTK 3 e te-los) */
scrollbar {
  -GtkScrollbar-has-backward-stepper: false;
  -GtkScrollbar-has-forward-stepper: false;
}
scrollbar.vertical:not(.overlay-indicator) { border-left: 2px solid @azul_claro; }
scrollbar.horizontal:not(.overlay-indicator) { border-top: 2px solid @azul_claro; }
scrollbar slider {
  min-width: 8px;
  min-height: 16px;
  margin: 4px;
  background-color: @azul_claro;
}
scrollbar.horizontal slider { min-width: 16px; min-height: 8px; }
scrollbar slider:hover, scrollbar slider:active { background-color: @azul; }
scrollbar.overlay-indicator:not(.dragging):not(.hovering) slider {
  min-width: 4px;
  min-height: 4px;
  margin: 2px;
}
scrollbar.overlay-indicator.horizontal:not(.dragging):not(.hovering) slider { min-width: 16px; }
scrollbar.overlay-indicator.vertical:not(.dragging):not(.hovering) slider { min-height: 16px; }
scrolledwindow undershoot, scrolledwindow overshoot { background: none; }
notebook header { border-bottom: 2px solid @azul_claro; }
notebook tab { padding: 2px 16px; color: @azul; }
notebook tab:checked { background-color: @azul_claro; color: @branco; }
notebook tab:checked button { color: @branco; }
notebook tab button { padding: 0; margin-left: 8px; }
notebook > stack:not(:only-child) { background-color: @branco; }
frame > border, .frame { border: none; }

/* ---- rodape, avisos, progresso ---- */
statusbar {
  padding: 2px 8px;
  border-top: 2px solid @azul_claro;
}
infobar { border-bottom: 2px solid @azul_claro; padding: 4px 8px; }
infobar.warning, infobar.error { color: #AA0000; }
progressbar trough, levelbar trough {
  min-height: 12px;
  min-width: 12px;
  border: 2px solid @azul_claro;
  padding: 2px;
}
progressbar progress, levelbar block.filled {
  min-height: 12px;
  background-color: @azul_claro;
}
levelbar block { min-width: 4px; }
scale { min-height: 16px; min-width: 16px; padding: 8px; }
scale trough { min-height: 2px; min-width: 2px; background-color: @azul_claro; }
scale highlight { background-color: @azul; }
scale slider { min-width: 16px; min-height: 16px; margin: -7px; background-color: @azul_claro; }
spinner {
  opacity: 0;
  min-width: 16px;
  min-height: 16px;
  -gtk-icon-source: -gtk-icontheme("process-working-symbolic");
}
spinner:checked { opacity: 1; animation: gira 1s linear infinite; }
arrow {
  min-width: 16px;
  min-height: 16px;
  -gtk-icon-source: -gtk-icontheme("pan-down-symbolic");
}
arrow.right { -gtk-icon-source: -gtk-icontheme("pan-end-symbolic"); }
arrow.left { -gtk-icon-source: -gtk-icontheme("pan-start-symbolic"); }
arrow.up { -gtk-icon-source: -gtk-icontheme("pan-up-symbolic"); }
combobox button { padding: 2px 4px 2px 8px; }
combobox arrow { margin-left: 8px; }
separator { min-width: 2px; min-height: 2px; background-color: @azul_claro; }
image { -gtk-icon-shadow: none; }
''')
print('tema em', os.path.dirname(DEST))
