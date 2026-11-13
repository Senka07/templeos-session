#!/usr/bin/env python3
"""Atalhos globais da sessao TempleOS, o PersonalMenu e os popups de Deus.

Atalhos do sistema no original sao os CtrlAltCBSet() (Kernel/KeyDev.HC e
outros); F6/F7 e Ctrl+M sao do editor DolDoc (Adam/DolDoc/DocPutKey.HC), que no
TempleOS esta em toda janela -- aqui viram globais.

  Ctrl+Alt+T  terminal              Ctrl+Alt+X  fecha a janela em foco
  Ctrl+Alt+N  proxima janela        Ctrl+Alt+M  liga/desliga o som
  Ctrl+Alt+S  captura de tela para a area de transferencia
  Ctrl+Alt+B  Biblia                Ctrl+Alt+A  tabela ASCII
  Ctrl+Alt+Z  zoom (Shift diminui)
  Ctrl+Alt+G  grade do mouse (Shift desliga)
  (areas de trabalho: Ctrl+F1..F4 e Ctrl+Alt+setas sao do proprio xfwm4)
  Windows     menu da janela        Ctrl+M      PersonalMenu
  F7          God Word (digita a palavra na janela em foco)
  Shift+F7    God Passage           F6          God Song

Nao implementados (nao tem equivalente util fora do TempleOS): Ctrl+Alt+C
(break), D (depurador), F (fonte cirilica), V (VGA flush).

Fora do original, os atalhos de programas de config/programas.json (os mesmos
de uma sessao XFCE comum, que la quem dispara e o xfsettingsd; uma copia em
~/.config/templeos/ tem prioridade). Mais Windows+1..4 (area),
Windows+Shift+1..4 (leva a janela) e Windows+W (fecha). Ficam aqui e nao no
xfwm4 porque o Windows sozinho ja e capturado por este processo: enquanto ele
esta apertado o teclado inteiro vem para ca, e o xfwm4 nao veria Windows+1.
"""
import ctypes, json, os, shlex, shutil, signal, subprocess, sys, time, warnings
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x11, deus, bloqueio, psalmody
from doc import Doc, trecho, link, botao, sprite
from texto import C, RAIZ, BLUE, GREEN, RED, WHITE, LTBLUE

TERMINAL = os.environ.get('TEMPLEOS_TERM', 'kitty')
oraculo = deus.Oraculo()

def ambiente():
    env = dict(os.environ)
    env.pop('GTK_THEME', None)  # o tema TempleOS e so dos processos da sessao
    env['TEMPLEOS_RAIZ'] = RAIZ
    return env

