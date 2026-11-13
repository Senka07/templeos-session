#!/bin/sh
# Sessao TempleOS (o que o LightDM vai chamar).
# Roda num barramento D-Bus proprio. O dbus-daemon guarda o ambiente de quando
# sobe, entao o xfconfd ativado por esse barramento le $CFG/xfconf-home e o xfwm4 daqui tem
# tema e opcoes proprios -- o canal xfwm4 da sessao XFCE nao e tocado. Os apps
# voltam ao XDG_CONFIG_HOME normal logo depois.
D=$(cd "$(dirname "$0")" && pwd)

if [ -z "$TEMPLEOS_SESSAO" ]; then
  CFG=${XDG_CONFIG_HOME:-$HOME/.config}/templeos
  export TEMPLEOS_SESSAO=1 TEMPLEOS_CFG="$CFG" TEMPLEOS_XCH="${XDG_CONFIG_HOME-}"
  exec env XDG_CONFIG_HOME="$CFG/xfconf-home" dbus-run-session -- sh "$0" "$@"
fi
if [ -n "$TEMPLEOS_XCH" ]; then export XDG_CONFIG_HOME="$TEMPLEOS_XCH"; else unset XDG_CONFIG_HOME; fi
unset TEMPLEOS_XCH
CFG=$TEMPLEOS_CFG
export TEMPLEOS_WM_PID=$$  # a ultima linha faz exec no xfwm4: o PID continua este

export XDG_CURRENT_DESKTOP=TempleOS
export TEMPLEOS_TERM="kitty --config '$CFG/kitty.conf'"

# Ajustes locais (teclado, ultima tecla, menu): ver config/sessao.conf.
[ -f "$CFG/sessao.conf" ] && . "$CFG/sessao.conf"
export TEMPLEOS_TECLA TEMPLEOS_MENU_INICIAL TEMPLEOS_RESERVA_BLOQUEIO TEMPLEOS_BLOQUEIO_MIN

# Teclado: no XFCE quem aplica o layout e o xfsettingsd, que aqui nao roda.
# Precisa vir antes do atalhos.py, que traduz as teclas pelo mapa atual.
if [ -n "$XKB_LAYOUT" ]; then
  setxkbmap ${XKB_MODEL:+-model "$XKB_MODEL"} -layout "$XKB_LAYOUT" \
    -option '' ${XKB_OPTIONS:+-option "$XKB_OPTIONS"}  # '' limpa as anteriores
fi

# Tela sempre acesa, como no original. Aqui nao roda gerenciador de energia e
# valeria o padrao do Xorg, que apaga o monitor apos 10 min parado.
if [ "$TEMPLEOS_TELA_ACESA" != 0 ]; then
  xset s off s noblank -dpms
fi

export XCURSOR_THEME=TempleOS XCURSOR_SIZE=22
# 96 DPI fixo: a fonte e de pixels e so sai exata em 8px (6pt) e 16px (12pt)
printf 'Xft.dpi: 96\nXcursor.theme: TempleOS\nXcursor.size: 22\n' | xrdb -merge 2>/dev/null
# ...isso vale para Xcursor (kitty, xfwm4, Qt); os apps GTK pedem o cursor ao
# XSETTINGS, e o fundo.py poe o da raiz (a tela atras de tudo)
command -v xsettingsd >/dev/null && xsettingsd -c "$D/config/xsettingsd.conf" &

# Agente de senha do polkit: sem um, montar disco no Thunar e ligar a camera
# virtual do OBS falham sem perguntar nada. Fala com o barramento do sistema,
# entao o D-Bus proprio da sessao nao atrapalha. O caminho muda por distro.
for a in /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1 \
         /usr/libexec/polkit-gnome-authentication-agent-1 \
         /usr/lib/x86_64-linux-gnu/polkit-gnome/polkit-gnome-authentication-agent-1; do
  [ -x "$a" ] && { "$a" & break; }
done

# Notificacoes no estilo da sessao. Antes de qualquer app, senao o D-Bus ativa o
# notifyd instalado na primeira notificacao.
python3 "$D/avisos.py" &

# org.freedesktop.ScreenSaver: os pedidos de "nao apague a tela" dos players e
# o bloqueio por inatividade (TEMPLEOS_BLOQUEIO_MIN). Depois do xset acima, que
# ele guarda e devolve ao sair, e antes dos apps, que perguntam por ele uma vez.
python3 "$D/protetor.py" &

# Thunar ja como daemon: toda janela dele (Windows+E, menu, "abrir pasta"
# pedido por outro app via D-Bus) sai deste processo, que tem o tema TempleOS.
command -v thunar >/dev/null && sh "$D/thunar.sh" --daemon &

GTK_THEME=TempleOS python3 "$D/fundo.py" &
# atalhos, PersonalMenu, Deus e o arranjo do boot (menu + primeiro terminal,
# calculados pela resolucao da tela)
GTK_THEME=TempleOS python3 "$D/atalhos.py" &
GTK_THEME=TempleOS exec xfwm4 --replace
