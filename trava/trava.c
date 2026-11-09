/* Bloqueador de tela da sessao TempleOS.
 *
 * O TempleOS nao tem senha nem bloqueio; o desenho vem das janelas dele: fundo
 * azul, moldura de linha dupla (janela em foco) feita dos glifos 3..13 da fonte
 * e linha de status no topo. Uma passagem da Biblia vem pela entrada padrao
 * (referencia na primeira linha); o atalhos.py escolhe com o oraculo.
 *
 * Em C, e nao no GTK do resto da sessao, porque um bloqueador em X11 que cai
 * devolve a tela destravada. Por isso tambem:
 *
 *   saida 0     so com a senha certa (ou --timeout, ou se ja ha outro bloqueio)
 *   saida != 0  qualquer outra coisa: nao pegou o teclado, PAM quebrado, sinal.
 *               Quem chama faz `trava || dm-tool lock`, entao uma falha cai na
 *               tela de login do LightDM, nunca na sessao aberta.
 *
 * Servico PAM: vlock (pam_unix puro; no Arch vem no pacote kbd). As pilhas login e
 * system-auth passam pelo pam_faillock, que bloquearia a conta inteira por
 * senha errada aqui, onde e facil errar o layout do teclado.
 *
 * A selecao _TEMPLEOS_TRAVA marca a tela como bloqueada (o X a solta sozinho se
 * o processo morrer); o avisos.py olha para ela e segura as notificacoes.
 *
 * Uso: trava [--timeout SEGUNDOS]
 *   --timeout destrava sozinho e mostra a contagem: e o jeito seguro de testar
 *   a senha pela primeira vez.
 *
 * Teste automatico: -DSENHA_TESTE='"..."' troca o PAM por uma comparacao. O
 * instalar.sh nao define isso.
 */
#define _GNU_SOURCE
#include <X11/XKBlib.h>
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#include <locale.h>
#include <poll.h>
#include <pwd.h>
#include <security/pam_appl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <time.h>
#include <unistd.h>

#include "fonte8x8.h" /* gerado de dados/fonte8x8.json pelo instalar.sh */

#define SERVICO_PAM "vlock"

enum { E = 2, C = 8 * E };
enum { BLUE = 1, RED = 4, LTGRAY = 7, LTBLUE = 9, WHITE = 15 };
static const unsigned PALETA[16] = {
    0x000000, 0x0000AA, 0x00AA00, 0x00AAAA, 0xAA0000, 0xAA00AA, 0xAA5500, 0xAAAAAA,
    0x555555, 0x5555FF, 0x55FF55, 0x55FFFF, 0xFF5555, 0xFF55FF, 0xFFFF55, 0xFFFFFF};
/* glifos de moldura em linha dupla (ver BORDAS em xfwm4/gerar-tema.py) */
enum { H2 = 3, V2 = 5, SE2 = 7, SD2 = 9, IE2 = 11, ID2 = 13 };

enum { MAX_LINHAS = 12, MAX_COLS = 200, MIN_COLS = 46, FICHAS = 8 };

static Display *dpy;
static Window raiz, win;
static GC gc;
static int larg, alt;
static XIC ic;

static char senha[1024];
static size_t nsenha;
static char fichas[FICHAS + 1]; /* desenho do campo: nao entrega o tamanho da senha */

static char passagem[MAX_LINHAS + 1][MAX_COLS + 1];
static int npassagem;
static const char *usuario;
static char layouts[8][16];
static int nlayouts;

static XImage *img_dlg, *img_topo;
static int dlg_cols, dlg_lins, topo_cols;

static const char *aviso = "";
static int erros;
static long timeout_fim; /* relogio monotonico; 0 = sem --timeout */

static long agora_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000L + t.tv_nsec / 1000000L;
}

static void limpa_senha(void) {
    explicit_bzero(senha, sizeof senha);
    nsenha = 0;
    fichas[0] = 0;
}

