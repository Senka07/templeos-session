#!/bin/sh
# Sessao TempleOS de teste em Xephyr :9, com HOME falso: nada da sessao real
# e tocado. O zsh e o oh-my-zsh entram por symlink; o resto vem do instalar.sh.
# Precisa do Xephyr (xorg-server-xephyr).
# Uso: sh testar.sh [diretorio-de-teste]
D=$(cd "$(dirname "$0")" && pwd)
T=${1:-${XDG_RUNTIME_DIR:-/tmp}/templeos-teste}
F="$T/home"
rm -rf "$T"
mkdir -p "$F/.config" "$F/.local/share/fonts" "$F/.local/share/icons"
# Shell e icones de verdade entram por symlink, para o terminal do teste
# parecer o de sempre.
for p in .zshrc .oh-my-zsh .icons; do
  [ -e "$HOME/$p" ] && ln -s "$HOME/$p" "$F/$p"
done
# Pastas em que o instalar.sh escreve nunca entram inteiras por symlink (senao
# o instalar.sh grava no HOME real): so o conteudo, e sem o que a sessao instala.
ln -s "$HOME/.local/share/fonts" "$F/.local/share/fonts/pessoais"
for p in "$HOME"/.local/share/icons/*; do
  [ "${p##*/}" = TempleOS ] || ln -s "$p" "$F/.local/share/icons/"
done
sh "$D/instalar.sh" "$F" > "$T/instalar.log" 2>&1

# TEMPLEOS_TELA muda a resolucao do teste (padrao: 1280x1024)
Xephyr :9 -screen "${TEMPLEOS_TELA:-1280x1024}" -resizeable -no-host-grab >/dev/null 2>&1 &
sleep 1.5
env -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_DATA_HOME -u SESSION_MANAGER \
    -u DBUS_SESSION_BUS_ADDRESS -u TEMPLEOS_SESSAO \
    HOME="$F" DISPLAY=:9 sh "$D/sessao.sh" >"$T/sessao.log" 2>&1 &
echo "teste em :9, home falso em $F"
