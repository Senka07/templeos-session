"""O pouco de Xlib que a sessao usa, via ctypes (nao ha python-xlib instalado).

Cada processo abre a sua conexao (DPY). O tratador de erro troca o padrao da
Xlib, que encerra o processo: um XGrabKey recusado (BadAccess, outro cliente ja
pegou a tecla) ou uma janela que sumiu no meio do caminho nao derrubam nada.
"""
import ctypes
from ctypes import (c_char, c_char_p, c_int, c_long, c_uint, c_ubyte, c_ulong,
                    c_void_p, POINTER, Structure, Union, byref)

x11 = ctypes.CDLL('libX11.so.6')

def _f(nome, res, args):
    fn = getattr(x11, nome)
    fn.restype, fn.argtypes = res, args

_f('XOpenDisplay', c_void_p, [c_char_p])
_f('XDefaultRootWindow', c_ulong, [c_void_p])
_f('XConnectionNumber', c_int, [c_void_p])
_f('XInternAtom', c_ulong, [c_void_p, c_char_p, c_int])
_f('XChangeProperty', c_int, [c_void_p, c_ulong, c_ulong, c_ulong, c_int, c_int, c_void_p, c_int])
_f('XGetWindowProperty', c_int, [c_void_p, c_ulong, c_ulong, c_long, c_long, c_int, c_ulong,
                                 POINTER(c_ulong), POINTER(c_int), POINTER(c_ulong),
                                 POINTER(c_ulong), POINTER(c_void_p)])
_f('XFree', c_int, [c_void_p])
_f('XFlush', c_int, [c_void_p])
_f('XSync', c_int, [c_void_p, c_int])
_f('XPending', c_int, [c_void_p])
_f('XNextEvent', c_int, [c_void_p, c_void_p])
_f('XSendEvent', c_int, [c_void_p, c_ulong, c_int, c_long, c_void_p])
_f('XGrabKey', c_int, [c_void_p, c_int, c_uint, c_ulong, c_int, c_int, c_int])
_f('XStringToKeysym', c_ulong, [c_char_p])
_f('XKeysymToKeycode', c_ubyte, [c_void_p, c_ulong])
_f('XKeysymToString', c_char_p, [c_ulong])
_f('XkbKeycodeToKeysym', c_ulong, [c_void_p, c_ubyte, c_int, c_int])
_f('XQueryKeymap', c_int, [c_void_p, c_char * 32])
_f('XGetSelectionOwner', c_ulong, [c_void_p, c_ulong])

_TRATADOR = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)(lambda d, e: 0)
x11.XSetErrorHandler.argtypes = [ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)]
x11.XSetErrorHandler(_TRATADOR)

DPY = x11.XOpenDisplay(None)
RAIZ = x11.XDefaultRootWindow(DPY)

KEYPRESS, KEYRELEASE, CLIENTMESSAGE = 2, 3, 33
SHIFT, LOCK, CTRL, ALT, NUMLOCK, SUPER = 1, 2, 4, 8, 16, 64

class XKeyEvent(Structure):
    _fields_ = [('type', c_int), ('serial', c_ulong), ('send_event', c_int),
                ('display', c_void_p), ('window', c_ulong), ('root', c_ulong),
                ('subwindow', c_ulong), ('time', c_ulong), ('x', c_int), ('y', c_int),
                ('x_root', c_int), ('y_root', c_int), ('state', c_uint),
                ('keycode', c_uint), ('same_screen', c_int)]

class XClientMessageEvent(Structure):
    _fields_ = [('type', c_int), ('serial', c_ulong), ('send_event', c_int),
                ('display', c_void_p), ('window', c_ulong), ('message_type', c_ulong),
                ('format', c_int), ('data', c_long * 5)]

class XEvent(Union):
    _fields_ = [('type', c_int), ('xkey', XKeyEvent),
                ('xclient', XClientMessageEvent), ('pad', c_long * 24)]

_atomos = {}
def atomo(nome):
    if nome not in _atomos:
        _atomos[nome] = x11.XInternAtom(DPY, nome.encode(), False)
    return _atomos[nome]

def propriedade(janela, nome):
    """Valores de 32 bits (janelas, atomos, cardinais) de uma propriedade."""
    tipo, fmt, n, resto = c_ulong(), c_int(), c_ulong(), c_ulong()
    dados = c_void_p()
    if x11.XGetWindowProperty(DPY, janela, atomo(nome), 0, 4096, False, 0, byref(tipo),
                              byref(fmt), byref(n), byref(resto), byref(dados)) != 0 \
            or not dados.value:
        return []
    r = list(ctypes.cast(dados, POINTER(c_ulong))[:n.value]) if fmt.value == 32 else []
    x11.XFree(dados)
    return r

def define_cardinais(janela, nome, valores):
    arr = (c_long * len(valores))(*valores)
    x11.XChangeProperty(DPY, janela, atomo(nome), atomo('CARDINAL'), 32, 0, byref(arr), len(valores))
    x11.XFlush(DPY)

def mensagem_raiz(janela, tipo, *dados):
    """ClientMessage para o WM, como os pagers fazem (EWMH)."""
    ev = XEvent()
    ev.xclient.type = CLIENTMESSAGE
    ev.xclient.send_event = 1
    ev.xclient.window = janela
    ev.xclient.message_type = atomo(tipo)
    ev.xclient.format = 32
    for i, v in enumerate(dados[:5]):
        ev.xclient.data[i] = v
    x11.XSendEvent(DPY, RAIZ, False, (1 << 20) | (1 << 19), byref(ev))  # SubstructureRedirect|Notify
    x11.XFlush(DPY)

def janela_ativa():
    v = propriedade(RAIZ, '_NET_ACTIVE_WINDOW')
    return v[0] if v else 0

def janelas_normais():
    """Clientes de baixo para cima, sem a linha de status, o fundo e os avisos."""
    fora = {atomo('_NET_WM_WINDOW_TYPE_DOCK'), atomo('_NET_WM_WINDOW_TYPE_DESKTOP'),
            atomo('_NET_WM_WINDOW_TYPE_NOTIFICATION')}
    return [j for j in propriedade(RAIZ, '_NET_CLIENT_LIST_STACKING')
            if not fora & set(propriedade(j, '_NET_WM_WINDOW_TYPE'))]

def keysym_nome(keycode):
    s = x11.XKeysymToString(x11.XkbKeycodeToKeysym(DPY, keycode, 0, 0))
    return s.decode() if s else ''

def pega_tecla(keysym, mods):
    """XGrabKey na raiz, repetido com NumLock e CapsLock para valer com eles ligados."""
    kc = x11.XKeysymToKeycode(DPY, x11.XStringToKeysym(keysym.encode()))
    if not kc:
        return None
    for extra in (0, NUMLOCK, LOCK, NUMLOCK | LOCK):
        x11.XGrabKey(DPY, kc, mods | extra, RAIZ, True, 1, 1)
    x11.XSync(DPY, False)
    return kc
