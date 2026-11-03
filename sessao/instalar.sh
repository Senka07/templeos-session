#!/bin/sh
# Coloca tema, fonte e configs da sessao TempleOS num HOME.
# Uso: sh instalar.sh [home]   (padrao: $HOME; o testar.sh passa um HOME falso)
# So escreve em caminhos novos e exclusivos da sessao:
#   ~/.local/share/themes/TempleOS   ~/.local/share/themes/TempleOS-Thunar
#   ~/.local/share/icons/TempleOS (cursor)   ~/.local/share/icons/TempleOS-Thunar
#   ~/.local/share/fonts/TempleStd.ttf
#   ~/.config/fontconfig/conf.d/60-templeos.conf   ~/.config/templeos/
# e gera build/templeos.desktop, a entrada do gerenciador de login.
set -e
D=$(cd "$(dirname "$0")/.." && pwd)
H=${1:-$HOME}
CFG=$H/.config/templeos
XML=$CFG/xfconf-home/xfce4/xfconf/xfce-perchannel-xml

# A fonte so e refeita a partir da ISO extraida (ver README); sem ela vale a
# TempleStd.ttf e o fonte8x8.json que ja vem no repositorio.
if [ -f "$D/iso-extraida/Kernel/FontStd.HC" ]; then
  python3 -I "$D/fonte/gerar-fonte.py" >/dev/null
fi
python3 -I "$D/xfwm4/gerar-tema.py" "$H/.local/share/themes" >/dev/null
python3 -I "$D/thunar/gerar-tema.py" "$H/.local/share/themes" >/dev/null
python3 -I "$D/thunar/gerar-icones.py" "$H/.local/share/icons" >/dev/null
python3 -I "$D/cursor/gerar-cursor.py" "$H/.local/share/icons" >/dev/null

mkdir -p "$H/.local/share/fonts" "$H/.config/fontconfig/conf.d" "$XML" "$CFG/zsh"
cp "$D/fonte/TempleStd.ttf" "$H/.local/share/fonts/"
cp "$D/sessao/config/60-templeos.conf" "$H/.config/fontconfig/conf.d/"
cp "$D/sessao/config/xfwm4.xml" "$XML/"
cp "$D/sessao/config/zshrc" "$CFG/zsh/.zshrc"
# o modulo que aplica o tema TempleOS-Thunar so no Thunar (thunar/tema-app.c)
if ! gcc -O2 -shared -fPIC -o "$CFG/tema-app.so" "$D/thunar/tema-app.c" \
     $(pkg-config --cflags --libs gtk+-3.0) 2>/dev/null; then
  echo "aviso: sem gcc ou gtk3 para compilar o thunar/tema-app.c; o Thunar fica com o tema normal" >&2
fi
{ cat "$D/sessao/config/kitty.conf"; echo; echo "env ZDOTDIR=$CFG/zsh"; } > "$CFG/kitty.conf"
sed "s|@RAIZ@|$D|g" "$D/sessao/config/fastfetch.jsonc" > "$CFG/fastfetch.jsonc"
# Os arquivos que a pessoa edita so sao copiados na primeira vez
for f in menu.json programas.json sessao.conf; do
  [ -e "$CFG/$f" ] || cp "$D/sessao/config/$f" "$CFG/"
done
fc-cache "$H/.local/share/fonts" >/dev/null 2>&1 || true

mkdir -p "$D/build"
sed "s|@RAIZ@|$D|g" "$D/sessao/templeos.desktop" > "$D/build/templeos.desktop"
echo "instalado em $H"
