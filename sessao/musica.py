"""O Play() do TempleOS (Adam/ASnd.HC) e o alto-falante do PC.

No original o estado da musica (oitava, duracao, tempo, staccato) fica em
`music`, uma variavel global, e sobrevive de um Play() para o outro: um Play
que comeca em "eB" toca colcheia na oitava que o anterior deixou. Por isso
aqui o estado e um objeto, `Musica`, que a cancao inteira compartilha.

A letra vai junto: Play(notas, palavras) separa as palavras por \\0 e escreve
a palavra i quando a nota i comeca (LstSub). O `Tocador` manda o som para o
PipeWire/PulseAudio e entrega cada palavra no instante em que a nota soa.
"""
import array, queue, subprocess, threading, time

TAXA = 44100
MAPA = [0, 2, 3, 5, 7, 8, 10]   # music.note_map: A B C D E F G em semitons a partir do A

class Musica:
    """CMusicGlbls. reinicia() e o MusicSettingsRst."""
    def __init__(self):
        self.reinicia()

    def reinicia(self):
        self.oitava, self.dur, self.tempo, self.staccato = 4, 1.0, 2.5, 0.9

    def notas(self, st):
        """(frequencia, ligada_s, desligada_s, ligadura) de cada nota da string.

        Mesma ordem do laco do Play(): ligadura '(', compasso 'M', oitava,
        duracao; depois a letra da nota, bemol/sustenido. Letra fora de A-G
        (o 'R' dos Psalmody) e pausa: ona 0, sem som.
        """
        i, r = 0, []
        while i < len(st):
            liga = False
            while True:
                antes = i
                if st[i] == '(':
                    liga = True; i += 1
                else:
                    while i < len(st) and st[i] == 'M':
                        i += 1
                        while i < len(st) and (st[i].isdigit() or st[i] == '/'):
                            i += 1
                    while i < len(st) and st[i].isdigit():
                        self.oitava = int(st[i]); i += 1
                    while i < len(st) and st[i] in 'whqest.':
                        self.dur = {'w': 4.0, 'h': 2.0, 'q': 1.0, 'e': 0.5, 's': 0.25,
                                    't': 2.0 * self.dur / 3.0, '.': 1.5 * self.dur}[st[i]]
                        i += 1
                if i == antes or i >= len(st):
                    break
            if i >= len(st):
                break
            n = ord(st[i]) - ord('A'); i += 1
            ona = 0
            if 0 <= n < 7:
                n, o = MAPA[n], self.oitava
                if i < len(st) and st[i] == 'b':
                    n -= 1; i += 1
                    if n == 2: o -= 1
                elif i < len(st) and st[i] == '#':
                    n += 1; i += 1
                    if n == 3: o += 1
                ona = (o + 1) * 12 + n if n < 3 else o * 12 + n   # Note2Ona
            d = self.dur / self.tempo
            r.append((frequencia(ona), d * self.staccato, d * (1 - self.staccato), liga))
        return r

def frequencia(ona):
    """Ona2Freq: ona 60 e o La de 440 Hz; 0 e silencio."""
    return 440.0 / 32 * 2 ** (ona / 12.0) if ona else 0.0

class Onda:
    """Onda quadrada continua, como o Snd() programando o PIT do alto-falante.

    A fase passa de uma nota para a outra; com a ligadura a nota segue soando
    no tempo em que estaria desligada.
    """
    def __init__(self, volume=0.12):
        self.a = int(32767 * volume)
        self.fase = 0.0

    def amostras(self, freq, segundos):
        n = int(segundos * TAXA)
        if not freq or n <= 0:
            return bytes(2 * max(n, 0))
        passo, f0, a = freq / TAXA, self.fase, self.a
        buf = array.array('h', (a if (f0 + k * passo) % 1.0 < 0.5 else -a for k in range(n)))
        self.fase = (f0 + n * passo) % 1.0
        return buf.tobytes()

def onda(st, volume=0.12):
    """A string inteira de uma vez, com o estado inicial do MusicSettingsRst."""
    m, o, r = Musica(), Onda(volume), bytearray()
    for freq, on, off, liga in m.notas(st):
        r += o.amostras(freq, on)
        r += o.amostras(freq if liga else 0, off)
    return bytes(r)

