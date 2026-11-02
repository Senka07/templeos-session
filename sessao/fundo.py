#!/usr/bin/env python3
"""Fundo da sessao TempleOS: o WallPaper() de Adam/WallPaper.HC, com dados do Linux.

Duas janelas:
  topo   linha de status (tipo DOCK, reserva a primeira linha de texto da tela):
         dia, data, hora, FPS, memoria livre, carga por CPU e a ultima tecla,
         redesenhada a ~30 quadros por segundo como o WinMgr do original.
  fundo  janela tipo DESKTOP azul com o monitor de tarefas por CPU no rodape e
         o botao "Term" piscando no canto inferior direito (clique abre um terminal).

Correspondencias com o original (as colunas e os formatos sao os mesmos):
  Data_Heap / Code_Heap   RAM usada/total, swap usada/total (bytes, hex)
  Lines                   processos criados desde o boot (/proc/stat)
  Reads / Writes          operacoes de disco concluidas (/proc/diskstats)
  ProgressBars            loadavg de 1, 5 e 15 min (x100) e processos rodando
  linha de tarefa         comm, #PID, pilha (VmStk), RSS/VmSize, flags:threads:flags
  linha amarela           wchan das ate 4 primeiras threads (onde o kernel as parou)
  ContextSwaps/s          fatias de tempo por segundo da CPU (/proc/schedstat)

Variaveis: TEMPLEOS_TERM (comando do terminal, padrao kitty),
TEMPLEOS_TECLA=0 para nao mostrar a ultima tecla no topo.
"""
import ctypes, glob, os, subprocess, sys, time, warnings
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, GLib
import cairo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x11
from texto import C, RAIZ, BLUE, BROWN, WHITE, YELLOW, rgb, escreve

TERMINAL = os.environ.get('TEMPLEOS_TERM', 'kitty')
MOSTRA_TECLA = os.environ.get('TEMPLEOS_TECLA', '1') != '0'
TAREFAS_POR_CPU = 2
NCPU = os.cpu_count() or 1
DIAS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# ---------------------------------------------------------------- X11
def reserva_topo(gdkwin, altura, largura):
    """_NET_WM_STRUT(_PARTIAL) no topo: janelas maximizadas comecam abaixo da linha de status."""
    xid = gdkwin.get_xid()
    x11.define_cardinais(xid, '_NET_WM_STRUT_PARTIAL', [0, 0, altura, 0, 0, 0, 0, 0, 0, largura - 1, 0, 0])
    x11.define_cardinais(xid, '_NET_WM_STRUT', [0, 0, altura, 0])

# Nomes como ScanCode2KeyName() (Kernel/SerialDev/Keyboard.HC): modificadores
# colados na frente ("CTRLALTt") e a tecla sem shift.
MODS = {'Control_L': 'CTRL', 'Control_R': 'CTRL', 'Alt_L': 'ALT', 'Alt_R': 'ALT',
        'ISO_Level3_Shift': 'ALT', 'Shift_L': 'SHIFT', 'Shift_R': 'SHIFT'}
ESPECIAIS = {'Return': 'ENTER', 'KP_Enter': 'ENTER', 'BackSpace': 'BACK', 'Tab': 'TAB',
             'Escape': 'ESC', 'space': 'SPACE', 'Caps_Lock': 'CAPS', 'Num_Lock': 'NUM',
             'Scroll_Lock': 'SCROLL', 'Up': 'UP', 'Down': 'DOWN', 'Left': 'LEFT',
             'Right': 'RIGHT', 'Prior': 'PAGE_UP', 'Next': 'PAGE_DOWN', 'Home': 'HOME',
             'End': 'END', 'Insert': 'INS', 'Delete': 'DELETE', 'Super_L': 'WINDOWS',
             'Super_R': 'WINDOWS', 'Print': 'PRTSCRN1'}

