"""As cancoes do Psalmody: ler, classificar e gravar, como o JukeBox original.

Uma cancao e um programa HolyC (`Apps/Psalmody/Examples/*.HC`): uma funcao
Song() com Play("notas", "pa\\0la\\0vras") dentro de um `while`. Aqui nao ha
compilador de HolyC; `Cancao` reconhece o que o Psalmody escreve e o que as
cancoes do Terry usam: Play(), texto solto entre aspas, music.tempo,
music.stacatto_factor, MusicSettingsRst, Fs->text_attr e o laco. O que tiver
DrawIt (as "has graphics") toca e mostra a letra, mas sem o desenho.

A primeira linha e um comentario com a nota e a categoria (Doc/Tips.DD):
"//9 has words". O terceiro caractere e a nota de 0 a 9.

O arquivo e um documento DolDoc: o texto ate o primeiro NUL, depois os dados
binarios dos sprites. Tudo o que se grava aqui mexe so no texto e preserva os
bytes do resto.
"""
import os, re, shutil

from texto import RAIZ

CORES_NOME = {n: i for i, n in enumerate(
    'BLACK BLUE GREEN CYAN RED PURPLE BROWN LTGRAY DKGRAY LTBLUE LTGREEN LTCYAN LTRED '
    'LTPURPLE YELLOW WHITE'.split())}

PASTA = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'),
                     'templeos', 'Psalmody')
EXEMPLOS = os.path.join(RAIZ, 'dados', 'psalmody')

# categoria -> cor no JukeBox (BLACK incomplete, GREEN graphics, BLUE words,
# CYAN special, RED no nothing), na ordem em que o original testa
CATEGORIAS = [('incomplete', 'BLACK'), ('has graphics', 'GREEN'), ('has words', 'BLUE'),
              ('special', 'CYAN'), ('no nothing', 'RED')]

def prepara():
    """Install.HC cria ~/Psalmody. Aqui ela ja nasce com as cancoes da ISO,
    para que dar nota e apagar funcionem nelas como nas suas."""
    if not os.path.isdir(PASTA):
        os.makedirs(PASTA)
        for n in sorted(os.listdir(EXEMPLOS)):
            if n.endswith('.HC'):
                shutil.copy(os.path.join(EXEMPLOS, n), os.path.join(PASTA, n))
    return PASTA

def lista():
    r = []
    for n in sorted(os.listdir(PASTA), key=str.lower):
        caminho = os.path.join(PASTA, n)
        if n.endswith('.HC') and os.path.isfile(caminho):
            try:
                c = Cancao(caminho)
            except OSError:
                continue
            if 'Play(' in c.texto:   # FileOcc("Play(",...): o resto nao e cancao
                r.append(c)
    return r

# ---------------------------------------------------------------- leitura
def _partes(caminho):
    dados = open(caminho, 'rb').read()
    i = dados.find(b'\0')
    if i < 0:
        return dados.decode('latin1'), b''
    return dados[:i].decode('latin1'), dados[i:]

def _sem_doldoc(t):
    """O que o compilador ve: $$ vira $, os outros comandos DolDoc somem."""
    return re.sub(r'\$\$|\$[^$\n]*\$', lambda m: '$' if m.group() == '$$' else '', t)

TOKEN = re.compile(r'''
    (?P<com>//[^\n]*|/\*.*?\*/)
  | (?P<str>"(?:\\.|[^"\\])*")
  | (?P<chr>'(?:\\.|[^'\\])*')
  | (?P<nome>[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*)
  | (?P<num>\d+\.?\d*|\.\d+)
  | (?P<esp>\s+)
  | (?P<op><<|.)
''', re.S | re.X)

_ESC = {'n': '\n', 't': '\t', '0': '\0', '"': '"', "'": "'", '\\': '\\', 'd': '$', 'r': ''}

def _literal(s):
    s = s[1:-1]
    return re.sub(r'\\(x[0-9A-Fa-f]{1,2}|.)',
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] == 'x'
                  else _ESC.get(m.group(1), m.group(1)), s)

