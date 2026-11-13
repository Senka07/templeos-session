"""As teclas de Deus do TempleOS, portadas de Adam/God/ e Adam/ASnd.HC.

O oraculo do original: cada evento de teclado ou mouse guarda o instante em que
aconteceu (KbdMsEvtTime, em ciclos de CPU). Os bits baixos desse instante,
descontados os GOD_BAD_BITS mais finos, entram numa fila; GodBits(n) tira n bits
dela. Quando falta bit, o original abre o dialogo "Timer/Latch/OKAY" e usa o
instante do clique. Aqui o relogio e o perf_counter_ns() no momento em que a
tecla chega.

  F7        GodWord: uma palavra do Vocab.DD (17 bits)
  Shift+F7  GodBiblePassage: 20 linhas da Biblia a partir de uma linha (21 bits)
  F6        GodSong: dois compassos x2 + dois compassos x2, notacao do Play()
"""
import os, time
from collections import deque
from musica import Musica

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOD_BAD_BITS, GOD_GOOD_BITS = 4, 24

class Oraculo:
    def __init__(self):
        self.fila = deque()

    @staticmethod
    def relogio():
        return time.perf_counter_ns() >> GOD_BAD_BITS

    def insere(self, n=None, bits=GOD_GOOD_BITS):
        """GodBitsIns: o bit menos significativo entra primeiro."""
        n = self.relogio() if n is None else n
        for _ in range(bits):
            self.fila.append(n & 1)
            n >>= 1

    def tem(self, n):
        return len(self.fila) >= n

    def bits(self, n):
        r = 0
        for _ in range(n):
            r = (r << 1) + self.fila.popleft()
        return r

    def esvazia(self):
        self.fila.clear()

# ---------------------------------------------------------------- palavra e passagem
_palavras = None
def palavras():
    global _palavras
    if _palavras is None:
        _palavras = open(os.path.join(RAIZ, 'dados', 'vocab.txt')).read().split()
    return _palavras

def palavra(oraculo):
    return palavras()[oraculo.bits(17) % len(palavras())]

# ST_BIBLE_BOOKS de Adam/God/GodBible.HC ('_' no lugar do espaco)
LIVROS = [l.replace('_', ' ') for l in (
    'Genesis Exodus Leviticus Numbers Deuteronomy Joshua Judges Ruth '
    '1_Samuel 2_Samuel 1_Kings 2_Kings 1_Chronicles 2_Chronicles Ezra Nehemiah '
    'Esther Job Psalms Proverbs Ecclesiastes Song_of_Songs Isaiah Jeremiah '
    'Lamentations Ezekiel Daniel Hosea Joel Amos Obadiah Jonah Micah Nahum '
    'Habakkuk Zephaniah Haggai Zechariah Malachi Matthew Mark Luke John Acts '
    'Romans 1_Corinthians 2_Corinthians Galatians Ephesians Philippians '
    'Colossians 1_Thessalonians 2_Thessalonians 1_Timothy 2_Timothy Titus '
    'Philemon Hebrews James 1_Peter 2_Peter 1_John 2_John 3_John Jude '
    'Revelation').split()]
# ST_BIBLE_BOOK_LINES de Adam/God/GodBible.HC: linha (1 = primeira) onde cada livro comeca
INICIOS = [297, 5068, 9123, 12005, 15977, 19168, 21329, 23598, 23902, 26892, 29345, 32241,
           34961, 37633, 40756, 41671, 42963, 43605, 46190, 53793, 56267, 56966, 57332,
           61806, 66736, 67217, 71804, 73189, 73876, 74130, 74615, 74697, 74860, 75241,
           75416, 75604, 75806, 75932, 76684, 76908, 79970, 81941, 85266, 87803, 90914,
           92110, 93323, 94088, 94514, 94869, 95153, 95402, 95647, 95772, 96090, 96320,
           96440, 96500, 97370, 97687, 97976, 98163, 98506, 98552, 98597, 98684, 100111]

_biblia = None
def biblia():
    global _biblia
    if _biblia is None:
        _biblia = open(os.path.join(RAIZ, 'dados', 'Bible.TXT'), encoding='latin1').read().splitlines()
    return _biblia

def versiculo(linha):
    """BibleLine2Verse: 'Livro cap:vers' da primeira linha numerada a partir de `linha`."""
    livro = None
    for i in range(len(LIVROS)):
        if INICIOS[i] <= linha < INICIOS[i + 1]:
            livro = LIVROS[i]
    if livro is None:
        return ''
    for t in biblia()[linha - 1:linha + 40]:
        p = t.split(' ', 1)[0]
        if p[:1].isdigit() and ':' in p:
            return '%s %s' % (livro, p)
    return livro

def passagem(oraculo, n=20):
    total = min(INICIOS[-1] - 1, len(biblia()))
    inicio = oraculo.bits(21) % (total - (n - 1)) + 1
    return versiculo(inicio), biblia()[inicio - 1:inicio - 1 + n]

# ---------------------------------------------------------------- hino (GodSongStr)
DUR_4, DUR_8_8, DUR_3_3_3, DUR_16_16_16_16, DUR_8DOT_16, DUR_8_16_16, DUR_16_16_8 = range(7)
NORMAL = [DUR_4, DUR_4, DUR_8_8, DUR_3_3_3, DUR_16_16_16_16]

def hino_str(oraculo, oitava=4):
    """Gerador: faz `yield` sempre que a fila nao tem bits; devolve a string do Play().

    E o GodSongStr com complexidade Normal, sem pausas e em 4/4 (os padroes do
    formulario do original). Comeca esvaziando a fila, como o FifoU8Flush de la.
    """
    def bits(n):
        while not oraculo.tem(n):
            yield
        return oraculo.bits(n)

    buf = []
    estado = [oitava + 1]
    buf.append(str(estado[0]))

    def nota(k):
        k //= 2
        alvo = oitava if k < 3 else oitava + 1
        if estado[0] != alvo:
            estado[0] = alvo
            buf.append(str(alvo))
        buf.append('G' if k == 0 else chr(k - 1 + ord('A')))

    oraculo.esvazia()
    ultima = -1
    for _ in range(8):
        n = yield from bits(8)
        dur = NORMAL[n % 5]
        if dur == DUR_8_8:
            if ultima != DUR_8_8:
                buf.append('e')
            nota((yield from bits(4)))
            nota((yield from bits(4)))
        elif dur == DUR_3_3_3:
            if ultima != DUR_3_3_3:
                buf.append('et')
            for _ in range(3):
                nota((yield from bits(4)))
        elif dur == DUR_16_16_16_16:
            if ultima != DUR_16_16_16_16:
                buf.append('s')
            k, k2 = (yield from bits(4)), (yield from bits(4))
            for x in (k, k2, k, k2):
                nota(x)
        else:
            if ultima != DUR_4:
                buf.append('q')
            nota((yield from bits(4)))
        ultima = dur
    return ''.join(buf)

def hino(oraculo):
    """GodSong: st1 st1 st2 st2."""
    a = yield from hino_str(oraculo)
    b = yield from hino_str(oraculo)
    return a + a + b + b

# ---------------------------------------------------------------- Play() e o PC speaker
# O motor do Play() mora em musica.py (o JukeBox usa o mesmo); aqui ficam os
# nomes antigos.
from musica import TAXA, onda, toca

def notas(st):
    return Musica().notas(st)
