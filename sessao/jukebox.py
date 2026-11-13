#!/usr/bin/env python3
"""JukeBox, o tocador de hinos do TempleOS (Apps/Psalmody/JukeBox.HC).

Uma lista com as cancoes de ~/.local/share/templeos/Psalmody, na cor da
categoria e com a nota na frente do nome. Escolher uma abre a janela da
cancao (SingleSong): 51 colunas por 9 linhas, a letra aparecendo nota a nota,
em laco ate fechar a janela ou escolher outra.

  setas, mouse     escolhe          Enter, espaco, clique  toca
  Delete           apaga (bipe, vai para a lixeira)
  0 a 9            da a nota        r   pede a recompensa de Deus
  Esc, DONE        fecha (e para a cancao)

A recompensa (JukeReward) sao linhas de quatro God Words gravadas dentro do
arquivo da cancao; quando a cancao toca, elas aparecem numa janela vermelha a
direita. Uma instancia so: chamar de novo traz a janela para frente.
"""
import os, re, sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deus, musica, psalmody
from doc import Doc, trecho
from texto import (C, rgb, escreve, para_glifos, BLACK, BLUE, GREEN, CYAN, RED,
                   LTGRAY, WHITE)

COLS_CANCAO, LINHAS_CANCAO = 51, 9    # WinHorz(l, l+50), WinVert(2, 2+8)
POR_LINHA = 5                          # if (!(i++%5)) DocPrint(doc,"\n");

def tamanho_tela():
    """Monitor onde esta o mouse (o Gdk.Screen.get_width foi descontinuado)."""
    d = Gdk.Display.get_default()
    _, x, y = d.get_default_seat().get_pointer().get_position()[0:3]
    g = (d.get_monitor_at_point(x, y) or d.get_monitor(0)).get_geometry()
    return g.width, g.height

# ---------------------------------------------------------------- texto com DolDoc
class Tela:
    """Grade de celulas que entende o pouco de DolDoc que as cancoes imprimem:
    cores ($RED$, $FG,n$, $BG,n$, $FD$, $BD$), $CL$ e $CM$. O resto e ignorado."""
    def __init__(self, cols, linhas, fg=BLUE, bg=WHITE, quebra=False, guarda=100):
        self.cols, self.linhas, self.quebra, self.guarda = cols, linhas, quebra, guarda
        self.fg_pad, self.bg_pad = fg, bg
        self.limpa()

    def limpa(self):
        self.fg, self.bg = self.fg_pad, self.bg_pad
        self.texto = [[]]
        self.x = 0

    def cores(self, bg, fg):
        self.fg_pad = self.fg = fg
        self.bg_pad = self.bg = bg

    def escreve(self, s):
        for parte in re.split(r'(\$[^$]*\$)', s):
            if len(parte) > 1 and parte[0] == parte[-1] == '$':
                self._comando(parte[1:-1])
            elif parte == '$':
                pass
            else:
                for ch in parte:
                    self._char(ch)
        del self.texto[:-self.guarda]

    def _cor(self, v, padrao):
        v = v.strip()
        if not v:
            return padrao
        if v.upper() in psalmody.CORES_NOME:
            return psalmody.CORES_NOME[v.upper()]
        try:
            return int(v, 0) & 15
        except ValueError:
            return padrao

    def _comando(self, corpo):
        cab, _, args = corpo.partition(',')
        nome = re.split(r'[+-]', cab, 1)[0].upper()
        segura = '+H' in cab.upper()
        if nome in psalmody.CORES_NOME:
            self.fg = psalmody.CORES_NOME[nome]
        elif nome == 'FG':
            self.fg = self._cor(args, self.fg_pad)
            if segura: self.fg_pad = self.fg
        elif nome == 'BG':
            self.bg = self._cor(args, self.bg_pad)
            if segura: self.bg_pad = self.bg
        elif nome == 'FD':
            self.fg_pad = self.fg = self._cor(args, self.fg_pad)
        elif nome == 'BD':
            self.bg_pad = self.bg = self._cor(args, self.bg_pad)
        elif nome == 'CL':
            self.texto = [[]]; self.x = 0
        elif nome == 'CM':
            nums = [int(n) for n in re.findall(r'-?\d+', args)]
            if nums:
                self.x = max(0, self.x + nums[0])
            for _ in range(nums[1] if len(nums) > 1 and nums[1] > 0 else 0):
                self._char('\n')

    def _char(self, ch):
        if ch == '\n':
            self.texto.append([]); self.x = 0
            return
        if ch == '\t':
            for _ in range(8 - self.x % 8):
                self._char(' ')
            return
        g = para_glifos(ch)
        if not g:
            return
        if self.quebra and self.x >= self.cols:
            self.texto.append([]); self.x = 0
        linha = self.texto[-1]
        while len(linha) < self.x:
            linha.append((' ', self.fg, self.bg_pad))
        cel = (g, self.fg, self.bg)
        if self.x < len(linha):
            linha[self.x] = cel
        else:
            linha.append(cel)
        self.x += 1

    def quebra_palavras(self, s):
        """$WW$: quebra entre palavras, nao no meio delas."""
        r, col = [], 0
        for pal in re.split(r'( +)', s):
            if col + len(pal) > self.cols and col and not pal.startswith(' '):
                r.append('\n'); col = 0
            r.append(pal); col += len(pal)
        return ''.join(r)

    def desenha(self, cr):
        cr.set_source_rgb(*rgb(self.bg_pad)); cr.paint()
        for lin, linha in enumerate(self.texto[-self.linhas:]):
            for col, (g, fg, bg) in enumerate(linha[:self.cols]):
                escreve(cr, col, lin, g, fg, bg)

