"""DolDoc sem interface: le um documento do TempleOS e monta a pagina em celulas.

Segue o original onde importa, em Adam/DolDoc:
  DocInit.HC       comandos, flags e o que cada um tem por padrao
  DocRecalc.HC     largura de tab, $ID$, arvores, cores de cada tipo, sprites
  DocHighlight.HC  cores do codigo-fonte
  DocLink.HC       tipos de link (FI, FA, FF, FL, MN, HI, BF...)

Fica de fora o que so faz sentido com o sistema rodando: macros ($MA$, $BT$),
formularios ($DA$, $CB$, $LS$), musica ($SO$), o $HC$ (HTML) e o editor.
"""
import os, re

# Kernel: BLACK BLUE GREEN CYAN RED PURPLE BROWN LTGRAY DKGRAY LTBLUE LTGREEN
# LTCYAN LTRED LTPURPLE YELLOW WHITE
CORES = {n: i for i, n in enumerate(
    'BLACK BLUE GREEN CYAN RED PURPLE BROWN LTGRAY DKGRAY LTBLUE LTGREEN '
    'LTCYAN LTRED LTPURPLE YELLOW WHITE'.split())}
BLUE, WHITE = CORES['BLUE'], CORES['WHITE']
# DOC_COLOR_* em Kernel/KernelA.HH
ALT, LINK, MACRO, ANCORA, ARVORE = (CORES[c] for c in ('LTGRAY', 'RED', 'LTBLUE', 'DKGRAY', 'PURPLE'))
COMENTARIO, BIN, TEXTO_CONST = CORES['GREEN'], CORES['LTGREEN'], CORES['BROWN']
SIM_FUN, SIM_CLASSE, SIM_DEFINE, SIM_GLOBAL, SIM_CHAVE, SIM_REG = (
    CORES[c] for c in ('PURPLE', 'LTBLUE', 'CYAN', 'LTCYAN', 'BLUE', 'LTRED'))

SUB, PISCA, INVERTE = 1, 2, 4  # bits de atributo da celula
FONTE_EXT = ('.HC', '.HH', '.IN', '.PRJ')  # FILEMASK_SRC: destaque ligado
TEXTO_EXT = FONTE_EXT + ('.DD', '.TXT', '.MAP')
MAX_LINHAS_TEXTO = 3000

# Conteudo ofensivo: o leitor nao abre.
BLOQUEADOS = {'adam/god/hsnotes.dd', 'demo/acctexample/personalnotes.dd'}

CHAVES = set('''if else switch start end case default break goto return
    do while for class union public extern import try catch lock asm reg noreg
    no_warn sizeof offset lastclass interrupt haserrcode argpop noargpop
    _extern _import nowarn U0 I0 U8 I8 Bool U16 I16 U32 I32 U64 I64 F64
    include define help_index help_file ifdef ifndef ifaot ifjit endif exe'''.split())
REGISTROS = set('''RAX RCX RDX RBX RSP RBP RSI RDI R8 R9 R10 R11 R12 R13 R14 R15
    EAX ECX EDX EBX ESP EBP ESI EDI AX CX DX BX SP BP SI DI AL CL DL BL AH CH DH BH
    CS DS ES SS FS GS RIP RFLAGS'''.split())

# ---------------------------------------------------------------- analise
class Comando:
    __slots__ = ('nome', 'liga', 'tira', 'tag', 'args', 'nums', 'linha')

    def tem(self, flag):
        return flag in self.liga

    def alvo(self):
        return self.args.get('A') or self.tag or ''

class Trecho:
    __slots__ = ('texto', 'linha')

    def __init__(self, texto, linha):
        self.texto, self.linha = texto, linha

def _fim_comando(t, i):
    """Posicao do $ que fecha o comando. Aspas protegem $ e virgula."""
    aspas, n = False, len(t)
    while i < n:
        c = t[i]
        if aspas:
            if c == '\\':
                i += 1
            elif c == '"':
                aspas = False
        elif c == '"':
            aspas = True
        elif c == '$':
            return i
        i += 1
    return -1

def _partes(s):
    """Divide nos argumentos de nivel de cima (fora de aspas)."""
    r, atual, aspas, i, n = [], [], False, 0, len(s)
    while i < n:
        c = s[i]
        if aspas and c == '\\' and i + 1 < n:
            atual.append(s[i:i + 2]); i += 2; continue
        if c == '"':
            aspas = not aspas
        if c == ',' and not aspas:
            r.append(''.join(atual)); atual = []
        else:
            atual.append(c)
        i += 1
    r.append(''.join(atual))
    return r