def _tokens(t):
    r = []
    for m in TOKEN.finditer(t):
        k = m.lastgroup
        if k in ('com', 'esp'):
            continue
        r.append((k, m.group()))
    return r

def _fecha(toks, i, abre, fecha):
    """Indice do `fecha` que casa com o `abre` em toks[i]."""
    n = 0
    for j in range(i, len(toks)):
        if toks[j][1] == abre:
            n += 1
        elif toks[j][1] == fecha:
            n -= 1
            if n == 0:
                return j
    return len(toks)

def _cor(nome):
    return CORES_NOME.get(nome.upper())

def _ops(toks):
    """Operacoes de um trecho do corpo de Song(). Devolve (antes, laco):
    `laco` e None se nao houver while."""
    ops, i, inicio = [], 0, True
    while i < len(toks):
        k, v = toks[i]
        prox = toks[i + 1][1] if i + 1 < len(toks) else ''
        if v == 'while' and prox == '(':
            j = _fecha(toks, i + 1, '(', ')')
            if j + 1 < len(toks) and toks[j + 1][1] == '{':
                fim = _fecha(toks, j + 1, '{', '}')
                laco, _ = _ops(toks[j + 2:fim])
                return ops, laco
            i = j + 1
            continue
        if v == 'Play' and prox == '(':
            fim = _fecha(toks, i + 1, '(', ')')
            args, atual = [], []
            for kk, vv in toks[i + 2:fim]:
                if vv == ',':
                    args.append(atual); atual = []
                elif kk == 'str':
                    atual.append(_literal(vv))
            args.append(atual)
            notas = ''.join(args[0]) if args and args[0] else ''
            palavras = None
            if len(args) > 1 and args[1]:
                palavras = [p.replace('\x1f', ' ') for p in ''.join(args[1]).split('\0')]
            ops.append(('play', notas, palavras))
            i = fim + 1
        elif k == 'str' and inicio:
            partes = []
            while i < len(toks) and toks[i][0] == 'str':
                partes.append(_literal(toks[i][1])); i += 1
            ops.append(('texto', ''.join(partes)))
        elif v == 'MusicSettingsRst':
            ops.append(('reinicia',)); i += 1
        elif v in ('music.tempo', 'music.stacatto_factor') and prox == '=':
            j = i + 2
            sinal = -1 if j < len(toks) and toks[j][1] == '-' else 1
            j += sinal < 0
            if j < len(toks) and toks[j][0] == 'num':
                ops.append(('tempo' if v == 'music.tempo' else 'staccato',
                            sinal * float(toks[j][1])))
            i = j + 1
        elif v == 'Fs->text_attr' and prox == '=':
            # Fs->text_attr=FUNDO<<4+FRENTE;
            fim = i + 2
            while fim < len(toks) and toks[fim][1] != ';':
                fim += 1
            nomes = [vv for kk, vv in toks[i + 2:fim] if kk == 'nome']
            if len(nomes) == 2 and None not in map(_cor, nomes):
                ops.append(('cores', _cor(nomes[0]), _cor(nomes[1])))
            i = fim
        else:
            i += 1
        inicio = v in (';', '{', '}') or (k == 'nome' and v in ('try', 'else', 'do'))
    return ops, None