class JanelaTexto(Gtk.Window):
    """Janela de tarefa que nao pega o foco (WIG_NO_FOCUS_TASK_DFT)."""
    def __init__(self, titulo, tela, x, y):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.tela = tela
        self.set_title(titulo)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_app_paintable(True)
        self.set_default_size(tela.cols * C, tela.linhas * C)
        self.move(x, y)
        self.connect('draw', lambda _w, cr: self.tela.desenha(cr) or True)

# ---------------------------------------------------------------- a cancao tocando
class Tocando:
    """SingleSong + JukeReward: a janela da letra, o som e a recompensa."""
    def __init__(self, cancao, app):
        self.app = app
        self.tela = Tela(COLS_CANCAO, LINHAS_CANCAO)
        self.janela = JanelaTexto(cancao.nome, self.tela, 2 * C, 2 * C)
        app.add_window(self.janela)
        self.premio = None
        self.janela.connect('destroy', lambda *_: self.para())
        self.tocador = musica.Tocador(cancao.operacoes())
        self.vivo = True
        GLib.timeout_add(15, self.atualiza)
        self.janela.show_all()

    def atualiza(self):
        if not self.vivo:
            return False
        mudou = False
        for ev in self.tocador.prontos():
            tipo = ev[0]
            if tipo == 'texto':
                self.tela.escreve(ev[1]); mudou = True
            elif tipo == 'cores':
                self.tela.cores(ev[1], ev[2]); mudou = True
            elif tipo == 'premio':
                self.mostra_premio(ev[1])
            elif tipo == 'fim':   # cancao sem laco: a tarefa termina e a janela fecha
                self.janela.destroy()
                return False
        if mudou:
            self.janela.queue_draw()
        return True

    def mostra_premio(self, msg):
        """Reward: da coluna seguinte a da cancao ate a borda, linhas 2 a TEXT_ROWS-2."""
        largura, altura = tamanho_tela()
        cols, linhas = largura // C, altura // C
        x0 = 2 + COLS_CANCAO + 2
        largura = max(16, cols - 2 - x0)
        t = Tela(largura, max(4, linhas - 4), fg=BLUE, bg=LTGRAY, quebra=True)
        t.fg = RED
        t.escreve(t.quebra_palavras(msg.strip()))
        self.premio = JanelaTexto('Reward', t, x0 * C, 2 * C)
        self.app.add_window(self.premio)
        self.premio.show_all()

    def para(self):
        if not self.vivo:
            return
        self.vivo = False
        self.tocador.para()
        if self.premio:
            self.premio.destroy()
            self.premio = None

    def fecha(self):
        self.para()
        self.janela.destroy()

