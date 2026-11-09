#!/usr/bin/env python3
"""Imprime a fonte 8x8 do TempleOS como cabecalho C para o trava.c.

Compilada dentro do binario, e nao lida em tempo de execucao: o bloqueador nao
pode depender de um arquivo que talvez nao abra na hora de desenhar a tela.
"""
import json, os

raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
glifos = json.load(open(os.path.join(raiz, 'dados', 'fonte8x8.json')))
print('static const unsigned long long FONTE[256] = {')
for i in range(0, 256, 4):
    print('  ' + ' '.join('0x%016xULL,' % g for g in glifos[i:i + 4]))
print('};')
