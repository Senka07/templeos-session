"""Janela de documento no estilo DolDoc: texto da fonte original em celulas,
links vermelhos sublinhados, botoes com borda de glifos e sprites.

O conteudo e uma lista de linhas; cada linha, uma lista de trechos
(texto, cor, acao). Trecho com acao e link. Esc fecha (Esc e Shift+Esc fecham
o documento no original), Enter chama `ao_enter`.
"""
import os
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from texto import C, RAIZ, BLUE, RED, WHITE, LTBLUE, rgb, escreve

def trecho(texto, cor=BLUE, acao=None, fundo=WHITE):
    return dict(t=texto, fg=cor, bg=fundo, acao=acao)

def link(texto, acao):
    p = trecho(texto, RED, acao)
    p['sub'] = True
    return p

def botao(texto, acao, cor=BLUE):
    """Ocupa tres linhas: a de cima e a de baixo do conteudo precisam estar livres."""
    return dict(t=texto, fg=cor, bg=WHITE, acao=acao, borda=True)

def sprite(caminho, escala=2):
    pb = GdkPixbuf.Pixbuf.new_from_file(caminho)
    return pb.scale_simple(pb.get_width() * escala, pb.get_height() * escala,
                           GdkPixbuf.InterpType.NEAREST)

class Doc(Gtk.Window):
    def __init__(self, titulo, colunas, linhas, conteudo=None, x=None, y=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title(titulo)
        self.colunas, self.linhas = colunas, linhas
        self.conteudo = conteudo or []
        self.sprites = []          # (x_px, y_px, pixbuf, acao)
        self.ao_enter = None
        self.ao_fechar = None
        self.set_app_paintable(True)
        self.set_default_size(colunas * C, linhas * C)
        if x is not None:
            self.move(x, y)
        else:
            self.set_position(Gtk.WindowPosition.CENTER)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('draw', self.desenha)
        self.connect('button-press-event', self.clique)
        self.connect('key-press-event', self.tecla)
        self.connect('destroy', lambda *_: self.ao_fechar and self.ao_fechar())

    # ------------------------------------------------------------ desenho
    def desenha(self, _w, cr):
        cr.set_source_rgb(*rgb(WHITE)); cr.paint()
        for x, y, pb, _ in self.sprites:
            Gdk.cairo_set_source_pixbuf(cr, pb, x, y)
            cr.paint()
        for lin, partes in enumerate(self.conteudo):
            col = 0
            for p in partes:
                if p.get('borda'):
                    self.botao(cr, col, lin, p)
                else:
                    escreve(cr, col, lin, p['t'], p['fg'], p['bg'])
                    if p.get('sub'):  # sublinhado na ultima linha de pixels da celula
                        cr.set_source_rgb(*rgb(p['fg']))
                        cr.rectangle(col * C, lin * C + C - 2, len(p['t']) * C, 2)
                        cr.fill()
                col += len(p['t']) + (2 if p.get('borda') else 0)
        return True

    def botao(self, cr, col, lin, p):
        """Botao do DolDoc ($BT): o texto dentro de uma moldura de glifos (TextBorder)."""
        w = len(p['t'])
        escreve(cr, col, lin - 1, '\x06' + '\x02' * w + '\x08', LTBLUE, WHITE)
        escreve(cr, col, lin, '\x04', LTBLUE, WHITE)
        escreve(cr, col + 1, lin, p['t'], p['fg'], p['bg'])
        escreve(cr, col + w + 1, lin, '\x04', LTBLUE, WHITE)
        escreve(cr, col, lin + 1, '\x0a' + '\x02' * w + '\x0c', LTBLUE, WHITE)

    # ------------------------------------------------------------ entrada
    def clique(self, _w, ev):
        if ev.button != 1:
            return False
        for x, y, pb, acao in self.sprites:
            if acao and x <= ev.x < x + pb.get_width() and y <= ev.y < y + pb.get_height():
                acao(); return True
        lin, alvo = int(ev.y // C), int(ev.x // C)
        if 0 <= lin < len(self.conteudo):
            col = 0
            for p in self.conteudo[lin]:
                largura = len(p['t']) + (2 if p.get('borda') else 0)
                if col <= alvo < col + largura and p['acao']:
                    p['acao'](); return True
                col += largura
        return True

    def tecla(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
        elif ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space) and self.ao_enter:
            self.ao_enter()
        return True