class Cancao:
    def __init__(self, caminho):
        self.caminho = caminho
        self.nome = os.path.basename(caminho)[:-3]   # FileExtRem
        self.texto, self.binario = _partes(caminho)
        primeira = self.texto.split('\n', 1)[0]
        self.nota = primeira[2] if len(primeira) > 2 and primeira[2].isdigit() else '0'
        self.cor = None
        for cat, cor in CATEGORIAS:
            if cat in primeira:
                self.cor = CORES_NOME[cor]
                break
        self._programa = None

    # ------------------------------------------------------------ programa
    def programa(self):
        """(premio, antes, laco) do texto como o compilador o ve."""
        if self._programa is None:
            t = _sem_doldoc(self.texto)
            premio = None
            m = re.search(r'CallExtStr\s*\(\s*"JukeReward"\s*,', t)
            if m:
                toks = _tokens(t[m.end():])
                fim = _fecha([('op', '(')] + toks, 0, '(', ')') - 1
                premio = ''.join(_literal(v) for k, v in toks[:fim] if k == 'str')
            antes, laco = [], None
            m = re.search(r'\bSong\s*\(\s*\)\s*\{', t)
            if m:
                toks = _tokens(t[m.end() - 1:])
                corpo = toks[1:_fecha(toks, 0, '{', '}')]
                antes, laco = _ops(corpo)
            self._programa = (premio, antes, laco)
        return self._programa

    def operacoes(self):
        """Gerador para o Tocador: o comeco uma vez, o laco para sempre."""
        premio, antes, laco = self.programa()
        if premio:
            yield ('premio', premio)
        yield from antes
        if laco and any(op[0] == 'play' for op in laco):
            while True:
                yield from laco

    # ------------------------------------------------------------ gravacao
    def _grava(self, texto):
        tmp = self.caminho + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(texto.encode('latin1', 'replace') + self.binario)
        os.replace(tmp, self.caminho)
        self.texto = texto
        self._programa = None

    def da_nota(self, digito):
        """JBPutKey '0'-'9': o terceiro caractere da primeira linha."""
        primeira, _, resto = self.texto.partition('\n')
        if len(primeira) < 3:
            return
        self._grava(primeira[:2] + digito + primeira[3:] + '\n' + resto)
        self.nota = digito

    def recompensa(self, palavras):
        """JBPutKey 'r': uma arvore Reward1/Reward2 com CallExtStr("JukeReward",...)
        logo depois da primeira linha; cada 'r' acrescenta uma linha de palavras."""
        linha = '"%s "\n' % ' '.join(palavras)
        t = self.texto
        if '$TR,"Reward1"$' not in t:
            primeira, _, resto = t.partition('\n')
            t = (primeira + '\n'
                 '\n$TR,"Reward1"$\n'
                 '$ID,2$CallExtStr("JukeReward",""\n'
                 '$TR,"Reward2"$\n'
                 '$ID,2$\n'
                 '$ID,-2$\n'
                 ');\n$ID,-2$\n' + resto)
        i = t.index('$TR,"Reward2"$\n$ID,2$\n') + len('$TR,"Reward2"$\n$ID,2$\n')
        fim = t.index('$ID,-2$\n);', i)
        t = t[:fim] + linha + t[fim:]
        self._grava(t)

def salva_hino(st):
    """Grava um God Song como o PsmSaveSong grava: um Play() por pedaco.

    `st` e a+a+b+b (deus.hino): cada pedaco vira um Play(). Devolve o nome.
    """
    prepara()
    n = 1
    while os.path.exists(os.path.join(PASTA, 'God%d.HC' % n)):
        n += 1
    nome = 'God%d' % n
    pedacos = [st]
    for la in range(1, len(st) // 2 + 1):   # acha a e b em a+a+b+b
        a, resto = st[:la], st[2 * la:]
        if st[la:2 * la] == a and len(resto) % 2 == 0 and \
                resto[:len(resto) // 2] == resto[len(resto) // 2:]:
            b = resto[:len(resto) // 2]
            pedacos = [a, a, b, b] if b else [a, a]
            break
    corpo = ''.join('\tPlay("%s");\n' % p for p in pedacos)
    texto = ('//0 no nothing\n'
             'U0 Song()\n'
             '{\n'
             'Fs->task_end_cb=&SndTaskEndCB;\n'
             'MusicSettingsRst;\n'
             'music.tempo= 2.500;\n'
             'music.stacatto_factor= 0.900;\n'
             'try {\n'
             'while (!ScanKey) {\n' + corpo +
             '}\n'
             '} catch\n'
             'PutExcept;\n'
             'Snd;\n'
             '}\n'
             '\n'
             'Song;\n')
    with open(os.path.join(PASTA, nome + '.HC'), 'w', encoding='latin1') as f:
        f.write(texto)
    return nome