_ESCAPES = {'n': '\n', 't': '\t', '"': '"', '\\': '\\', '$': '$', "'": "'", '0': ''}

def _texto_de(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return re.sub(r'\\(.)', lambda m: _ESCAPES.get(m[1], m[1]), s[1:-1], flags=re.S)
    return s

def _comando(corpo, linha):
    partes = _partes(corpo)
    m = re.match(r'([A-Za-z_][A-Za-z0-9_]*)((?:[+-][A-Za-z0-9]+)*)$', partes[0].strip())
    if not m:
        return None
    c = Comando()
    c.nome, c.linha, c.tag, c.args, c.nums = m[1], linha, None, {}, []
    flags = re.findall(r'([+-])([A-Za-z0-9]+)', m[2])
    c.liga = {f for s, f in flags if s == '+'}
    c.tira = {f for s, f in flags if s == '-'}
    for p in partes[1:]:
        k = re.match(r'\s*([A-Z][A-Z0-9]*)\s*=(.*)$', p, re.S)
        if k:
            c.args[k[1]] = _texto_de(k[2])
        elif p.lstrip().startswith('"'):
            if c.tag is None:
                c.tag = _texto_de(p)
        else:
            c.nums.append(p.strip())
    return c

def analisa(t):
    """Texto DolDoc em lista de Trecho e Comando. $$ e um cifrao literal."""
    r, i, n, linha = [], 0, len(t), 1
    def poe(s):
        nonlocal linha
        if s:
            if r and isinstance(r[-1], Trecho) and '\n' not in r[-1].texto[-1:]:
                r[-1].texto += s
            else:
                r.append(Trecho(s, linha))
            linha += s.count('\n')
    while i < n:
        j = t.find('$', i)
        if j < 0:
            poe(t[i:]); break
        poe(t[i:j])
        k = _fim_comando(t, j + 1)
        if k < 0:      # sem fechamento: e so um cifrao
            poe(t[j:]); break
        corpo = t[j + 1:k]
        if not corpo:
            poe('$')
        else:
            c = _comando(corpo, linha)
            if c:
                r.append(c)
            linha += corpo.count('\n')
        i = k + 1
    return r

def _num(s, padrao=0):
    try:
        return int(s, 0)
    except (TypeError, ValueError):
        return padrao

def _cor(c, padrao):
    if not c.nums or not c.nums[0]:
        return padrao
    v = c.nums[0].strip()
    return CORES.get(v, _num(v, padrao) & 15)

# ---------------------------------------------------------------- arquivos
class Documento:
    def __init__(self, titulo, texto, bins=None, plano=False, fonte=False, caminho=None):
        self.titulo, self.bins, self.fonte, self.caminho = titulo, bins or {}, fonte, caminho
        self.partes = [Trecho(texto, 1)] if plano else analisa(texto)
        self.arvores = self._arvores()

    def _arvores(self):
        """{indice do $TR$: (primeiro_escondido, ultimo_escondido, colapsa_por_padrao)}.

        Como em DocRecalc.HC: o que a arvore esconde comeca no primeiro $ID$
        depois dela e vai ate o $ID$ que traz a indentacao de volta.
        """
        r, p = {}, self.partes
        for i, c in enumerate(p):
            if not (isinstance(c, Comando) and c.nome == 'TR'):
                continue
            ini = i + 1
            while ini < len(p) and not (isinstance(p[ini], Comando) and p[ini].nome in ('ID', 'TR')):
                ini += 1
            if ini == len(p) or p[ini].nome == 'TR':
                r[i] = (0, -1, 'C' not in c.tira)
                continue
            base = atual = 0
            k = ini
            while k < len(p):
                q = p[k]
                if isinstance(q, Comando) and q.nome == 'ID':
                    atual = _num(q.nums[0] if q.nums else '') if 'LX' in q.liga else atual + _num(q.nums[0] if q.nums else '')
                    if atual <= base:
                        break
                k += 1
            r[i] = (ini, min(k, len(p) - 1), 'C' not in c.tira)
        return r

    def abre_ate(self, idx, abertos):
        """Abre as arvores que escondem a parte idx."""
        for tr, (ini, fim, _) in self.arvores.items():
            if ini <= idx <= fim:
                abertos[tr] = True

    def parte_da_linha(self, n):
        ultimo = 0
        for i, q in enumerate(self.partes):
            if q.linha > n:
                break
            ultimo = i
        return ultimo

    def parte_com(self, agulha, ocorrencia=1):
        vistos = 0
        for i, q in enumerate(self.partes):
            texto = q.texto if isinstance(q, Trecho) else (q.tag or '')
            if isinstance(q, Comando) and q.nome == 'AN':
                texto = '%s %s' % (q.tag or '', q.args.get('A', ''))
            vistos += texto.count(agulha)
            if agulha in texto and vistos >= ocorrencia:
                return i
        return None

class Erro(Exception):
    pass

def raiz_iso():
    return os.environ.get('TEMPLEOS_ISO') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'iso-extraida')

