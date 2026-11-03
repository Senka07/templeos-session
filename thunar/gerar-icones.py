#!/usr/bin/env python3
"""Gera o tema de icones "TempleOS-Thunar": icones de uma cor so, no azul do texto.

Base: os icones simbolicos do Adwaita (pastas, tipos de arquivo, locais,
acoes), com toda cor trocada pelo azul (BLUE, #0000AA). Cada um sai com o nome
normal (o que a vista de arquivos do Thunar pede, e que o GTK desenha como esta)
e com o nome -symbolic (o que menus e barra pedem; esses o GTK repinta com a
cor do texto, entao ficam brancos no item selecionado).

O GTK procura tema por tema, e dentro de cada tema nome por nome: um arquivo
.py pede "text-x-python" e depois "text-x-generic", e o "text-x-generic" daqui
ganha do "text-x-python" colorido do tema herdado. Assim os genericos cobrem
quase todos os tipos. O que nao estiver aqui (icones de apps no "Abrir com")
vem do Adwaita e do hicolor, com as cores de sempre.

Uso: gerar-icones.py [diretorio-de-icones]   (padrao: build/icons)
"""
import glob, os, re, shutil, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, 'build', 'icons'),
                    'TempleOS-Thunar')
ORIGEM = '/usr/share/icons/Adwaita/symbolic'
AZUL = '#0000AA'

# fill/stroke em atributo ou em style; "none" e url(#...) ficam como estao
COR = re.compile(r'((?:fill|stroke|stop-color|color)\s*[:=]\s*["\']?)(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|[a-z]+(?=["\';\s]))')

def recolore(svg):
    def troca(m):
        valor = m.group(2)
        if valor in ('none', 'currentColor', 'transparent', 'inherit'):
            return m.group(0)
        return m.group(1) + AZUL
    svg = COR.sub(troca, svg)
    # caminho sem fill herda o preto padrao do SVG: o azul vai na raiz
    return re.sub(r'<svg\b(?![^>]*\sfill=)', '<svg fill="%s"' % AZUL, svg, count=1)

if os.path.islink(DEST):  # nunca escrever atraves de um link (o HOME falso do teste)
    os.unlink(DEST)
elif os.path.isdir(DEST):
    shutil.rmtree(DEST)
contextos = []
for pasta in sorted(glob.glob(os.path.join(ORIGEM, '*'))):
    ctx = os.path.basename(pasta)
    if ctx == 'legacy':  # nomes antigos duplicados
        continue
    alvo = os.path.join(DEST, 'scalable', ctx)
    os.makedirs(alvo)
    for f in sorted(glob.glob(os.path.join(pasta, '*-symbolic.svg'))):
        nome = os.path.basename(f)[:-len('-symbolic.svg')]
        open(os.path.join(alvo, nome + '.svg'), 'w').write(recolore(open(f).read()))
        os.symlink(nome + '.svg', os.path.join(alvo, nome + '-symbolic.svg'))
    contextos.append(ctx)

# Tipos de arquivo. O Thunar nao pede a lista de nomes ao GTK de uma vez: fica
# com o primeiro nome que existe em qualquer tema ("text-plain" antes de
# "text-x-generic"), e um icone colorido que algum app pos no hicolor ganhava.
# Entao cada tipo do shared-mime-info ganha aqui o nome dele, apontando para o
# generico azul do grupo (o generic-icon do proprio banco MIME).
MIME = '/usr/share/mime'
GRUPO = {'text': 'text-x-generic', 'image': 'image-x-generic', 'audio': 'audio-x-generic',
         'video': 'video-x-generic', 'font': 'font-x-generic', 'inode': 'inode-directory',
         'model': 'image-x-generic', 'message': 'text-x-generic', 'multipart': 'package-x-generic'}
existentes = {os.path.basename(f)[:-4]: f
              for f in glob.glob(os.path.join(DEST, 'scalable', '*', '*.svg'))
              if not f.endswith('-symbolic.svg')}
def le_mapa(nome):
    try:
        return dict(l.strip().split(':', 1) for l in open(os.path.join(MIME, nome)) if ':' in l)
    except OSError:
        return {}
genericos, proprios = le_mapa('generic-icons'), le_mapa('icons')
try:
    tipos = [l.strip() for l in open(os.path.join(MIME, 'types')) if '/' in l]
except OSError:
    tipos = []
# apelidos (application/x-shellscript = text/x-shellscript etc.) seguem o canonico
try:
    for l in open(os.path.join(MIME, 'aliases')):
        partes = l.split()
        if len(partes) == 2:
            tipos.append(partes[0])
            genericos.setdefault(partes[0], genericos.get(partes[1], partes[1].split('/')[0] + '-x-generic'))
except OSError:
    pass
alvo_mime = os.path.join(DEST, 'scalable', 'mimetypes')
apelidos = 0
for t in tipos:
    grupo = t.split('/')[0]
    g = genericos.get(t, grupo + '-x-generic')
    destino = existentes.get(g) or existentes.get(GRUPO.get(grupo, 'text-x-generic'))
    for nome in {t.replace('/', '-'), proprios.get(t, ''), g}:
        if not nome or nome in existentes:
            continue
        rel = os.path.relpath(destino, alvo_mime)
        os.symlink(rel, os.path.join(alvo_mime, nome + '.svg'))
        os.symlink(rel, os.path.join(alvo_mime, nome + '-symbolic.svg'))
        existentes[nome] = os.path.join(alvo_mime, nome + '.svg')
        apelidos += 1
print('tipos de arquivo apontados para os genericos:', apelidos)

CONTEXTO = {'actions': 'Actions', 'apps': 'Applications', 'categories': 'Categories',
            'devices': 'Devices', 'emblems': 'Emblems', 'emotes': 'Emotes',
            'mimetypes': 'MimeTypes', 'places': 'Places', 'status': 'Status', 'ui': 'UI'}
with open(os.path.join(DEST, 'index.theme'), 'w') as f:
    f.write('[Icon Theme]\nName=TempleOS-Thunar\n'
            'Comment=Icones simbolicos do Adwaita no azul do TempleOS (gerado)\n'
            'Inherits=Adwaita,hicolor\nHidden=true\n'
            'Directories=%s\n' % ','.join('scalable/' + c for c in contextos))
    for c in contextos:
        f.write('\n[scalable/%s]\nContext=%s\nSize=16\nMinSize=8\nMaxSize=512\nType=Scalable\n'
                % (c, CONTEXTO.get(c, c.capitalize())))
print('icones em', DEST, '(%d)' % sum(len(glob.glob(os.path.join(DEST, 'scalable', c, '*-symbolic.svg')))
                                     for c in contextos))