/* ------------------------------------------------------------ desenho */
static XImage *nova_imagem(int cols, int lins) {
    int w = cols * C, h = lins * C, tela = DefaultScreen(dpy);
    char *px = malloc((size_t)w * h * 4);
    XImage *im;
    if (!px)
        exit(1);
    im = XCreateImage(dpy, DefaultVisual(dpy, tela), DefaultDepth(dpy, tela), ZPixmap, 0, px,
                      w, h, 32, 0);
    /* escrevemos 0xRRGGBB direto; outro formato de tela cai na tela de login */
    if (!im || im->bits_per_pixel != 32 || im->red_mask != 0xFF0000 || im->blue_mask != 0xFF)
        exit(1);
    return im;
}

static void troca_imagem(XImage **im, int cols, int lins) {
    if (*im)
        XDestroyImage(*im); /* libera os pixels tambem */
    *im = nova_imagem(cols, lins);
}

static void glifo(XImage *im, int col, int lin, unsigned char ch, int fg, int bg) {
    unsigned long long v = FONTE[ch];
    unsigned f = PALETA[fg], b = PALETA[bg];
    int x, y, i, j;
    if (col < 0 || lin < 0 || (col + 1) * C > im->width || (lin + 1) * C > im->height)
        return;
    for (y = 0; y < 8; y++)
        for (x = 0; x < 8; x++) {
            unsigned p = (v >> (8 * y + x)) & 1 ? f : b;
            for (j = 0; j < E; j++) {
                unsigned *linha = (unsigned *)(im->data + (lin * C + y * E + j) * im->bytes_per_line);
                for (i = 0; i < E; i++)
                    linha[col * C + x * E + i] = p;
            }
        }
}

static void escreve(XImage *im, int col, int lin, const char *s, int fg, int bg) {
    for (; *s; s++, col++)
        glifo(im, col, lin, (unsigned char)*s, fg, bg);
}

/* Quantas linhas da passagem cabem na tela e o tamanho do dialogo */
static int linhas_de_passagem(void) {
    int cabe = alt / C - 2 - 11; /* status em cima + moldura e campos */
    if (cabe < 0)
        cabe = 0;
    return npassagem < cabe ? npassagem : cabe;
}

static void dimensiona(void) {
    int i, n = linhas_de_passagem(), cols = MIN_COLS, max_cols = larg / C - 2;
    for (i = 0; i <= n && i < npassagem + 1; i++) {
        int l = (int)strlen(passagem[i]) + 4;
        if (l > cols)
            cols = l;
    }
    if (cols > max_cols)
        cols = max_cols;
    if (cols < 20)
        cols = 20;
    dlg_cols = cols;
    /* 8 sem passagem: moldura, branco, senha, branco, aviso, branco, teclado, moldura.
       Com ela, mais referencia, branco, as linhas e outro branco. */
    dlg_lins = 8 + (n ? n + 3 : 0);
    troca_imagem(&img_dlg, dlg_cols, dlg_lins);
    topo_cols = 18;
    troca_imagem(&img_topo, topo_cols, 1);
}

static void linha_cortada(int lin, const char *s, int fg) {
    char buf[MAX_COLS + 1];
    int max = dlg_cols - 4;
    snprintf(buf, sizeof buf, "%.*s", max, s);
    escreve(img_dlg, 2, lin, buf, fg, WHITE);
}