def resolve(nome, base=None):
    """Nome do TempleOS ('::/Doc/X.DD', 'C:/...', '~/x', relativo) em (arquivo, relativo)."""
    raiz = raiz_iso()
    nome = nome.strip()
    nome = re.sub(r'^(?:[A-Za-z]:|:)?:?/', '', nome) if re.match(r'^(?:[A-Za-z]:/|::/|/)', nome) else nome
    if nome.startswith('~/'):
        # O /Home da ISO esta vazio: os arquivos ficam na raiz e no exemplo de conta
        resto = nome[2:]
        nome = next((p + resto for p in ('Home/', '', 'Demo/AcctExample/')
                     if os.path.exists(os.path.join(raiz, p + resto))), 'Home/' + resto)
    elif base and not os.path.isabs(nome):
        tentativa = os.path.join(os.path.dirname(base), nome)
        if os.path.exists(os.path.join(raiz, tentativa)):
            nome = tentativa
    nome = os.path.normpath(nome)
    if nome.endswith('.Z'):
        nome = nome[:-2]
    if nome.startswith('..') or os.path.isabs(nome):
        raise Erro('Bad path: ' + nome)
    atual = raiz
    for parte in nome.split('/'):  # sem diferenciar maiusculas, como o RedSea
        if not os.path.isdir(atual):
            raise Erro('Not found: ::/' + nome)
        achado = next((x for x in sorted(os.listdir(atual)) if x.lower() == parte.lower()), None)
        if achado is None:
            raise Erro('Not found: ::/' + nome)
        atual = os.path.join(atual, achado)
    if os.path.isdir(atual):
        raise Erro('Is a folder: ::/' + nome)
    return atual, os.path.relpath(atual, raiz)

_cache = {}

def abre(nome, base=None):
    arq, rel = resolve(nome, base)
    if rel in _cache:
        return _cache[rel]
    if rel.lower() in BLOQUEADOS:
        raise Erro('Not available here: ::/' + rel)
    ext = os.path.splitext(arq)[1].upper()
    if ext not in TEXTO_EXT:
        raise Erro('Not a document: ::/' + rel)
    d = open(arq, 'rb').read()
    if ext == '.TXT' and d.count(b'\n') > MAX_LINHAS_TEXTO:  # a Biblia: 100 mil linhas
        d = b'\n'.join(d.split(b'\n', MAX_LINHAS_TEXTO)[:MAX_LINHAS_TEXTO]) + b'\n\n[...]\n'
    i = d.find(b'\0')
    texto, bins = d.decode('latin1') if i < 0 else d[:i].decode('latin1'), {}
    if i >= 0:
        p = i + 1
        while p + 16 <= len(d):
            num = int.from_bytes(d[p:p + 4], 'little')
            tam = int.from_bytes(d[p + 8:p + 12], 'little')
            bins[num] = d[p + 16:p + 16 + tam]
            p += 16 + tam
    doc = Documento('/' + rel, texto, bins, plano=ext == '.TXT',
                    fonte=ext in FONTE_EXT, caminho=rel)
    _cache[rel] = doc
    return doc

