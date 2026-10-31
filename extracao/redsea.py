#!/usr/bin/env python3
"""Extrai o sistema de arquivos RedSea de uma ISO do TempleOS e expande os .Z."""
import os, struct, sys

ISO, OUT = sys.argv[1], sys.argv[2]
img = open(ISO, 'rb').read()
BLK = 512
MAXE = 4095  # ARC_MAX_TABLE_ENTRY

def expand(buf):
    csize, esize, ctype = struct.unpack_from('<qqB', buf, 0)
    if ctype == 1:
        return buf[17:17+esize]
    min_bits = 7 if ctype == 2 else 8
    min_entry = 1 << min_bits
    base = [MAXE]*(MAXE+1); ch = [0]*(MAXE+1)
    for i in range(min_entry):
        ch[i] = i
    kids = [set() for _ in range(MAXE+1)]  # hash[] do original: so recicla folhas
    st = dict(free_idx=min_entry, nbits=min_bits+1, free_limit=1 << (min_bits+1),
              cur=None, nxt=None, used=True)
    def get_entry():
        if not st['used']:
            return
        i = st['free_idx']; st['used'] = False
        st['cur'] = st['nxt']
        if st['nbits'] < 12:
            st['nxt'] = i; i += 1
            if i == st['free_limit']:
                st['nbits'] += 1; st['free_limit'] = 1 << st['nbits']
        else:
            while True:
                i += 1
                if i == st['free_limit']:
                    i = min_entry
                if not kids[i]:
                    break
            st['nxt'] = i
            kids[base[i]].discard(i)
        st['free_idx'] = i
    get_entry(); st['used'] = True
    srcbits = csize*8; pos = 17*8
    src = bytes(buf[:csize]) + b'\0\0\0\0'
    def rd(n):
        nonlocal pos
        b = pos >> 3
        v = (int.from_bytes(src[b:b+4], 'little') >> (pos & 7)) & ((1 << n)-1)
        pos += n; return v
    out = bytearray()
    last = rd(st['nbits']); out.append(last & 0xff)
    get_entry(); st['used'] = True; last_ch = last
    while len(out) < esize and pos + st['nbits'] <= srcbits:
        code = rd(st['nbits'])
        stack = []
        if st['cur'] == code:
            stack.append(last_ch); t = last
        else:
            t = code
        while base[t] != MAXE:
            stack.append(ch[t]); t = base[t]
        last_ch = ch[t]
        base[st['cur']] = last; ch[st['cur']] = last_ch
        kids[last].add(st['cur'])
        get_entry(); st['used'] = True
        stack.append(last_ch)
        out += bytes(reversed(stack))
        last = code
    return bytes(out[:esize])

def walk(clus, size, path):
    d = img[clus*BLK:clus*BLK+size]
    for o in range(64, len(d), 64):
        e = d[o:o+64]
        attr = struct.unpack_from('<H', e)[0]
        name = e[2:40].split(b'\0')[0].decode('latin1')
        if not name or name in ('.', '..'):
            continue
        c, s = struct.unpack_from('<qq', e, 40)
        p = os.path.join(path, name)
        if attr & 0x10:
            os.makedirs(p, exist_ok=True); walk(c, s, p)
        else:
            data = img[c*BLK:c*BLK+s]
            if name.endswith('.Z'):
                try:
                    data = expand(data); p = p[:-2]
                except Exception as ex:
                    print('falhou', p, ex)
            open(p, 'wb').write(data)

root = struct.unpack_from('<q', img, 50176+40)[0]
os.makedirs(OUT, exist_ok=True)
walk(98, 1536, OUT)
