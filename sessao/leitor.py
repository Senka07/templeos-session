#!/usr/bin/env python3
"""Leitor DolDoc: a ajuda e o codigo-fonte do TempleOS na sessao.

Abre os documentos da ISO como o editor do original os mostra: cores, links,
arvores que abrem e fecham, sprites. O formato e o layout estao em doldoc.py.

  leitor.py [nome]   nome como no TempleOS (::/Doc/Welcome.DD, MN:Print, HI:DolDoc)

Teclas, as do original onde existem: Esc volta um documento (na raiz fecha),
setas/PgUp/PgDn/Home/End rolam, Tab passa pelos links, Enter ou Espaco segue,
F1 abre o indice da ajuda, Ctrl+F procura, F3 repete, Ctrl+mais/menos muda o
tamanho do texto. Alt+Esquerda tambem volta.
"""
import os, re, sys, warnings
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import doldoc
from texto import GLIFOS, PALETA, RAIZ

sys.path.insert(0, os.path.join(RAIZ, 'extracao'))
try:
    import sprite as _sprite   # precisa do Pillow; sem ele o texto continua
except ImportError:
    _sprite = None

INICIO = '::/Doc/HelpIndex.DD'
TAMANHOS = (8, 12, 16)  # 8 e 16 sao exatos; 12 e o do terminal da sessao
TAMANHO_PADRAO = 12
COR = [tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) for h in PALETA]
BRANCO, AZUL_CLARO, VERMELHO = 15, 9, 4
SEM_ISO = '''The help reader shows the documents from the TempleOS ISO,
which is not in the repository. Get TempleOS.ISO from templeos.org and,
in the folder of this project:

  mkdir -p iso && cp ~/Downloads/TempleOS.ISO iso/
  python3 extracao/redsea.py iso/TempleOS.ISO iso-extraida
'''
AJUDA_RODAPE = 'Esc back  Tab link  F1 help  Ctrl+F find  Ctrl+/- size'

class Fonte:
    """Glifos como mascaras A8 num tamanho de celula qualquer (vizinho mais proximo)."""

    def __init__(self):
        self.cache = {}

    def glifo(self, ch, cel):
        chave = (ch, cel)
        m = self.cache.get(chave)
        if m is None:
            m = cairo.ImageSurface(cairo.FORMAT_A8, cel, cel)
            buf, passo, v = m.get_data(), m.get_stride(), GLIFOS[ch]
            for y in range(cel):
                for x in range(cel):
                    if v >> (8 * (y * 8 // cel) + x * 8 // cel) & 1:
                        buf[y * passo + x] = 255
            m.mark_dirty()
            self.cache[chave] = m
        return m

class Sprites:
    """Sprites do documento como superficies cairo, feitas so quando aparecem."""

    def __init__(self):
        self.cache = {}

    def pega(self, doc, num, cel):
        chave = (doc.titulo, num, cel)
        if chave in self.cache:
            return self.cache[chave]
        r = None
        if _sprite and num in doc.bins:
            try:
                feito = _sprite.render(doc.bins[num], GLIFOS, origem=True)
            except Exception:  # alguns tipos raros do formato nao sao desenhados
                feito = None
            if feito:
                img, ox, oy = feito
                k = cel / 8
                img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), 0)
                dados = bytearray(img.tobytes('raw', 'BGRa'))
                s = cairo.ImageSurface.create_for_data(dados, cairo.FORMAT_ARGB32, img.width,
                                                       img.height, img.width * 4)
                r = (s, dados, round(ox * k), round(oy * k))
        self.cache[chave] = r
        return r