# ---------------------------------------------------------------- indice
class Indice:
    """Tabela de simbolos e #help_index, que no original o compilador mantem na memoria.

    Vem dos .MAP e de uma varredura das definicoes do codigo.
    """
    DEF_FUNCAO = re.compile(
        r'^(?:(?:public|extern|_extern|import|_import|interrupt|argpop|noargpop|haserrcode|static)\s+)*'
        r'[A-Za-z_]\w*\s*\*{0,3}\s*([A-Za-z_]\w*)\s*\(')
    DEF_CLASSE = re.compile(r'^(?:public\s+)?(?:class|union)\s+([A-Za-z_]\w*)')
    DEF_DEFINE = re.compile(r'^#define\s+([A-Za-z_]\w*)')
    DEF_GLOBAL = re.compile(r'^(?:public\s+|extern\s+)*[A-Z]\w*\s*\*{0,3}\s*([A-Za-z_]\w*)\s*(?:[;=\[,])')

    def __init__(self):
        self.lugar, self.tipo, self.ajuda, self.arq_ajuda = {}, {}, {}, {}
        raiz = raiz_iso()
        for pasta, _, nomes in os.walk(raiz):
            for nome in sorted(nomes):
                if nome.upper().endswith(('.HC', '.HH')):
                    self._varre(os.path.join(pasta, nome), os.path.relpath(os.path.join(pasta, nome), raiz))
        # Os .MAP tem a posicao exata e valem por cima da varredura
        for m in ('Kernel/Kernel.MAP', 'Compiler/Compiler.MAP'):
            try:
                t = open(os.path.join(raiz, m), 'rb').read().decode('latin1')
            except OSError:
                continue
            for s, a, n in re.findall(r'\$LK,"([^"]+)",A="FL:::/([^,"]+),(\d+)"\$', t):
                self.lugar[s] = (a, int(n))

    def _varre(self, arq, rel):
        indice, dentro = '', False
        with open(arq, 'rb') as f:
            bruto = f.read()
        fim = bruto.find(b'\0')
        linhas = (bruto if fim < 0 else bruto[:fim]).decode('latin1').split('\n')
        for n, l in enumerate(linhas, 1):
            m = 'DefineLstLoad' in l and re.search(r'DefineLstLoad\("(\w+)"', l)
            if m:  # as listas ST_* que os documentos citam
                self.lugar.setdefault(m[1], (rel, n))
            if l[:1] == '{':     # dentro de funcao ou classe nada e definicao global
                dentro = True
            elif l[:1] == '}':
                dentro = False
            if dentro or not l or l[0] in ' \t/}{':
                continue
            if l.startswith('#help_index'):
                m = re.search(r'"([^"]*)"', l)
                indice = m[1] if m else ''
                continue
            if l.startswith('#help_file'):
                m = re.search(r'"([^"]*)"', l)
                if m and indice:
                    self.arq_ajuda.setdefault(indice, []).append(m[1])
                continue
            for rx, tipo in ((self.DEF_DEFINE, SIM_DEFINE), (self.DEF_CLASSE, SIM_CLASSE),
                             (self.DEF_FUNCAO, SIM_FUN), (self.DEF_GLOBAL, SIM_GLOBAL)):
                m = rx.match(l)
                if m and m[1] not in CHAVES:
                    self.lugar.setdefault(m[1], (rel, n))
                    # O destaque olha a tabela do adam_task: so o sistema, nao as
                    # demos e os apps, que definem globais como x, y e dc.
                    if rel.split('/')[0] in ('Kernel', 'Adam', 'Compiler') and len(m[1]) > 2:
                        self.tipo.setdefault(m[1], tipo)
                    if indice and tipo != SIM_GLOBAL:
                        for i in indice.split(';'):
                            self.ajuda.setdefault(i.strip(), {}).setdefault(m[1], (rel, n))
                    break

    def pagina_ajuda(self, nome):
        """O equivalente do DocHelpIdx: pagina com o que esta naquele #help_index."""
        filhos = sorted(k for k in self.ajuda if k.startswith(nome + '/'))
        linhas = ['$WW,1$$FG,5$$TX+CX,"Help Index: %s"$$FG$\n' % nome]
        for arq in self.arq_ajuda.get(nome, []):
            linhas.append('$LK,"%s",A="FI:%s"$' % (arq, arq))
        if filhos:
            linhas += ['', '$FG,2$Sections:$FG$']
            linhas += ['$LK,"%s",A="HI:%s"$' % (f, f) for f in filhos]
        itens = self.ajuda.get(nome, {})
        if itens:
            linhas += ['', '$FG,2$Symbols:$FG$']
            for s in sorted(itens, key=str.lower):
                a, n = itens[s]
                linhas.append('$LK,"%s",A="FL:::/%s,%d"$' % (s, a, n))
        if not (filhos or itens):
            return None
        return Documento('Help Index: ' + nome, '\n'.join(linhas) + '\n')