# ---------------------------------------------------------------- a lista
class JukeBox(Doc):
    def __init__(self, app):
        super().__init__('JukeBox', 52, 12)
        self.app = app
        self.oraculo = deus.Oraculo()
        self.tocando = None
        self.sel = 0
        self.aviso = None
        psalmody.prepara()
        self.cancoes = psalmody.lista()
        self.refaz()
        # embaixo da janela da cancao e a esquerda da recompensa (coluna 55)
        self.move(2 * C, (2 + LINHAS_CANCAO + 2) * C)
        self.connect('destroy', lambda *_: self.tocando and self.tocando.fecha())

    def recarrega(self):
        """Chamado de novo (icone, outro God Song salvo): relê a pasta."""
        atual = self.cancoes[self.sel].caminho if self.sel < len(self.cancoes) else None
        self.cancoes = psalmody.lista()
        caminhos = [c.caminho for c in self.cancoes]
        self.sel = caminhos.index(atual) if atual in caminhos else 0
        self.refaz()

    def conteudo_novo(self):
        g = lambda t: trecho(t, GREEN)
        r = [[trecho('Key: '), trecho('Graphics ', GREEN), trecho('Words ', BLUE),
              trecho('No Nothing ', RED), trecho('Incomplete ', BLACK),
              trecho('Special', CYAN)],
             [],
             [g('<DEL>'), trecho('   to delete a song.')],
             [trecho("'"), g('0'), trecho("'-'"), g('9'), trecho("'"), trecho(' to rate a song.')],
             [trecho("'"), g('r'), trecho("'"), trecho('     to get your reward from God.')]]
        self.posicoes = []   # (linha, indice do trecho) de cada cancao, e DONE no fim
        for i, c in enumerate(self.cancoes):
            if i == 0:
                r.append([])     # o "\n" do i=0 deixa uma linha em branco
            if i % POR_LINHA == 0:
                r.append([])
            cor = c.cor if c.cor is not None else BLUE
            texto = '%s%-8s' % (c.nota, c.nome[:8])
            r[-1].append(trecho(texto, cor, lambda i=i: self.escolhe(i)))
            r[-1].append(trecho(' '))
            self.posicoes.append((len(r) - 1, len(r[-1]) - 2))
        r.append([trecho('DONE', CYAN, self.close)])
        self.posicoes.append((len(r) - 1, 0))
        if self.aviso:
            r += [[], [trecho(self.aviso, RED)]]
        # o cursor do DolDoc: a entrada escolhida com as cores trocadas
        if self.posicoes:
            self.sel = min(self.sel, len(self.posicoes) - 1)
            lin, k = self.posicoes[self.sel]
            p = r[lin][k]
            p['fg'], p['bg'] = WHITE, p['fg']
        return r

    def refaz(self):
        self.conteudo = self.conteudo_novo()
        self.set_default_size(self.colunas * C, (len(self.conteudo) + 1) * C)
        self.resize(self.colunas * C, (len(self.conteudo) + 1) * C)
        self.queue_draw()

    # ------------------------------------------------------------ acoes
    def escolhe(self, i):
        self.sel = i
        self.aviso = None
        self.refaz()
        self.toca(i)

    def toca(self, i):
        if self.tocando:
            self.tocando.fecha()
            self.tocando = None
        if i >= len(self.cancoes):   # DONE
            self.close()
            return
        self.tocando = Tocando(self.cancoes[i], self.app)
        self.present()

    def apaga(self, i):
        """<DEL>: Beep e Del. Aqui vai para a lixeira, nao some de vez."""
        c = self.cancoes[i]
        musica.bipe()
        try:
            Gio.File.new_for_path(c.caminho).trash(None)
        except GLib.Error:
            os.remove(c.caminho)
        del self.cancoes[i]
        self.refaz()

    def recompensa(self, i):
        palavras = []
        for _ in range(4 * 5):
            self.oraculo.esvazia()
            self.oraculo.insere()
            palavras.append(deus.palavra(self.oraculo))
        c = self.cancoes[i]
        for k in range(5):
            c.recompensa(palavras[4 * k:4 * k + 4])
        # o original para num In("") depois de gravar; aqui um aviso basta
        self.aviso = 'Reward added to %s.' % c.nome
        self.refaz()

    def tecla(self, _w, ev):
        k = ev.keyval
        n = len(self.posicoes)
        mods = ev.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK |
                           Gdk.ModifierType.SHIFT_MASK)
        e_cancao = self.sel < len(self.cancoes)
        if k == Gdk.KEY_Escape:
            self.close()
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.toca(self.sel)
        elif k in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Home,
                   Gdk.KEY_End):
            passo = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1, Gdk.KEY_Up: -POR_LINHA,
                     Gdk.KEY_Down: POR_LINHA, Gdk.KEY_Home: -n, Gdk.KEY_End: n}[k]
            self.sel = max(0, min(n - 1, self.sel + passo))
            self.refaz()
        elif mods:
            return False
        elif e_cancao and k in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            self.apaga(self.sel)
        elif e_cancao and Gdk.KEY_0 <= k <= Gdk.KEY_9:
            self.cancoes[self.sel].da_nota(chr(k))
            self.refaz()
        elif e_cancao and k == Gdk.KEY_r:
            self.recompensa(self.sel)
        return True

def main():
    app = Gtk.Application(application_id='org.templeos.JukeBox',
                          flags=Gio.ApplicationFlags.FLAGS_NONE)
    estado = {}

    def ativa(app):
        jb = estado.get('jb')
        if jb is None:
            jb = estado['jb'] = JukeBox(app)
            app.add_window(jb)
            jb.connect('destroy', lambda *_: app.quit())
            jb.show_all()
        else:
            jb.recarrega()
        jb.present()
    app.connect('activate', ativa)
    return app.run(sys.argv[:1])

if __name__ == '__main__':
    sys.exit(main())