static void desenha_dialogo(int cursor) {
    int x = (larg - dlg_cols * C) / 2, y = (alt - dlg_lins * C) / 2;
    int lin, col, n = linhas_de_passagem(), i, grupo = 0, caps = 0;
    static const char titulo[] = " Locked ";
    char buf[128];
    XkbStateRec st;

    if (y < C)
        y = C;
    memset(img_dlg->data, 0xFF, (size_t)img_dlg->bytes_per_line * img_dlg->height);
    for (lin = 0; lin < dlg_lins; lin++) {
        int ponta = lin == 0 || lin == dlg_lins - 1;
        glifo(img_dlg, 0, lin, lin == 0 ? SE2 : lin == dlg_lins - 1 ? IE2 : V2, LTBLUE, WHITE);
        glifo(img_dlg, dlg_cols - 1, lin, lin == 0 ? SD2 : lin == dlg_lins - 1 ? ID2 : V2,
              LTBLUE, WHITE);
        if (ponta)
            for (col = 1; col < dlg_cols - 1; col++)
                glifo(img_dlg, col, lin, H2, LTBLUE, WHITE);
    }
    /* titulo invertido, como o da barra de janela */
    escreve(img_dlg, (dlg_cols - (int)strlen(titulo)) / 2, 0, titulo, WHITE, LTBLUE);

    lin = 2;
    if (n) {
        linha_cortada(lin++, passagem[0], RED);
        lin++;
        for (i = 1; i <= n; i++)
            linha_cortada(lin++, passagem[i], BLUE);
        lin++;
    }
    snprintf(buf, sizeof buf, "Password for %s:", usuario);
    linha_cortada(lin, buf, BLUE);
    col = 2 + (int)strlen(buf) + 1;
    if (col + FICHAS + 2 <= dlg_cols - 1) {
        escreve(img_dlg, col, lin, fichas, LTBLUE, WHITE);
        col += (int)strlen(fichas);
        glifo(img_dlg, col, lin, cursor ? 0xDB : ' ', BLUE, WHITE);
    }
    lin += 2;
    if (timeout_fim && !*aviso) {
        snprintf(buf, sizeof buf, "TEST: opens by itself in %lds", (timeout_fim - agora_ms()) / 1000 + 1);
        linha_cortada(lin, buf, RED);
    } else if (erros && !strcmp(aviso, "Wrong password")) {
        snprintf(buf, sizeof buf, "Wrong password (%d)", erros);
        linha_cortada(lin, buf, RED);
    } else
        linha_cortada(lin, aviso, RED);
    lin += 2;
    /* Alt+Shift troca o layout mesmo com o teclado capturado: senha certa no
       layout errado e o erro mais provavel aqui */
    if (XkbGetState(dpy, XkbUseCoreKbd, &st) == Success) {
        grupo = st.group;
        caps = (st.locked_mods & LockMask) != 0;
    }
    snprintf(buf, sizeof buf, "Keyboard: %s%s", grupo < nlayouts ? layouts[grupo] : "?",
             caps ? "  CAPS" : "");
    linha_cortada(lin, buf, caps ? RED : LTBLUE);
    XPutImage(dpy, win, gc, img_dlg, 0, 0, x, y, img_dlg->width, img_dlg->height);
}

