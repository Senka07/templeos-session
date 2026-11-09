#!/usr/bin/env python3
"""Renderiza os sprites (CSprite) embutidos nos documentos DolDoc do TempleOS."""
import math, re, struct, sys
from PIL import Image, ImageDraw

PAL = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),
       (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]
GX = [-1,0,1,-1,1,-1,0,1]; GY = [-1,-1,-1,0,0,1,1,1]
BASE = {0:1,1:2,2:3,3:5,4:17,5:1,6:1,7:9,8:9,9:13,10:17,11:5,12:17,13:25,14:13,15:25,16:29,
        17:5,18:5,19:5,20:5,21:9,22:9,23:17,24:9,25:21,26:17,27:9,28:9,29:9}

def doc_bins(path):
    d = open(path, 'rb').read()
    if b'\0' not in d: return '', {}
    i = d.index(b'\0') + 1
    text = d[:i-1].decode('latin1')
    bins = {}
    while i + 16 <= len(d):
        num, flags, size, use = struct.unpack_from('<IIII', d, i); i += 16
        bins[num] = d[i:i+size]; i += size
    return text, bins

def render(elems, font, scale=1, origem=False):
    """origem=True devolve (imagem, x, y): onde o canto dela fica em relacao a origem do sprite."""
    W = 1024; img = Image.new('RGBA', (W, W), (0,0,0,0)); dr = ImageDraw.Draw(img)
    O = W//2; col = (0,0,0,255); thick = 1; x0 = y0 = 0; p = 0
    def P(x, y): return (O+x+x0, O+y+y0)
    def text(x, y, s):
        for k, c in enumerate(s.encode('latin1')):
            v = font[c]
            for yy in range(8):
                r = (v >> (8*yy)) & 0xff
                for xx in range(8):
                    if r >> xx & 1: img.putpixel(P(x+8*k+xx, y+yy), col)
    while p < len(elems):
        t = elems[p] & 0x7f
        if t == 0: break
        e = elems[p+1:]
        if t == 1: col = PAL[e[0] & 15] + (255,)
        elif t == 2: col = PAL[e[0] & 15] + (255,)
        elif t == 3: thick = max(1, struct.unpack_from('<i', e)[0])
        elif t == 7:
            a, b = struct.unpack_from('<ii', e); x0 += a; y0 += b
        elif t == 8:
            a, b = struct.unpack_from('<ii', e); img.putpixel(P(a, b), col)
        elif t in (10, 26):
            a, b, c, d = struct.unpack_from('<iiii', e); dr.line([P(a,b), P(c,d)], col, thick)
        elif t == 12:
            a, b, c, d = struct.unpack_from('<iiii', e)
            dr.rectangle([P(a,b), (P(c,d)[0]-1, P(c,d)[1]-1)], col)
        elif t == 13:
            a, b, c, d, ang = struct.unpack_from('<iiiid', e)
            w, h = c-a, d-b; ca, sa = math.cos(-ang), math.sin(-ang)
            pts = [P(a+u*ca-v*sa, b+u*sa+v*ca) for u, v in ((0,0),(w,0),(w,h),(0,h))]
            dr.polygon(pts, col)
        elif t == 14:
            a, b, r = struct.unpack_from('<iii', e); cx, cy = P(a, b)
            dr.ellipse([cx-r, cy-r, cx+r, cy+r], outline=col, width=thick)
        elif t in (15, 16):
            a, b, w, h, ang = struct.unpack_from('<iiiid', e)
            n = struct.unpack_from('<i', e, 24)[0] if t == 16 else 64
            cx, cy = P(a, b); ca, sa = math.cos(ang), math.sin(ang); pts = []
            for k in range(n+1):
                q = 2*math.pi*k/n; u, v = w*math.cos(q), h*math.sin(q)
                pts.append((cx+u*ca-v*sa, cy+u*sa+v*ca))
            dr.line(pts, col, thick)
        elif t == 11:
            n = struct.unpack_from('<i', e)[0]; pts = struct.unpack_from('<%di' % (2*n), e, 4)
            dr.line([P(pts[2*k], pts[2*k+1]) for k in range(n)], col, thick)
        elif t == 9:
            n, a, b = struct.unpack_from('<iii', e); bits = int.from_bytes(e[12:12+(n*3+7)//8+1], 'little')
            img.putpixel(P(a, b), col)
            for k in range(n):
                j = (bits >> (3*k)) & 7; a += GX[j]; b += GY[j]; img.putpixel(P(a, b), col)
        elif 17 <= t <= 20:
            n = struct.unpack_from('<i', e)[0]; pts = struct.unpack_from('<%di' % (3*n), e, 4)
            pts = [P(pts[3*k], pts[3*k+1]) for k in range(n)]
            if t in (18, 20): pts.append(pts[0])
            dr.line(pts, col, thick)
        elif t in (21, 22):
            a, b = struct.unpack_from('<ii', e)
            try: ImageDraw.floodfill(img, P(a, b), col, border=col if t == 22 else None)
            except Exception: pass
        elif t == 23:
            a, b, w, h = struct.unpack_from('<iiii', e); wi = (w+7) & ~7
            for yy in range(h):
                for xx in range(w):
                    c = e[16+yy*wi+xx]
                    if c != 0xff: img.putpixel(P(a+xx, b+yy), PAL[c & 15] + (255,))
        elif t in (27, 28, 29):
            a, b = struct.unpack_from('<ii', e); s = e[8:e.index(b'\0', 8)].decode('latin1'); text(a, b, s)
            p += 1 + BASE[t] - 1 + len(s) + 1; continue
        size = BASE[t]
        if t == 11: size += struct.unpack_from('<i', e)[0]*8
        elif t == 9: size += (struct.unpack_from('<i', e)[0]*3+7) >> 3
        elif 17 <= t <= 20: size += struct.unpack_from('<i', e)[0]*12
        elif t == 23:
            w, h = struct.unpack_from('<ii', e, 8); size += ((w+7) & ~7)*h
        elif t == 24:
            vc, tc = struct.unpack_from('<ii', e); size += vc*12 + tc*16
        elif t == 25:
            vc, tc = struct.unpack_from('<ii', e, 12); size += vc*12 + tc*16
        p += size
    bb = img.getbbox()
    if origem:
        return (img.crop(bb), bb[0] - O, bb[1] - O) if bb else None
    return img.crop(bb) if bb else None

if __name__ == '__main__':
    fsrc = open(sys.argv[1], 'rb').read().decode('latin1')
    font = [int(x, 16) for x in re.findall(r'0x([0-9A-F]{16})', fsrc)][:256]
    out = sys.argv[2]
    for path in sys.argv[3:]:
        text, bins = doc_bins(path)
        tags = dict((int(m.group(2)), m.group(1)) for m in re.finditer(r'\$SP[^,$]*,"([^"]*)"[^$]*?BI=(\d+)', text))
        for num, data in bins.items():
            im = render(data, font)
            if im:
                name = re.sub(r'[^A-Za-z0-9]+', '', tags.get(num, '')) or 'bin%d' % num
                stem = re.sub(r'\W', '_', path.split('iso/')[-1])
                im.save('%s/%s__%s.png' % (out, stem, name))