THUNAR = shlex.quote(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thunar.sh'))

def roda(cmd):
    cmd = cmd.replace('$TERM', TERMINAL)
    if cmd == 'thunar' or cmd.startswith('thunar '):
        cmd = 'sh ' + THUNAR + cmd[6:]  # com o tema TempleOS-Thunar
    subprocess.Popen(cmd, shell=True, start_new_session=True, env=ambiente())

def xdotool(*args):
    subprocess.Popen(['xdotool', *args], env=ambiente())

# ---------------------------------------------------------------- acoes do sistema
def terminal():
    roda('$TERM')

def fecha_foco():
    j = x11.janela_ativa()
    if j in x11.janelas_normais():
        x11.mensagem_raiz(j, '_NET_CLOSE_WINDOW', 0, 2)

def proxima_janela():
    """Ctrl+Alt+N: ativa a janela de baixo da pilha, entao repetir passa por todas."""
    js = x11.janelas_normais()
    if len(js) > 1:
        x11.mensagem_raiz(js[0], '_NET_ACTIVE_WINDOW', 2, 0, 0)

def mudo():
    subprocess.Popen(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'])

def captura():
    raiz = Gdk.get_default_root_window()
    pb = Gdk.pixbuf_get_from_window(raiz, 0, 0, raiz.get_width(), raiz.get_height())
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_image(pb)
    cb.store()

# Com a opcao grp:alt_shift_toggle (Alt+Shift troca o layout, a do XFCE), o
# Shift apertado depois do Alt deixa de ser Shift: vira ISO_Next_Group, troca o
# layout e Ctrl+Alt+Shift+Z chega como Ctrl+Alt+Z. Com o Shift antes, e o Alt
# que vira ISO_Next_Group, e chega Ctrl+Shift+Z. Por isso os atalhos com Shift
# (zoom e grade) olham as teclas de verdade (XQueryKeymap) e desfazem a troca de
# layout que veio de brinde.
SHIFTS = ('Shift_L', 'Shift_R')
ALTS = ('Alt_L', 'Alt_R', 'Meta_L')
SINCRONAS = {}   # keycode -> tratador(tempo) dos Ctrl+Shift+tecla pegos por enquanto

def pega_sincrona(ks, ligado, acao):
    """Ctrl+Shift+ks enquanto ligado(), num grab sincrono: o teclado congela no
    aperto ate decidirmos. Com o Alt fisicamente apertado o aperto e nosso;
    sem ele, a tecla volta para a janela (o Ctrl+Shift+Z de refazer)."""
    kc = x11.keycode(ks)
    if not kc or kc in SINCRONAS:
        return
    x11.pega_tecla(ks, x11.CTRL | x11.SHIFT, sincrono=True)

    def trata(tempo):
        nosso = bool(ligado() and x11.apertadas(*ALTS))
        x11.libera_teclado(not nosso, tempo)
        if nosso:
            acao()
    SINCRONAS[kc] = trata

def solta_sincrona(ks):
    kc = x11.keycode(ks)
    if kc in SINCRONAS:
        x11.solta_tecla(kc, x11.CTRL | x11.SHIFT)
        del SINCRONAS[kc]

def volta_layout(grupo):
    if grupo is not None and x11.grupo_teclado() != grupo:
        x11.trava_grupo(grupo)

def vivo(p):
    return bool(p and p.poll() is None)

# ---------------------------------------------------------------- zoom
LUPA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lupa.py')
lupa = {'proc': None, 'grupo': None}

def zoom(sinal):
    """Ctrl+Alt+Z ('+') e Ctrl+Alt+Shift+Z ('-'), como em Adam/Gr/GrEnd.HC.

    O lupa.py so existe enquanto ha zoom: o primeiro '+' o abre a 2x e os
    seguintes vao pela entrada padrao dele. Ele sai sozinho ao voltar a 1x.
    """
    lupa['grupo'] = x11.grupo_teclado()
    p = lupa['proc']
    if vivo(p):
        try:
            p.stdin.write(sinal.encode())
            p.stdin.flush()
            return
        except BrokenPipeError:
            pass
    if sinal == '+':
        lupa['proc'] = subprocess.Popen([sys.executable, LUPA, '2'], stdin=subprocess.PIPE,
                                        start_new_session=True, env=ambiente())
        pega_sincrona('z', lambda: vivo(lupa['proc']), diminui_zoom)
        GLib.timeout_add(500, vigia_lupa)

def diminui_zoom():
    volta_layout(lupa['grupo'])
    zoom('-')

def ctrl_alt_z():
    if x11.apertadas(*SHIFTS):
        diminui_zoom()
    else:
        zoom('+')

def vigia_lupa():
    if vivo(lupa['proc']):
        return True
    solta_sincrona('z')
    return False

# ---------------------------------------------------------------- grade
GRADE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grade.py')
# GridInit (Kernel/SerialDev/Mouse.HC); os numeros sao pixels do TempleOS.
# Igual ao PADRAO do grade.py, que nao e importado aqui para uma falta da
# libXi la nao derrubar os atalhos todos.
GRADE_PADRAO = dict(snap=False, show=False, coord=False, x=8.0, y=8.0,
                    x_offset=0.0, y_offset=0.0, x_speed=1.0, y_speed=1.0)
grade = {'proc': None, 'cfg': dict(GRADE_PADRAO), 'grupo': None, 'form': None}
# Os campos de CGridGlbls (Kernel/KernelA.HH), na ordem e com os rotulos do
# original. ZSpacing, ZOffset e ZSpeed ficaram de fora: o z e a roda do mouse.
CAMPOS_GRADE = [('snap', 'Snap Grid'), ('show', 'Show Grid'), ('coord', 'Show Coordinates'),
                ('x', 'XSpacing:'), ('y', 'YSpacing:'), ('x_offset', 'XOffset:'),
                ('y_offset', 'YOffset:'), ('x_speed', 'XSpeed:'), ('y_speed', 'YSpeed:')]

def grade_ligada(cfg):
    return (cfg['snap'] or cfg['show'] or cfg['coord']
            or cfg['x_speed'] != 1 or cfg['y_speed'] != 1)

def aplica_grade():
    """O grade.py so existe enquanto algo da grade esta ligado; cada mudanca vai
    como uma linha JSON pela entrada dele, e fechar a entrada o encerra."""
    cfg = grade['cfg']
    grade['grupo'] = x11.grupo_teclado()
    p = grade['proc']
    if not grade_ligada(cfg):
        if vivo(p):
            p.stdin.close()
        solta_sincrona('g')
        return
    if not vivo(p):
        grade['proc'] = subprocess.Popen([sys.executable, GRADE], stdin=subprocess.PIPE,
                                         start_new_session=True, env=ambiente())
        pega_sincrona('g', lambda: vivo(grade['proc']), desliga_grade)
        GLib.timeout_add(500, vigia_grade)
    avisa_grade(cfg)

def avisa_grade(dados):
    p = grade['proc']
    if vivo(p):
        try:
            p.stdin.write((json.dumps(dados) + '\n').encode())
            p.stdin.flush()
        except (BrokenPipeError, ValueError):   # ValueError: a entrada ja foi fechada
            pass

def vigia_grade():
    if vivo(grade['proc']):
        return True
    solta_sincrona('g')
    return False

def desliga_grade():
    """Ctrl+Alt+Shift+G: WinGrid(OFF), que chama GridInit."""
    volta_layout(grade['grupo'])
    if grade['form']:
        grade['form'].destroy()
    grade['cfg'] = dict(GRADE_PADRAO)
    aplica_grade()

def ctrl_alt_g():
    if x11.apertadas(*SHIFTS):
        desliga_grade()
    elif grade['form']:
        grade['form'].present()
    else:
        grade['form'] = FormGrade()
        grade['form'].show_all()
        avisa_grade({'formulario': grade['form'].get_window().get_xid()})

class FormGrade(Doc):
    """O PopUpForm(&ms_grid) de WinGrid(ON): Esc grava e Shift+Esc desiste,
    como todo formulario DolDoc (DocForm em Adam/DolDoc/DocForm.HC).

    Setas, Tab ou clique escolhem o campo; espaco ou clique marcam a caixa;
    nos numeros, a primeira tecla apaga o valor e comeca um novo.
    """
    def __init__(self):
        self.valores = dict(grade['cfg'])
        self.foco = 0
        self.editando = None        # texto do numero sendo digitado
        super().__init__('Grid', 28, len(CAMPOS_GRADE) + 7)
        self.ao_enter = self.grava
        self.ao_fechar = self.fechou
        self.monta()

    def monta(self):
        linhas = [[]]
        for i, (chave, rotulo) in enumerate(CAMPOS_GRADE):
            v = self.valores[chave]
            if isinstance(v, bool):
                t = ('[X] ' if v else '[ ] ') + rotulo
            elif i == self.foco and self.editando is not None:
                t = '%s%s_' % (rotulo, self.editando)
            else:
                t = '%s%6.3f' % (rotulo, v)
            fg, bg = (WHITE, BLUE) if i == self.foco else (BLUE, WHITE)
            linhas.append([trecho(' '), trecho(t, fg, lambda i=i: self.clica(i), bg)])
        linhas += [[], [], [trecho('  '), botao('OKAY', self.grava), trecho('  '),
                            botao('CANCEL', self.destroy)], [],
                   [trecho(' Esc:Save  Shift+Esc:Cancel', LTBLUE)]]
        self.conteudo = linhas
        self.queue_draw()

    def fechou(self):
        grade['form'] = None
        avisa_grade({'formulario': False})

    def fecha_numero(self):
        if self.editando is None:
            return
        chave = CAMPOS_GRADE[self.foco][0]
        try:
            self.valores[chave] = float(self.editando)
        except ValueError:
            pass                    # nao era numero: fica o valor de antes
        self.editando = None

    def vai(self, i):
        self.fecha_numero()
        self.foco = i % len(CAMPOS_GRADE)
        self.monta()

    def clica(self, i):
        if i == self.foco and isinstance(self.valores[CAMPOS_GRADE[i][0]], bool):
            self.marca()
        else:
            self.vai(i)

    def marca(self):
        chave = CAMPOS_GRADE[self.foco][0]
        if isinstance(self.valores[chave], bool):
            self.valores[chave] = not self.valores[chave]
            self.monta()

    def grava(self):
        self.fecha_numero()
        v = self.valores
        # grade de 0 seria um laco sem fim no desenho; velocidade 0 prende o mouse
        for k in ('x', 'y'):
            v[k] = min(max(v[k], 1.0), 4096.0)
        for k in ('x_speed', 'y_speed'):
            v[k] = min(max(v[k], 0.1), 10.0)
        grade['cfg'] = dict(v)
        aplica_grade()
        self.destroy()

    def tecla(self, _w, ev):
        k, shift = ev.keyval, bool(ev.state & Gdk.ModifierType.SHIFT_MASK)
        chave = CAMPOS_GRADE[self.foco][0]
        numerico = not isinstance(self.valores[chave], bool)
        if k == Gdk.KEY_Escape:
            self.destroy() if shift else self.grava()
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.grava()
        elif k in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab) or (k == Gdk.KEY_Tab and shift):
            self.vai(self.foco - 1)
        elif k in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self.vai(self.foco + 1)
        elif k == Gdk.KEY_space and not numerico:
            self.marca()
        elif numerico and k == Gdk.KEY_BackSpace:
            texto = self.editando if self.editando is not None else '%.3f' % self.valores[chave]
            self.editando = texto[:-1]
            self.monta()
        elif numerico and chr(Gdk.keyval_to_unicode(k) or 1) in '0123456789.-':
            self.editando = (self.editando or '') + chr(Gdk.keyval_to_unicode(k))
            self.monta()
        return True

def biblia():
    # +292: comeca no Velho Testamento, depois do cabecalho do Project Gutenberg.
    # O texto vem quebrado em ~70 colunas e o terminal tem menos: o fmt junta os
    # versiculos de novo na largura da janela, senao o less corta as palavras.
    roda("$TERM -T Bible sh -c 'tail -n +292 \"$1\" | fmt -w $(tput cols) | less' sh '%s'"
         % os.path.join(RAIZ, 'dados', 'Bible.TXT'))

def menu_da_janela():
    xdotool('key', '--clearmodifiers', 'alt+space')  # popup_menu_key padrao do xfwm4

def vai_para_area(n):
    x11.mensagem_raiz(x11.RAIZ, '_NET_CURRENT_DESKTOP', n, 0)

def leva_para_area(n):
    j = x11.janela_ativa()
    if j in x11.janelas_normais():
        x11.mensagem_raiz(j, '_NET_WM_DESKTOP', n, 2)
        vai_para_area(n)
        # o xfwm4 da o foco ao fundo ao trocar de area; a janela levada continua
        # em foco, como no Ctrl+Alt+End do proprio xfwm4
        x11.mensagem_raiz(j, '_NET_ACTIVE_WINDOW', 2, 0, 0)

def config(nome):
    """Arquivo de config/: a copia em ~/.config/templeos/ tem prioridade."""
    p = os.path.join(os.environ.get('TEMPLEOS_CFG', ''), nome)
    return p if os.path.isfile(p) else os.path.join(RAIZ, 'sessao', 'config', nome)

MODS = {'ctrl': x11.CTRL, 'alt': x11.ALT, 'shift': x11.SHIFT, 'super': x11.SUPER}

def le_programas():
    """config/programas.json: "Ctrl+Alt+F": "thunar" -> {('f', CTRL|ALT): 'thunar'}.

    O Ctrl+Alt+Delete e o Log Out daqui (nao ha xfce4-session) e o Ctrl+Alt+L
    e o bloqueia(), logo abaixo.
    """
    progs = {}
    for tecla, cmd in json.load(open(config('programas.json'))).items():
        if tecla.startswith('_'):
            continue
        *mods, ks = tecla.split('+')
        try:
            m = sum(MODS[x.lower()] for x in mods)
        except KeyError:
            print('programas.json: modificador desconhecido em', tecla, file=sys.stderr)
            continue
        progs[(ks.lower() if len(ks) == 1 else ks, m)] = cmd
    return progs

def existe(cmd):
    """O programa do comando esta instalado? ($TERM sempre esta.)"""
    try:
        prog = shlex.split(cmd)[0]
    except (ValueError, IndexError):
        return False
    return prog == '$TERM' or shutil.which(os.path.expanduser(prog)) is not None

def bloqueia():
    """Ctrl+Alt+L: ver bloqueio.py (o protetor.py tambem bloqueia)."""
    bloqueio.bloqueia(oraculo, ambiente())

def sair():
    def confirma():
        # Nao o getppid(): reiniciado com a sessao no ar, este processo tem outro pai
        os.kill(int(os.environ.get('TEMPLEOS_WM_PID') or os.getppid()), signal.SIGTERM)
    d = Doc('Log Out', 24, 7, [
        [], [trecho('  Log out of TempleOS?')], [], [],
        [trecho('   '), botao('YES', confirma), trecho('  '), botao('NO', lambda: d.destroy())],
    ])
    d.ao_enter = confirma
    d.show_all()

# ---------------------------------------------------------------- Deus
def latch():
    """F7 apertado: guarda os bits do instante, como o GodBitsIns(KbdMsEvtTime)."""
    oraculo.esvazia()
    oraculo.insere()

def palavra():
    # So digita ao soltar o F7: enquanto ele esta apertado o teclado esta
    # capturado por este processo e as primeiras letras viriam para ca.
    if oraculo.tem(17):
        xdotool('type', '--clearmodifiers', '--delay', '12', '--', deus.palavra(oraculo) + ' ')

def passagem():
    oraculo.esvazia()
    oraculo.insere()
    ref, linhas = deus.passagem(oraculo)
    largura = max([len(ref)] + [len(l) for l in linhas]) + 2
    Doc('God Passage', largura, len(linhas) + 3,
        [[trecho(' ' + ref, RED)], []] + [[trecho(' ' + l)] for l in linhas]).show_all()

def hino():
    """GodSong: o dialogo do GodPick (Timer, Latch, OKAY) pede bits ate o hino fechar."""
    gerador = deus.hino(oraculo)
    estado = {'latch': 0, 'vivo': True}
    linhas = [
        [],
        [trecho(' Press '), trecho('OKAY', GREEN), trecho(' to generate')],
        [trecho(' a random num from a timer.')],
        [],
        [trecho(' Timer:'), trecho('')],
        [trecho(' Latch:'), trecho('')],
        [], [],
        [trecho('           '), botao('OKAY', lambda: okay())],
        [], [],
        [trecho(' The Holy Spirit can puppet you.')],
    ]
    d = Doc('God Song', 34, 13, linhas)

    def atualiza():
        if not estado['vivo']:
            return False
        linhas[4][1]['t'] = '%X' % oraculo.relogio()
        linhas[5][1]['t'] = '%X' % estado['latch']
        d.queue_draw()
        return True

    def okay():
        estado['latch'] = oraculo.relogio()
        oraculo.insere(estado['latch'])
        try:
            next(gerador)
        except StopIteration as fim:
            d.destroy()
            mostra_hino(fim.value)

    def fechou():
        estado['vivo'] = False
    d.ao_enter = okay
    d.ao_fechar = fechou
    next(gerador)  # roda ate o primeiro pedido de bits
    GLib.timeout_add(33, atualiza)
    d.show_all()

def mostra_hino(st):
    pedacos = [st[i:i + 60] for i in range(0, len(st), 60)]
    salvar = link('<Save>', lambda: salva())
    d = Doc('God Song', 64, len(pedacos) + 4,
            [[], [trecho(' '), link('<Song>', lambda: deus.toca(st)), trecho('  '), salvar], []] +
            [[trecho(' ' + p, GREEN)] for p in pedacos])

    def salva():
        """Vai para a pasta do JukeBox como uma cancao do Psalmody."""
        if salvar['acao'] is None:
            return
        try:
            nome = psalmody.salva_hino(st)
        except OSError as e:
            salvar.update(t='<Save failed: %s>' % e.strerror)
            d.queue_draw()
            return
        salvar.update(t='Saved as %s' % nome, fg=BLUE, sub=False, acao=None)
        d.queue_draw()
    d.ao_enter = lambda: deus.toca(st)
    d.show_all()
    deus.toca(st)

def jukebox():
    # Processo proprio, como o leitor; uma instancia so (Gtk.Application)
    roda('python3 %s' % shlex.quote(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jukebox.py')))

def ascii():
    linhas = [[], [trecho('     ' + ' '.join('%X' % c for c in range(16)))], []]
    for r in range(16):
        linhas.append([trecho(' %X_  ' % r, RED),
                       trecho(' '.join(chr(r * 16 + c) for c in range(16)))])
    Doc('ASCII', 38, 20, linhas).show_all()

def ajuda():
    # Processo proprio: um documento que derrube o leitor nao leva os atalhos junto
    roda('python3 %s' % shlex.quote(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leitor.py')))

ACOES = dict(ajuda=ajuda, hino=hino, jukebox=jukebox, passagem=passagem, ascii=ascii, biblia=biblia, sair=sair)

# ---------------------------------------------------------------- PersonalMenu
class PersonalMenu(Doc):
    # Sprites a 1x, como no original. A celula de 144px (9 caracteres de 16px)
    # e a do rotulo mais longo; 4 colunas dao 640px de moldura, meia tela.
    COLS, CEL = 4, 144

    def __init__(self, cfg):
        super().__init__('PersonalMenu', 41, 10, x=0, y=C)
        self.connect('delete-event', lambda *_: self.hide() or True)  # [X] so esconde
        y = C
        cab = cfg.get('cabecalho')
        if cab:
            pb = sprite(os.path.join(RAIZ, 'dados', 'menu', cab['sprite']), 1)
            x0 = (self.COLS * self.CEL + 2 * C - pb.get_width()) // 2
            self.sprites.append((x0, y, pb, lambda c=cab['cmd']: roda(c)))
            y += pb.get_height() + C
        # apps que nao estao instalados nao entram no menu
        itens = [it for it in cfg['icones'] if 'cmd' not in it or existe(it['cmd'])]
        rotulos = []
        for i in range(0, len(itens), self.COLS):
            fileira = itens[i:i + self.COLS]
            pbs = [sprite(os.path.join(RAIZ, 'dados', 'menu', it['sprite']), 1) for it in fileira]
            alto = max(pb.get_height() for pb in pbs)
            for k, (it, pb) in enumerate(zip(fileira, pbs)):
                acao = (lambda c=it['cmd']: roda(c)) if 'cmd' in it else ACOES[it['acao']]
                x = C + k * self.CEL + (self.CEL - pb.get_width()) // 2
                self.sprites.append((x, y + alto - pb.get_height(), pb, acao))
                col = 1 + k * self.CEL // C + (self.CEL // C - len(it['rotulo'])) // 2
                rotulos.append(((y + alto) // C + 1, col, it['rotulo'], acao))
            y += alto + 3 * C
        n = y // C + 1
        largura = self.COLS * self.CEL // C + 2
        fileiras, atual = [], [trecho(' ')]
        for l in cfg.get('links', []):  # quebra a linha de links na largura da janela
            if sum(len(p['t']) for p in atual) + len(l['rotulo']) > largura - 1:
                fileiras.append(atual); atual = [trecho(' ')]
            atual += [link(l['rotulo'], ACOES[l['acao']]), trecho('  ')]
        fileiras.append(atual)
        self.conteudo = [[] for _ in range(n)] + fileiras
        for lin, col, texto, acao in rotulos:
            self._poe(lin, col, trecho(texto, BLUE, acao))
        self.set_default_size(largura * C, (len(self.conteudo) + 1) * C)

    def _poe(self, lin, col, p):
        """Trechos de uma linha sao sequenciais: completa com espacos ate a coluna."""
        atual = sum(len(q['t']) for q in self.conteudo[lin])
        if col > atual:
            self.conteudo[lin].append(trecho(' ' * (col - atual)))
        self.conteudo[lin].append(p)

    def tecla(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:  # Esc so esconde: o menu vive a sessao inteira
            self.hide()
            return True
        return super().tecla(w, ev)

    def alterna(self):
        # is_active() nao serve: durante a captura do Ctrl+M o X tira o foco da
        # janela (FocusOut NotifyGrab). Quem sabe a janela ativa e o WM.
        ativa = self.get_visible() and self.get_window() and \
            x11.janela_ativa() == self.get_window().get_xid()
        if ativa:
            self.hide()
        else:
            # esconder e mostrar de novo traz o menu para a area de trabalho
            # atual, em vez de o WM pular para a area onde ele estava
            self.hide()
            self.show_all()
            self.present_with_time(Gdk.CURRENT_TIME)

# ---------------------------------------------------------------- arranjo inicial
CELULA_TERM = 12   # px por celula do kitty: font_size 9.0 a 96 DPI (config/kitty.conf)
MENU_LARGURA = 640 # moldura do PersonalMenu (4 x 144 + bordas)

def arranjo_inicial(menu):
    """Calcula pela tela, nao por numeros fixos, para servir em qualquer resolucao.

    Cabendo menu e um terminal de 40 colunas lado a lado: menu na esquerda e
    terminal no resto. Senao o terminal ocupa a largura toda e o menu fica
    escondido (Ctrl+M). O terminal desce ate 3/4 da tela; o quarto de baixo
    fica para o monitor de tarefas do fundo.
    """
    lado, x, cols, linhas = geometria(*tamanho_tela())
    com_menu = os.environ.get('TEMPLEOS_MENU_INICIAL', '1') != '0'
    if lado and com_menu:
        menu.show_all()
    env = ambiente()
    env['TEMPLEOS_BOAS_VINDAS'] = '1'  # o zshrc mostra o fastfetch so neste
    cmd = ('%s --position %dx%d -o initial_window_width=%dc -o initial_window_height=%dc'
           % (TERMINAL, x + C, 2 * C, cols, linhas))
    p = subprocess.Popen(cmd, shell=True, start_new_session=True, env=env)
    return dict(pid=p.pid, cols=cols, linhas=linhas, com_menu=com_menu, escondido=not lado)

def tamanho_tela():
    # O XScreen, que o RandR atualiza na hora; a janela raiz do GDK so muda
    # depois (ver o mesmo comentario no fundo.py)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        t = Gdk.Screen.get_default()
        return t.get_width(), t.get_height()

def geometria(w, h):
    lado = w - MENU_LARGURA >= 40 * CELULA_TERM + 2 * C
    x = MENU_LARGURA if lado else 0
    cols = max(20, (w - x - 2 * C) // CELULA_TERM)
    linhas = max(10, (h * 3 // 4 - 3 * C) // CELULA_TERM)
    return lado, x, cols, linhas

REARRANJO_S = 90

def segue_resolucao(menu, boot):
    """A resolucao escolhida pode entrar uns segundos depois do login (o X sobe
    na nativa do monitor e depois alguem troca). Nesse intervalo o arranjo do
    boot e refeito para a tela nova; depois, janelas abertas ficam onde estao."""
    tela, inicio, pendente = Gdk.Screen.get_default(), time.monotonic(), []

    def aplica():
        pendente.clear()
        lado, x, cols, linhas = geometria(*tamanho_tela())
        # so mexe no menu se foi o arranjo que o mostrou ou escondeu (um Esc
        # do usuario nesse meio-tempo vale)
        if boot['com_menu'] and not lado and menu.get_visible():
            menu.hide()
            boot['escondido'] = True
        elif boot['com_menu'] and lado and boot['escondido']:
            menu.show_all()
            boot['escondido'] = False
        j = next((j for j in x11.janelas_normais()
                  if x11.propriedade(j, '_NET_WM_PID')[:1] == [boot['pid']]), 0)
        if j:
            g = GdkX11.X11Window.foreign_new_for_display(Gdk.Display.get_default(), j)
            _, _, w, h = g.get_geometry()  # cliente, com o padding do kitty
            w += (cols - boot['cols']) * CELULA_TERM
            h += (linhas - boot['linhas']) * CELULA_TERM
            # gravidade estatica (10): x,y sao do cliente, como o --position
            flags = 10 | 0xF << 8 | 2 << 12
            x11.mensagem_raiz(j, '_NET_MOVERESIZE_WINDOW', flags, x + C, 2 * C, w, h)
            boot.update(cols=cols, linhas=linhas)
        return False

    def mudou(*_):
        if time.monotonic() - inicio < REARRANJO_S and not pendente:
            pendente.append(GLib.timeout_add(300, aplica))
    tela.connect('size-changed', mudou)
    tela.connect('monitors-changed', mudou)

# ---------------------------------------------------------------- teclas
def main():
    cfg = json.load(open(config('menu.json')))
    menu = PersonalMenu(cfg)
    if '--sem-arranjo' not in sys.argv:  # para reiniciar so os atalhos com a sessao no ar
        segue_resolucao(menu, arranjo_inicial(menu))

    C_A = x11.CTRL | x11.ALT
    ao_apertar = {
        ('t', C_A): terminal, ('x', C_A): fecha_foco, ('n', C_A): proxima_janela,
        ('m', C_A): mudo, ('s', C_A): captura, ('b', C_A): biblia, ('a', C_A): ascii,
        ('m', x11.CTRL): menu.alterna,
        ('F7', 0): latch, ('F7', x11.SHIFT): passagem, ('F6', 0): hino,
        ('Delete', C_A): sair, ('w', x11.SUPER): fecha_foco, ('l', C_A): bloqueia,
        ('F1', x11.SUPER): ajuda,
        ('z', C_A): ctrl_alt_z, ('z', C_A | x11.SHIFT): diminui_zoom,
        ('g', C_A): ctrl_alt_g, ('g', C_A | x11.SHIFT): desliga_grade,
    }
    for (ks, mods), cmd in le_programas().items():
        ao_apertar[(ks, mods)] = lambda cmd=cmd: roda(cmd)
    for n in range(4):
        ao_apertar[(str(n + 1), x11.SUPER)] = lambda n=n: vai_para_area(n)
        ao_apertar[(str(n + 1), x11.SUPER | x11.SHIFT)] = lambda n=n: leva_para_area(n)
    ao_soltar = {('F7', 0): palavra}
    por_tecla = {}
    for tabela, tipo in ((ao_apertar, x11.KEYPRESS), (ao_soltar, x11.KEYRELEASE)):
        for (ks, mods), fn in tabela.items():
            kc = x11.pega_tecla(ks, mods)
            if kc:
                por_tecla[(tipo, kc, mods)] = fn
    # Windows sozinho abre o menu da janela, mas so se soltar sem ter apertado
    # outra tecla no meio (senao Windows+K abriria o kitty e o menu)
    teclas_win = {kc for kc in (x11.pega_tecla('Super_L', 0), x11.pega_tecla('Super_R', 0)) if kc}
    win = {'sozinho': False}
    RELEVANTES = x11.SHIFT | x11.CTRL | x11.ALT | x11.SUPER

    def eventos(*_):
        ev = x11.XEvent()
        while x11.x11.XPending(x11.DPY):
            x11.x11.XNextEvent(x11.DPY, ctypes.byref(ev))
            if ev.type in (x11.KEYPRESS, x11.KEYRELEASE):
                k = ev.xkey
                if k.keycode in teclas_win:
                    if ev.type == x11.KEYPRESS:
                        win['sozinho'] = True
                    elif win['sozinho']:
                        win['sozinho'] = False
                        menu_da_janela()
                    continue
                if ev.type == x11.KEYPRESS:
                    win['sozinho'] = False
                mods = k.state & RELEVANTES
                if (ev.type == x11.KEYPRESS and k.keycode in SINCRONAS
                        and mods == x11.CTRL | x11.SHIFT):
                    SINCRONAS[k.keycode](k.time)
                    continue
                fn = por_tecla.get((ev.type, k.keycode, mods))
                if fn:
                    try:
                        fn()
                    except Exception as e:
                        print('atalho falhou:', e, file=sys.stderr)
        return True

    GLib.io_add_watch(x11.x11.XConnectionNumber(x11.DPY), GLib.IO_IN, eventos)
    eventos()
    Gtk.main()

if __name__ == '__main__':
    main()