_indice = None

def indice():
    global _indice
    if _indice is None:
        _indice = Indice()
    return _indice

# ---------------------------------------------------------------- destaque de codigo
class Realce:
    """Maquina de estados do DocHighlight: None = cor normal do texto."""
    NORMAL, LINHA, BLOCO, ASPAS1, ASPAS2 = range(5)

    def __init__(self, simbolos):
        self.simbolos, self.estado, self.prof, self.parens, self.chaves = simbolos, 0, 0, 0, 0

    def cor_da_palavra(self, p):
        if p in CHAVES:
            return SIM_CHAVE
        if p in REGISTROS:
            return SIM_REG
        return self.simbolos.get(p)

    def cores(self, s):
        r, i, n = [], 0, len(s)
        while i < n:
            c = s[i]
            e = self.estado
            if e == self.LINHA:
                r.append(COMENTARIO)
                if c == '\n':
                    self.estado = self.NORMAL
                i += 1
            elif e == self.BLOCO:
                if s.startswith('/*', i):
                    self.prof += 1; r += [COMENTARIO] * 2; i += 2
                elif s.startswith('*/', i):
                    self.prof -= 1; r += [COMENTARIO] * 2; i += 2
                    if self.prof <= 0:
                        self.estado = self.NORMAL
                else:
                    r.append(COMENTARIO); i += 1
            elif e in (self.ASPAS1, self.ASPAS2):
                r.append(TEXTO_CONST)
                if c == '\\' and i + 1 < n:
                    r.append(TEXTO_CONST); i += 2; continue
                if c == ("'" if e == self.ASPAS1 else '"'):
                    self.estado = self.NORMAL
                i += 1
            elif c.isalnum() or c == '_':
                k = i
                while k < n and (s[k].isalnum() or s[k] == '_'):
                    k += 1
                r += [self.cor_da_palavra(s[i:k])] * (k - i)
                i = k
            elif s.startswith('//', i):
                self.estado = self.LINHA; r += [COMENTARIO] * 2; i += 2
            elif s.startswith('/*', i):
                self.estado = self.BLOCO; self.prof = 1; r += [COMENTARIO] * 2; i += 2
            else:
                cor = None
                if c == "'":
                    self.estado, cor = self.ASPAS1, TEXTO_CONST
                elif c == '"':
                    self.estado, cor = self.ASPAS2, TEXTO_CONST
                elif c == '(':
                    self.parens += 1
                    cor = ALT if (self.parens - 1) & 1 else None
                elif c == ')':
                    self.parens -= 1
                    cor = ALT if self.parens & 1 else None
                elif c == '{':
                    self.chaves += 1
                    cor = ALT if (self.chaves - 1) & 1 else None
                elif c == '}':
                    self.chaves -= 1
                    cor = ALT if self.chaves & 1 else None
                r.append(cor)
                i += 1
        return r

# ---------------------------------------------------------------- pagina
class Pagina:
    """linhas[n] = lista de None ou (glifo, fg, bg, atributos, link, sy)."""

    def __init__(self):
        self.linhas = [[]]
        self.sprites = []   # (coluna, linha, numero do bin, link)
        self.links = []     # ('alvo', texto) | ('arvore', indice) | ('macro', texto)
        self.ancoras = {}
        self.marcas = {}    # indice da parte -> linha
        self.pisca = False
        self.largura_max = 0

    def texto_linha(self, n):
        return ''.join(chr(c[0]) if c else ' ' for c in self.linhas[n])

    def inicio_do_link(self, ident):
        for n, l in enumerate(self.linhas):
            for col, c in enumerate(l):
                if c and c[4] == ident:
                    return n, col
        for col, n, _, lk in self.sprites:
            if lk == ident:
                return n, max(col, 0)
        return None

