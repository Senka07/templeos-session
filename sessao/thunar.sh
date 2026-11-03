#!/bin/sh
# Thunar com o tema TempleOS-Thunar (GTK e icones). O tema entra pelo tema-app.so (ver
# thunar/tema-app.c), que vale so para o processo do Thunar: com GTK_THEME os
# programas que ele abre herdariam o tema. Se ja ha um Thunar nesta sessao, o
# pedido vai para ele pelo D-Bus e este processo sai logo.
M=${TEMPLEOS_CFG:-$HOME/.config/templeos}/tema-app.so
if [ -f "$M" ]; then
  GTK_MODULES="$M${GTK_MODULES:+:$GTK_MODULES}"
  export GTK_MODULES TEMPLEOS_TEMA_GTK=TempleOS-Thunar TEMPLEOS_ICONES_GTK=TempleOS-Thunar
fi
exec thunar "$@"