static void desenha_topo(void) {
    static const char *const DIAS[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
    time_t t = time(NULL);
    struct tm tm;
    char buf[32];
    localtime_r(&t, &tm);
    /* mesmo formato da linha de status do fundo.py */
    snprintf(buf, sizeof buf, "%s %02d/%02d %02d:%02d:%02d", DIAS[tm.tm_wday], tm.tm_mon + 1,
             tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec);
    escreve(img_topo, 0, 0, buf, WHITE, BLUE);
    XPutImage(dpy, win, gc, img_topo, 0, 0, 0, 0, img_topo->width, img_topo->height);
}

/* ------------------------------------------------------------ senha */
__attribute__((unused)) static int conversa(int n, const struct pam_message **msg, struct pam_response **resp, void *_) {
    int i;
    struct pam_response *r = calloc((size_t)n, sizeof *r);
    (void)_;
    if (!r)
        return PAM_CONV_ERR;
    for (i = 0; i < n; i++)
        if (msg[i]->msg_style == PAM_PROMPT_ECHO_OFF || msg[i]->msg_style == PAM_PROMPT_ECHO_ON)
            r[i].resp = strdup(senha);
    *resp = r;
    return PAM_SUCCESS;
}

static int autentica(void) {
#ifdef SENHA_TESTE /* so no binario do teste automatico; o instalar.sh nao define */
    return strcmp(senha, SENHA_TESTE) ? PAM_AUTH_ERR : PAM_SUCCESS;
#else
    struct pam_conv c = {conversa, NULL};
    pam_handle_t *h = NULL;
    int r = pam_start(SERVICO_PAM, usuario, &c, &h);
    if (r != PAM_SUCCESS)
        return r;
    r = pam_authenticate(h, 0);
    if (r == PAM_SUCCESS)
        pam_setcred(h, PAM_REFRESH_CRED);
    pam_end(h, r);
    return r;
#endif
}

static void checa(void) {
    XEvent ev;
    int r;
    aviso = "Checking...";
    desenha_dialogo(0);
    XSync(dpy, False);
    r = autentica();
    if (r == PAM_SUCCESS) {
        limpa_senha();
        XCloseDisplay(dpy);
        exit(0);
    }
    limpa_senha();
    /* Sem conseguir perguntar ao PAM, ficar aqui prenderia o dono para sempre:
       sai com erro e o `|| dm-tool lock` leva para a tela de login. */
    if (r != PAM_AUTH_ERR) {
        fprintf(stderr, "trava: PAM respondeu %d\n", r);
        exit(3);
    }
    erros++;
    aviso = "Wrong password";
    while (XCheckTypedEvent(dpy, KeyPress, &ev)) /* o digitado durante a checagem */
        ;
}

static void novas_fichas(void) {
    int i;
    for (i = 0; i < FICHAS; i++)
        fichas[i] = rand() & 1 ? '*' : '.';
    fichas[FICHAS] = 0;
}

static void tecla(XKeyEvent *ev) {
    char buf[64];
    KeySym ks = NoSymbol;
    Status st = XLookupBoth;
    int n = ic ? Xutf8LookupString(ic, ev, buf, sizeof buf, &ks, &st)
               : XLookupString(ev, buf, sizeof buf, &ks, NULL);
    if (st == XBufferOverflow)
        return;
    /* Ctrl+Alt+L continua apertado ao bloquear e a tecla repete. AltGr e Mod5. */
    if (ev->state & (ControlMask | Mod1Mask | Mod4Mask)) {
        if ((ev->state & ControlMask) && ks == XK_u)
            limpa_senha();
        return;
    }
    switch (ks) {
    case XK_Return:
    case XK_KP_Enter:
        if (nsenha)
            checa();
        return;
    case XK_Escape:
        limpa_senha();
        aviso = "";
        return;
    case XK_BackSpace:
        while (nsenha && ((unsigned char)senha[--nsenha] & 0xC0) == 0x80) /* um caractere UTF-8 */
            senha[nsenha] = 0;
        senha[nsenha] = 0;
        if (nsenha)
            novas_fichas();
        else
            fichas[0] = 0;
        return;
    }
    if (n > 0 && (unsigned char)buf[0] >= 0x20 && buf[0] != 0x7F && nsenha + n < sizeof senha - 1) {
        memcpy(senha + nsenha, buf, (size_t)n);
        nsenha += (size_t)n;
        senha[nsenha] = 0;
        novas_fichas();
        aviso = "";
    }
    explicit_bzero(buf, sizeof buf);
}

/* ------------------------------------------------------------ preparacao */
static void le_passagem(void) {
    /* A espera curta e so para o caso de a entrada ser um pipe que nunca fecha */
    struct pollfd p = {0, POLLIN, 0};
    char buf[(MAX_COLS + 1) * (MAX_LINHAS + 1)], *s, *fim;
    size_t tem = 0;
    long limite = agora_ms() + 300;
    if (isatty(0))
        return;
    while (tem < sizeof buf - 1 && agora_ms() < limite && poll(&p, 1, 100) > 0) {
        ssize_t r = read(0, buf + tem, sizeof buf - 1 - tem);
        if (r <= 0)
            break;
        tem += (size_t)r;
    }
    buf[tem] = 0;
    for (s = buf; s && *s && npassagem <= MAX_LINHAS; s = fim) {
        fim = strchr(s, '\n');
        if (fim)
            *fim++ = 0;
        {
            size_t l = strlen(s); /* o array zerado garante o fim da string */
            memcpy(passagem[npassagem++], s, l < MAX_COLS ? l : MAX_COLS);
        }
    }
    npassagem = npassagem > 0 ? npassagem - 1 : 0; /* a primeira linha e a referencia */
}

static void le_layouts(void) {
    Atom tipo;
    int fmt;
    unsigned long n, resto;
    unsigned char *d = NULL;
    Atom a = XInternAtom(dpy, "_XKB_RULES_NAMES", True);
    nlayouts = 0;
    /* regras\0modelo\0layouts\0variantes\0opcoes */
    if (a != None && XGetWindowProperty(dpy, raiz, a, 0, 1024, False, XA_STRING, &tipo, &fmt, &n,
                                        &resto, &d) == Success && d && n) {
        const char *s = (const char *)d, *fim = s + n;
        int i;
        for (i = 0; i < 2 && s < fim; i++)
            s += strlen(s) + 1;
        while (s < fim && *s && nlayouts < 8) {
            size_t l = strcspn(s, ",");
            snprintf(layouts[nlayouts++], sizeof layouts[0], "%.*s", (int)l, s);
            s += l;
            if (*s == ',')
                s++;
            else
                break;
        }
    }
    if (d)
        XFree(d);
}

static int pega_entrada(Cursor cursor) {
    /* O atalho que nos chamou ainda segura o teclado ate a tecla ser solta */
    long limite = agora_ms() + 5000;
    struct timespec t = {0, 50000000};
    int teclado = 0, ponteiro = 0;
    while (agora_ms() < limite) {
        if (!teclado)
            teclado = XGrabKeyboard(dpy, raiz, False, GrabModeAsync, GrabModeAsync, CurrentTime) == GrabSuccess;
        if (!ponteiro)
            ponteiro = XGrabPointer(dpy, raiz, False, 0, GrabModeAsync, GrabModeAsync, None, cursor,
                                    CurrentTime) == GrabSuccess;
        if (teclado && ponteiro)
            return 1;
        nanosleep(&t, NULL);
    }
    return 0;
}

/* Sem o arquivo do servico, o PAM cai na politica "other", que costuma recusar
   tudo: nem a senha certa destravaria. Melhor nem bloquear e deixar a reserva. */
static int servico_pam_existe(void) {
    return access("/etc/pam.d/" SERVICO_PAM, R_OK) == 0 ||
           access("/usr/lib/pam.d/" SERVICO_PAM, R_OK) == 0;
}

static void abre_metodo_entrada(void) {
    /* Com o XIM embutido as teclas mortas do layout br compoem acentos */
    XIM im;
    XSetLocaleModifiers("@im=none");
    im = XOpenIM(dpy, NULL, NULL, NULL);
    if (im)
        ic = XCreateIC(im, XNInputStyle, XIMPreeditNothing | XIMStatusNothing, XNClientWindow, win,
                       XNFocusWindow, win, NULL);
}

int main(int argc, char **argv) {
    XSetWindowAttributes at;
    XWindowAttributes ra;
    Atom marca;
    Pixmap vazio;
    Cursor cursor;
    XColor preto = {0};
    static const char bit = 0;
    int tela, i, pisca = -1;
    time_t seg = 0;
    struct passwd *pw = getpwuid(getuid());
    struct pollfd pfd;

    prctl(PR_SET_DUMPABLE, 0); /* sem core dump nem ptrace lendo a senha */
    mlock(senha, sizeof senha);
    srand((unsigned)time(NULL) ^ (unsigned)getpid());
    setlocale(LC_CTYPE, "");
    usuario = pw ? pw->pw_name : getenv("USER");
    if (!usuario)
        return 1;
#ifndef SENHA_TESTE
    if (!servico_pam_existe()) {
        fprintf(stderr, "trava: falta /etc/pam.d/" SERVICO_PAM "\n");
        return 4;
    }
#endif
    for (i = 1; i + 1 < argc; i++)
        if (!strcmp(argv[i], "--timeout"))
            timeout_fim = agora_ms() + atol(argv[i + 1]) * 1000;

    if (!(dpy = XOpenDisplay(NULL)))
        return 1;
    XkbUseExtension(dpy, NULL, NULL);
    tela = DefaultScreen(dpy);
    raiz = RootWindow(dpy, tela);
    marca = XInternAtom(dpy, "_TEMPLEOS_TRAVA", False);
    if (XGetSelectionOwner(dpy, marca) != None)
        return 0; /* ja esta bloqueada */

    vazio = XCreateBitmapFromData(dpy, raiz, &bit, 1, 1);
    cursor = XCreatePixmapCursor(dpy, vazio, vazio, &preto, &preto, 0, 0);
    /* Captura antes de mostrar qualquer coisa: uma tela com cara de bloqueada
       e teclado solto seria pior que nada */
    if (!pega_entrada(cursor)) {
        fprintf(stderr, "trava: nao consegui capturar teclado e ponteiro\n");
        return 2;
    }

    XGetWindowAttributes(dpy, raiz, &ra);
    larg = ra.width;
    alt = ra.height;
    at.override_redirect = True;
    at.background_pixel = PALETA[BLUE];
    at.cursor = cursor;
    at.event_mask = ExposureMask | VisibilityChangeMask | StructureNotifyMask;
    win = XCreateWindow(dpy, raiz, 0, 0, (unsigned)larg, (unsigned)alt, 0, CopyFromParent, InputOutput,
                        CopyFromParent, CWOverrideRedirect | CWBackPixel | CWCursor | CWEventMask, &at);
    XStoreName(dpy, win, "TempleOS Locked");
    gc = XCreateGC(dpy, win, 0, NULL);
    XSetSelectionOwner(dpy, marca, win, CurrentTime);
    /* tudo que aparecer por cima (tooltip, menu, janela nova) ou mudar o tamanho da tela */
    XSelectInput(dpy, raiz, SubstructureNotifyMask | StructureNotifyMask);
    abre_metodo_entrada();
    usuario = strdup(usuario);
    le_passagem();
    le_layouts();
    dimensiona();
    XMapRaised(dpy, win);

    pfd.fd = ConnectionNumber(dpy);
    pfd.events = POLLIN;
    for (;;) {
        int sujo = 0, cursor_on;
        long ms = agora_ms();
        time_t s = time(NULL);
        while (XPending(dpy)) {
            XEvent ev;
            XNextEvent(dpy, &ev);
            if (XFilterEvent(&ev, win))
                continue;
            switch (ev.type) {
            case KeyPress:
                tecla(&ev.xkey);
                sujo = 1;
                break;
            case Expose:
                if (!ev.xexpose.count)
                    sujo = 2;
                break;
            case VisibilityNotify:
                if (ev.xvisibility.state != VisibilityUnobscured)
                    XRaiseWindow(dpy, win);
                break;
            case MapNotify:
                if (ev.xmap.window != win)
                    XRaiseWindow(dpy, win);
                break;
            case UnmapNotify:
                if (ev.xunmap.window == win)
                    XMapRaised(dpy, win);
                break;
            case ConfigureNotify:
                if (ev.xconfigure.window == raiz) {
                    if (ev.xconfigure.width != larg || ev.xconfigure.height != alt) {
                        larg = ev.xconfigure.width;
                        alt = ev.xconfigure.height;
                        XMoveResizeWindow(dpy, win, 0, 0, (unsigned)larg, (unsigned)alt);
                        dimensiona();
                        XClearWindow(dpy, win);
                        sujo = 2;
                    }
                } else if (ev.xconfigure.window != win)
                    XRaiseWindow(dpy, win);
                break;
            }
        }
        if (timeout_fim) {
            if (ms >= timeout_fim) {
                limpa_senha();
                XCloseDisplay(dpy);
                return 0;
            }
            sujo = sujo ? sujo : 1;
        }
        cursor_on = (int)(ms / 500 % 2);
        if (cursor_on != pisca) {
            pisca = cursor_on;
            sujo = sujo ? sujo : 1;
        }
        if (s != seg) {
            seg = s;
            sujo = sujo ? sujo : 1; /* o layout e o Caps podem ter mudado */
        }
        if (sujo) {
            desenha_dialogo(cursor_on);
            desenha_topo();
        }
        XFlush(dpy);
        poll(&pfd, 1, 200);
    }
}