class Leitor(Gtk.Window):
    def __init__(self, inicio):
        super().__init__(title='Help')
        self.fonte, self.sprites = Fonte(), Sprites()
        self.cel = TAMANHO_PADRAO
        self.hist = []        # (doc, abertos, topo, esquerda, foco)
        self.doc = self.pag = None
        self.abertos = {}
        self.topo = self.esq = 0
        self.foco = self.sobre = -1
        self.colunas = 0
        self.aviso = ''
        self.aviso_timer = None
        self.busca = None     # texto digitado com Ctrl+F; None = fora da busca
        self.ultima = ''
        self.achado = None    # (linha, coluna, tamanho)
        self.fundo = None
        self.pisca = False
        self.adiado = None
        self.set_app_paintable(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK |
                        Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect('draw', self.desenha)
        self.connect('key-press-event', self.tecla)
        self.connect('button-press-event', self.clique)
        self.connect('motion-notify-event', self.moveu)
        self.connect('leave-notify-event', self.saiu)
        self.connect('scroll-event', self.rolou)
        self.connect('configure-event', self.mudou_tamanho)
        self.connect('destroy', Gtk.main_quit)
        # 80 colunas, como a tela do original, sem passar da tela
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            t = Gdk.Screen.get_default()
            self.set_default_size(min(82 * self.cel, t.get_width() - 64),
                                  min(60 * self.cel, t.get_height() - 96))
        GLib.timeout_add(500, self.tique)
        self.segue(inicio)
        if self.doc is None:  # nada abriu: mostra o motivo em vez de janela vazia
            motivo = 'Could not open "%s".\n\n%s\n' % (inicio, self.aviso)
            if not os.path.isdir(doldoc.raiz_iso()):
                motivo = SEM_ISO
            self.abre_doc(doldoc.Documento('Help', motivo), {})

    # ------------------------------------------------------------ navegacao
    def mostra_aviso(self, texto):
        self.aviso = texto
        if self.aviso_timer:
            GLib.source_remove(self.aviso_timer)
        def limpa():
            self.aviso, self.aviso_timer = '', None
            self.queue_draw()
            return False
        self.aviso_timer = GLib.timeout_add_seconds(5, limpa)
        self.queue_draw()

    def guarda(self):
        if self.doc is not None:
            self.hist.append((self.doc, self.abertos, self.topo, self.esq, self.foco))

    def abre_doc(self, doc, abertos, topo=0, esq=0, foco=-1):
        self.doc, self.abertos = doc, abertos
        self.topo, self.esq, self.foco, self.sobre = topo, esq, foco, -1
        self.achado = None
        self.set_title('Help: ' + doc.titulo)
        self.refaz()

    def segue(self, alvo):
        """Os tipos de link de DocLink.HC. Sem prefixo o texto e o nome do arquivo."""
        m = re.match(r'([A-Z]{2}):(.*)$', alvo.strip(), re.S)
        tipo, resto = (m[1], m[2]) if m else ('FI', alvo.strip())
        base = self.doc.caminho if self.doc else None
        try:
            if tipo == 'FI':
                self.vai(doldoc.abre(resto, base))
            elif tipo in ('FA', 'FF'):
                nome, _, agulha = resto.partition(',')
                ocorrencia = 1
                k = re.match(r'(.*):(\d+)$', agulha, re.S)
                if k:
                    agulha, ocorrencia = k[1], int(k[2])
                self.vai(doldoc.abre(nome, base), agulha=agulha, ocorrencia=ocorrencia)
            elif tipo == 'FL':
                nome, _, n = resto.rpartition(',')
                self.vai(doldoc.abre(nome, base), linha=int(n))
            elif tipo == 'MN':
                lugar = doldoc.indice().lugar.get(resto)
                if not lugar:
                    raise doldoc.Erro('Symbol not found: ' + resto)
                self.vai(doldoc.abre('::/' + lugar[0]), linha=lugar[1])
            elif tipo == 'HI':
                d = doldoc.indice().pagina_ajuda(resto)
                if not d:
                    raise doldoc.Erro('Empty help index: ' + resto)
                self.vai(d)
            elif tipo == 'BF':
                livro, _, agulha = resto.partition(',')
                self.biblia(livro, agulha)
            else:
                raise doldoc.Erro('Needs the running system: ' + alvo)
        except (doldoc.Erro, ValueError, OSError) as e:
            self.mostra_aviso(str(e))

    def vai(self, doc, agulha=None, ocorrencia=1, linha=None):
        abertos, parte = {}, None
        if agulha:
            parte = doc.parte_com(agulha, ocorrencia)
            if parte is None:
                self.mostra_aviso('Not found in document: ' + agulha)
        elif linha:
            parte = doc.parte_da_linha(linha)
        if parte is not None:
            doc.abre_ate(parte, abertos)
        self.guarda()
        self.abre_doc(doc, abertos)
        if parte is not None:
            alvo = self.pag.marcas.get(parte, 0)
            if linha:  # a parte comeca antes da linha pedida
                alvo += max(0, linha - doc.partes[parte].linha)
            self.topo = max(0, alvo - 2)
            self.refaz_rolagem()

    def biblia(self, livro, agulha):
        # Inteira ela tem 100 mil linhas; o link so precisa do pedaco certo
        import deus
        if livro not in deus.LIVROS:
            raise doldoc.Erro('Unknown book: ' + livro)
        linhas = deus.biblia()
        ini = deus.INICIOS[deus.LIVROS.index(livro)] - 1
        fim = deus.INICIOS[deus.LIVROS.index(livro) + 1] - 1
        alvo = next((k for k in range(ini, fim) if agulha and agulha in linhas[k]), ini)
        self.guarda()
        self.abre_doc(doldoc.Documento('Bible: ' + livro, '\n'.join(linhas[alvo:alvo + 300]) + '\n',
                                       plano=True), {})

    def volta(self):
        if not self.hist:
            self.destroy()
            return
        doc, abertos, topo, esq, foco = self.hist.pop()
        self.abre_doc(doc, abertos, topo, esq, foco)

    def alterna_arvore(self, i):
        _, _, colapsa = self.doc.arvores[i]
        fechada = not self.abertos[i] if i in self.abertos else colapsa
        self.abertos[i] = fechada
        self.refaz()

    def ativa(self, ident):
        tipo, valor = self.pag.links[ident]
        if tipo == 'arvore':
            self.alterna_arvore(valor)
        elif tipo == 'alvo':
            self.segue(valor)
        else:
            self.mostra_aviso('Macro: runs only inside the real TempleOS')

    # ------------------------------------------------------------ layout
    def medidas(self):
        a = self.get_allocation()
        return max(1, a.width // self.cel), max(1, a.height // self.cel - 1)

    def refaz(self):
        if self.doc is None:
            return
        self.colunas, _ = self.medidas()
        self.pag = doldoc.monta(self.doc, self.colunas, self.abertos)
        self.refaz_rolagem()

    def refaz_rolagem(self):
        cols, lins = self.medidas()
        self.topo = max(0, min(self.topo, len(self.pag.linhas) - lins))
        self.esq = max(0, min(self.esq, self.pag.largura_max - cols))
        self.queue_draw()

    def mudou_tamanho(self, _w, ev):
        if self.fundo is None or self.fundo.get_width() != ev.width or self.fundo.get_height() != ev.height:
            self.fundo = cairo.ImageSurface(cairo.FORMAT_RGB24, max(1, ev.width), max(1, ev.height))
        if self.doc is not None and ev.width // self.cel != self.colunas:
            if self.adiado:  # arrastando a borda: refaz so quando parar
                GLib.source_remove(self.adiado)
            self.adiado = GLib.timeout_add(120, self.refaz_adiado)
        return False

    def refaz_adiado(self):
        self.adiado = None
        self.refaz()
        return False

    def muda_tamanho_texto(self, passo):
        i = TAMANHOS.index(self.cel) + passo
        if 0 <= i < len(TAMANHOS):
            self.cel = TAMANHOS[i]
            self.refaz()

    # ------------------------------------------------------------ desenho
    def desenha(self, _w, cr_janela):
        if self.fundo is None or self.pag is None:
            return True
        cr = cairo.Context(self.fundo)
        cr.set_source_rgb(*COR[BRANCO]); cr.paint()
        cel = self.cel
        cols, lins = self.medidas()
        e = cel // 8 or 1
        for n in range(lins):
            k = self.topo + n
            if k >= len(self.pag.linhas):
                break
            l = self.pag.linhas[k]
            for col in range(self.esq, min(len(l), self.esq + cols + 1)):
                c = l[col]
                if c is None:
                    continue
                ch, fg, bg, attr, lk, sy = c
                invertido = bool(attr & doldoc.INVERTE)
                if attr & doldoc.PISCA and self.pisca:
                    invertido = not invertido
                if lk >= 0 and lk in (self.sobre, self.foco):
                    invertido = not invertido
                if self.achado and self.achado[0] == k and self.achado[1] <= col < self.achado[1] + self.achado[2]:
                    invertido = not invertido
                if invertido:
                    fg, bg = bg, fg
                x, y = (col - self.esq) * cel, n * cel
                if bg != BRANCO:
                    cr.set_source_rgb(*COR[bg])
                    cr.rectangle(x, y, cel, cel); cr.fill()
                cr.set_source_rgb(*COR[fg])
                if ch != 32:
                    cr.mask_surface(self.fonte.glifo(ch, cel), x, y + sy * cel // 8)
                if attr & doldoc.SUB:
                    cr.rectangle(x, y + cel - e, cel, e); cr.fill()
        # Por cima do texto, como a camada grafica do original
        for col, lin, num, _ in self.pag.sprites:
            s = self.sprites.pega(self.doc, num, cel)
            if s:
                x = (col - self.esq) * cel + s[2]
                y = (lin - self.topo) * cel + s[3]
                if y < lins * cel and y + s[0].get_height() > 0:
                    cr.save()
                    cr.rectangle(0, 0, cols * cel, lins * cel); cr.clip()
                    cr.set_source_surface(s[0], x, y); cr.paint()
                    cr.restore()
        self.rodape(cr, cols, lins)
        cr_janela.set_source_surface(self.fundo, 0, 0)
        cr_janela.paint()
        return True

    def rodape(self, cr, cols, lins):
        """Ultima linha, no lugar da barra de rolagem de glifos do original."""
        total = len(self.pag.linhas)
        pos = '%d/%d' % (min(self.topo + lins, total), total)
        if self.busca is not None:
            texto, fundo = 'Find: %s\xdb' % self.busca, AZUL_CLARO
        elif self.aviso:
            texto, fundo = self.aviso, VERMELHO
        else:
            alvo = self.sobre if self.sobre >= 0 else self.foco
            if alvo >= 0 and self.pag.links[alvo][0] == 'alvo':
                texto = self.pag.links[alvo][1]
            else:
                texto = AJUDA_RODAPE
            fundo = AZUL_CLARO
        y = self.get_allocation().height - self.cel
        cr.set_source_rgb(*COR[fundo])
        cr.rectangle(0, y, self.get_allocation().width, self.cel); cr.fill()
        cr.set_source_rgb(*COR[BRANCO])
        lugar = cols - len(pos) - 1
        linha = texto[:max(0, lugar - 1)].ljust(max(0, lugar)) + ' ' + pos
        for i, ch in enumerate(linha[:cols].encode('latin1', 'replace')):
            if ch != 32:
                cr.mask_surface(self.fonte.glifo(ch, self.cel), i * self.cel, y)

    def tique(self):
        if self.pag is not None and self.pag.pisca:
            self.pisca = not self.pisca
            self.queue_draw()
        return True

    # ------------------------------------------------------------ mouse
    def link_em(self, px, py):
        cel = self.cel
        cols, lins = self.medidas()
        n, col = int(py // cel), int(px // cel) + self.esq
        if n >= lins:
            return -1
        k = self.topo + n
        if k < len(self.pag.linhas):
            l = self.pag.linhas[k]
            if 0 <= col < len(l) and l[col] is not None and l[col][4] >= 0:
                return l[col][4]
        for c, lin, num, lk in self.pag.sprites:
            if lk >= 0:
                s = self.sprites.pega(self.doc, num, cel)
                if s:
                    x = (c - self.esq) * cel + s[2]
                    y = (lin - self.topo) * cel + s[3]
                    if x <= px < x + s[0].get_width() and y <= py < y + s[0].get_height():
                        return lk
        return -1

    def clique(self, _w, ev):
        if ev.button == 8:   # botao "voltar" do mouse
            self.volta()
        elif ev.button == 1 and self.pag is not None:
            lk = self.link_em(ev.x, ev.y)
            if lk >= 0:
                self.ativa(lk)
        return True

    def moveu(self, _w, ev):
        if self.pag is not None:
            lk = self.link_em(ev.x, ev.y)
            if lk != self.sobre:
                self.sobre = lk
                self.queue_draw()
        return False

    def saiu(self, *_):
        if self.sobre != -1:
            self.sobre = -1
            self.queue_draw()
        return False

    def rolou(self, _w, ev):
        ok, _dx, dy = ev.get_scroll_deltas()
        if ev.direction == Gdk.ScrollDirection.UP:
            d = -3
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            d = 3
        elif ok:
            d = round(dy * 3)
        else:
            d = 0
        if d:
            self.topo += d
            self.refaz_rolagem()
        return True

    # ------------------------------------------------------------ teclado
    def proximo_link(self, passo):
        """Tab: entre os links da pagina, na ordem em que aparecem."""
        ids = range(len(self.pag.links))
        if not self.pag.links:
            return
        ordem = sorted(ids, key=lambda i: self.pag.inicio_do_link(i) or (1 << 30, 0))
        if self.foco in ordem:
            pos = (ordem.index(self.foco) + passo) % len(ordem)
        else:
            pos = next((j for j, i in enumerate(ordem)
                        if (self.pag.inicio_do_link(i) or (1 << 30, 0))[0] >= self.topo), 0)
        self.foco = ordem[pos]
        lugar = self.pag.inicio_do_link(self.foco)
        if lugar:
            _, lins = self.medidas()
            if not self.topo <= lugar[0] < self.topo + lins:
                self.topo = max(0, lugar[0] - lins // 3)
        self.refaz_rolagem()

    def procura(self, texto, desde):
        alvo = texto.lower()
        total = len(self.pag.linhas)
        for d in range(total):
            k = (desde + d) % total
            col = self.pag.texto_linha(k).lower().find(alvo)
            if col >= 0:
                self.achado = (k, col, len(texto))
                _, lins = self.medidas()
                if not self.topo <= k < self.topo + lins:
                    self.topo = max(0, k - lins // 3)
                self.refaz_rolagem()
                return True
        self.achado = None
        self.mostra_aviso('Not found: ' + texto)
        return False

    def tecla_da_busca(self, ev):
        k = ev.keyval
        if k == Gdk.KEY_Escape:
            self.busca = None
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.ultima, self.busca = self.busca, None
            if self.ultima:
                self.procura(self.ultima, self.topo)
        elif k == Gdk.KEY_BackSpace:
            self.busca = self.busca[:-1]
        else:
            u = Gdk.keyval_to_unicode(k)
            if u >= 32:
                self.busca += chr(u)
        self.queue_draw()
        return True

    def tecla(self, _w, ev):
        if self.pag is None:
            return True
        if self.busca is not None:
            return self.tecla_da_busca(ev)
        k = ev.keyval
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        alt = ev.state & Gdk.ModifierType.MOD1_MASK
        shift = ev.state & Gdk.ModifierType.SHIFT_MASK
        _, lins = self.medidas()
        passo = {Gdk.KEY_Up: -1, Gdk.KEY_Down: 1, Gdk.KEY_Page_Up: -(lins - 1),
                 Gdk.KEY_Page_Down: lins - 1}.get(k)
        if k == Gdk.KEY_Escape:
            if shift:      # Shift+Esc fecha direto, sem voltar por todos
                self.destroy()
            else:
                self.volta()
        elif (k == Gdk.KEY_Left and alt) or k == Gdk.KEY_BackSpace:
            self.volta()
        elif passo is not None:
            self.topo += passo
            self.refaz_rolagem()
        elif k == Gdk.KEY_Home:
            self.topo = 0; self.esq = 0
            self.refaz_rolagem()
        elif k == Gdk.KEY_End:
            self.topo = len(self.pag.linhas)
            self.refaz_rolagem()
        elif k == Gdk.KEY_Left:
            self.esq -= 8
            self.refaz_rolagem()
        elif k == Gdk.KEY_Right:
            self.esq += 8
            self.refaz_rolagem()
        elif k in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            self.proximo_link(-1 if shift else 1)
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if self.foco >= 0:
                self.ativa(self.foco)
            elif k == Gdk.KEY_space:
                self.topo += lins - 1
                self.refaz_rolagem()
        elif k == Gdk.KEY_F1:
            self.segue(INICIO)
        elif k == Gdk.KEY_F3 and self.ultima:
            self.procura(self.ultima, (self.achado[0] + 1) if self.achado else self.topo)
        elif ctrl and k in (Gdk.KEY_f, Gdk.KEY_F):
            self.busca = ''
            self.queue_draw()
        elif ctrl and k in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.muda_tamanho_texto(1)
        elif ctrl and k in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.muda_tamanho_texto(-1)
        return True

if __name__ == '__main__':
    janela = Leitor(sys.argv[1] if len(sys.argv) > 1 else INICIO)
    janela.show_all()
    janela.refaz()
    Gtk.main()