def monta(doc, largura, abertos=None):
    """Faz o trabalho do DocRecalc para um documento numa janela de `largura` colunas."""
    abertos = abertos or {}
    pag = Pagina()
    fg_padrao, bg_padrao = BLUE, WHITE
    fg, bg = fg_padrao, bg_padrao
    ww = hl = False
    if doc.fonte:
        hl = True
    bk = iv = ul = False
    indent = lm = sy = 0
    rm = None
    col = lin = 0
    realce = None
    bordas = []

    def inicio():
        return indent + lm

    def direita():
        # Coluna onde a linha acaba. $RM$ e absoluto em DocRecalc.HC; a janela
        # pode ser mais estreita, e nunca menos que um pedaco de texto.
        d = largura if rm is None else min(largura, rm + 1)
        return max(inicio() + 8, d)

    def linha_atual():
        while len(pag.linhas) <= lin:
            pag.linhas.append([])
        return pag.linhas[lin]

    def quebra():
        nonlocal lin, col
        l = pag.linhas[lin]
        ini = inicio()
        limite = direita()
        k = len(l) - 1
        while k > ini and not (l[k] and l[k][0] == 32):
            k -= 1
        if k > ini:
            resto = l[k + 1:]
            del l[k:]
        else:  # uma palavra so, maior que a linha
            resto = l[limite:]
            del l[limite:]
        lin += 1
        col = ini
        nova = linha_atual()
        nova[:0] = [None] * max(0, col - len(nova))
        for j, c in enumerate(resto):
            pos = col + j
            if pos >= len(nova):
                nova.extend([None] * (pos + 1 - len(nova)))
            nova[pos] = c
        col += len(resto)

    def poe(ch, cor, fundo, attr, lk):
        nonlocal col
        l = linha_atual()
        if col < 0:
            col = 0
        if col >= len(l):
            l.extend([None] * (col + 1 - len(l)))
        l[col] = (ch, cor, fundo, attr, lk, sy)
        col += 1
        if ww and col > direita():
            quebra()

    def atributos(c=None):
        a = (SUB if ul else 0) | (PISCA if bk else 0) | (INVERTE if iv else 0)
        if c is not None:
            if 'UL' in c.liga: a |= SUB
            if 'UL' in c.tira: a &= ~SUB
            if 'BK' in c.liga: a |= PISCA
            if 'IV' in c.liga: a |= INVERTE
        if a & PISCA:
            pag.pisca = True
        return a

    def escreve(s, cor, fundo, attr, lk=-1, cores=None):
        nonlocal col, lin
        for i, ch in enumerate(s):
            o = ord(ch)
            if o == 10:
                lin += 1
                col = inicio()
                linha_atual()
            elif o == 13 or o == 5:   # 5 e a posicao do cursor gravada no arquivo
                pass
            elif o == 9:
                while True:
                    poe(32, cor, fundo, attr, lk)
                    if col % 8 == 0:
                        break
            else:
                if o == 31:           # CH_SHIFT_SPACE
                    o = 32
                poe(o, (cores[i] if cores and cores[i] is not None else cor), fundo, attr, lk)

    def alinha(c, n):
        nonlocal col
        if 'CX' in c.liga:
            col = max(0, (largura - n) // 2)
        elif 'RX' in c.liga:
            col = max(0, largura - n)
        elif 'LX' in c.liga:
            col = 0

    partes = doc.partes
    i, total = 0, len(partes)
    while i < total:
        p = partes[i]
        pag.marcas[i] = lin
        if isinstance(p, Trecho):
            cores = None
            if hl:
                if realce is None:
                    realce = Realce(indice().tipo)
                cores = realce.cores(p.texto)
            escreve(p.texto, fg, bg, atributos(), cores=cores)
            i += 1
            continue
        n = p.nome
        if n == 'FG':
            fg = _cor(p, fg_padrao)
        elif n == 'BG':
            bg = _cor(p, bg_padrao)
        elif n == 'FD':
            fg_padrao = _cor(p, fg_padrao); fg = fg_padrao
        elif n == 'BD':
            bg_padrao = _cor(p, bg_padrao); bg = bg_padrao
        elif n in CORES:   # $RED$ e o mesmo que $FG,RED$
            fg = CORES[n]
        elif n == 'WW':
            ww = _num(p.nums[0] if p.nums else '1', 1) != 0
        elif n == 'HL':
            hl = _num(p.nums[0] if p.nums else '1', 1) != 0
        elif n == 'BK':
            bk = _num(p.nums[0] if p.nums else '1', 1) != 0
        elif n == 'IV':
            iv = _num(p.nums[0] if p.nums else '1', 1) != 0
        elif n == 'UL':
            ul = _num(p.nums[0] if p.nums else '1', 1) != 0
        elif n == 'SY':
            sy = _num(p.nums[0] if p.nums else '0')
        elif n == 'LM':
            na_margem = col == inicio()
            lm = _num(p.nums[0] if p.nums else '0')
            if na_margem:
                col = inicio()
        elif n == 'RM':
            rm = _num(p.nums[0] if p.nums else '0')
            if 'WR' in p.liga:
                rm = largura - 1 - rm
        elif n == 'ID':
            na_margem = col == inicio()
            v = _num(p.nums[0] if p.nums else '0')
            indent = v if 'LX' in p.liga else indent + v
            indent = max(0, indent)
            if na_margem:
                col = inicio()
        elif n == 'CM':
            dx = _num(p.nums[0] if p.nums else '0')
            dy = _num(p.nums[1] if len(p.nums) > 1 else '0')
            col = dx if 'LX' in p.liga else col + dx
            lin = max(0, lin + dy)
            linha_atual()
        elif n == 'PB':
            escreve('\n', fg, bg, 0)
        elif n == 'TX':
            t = p.tag or ''
            alinha(p, len(t))
            escreve(t, fg, bg, atributos(p))
        elif n == 'LK':
            t = p.tag if p.tag is not None else p.alvo()
            lk = len(pag.links)
            pag.links.append(('alvo', p.alvo()))
            alinha(p, len(t))
            a = atributos(p) | (0 if 'UL' in p.tira else SUB)
            c0, l0 = col, lin
            escreve(t, LINK, bg, a, lk)
            if 'B' in p.liga and lin == l0:
                bordas.append((l0, c0, col))
        elif n in ('MA', 'BT', 'MU'):
            t = p.tag or ''
            lk = len(pag.links)
            pag.links.append(('macro', p.args.get('LM', '')))
            alinha(p, len(t))
            a = atributos(p) | (0 if 'UL' in p.tira or n == 'BT' else SUB)
            c0, l0 = col, lin
            escreve(t, MACRO, bg, a, lk)
            if (n == 'BT' or 'B' in p.liga) and lin == l0:
                bordas.append((l0, c0, col))
        elif n == 'TR':
            ini, fim, colapsada = doc.arvores[i]
            colapsada = not abertos[i] if i in abertos else colapsada
            lk = len(pag.links)
            pag.links.append(('arvore', i))
            escreve(('+] ' if colapsada else '-] ') + (p.tag or ''), ARVORE, bg,
                    atributos(p) | (0 if 'UL' in p.tira else SUB), lk)
            if colapsada and fim >= ini:
                # o que esta entre a arvore e o primeiro $ID$ continua visivel
                j = i + 1
                while j < ini:
                    pag.marcas[j] = lin
                    q = partes[j]
                    if isinstance(q, Trecho):
                        escreve(q.texto, fg, bg, atributos())
                    j += 1
                for j in range(ini, fim + 1):
                    pag.marcas[j] = lin
                i = fim + 1
                continue
        elif n == 'AN':
            a = p.args.get('A') or p.tag or ''
            pag.ancoras[a] = lin
            if p.tag:
                escreve(p.tag, ANCORA, bg, atributos(p))
        elif n == 'SP':
            t = p.tag or ''
            lk = -1
            if 'A' in p.args:
                lk = len(pag.links)
                pag.links.append(('alvo', p.args['A']))
            escreve(t, BIN, bg, atributos(p), lk)
            num = _num(p.args.get('BI', ''), -1)
            if num in doc.bins:
                # a origem do sprite fica depois da tag (sem FROM_START em DocRecalc)
                pag.sprites.append((col, lin, num, lk))
        elif n in ('IB', 'IS'):
            escreve(p.tag or '', BIN, bg, atributos(p))
        elif n == 'PT':
            fg = CORES['GREEN']
        i += 1

    for l0, c0, c1 in bordas:  # TextBorder: glifos em volta, nas linhas de cima e de baixo
        w = c1 - c0
        def caixa(y, x, ch):
            if y < 0 or x < 0 or y >= len(pag.linhas):
                return
            q = pag.linhas[y]
            if x >= len(q):
                q.extend([None] * (x + 1 - len(q)))
            q[x] = (ch, MACRO, bg_padrao, 0, -1, 0)
        caixa(l0, c0 - 1, 4); caixa(l0, c1, 4)
        caixa(l0 - 1, c0 - 1, 6); caixa(l0 - 1, c1, 8)
        caixa(l0 + 1, c0 - 1, 10); caixa(l0 + 1, c1, 12)
        for x in range(c0, c1):
            caixa(l0 - 1, x, 2); caixa(l0 + 1, x, 2)

    pag.largura_max = max((len(l) for l in pag.linhas), default=0)
    return pag