def toca(st):
    """Toca em segundo plano e esquece (God Song, bipes)."""
    def tarefa():
        try:
            p = subprocess.Popen(['paplay', '--raw', '--format=s16le', '--rate=%d' % TAXA,
                                  '--channels=1'], stdin=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
            p.communicate(onda(st))
        except OSError:
            pass
    threading.Thread(target=tarefa, daemon=True).start()

def bipe():
    """Beep do original: Snd(62) por meio segundo."""
    toca_freq(frequencia(62), 0.5)

def toca_freq(freq, segundos):
    def tarefa():
        try:
            p = subprocess.Popen(['paplay', '--raw', '--format=s16le', '--rate=%d' % TAXA,
                                  '--channels=1'], stdin=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
            p.communicate(Onda().amostras(freq, segundos))
        except OSError:
            pass
    threading.Thread(target=tarefa, daemon=True).start()

class Tocador:
    """Toca um programa de cancao e entrega os eventos (palavras etc.) na hora certa.

    `programa` e um iteravel de operacoes (ver psalmody.Cancao.operacoes): pode
    ser infinito, como o `while (!ScanKey)` das cancoes. Uma thread gera o som
    nota a nota e escreve no pacat, nunca mais que ADIANTE segundos a frente do
    relogio, para que parar seja imediato e a letra nao se adiante ao som. Cada
    evento entra numa fila com a hora em que deve aparecer; quem desenha chama
    `prontos()` de tempos em tempos.
    """
    ADIANTE = 0.12   # quanto som fica escrito a frente do relogio
    LATENCIA = 0.05  # --latency-msec do pacat: o que se escreve agora soa daqui a isso
    BLOCO = 441      # 10 ms por escrita

    def __init__(self, programa, volume=0.12):
        self.programa = programa
        self.onda = Onda(volume)
        self.musica = Musica()
        self.eventos = queue.Queue()
        self.parado = threading.Event()
        try:
            self.saida = subprocess.Popen(
                ['pacat', '--playback', '--raw', '--format=s16le', '--rate=%d' % TAXA,
                 '--channels=1', '--latency-msec=%d' % (self.LATENCIA * 1000),
                 '--client-name=JukeBox', '--stream-name=Psalmody'],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.saida = None  # sem pacat a letra corre sozinha, no mesmo tempo
        self.t0 = None
        self.amostra = 0
        self.thread = threading.Thread(target=self._roda, daemon=True)
        self.thread.start()

    def para(self):
        self.parado.set()
        if self.saida:
            try:
                self.saida.kill()
            except OSError:
                pass

    def _larga_saida(self):
        p, self.saida = self.saida, None
        if p:
            try:
                p.stdin.close()
            except OSError:
                pass
            p.wait()

    def prontos(self):
        """Eventos cuja hora ja chegou, em ordem."""
        r, agora = [], time.monotonic()
        while True:
            try:
                ev = self.eventos.queue[0]
            except IndexError:
                break
            if ev[0] > agora:
                break
            r.append(self.eventos.get_nowait()[1:])
        return r

    def _hora(self):
        return self.t0 + self.amostra / TAXA + self.LATENCIA

    def _evento(self, *ev):
        self.eventos.put((self._hora(),) + ev)

    def _escreve(self, dados):
        for i in range(0, len(dados), 2 * self.BLOCO):
            if self.parado.is_set():
                return
            espera = self.t0 + self.amostra / TAXA - self.ADIANTE - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            bloco = dados[i:i + 2 * self.BLOCO]
            if self.saida:
                try:
                    self.saida.stdin.write(bloco)
                    self.saida.stdin.flush()
                except (ValueError, OSError):   # pacat morreu ou nao achou o servidor
                    self._larga_saida()
            self.amostra += len(bloco) // 2

    def _roda(self):
        self.t0 = time.monotonic()
        try:
            for op in self.programa:
                if self.parado.is_set():
                    break
                tipo = op[0]
                if tipo == 'play':
                    _, st, palavras = op
                    for i, (freq, on, off, liga) in enumerate(self.musica.notas(st)):
                        if self.parado.is_set():
                            break
                        if palavras and i < len(palavras) and palavras[i]:
                            self._evento('texto', palavras[i])
                        self._escreve(self.onda.amostras(freq, on))
                        self._escreve(self.onda.amostras(freq if liga else 0, off))
                elif tipo == 'reinicia':
                    self.musica.reinicia()
                elif tipo == 'tempo':
                    self.musica.tempo = op[1]
                elif tipo == 'staccato':
                    self.musica.staccato = op[1]
                else:  # texto, cores, premio: so para quem desenha
                    self._evento(*op)
        finally:
            self._evento('fim')
            self._larga_saida()
