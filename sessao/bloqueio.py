"""Bloquear a tela: trava/trava.c com uma passagem da Biblia.

Quem chama: o Ctrl+Alt+L do atalhos.py e o protetor.py (Lock() pelo D-Bus e o
bloqueio por inatividade). Cada um tem o seu oraculo de Deus.

A reserva (a tela de login do LightDM) entra se o binario nao existir e se ele
sair com erro, inclusive se cair com a tela ja bloqueada. Em outro gerenciador
de login, ver TEMPLEOS_RESERVA_BLOQUEIO no sessao.conf.
"""
import os, shlex, subprocess, sys

import x11, deus

def bloqueada():
    """A selecao _TEMPLEOS_TRAVA tem dono enquanto o trava esta na tela."""
    return x11.x11.XGetSelectionOwner(x11.DPY, x11.atomo('_TEMPLEOS_TRAVA')) != 0

def texto_da_passagem(oraculo):
    oraculo.esvazia()
    oraculo.insere()
    ref, linhas = deus.passagem(oraculo, 16)
    # A Biblia vem em linhas de ~70 colunas: a passagem cai no meio de uma
    # frase. Na tela de bloqueio ela comeca no versiculo da referencia.
    versiculo = ref.rsplit(' ', 1)[-1]
    i = next((i for i, l in enumerate(linhas) if l.startswith(versiculo + ' ')), 0)
    return '\n'.join([ref] + linhas[i:i + 6]) + '\n'

def bloqueia(oraculo, env):
    reserva = os.environ.get('TEMPLEOS_RESERVA_BLOQUEIO') or 'dm-tool lock'
    cfg = os.environ.get('TEMPLEOS_CFG') or os.path.expanduser('~/.config/templeos')
    trava = os.path.join(cfg, 'trava')
    if not os.access(trava, os.X_OK):
        subprocess.Popen(reserva, shell=True, start_new_session=True, env=env)
        return
    try:
        texto = texto_da_passagem(oraculo)
    except Exception as e:  # sem passagem, mas nunca sem bloquear
        print('passagem falhou:', e, file=sys.stderr)
        texto = ''
    p = subprocess.Popen('%s || %s' % (shlex.quote(trava), reserva), shell=True,
                         stdin=subprocess.PIPE, start_new_session=True, env=env)
    p.stdin.write(texto.encode('cp437', 'replace'))
    p.stdin.close()