class Teclado:
    def __init__(self):
        self.antes = bytes(32)
        self.nome = ''

    def atualiza(self):
        buf = (ctypes.c_char * 32)()
        x11.x11.XQueryKeymap(x11.DPY, buf)
        agora = bytes(buf)
        if agora == self.antes:
            return
        presos = [i * 8 + b for i in range(32) for b in range(8) if agora[i] >> b & 1]
        novos = [kc for kc in presos if not self.antes[kc // 8] >> (kc % 8) & 1]
        self.antes = agora
        if not novos:
            return
        nomes = [x11.keysym_nome(kc) for kc in presos]
        mods = ''.join(m for m in ('CTRL', 'ALT', 'SHIFT') if m in {MODS.get(n) for n in nomes})
        tecla = x11.keysym_nome(novos[-1])
        if tecla in MODS:
            tecla = ''
        elif tecla in ESPECIAIS:
            tecla = ESPECIAIS[tecla]
        elif len(tecla) > 1 and not tecla.startswith('F'):
            tecla = tecla.upper()
        self.nome = (mods + tecla)[-18:]

# ---------------------------------------------------------------- leituras do /proc
def le(caminho):
    try:
        with open(caminho) as f:
            return f.read()
    except OSError:
        return ''

def meminfo():
    m = {}
    for linha in le('/proc/meminfo').splitlines():
        k, v = linha.split(':', 1)
        m[k] = int(v.split()[0]) * 1024
    return m

def tempos_cpu():
    """{cpu: (ocupado, total)} em jiffies."""
    r = {}
    for linha in le('/proc/stat').splitlines():
        if linha.startswith('cpu') and linha[3].isdigit():
            p = linha.split()
            v = list(map(int, p[1:]))
            ocioso = v[3] + v[4]
            r[int(p[0][3:])] = (sum(v) - ocioso, sum(v))
    return r

def fatias_cpu():
    r = {}
    for linha in le('/proc/schedstat').splitlines():
        if linha.startswith('cpu'):
            p = linha.split()
            r[int(p[0][3:])] = int(p[9]) if len(p) > 9 else 0
    return r

def disco():
    """Leituras e escritas concluidas, somando so os discos inteiros (sem particoes)."""
    discos = {d for d in os.listdir('/sys/block') if not d.startswith(('loop', 'ram', 'zram', 'dm-'))}
    lidas = escritas = 0
    for linha in le('/proc/diskstats').splitlines():
        p = linha.split()
        if len(p) > 7 and p[2] in discos:
            lidas += int(p[3]); escritas += int(p[7])
    return lidas, escritas

def processos():
    """{pid: dict} com o que a linha de tarefa precisa."""
    r = {}
    for d in glob.glob('/proc/[0-9]*'):
        s = le(d + '/stat')
        if not s:
            continue
        i = s.rfind(')')
        comm = s[s.find('(') + 1:i]
        c = s[i + 2:].split()
        try:
            r[int(d[6:])] = dict(comm=comm, flags=int(c[6]), cpu_t=int(c[11]) + int(c[12]),
                                 threads=int(c[17]), vsize=int(c[20]), rss=int(c[21]) * 4096,
                                 cpu=int(c[36]))
        except (IndexError, ValueError):
            pass
    return r

def wchans(pid):
    r = []
    for t in sorted(glob.glob('/proc/%d/task/*' % pid), key=lambda p: int(p.rsplit('/', 1)[1]))[:4]:
        w = le(t + '/wchan').strip()
        r.append(('&' + w)[:18] if w and w != '0' else '')
    return r

def pilha(pid):
    for linha in le('/proc/%d/status' % pid).splitlines():
        if linha.startswith('VmStk:'):
            return int(linha.split()[1]) * 1024
    return 0

# ---------------------------------------------------------------- estado compartilhado
class Estado:
    def __init__(self):
        self.cpu_antes, self.cpu_carga = tempos_cpu(), {i: 0 for i in range(NCPU)}
        self.fatias_antes, self.fatias_t = fatias_cpu(), time.monotonic()
        self.proc_antes = processos()
        self.linhas = []

    def amostra_cpu(self):
        agora = tempos_cpu()
        for i, (oc, tot) in agora.items():
            oc0, tot0 = self.cpu_antes.get(i, (oc, tot))
            self.cpu_carga[i] = min(99, round(100 * (oc - oc0) / (tot - tot0))) if tot > tot0 else 0
        self.cpu_antes = agora
        return True

    def amostra_tarefas(self):
        """Monta as linhas do rodape, de baixo para cima, como WallPaper()."""
        m = meminfo()
        lidas, escritas = disco()
        stat = dict(l.split(None, 1) for l in le('/proc/stat').splitlines() if ' ' in l)
        load = le('/proc/loadavg').split()
        rodando = int(load[3].split('/')[0]) if len(load) > 3 else 0
        L = []  # (cor, texto), de baixo para cima
        L.append((YELLOW, '%010X/%010X%010X/%010X%12d%12d%12d' % (
            m['MemTotal'] - m['MemAvailable'], m['MemTotal'],
            m['SwapTotal'] - m['SwapFree'], m['SwapTotal'],
            int(stat.get('processes', '0')), lidas, escritas)))
        L.append((WHITE, '______Data_Heap____________Code_Heap______'
                         '___Lines______Reads_____Writes___'))
        L.append((WHITE, 'ProgressBars:%016X %016X %016X %016X' % (
            *(int(float(x) * 100) for x in load[:3]), rodando)))
        agora = processos()
        fatias, t = fatias_cpu(), time.monotonic()
        dt = max(t - self.fatias_t, 1e-3)
        for cpu in range(NCPU):
            daqui = [(p['cpu_t'] - self.proc_antes.get(pid, p)['cpu_t'], p['rss'], pid, p)
                     for pid, p in agora.items() if p['cpu'] == cpu]
            daqui.sort(reverse=True)
            for _, _, pid, p in daqui[:TAREFAS_POR_CPU]:
                L.append((YELLOW, '%-18s %-18s %-18s %-18s' % tuple((wchans(pid) + [''] * 4)[:4])))
                L.append((BROWN, '%-18s #%08X%010X %010X/%010X %04X:%02X:%08X' % (
                    p['comm'][:18], pid, pilha(pid), p['rss'], p['vsize'],
                    p['flags'] & 0xFFFF, min(p['threads'], 255), p['flags'])))
            por_s = int((fatias.get(cpu, 0) - self.fatias_antes.get(cpu, 0)) / dt)
            L.append((WHITE, 'CPU%02X %2d%% ContextSwaps/s:%9s' % (
                cpu, self.cpu_carga.get(cpu, 0), '{:,}'.format(por_s))))
        L.append((WHITE, '___Description____#__Task__UnusedStk__UsedMem__/_AllocMem_'
                         '______Flags_____'))
        self.proc_antes, self.fatias_antes, self.fatias_t = agora, fatias, t
        self.linhas = L
        return True

# ---------------------------------------------------------------- janelas
class Topo(Gtk.Window):
    def __init__(self, estado, largura):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.estado = estado
        self.teclado = Teclado()
        self.quadros, self.fps, self.seg = 0, 0, int(time.monotonic())
        self.livre = meminfo().get('MemAvailable', 0)
        self.set_title('TempleOS topo')
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.stick()
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self.clique)
        self.connect('draw', self.desenha)
        self.connect('realize', lambda w: reserva_topo(w.get_window(), C, self.largura))
        self.ajusta(largura)
        GLib.timeout_add(33, self.quadro)

    def ajusta(self, largura):
        """Linha de status na largura da tela; chamado de novo quando a resolucao muda."""
        self.largura, self.cols = largura, largura // C
        self.set_default_size(largura, C)
        self.resize(largura, C)
        self.move(0, 0)
        if self.get_realized():
            reserva_topo(self.get_window(), C, largura)

    # Areas de trabalho como unidades (C:, D:...), depois da carga das CPUs.
    # Nao existem no original; a atual vai invertida e um clique troca.
    def col_areas(self):
        return 44 + NCPU * 2 + 1

    def areas(self):
        n = (x11.propriedade(x11.RAIZ, '_NET_NUMBER_OF_DESKTOPS') or [1])[0]
        atual = (x11.propriedade(x11.RAIZ, '_NET_CURRENT_DESKTOP') or [0])[0]
        return n, atual

    def clique(self, _w, ev):
        n, _ = self.areas()
        i = int(ev.x // C) - self.col_areas()
        if ev.button == 1 and i >= 0 and i % 2 == 0 and i // 2 < n:
            x11.mensagem_raiz(x11.RAIZ, '_NET_CURRENT_DESKTOP', i // 2, 0)
        return True

    def quadro(self):
        if MOSTRA_TECLA:
            self.teclado.atualiza()
        self.queue_draw()
        return True

    def desenha(self, _w, cr):
        s = int(time.monotonic())
        if s != self.seg:  # a cada segundo, como o original faz a cada 32 quadros
            self.fps, self.quadros, self.seg = self.quadros, 0, s
            self.livre = meminfo().get('MemAvailable', 0)
        self.quadros += 1
        cr.set_source_rgb(*rgb(BLUE)); cr.paint()
        t = time.localtime()
        escreve(cr, 0, 0, '%s %02d/%02d %02d:%02d:%02d FPS:%2d Mem:%010X CPU' % (
            DIAS[t.tm_wday], t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec,
            min(self.fps, 99), self.livre), WHITE, BLUE)
        for i in range(NCPU):
            escreve(cr, 44 + i * 2, 0, '%2d' % self.estado.cpu_carga.get(i, 0),
                    WHITE if i & 1 else YELLOW, BLUE)
        n, atual = self.areas()
        livre = self.col_areas()  # primeira coluna depois da carga das CPUs/areas
        if n > 1:
            for i in range(n):
                escreve(cr, self.col_areas() + 2 * i, 0, chr(ord('C') + i),
                        *((BLUE, WHITE) if i == atual else (WHITE, BLUE)))
            livre += 2 * n
        if MOSTRA_TECLA:
            # 18 colunas encostadas na direita, como no original; em tela estreita
            # encolhe para nao escrever por cima da carga das CPUs e das areas
            largura = min(18, self.cols - livre)
            if largura > 0:
                escreve(cr, self.cols - largura, 0,
                        self.teclado.nome[-largura:].rjust(largura), YELLOW, BLUE)
        return True

class Fundo(Gtk.Window):
    def __init__(self, estado, largura, altura):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.estado, self.altura = estado, altura
        self.set_title('TempleOS fundo')
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.stick()
        self.term = cairo.ImageSurface.create_from_png(os.path.join(RAIZ, 'dados', 'term.png'))
        self.piscando = False
        self.ajusta(largura, altura)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self.clique)
        self.connect('draw', self.desenha)
        GLib.timeout_add(50, self.pisca)
        GLib.timeout_add(1000, lambda: (self.estado.amostra_tarefas(), self.queue_draw())[0])

    def ajusta(self, largura, altura):
        """Ocupa a tela inteira; chamado de novo quando a resolucao muda."""
        self.altura = altura
        tw, th = self.term.get_width(), self.term.get_height()
        self.botao = (largura - tw, altura - th, tw, th)
        self.set_default_size(largura, altura)
        self.resize(largura, altura)
        self.move(0, 0)
        self.queue_draw()

    def pisca(self):
        # Blink() de Kernel/KMisc.HC: alterna a 2,5 Hz
        p = int(time.monotonic() * 2 * 2.5) & 1 == 1
        if p != self.piscando:
            self.piscando = p
            self.queue_draw_area(*self.botao)
        return True

    def clique(self, _w, ev):
        x, y, w, h = self.botao
        if ev.button == 1 and x <= ev.x < x + w and y <= ev.y < y + h:
            env = dict(os.environ)
            env.pop('GTK_THEME', None)  # o tema TempleOS e so dos processos da sessao
            subprocess.Popen(TERMINAL, shell=True, start_new_session=True, env=env)
        return True

    def desenha(self, _w, cr):
        cr.set_source_rgb(*rgb(BLUE)); cr.paint()
        lin = self.altura // C - 1
        for cor, s in self.estado.linhas:
            if lin < 1:
                break
            escreve(cr, 0, lin, s, cor, BLUE)
            lin -= 1
        if self.piscando:
            cr.set_source_surface(self.term, self.botao[0], self.botao[1])
            cr.paint()
        return True

def main():
    raiz = Gdk.get_default_root_window()
    # ninguem mais poe cursor na raiz (o fundo e o topo herdam dela); sem isto
    # fica o X padrao do servidor
    raiz.set_cursor(Gdk.Cursor.new_from_name(raiz.get_display(), 'default'))
    largura, altura = raiz.get_width(), raiz.get_height()
    estado = Estado()
    GLib.timeout_add(500, estado.amostra_cpu)
    estado.amostra_tarefas()
    fundo, topo = Fundo(estado, largura, altura), Topo(estado, largura)
    fundo.show_all()
    topo.show_all()

    tela = Gdk.Screen.get_default()
    pendente = []

    def aplica():
        # Tamanho pelo XScreen (o RandR ja atualizou), nao pela janela raiz do
        # GDK: ela so muda com o ConfigureNotify da raiz, que chega depois do
        # RRScreenChangeNotify que dispara o size-changed -- lida ali, ainda
        # tinha o tamanho velho e o fundo ficava em 1920x1080 numa tela 1280x1024.
        with warnings.catch_warnings():  # get_width/height: obsoletos, mas sao o XScreen
            warnings.simplefilter('ignore')
            largura, altura = tela.get_width(), tela.get_height()
        if (largura, altura) != (fundo.get_size()[0], fundo.altura):
            fundo.ajusta(largura, altura)
        if largura != topo.largura:
            topo.ajusta(largura)
        pendente.clear()
        return False

    def mudou(*_):
        # xrandr, outro monitor, troca de resolucao: o X avisa e as duas
        # janelas voltam a cobrir a tela (a moldura e o resto nao dependem disso).
        # Espera os eventos da troca assentarem e le uma vez so.
        if not pendente:
            pendente.append(GLib.timeout_add(300, aplica))
    tela.connect('size-changed', mudou)
    tela.connect('monitors-changed', mudou)
    # e uma conferencia lenta, para o caso de algum aviso se perder
    GLib.timeout_add_seconds(5, lambda: (mudou(), True)[1])
    Gtk.main()

if __name__ == '__main__':
    main()
