#!/bin/sh
# templeos-session: check dependencies and install into $HOME
#
#   ./install.sh           check, then install
#   ./install.sh --check   only check dependencies
#
# Nothing outside $HOME is touched. Registering the session with the login
# manager needs root, so that last step is printed for you to run.
D=$(cd "$(dirname "$0")" && pwd)

falta=0
precisa() {  # precisa <comando> <pacote no Arch>
  command -v "$1" >/dev/null 2>&1 || { echo "  missing: $1 ($2)"; falta=1; }
}
opcional() {  # opcional <comando> <pacote no Arch> <para que serve>
  command -v "$1" >/dev/null 2>&1 || echo "  optional: $1 ($2) - $3"
}
modulo() {  # modulo <modulo python> <pacote no Arch>
  python3 -c "import $1" 2>/dev/null || { echo "  missing: python module $1 ($2)"; falta=1; }
}

echo "checking dependencies (Arch package names in parentheses)"
precisa xfwm4 xfwm4
precisa dbus-run-session dbus
precisa python3 python
precisa kitty kitty
precisa zsh zsh
precisa xdotool xdotool
precisa xrdb xorg-xrdb
precisa xcursorgen xorg-xcursorgen
modulo gi python-gobject
modulo cairo python-cairo
modulo PIL python-pillow
python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null || { echo "  missing: GTK 3 (gtk3)"; falta=1; }
opcional fastfetch fastfetch "system info in the first terminal"
opcional xsettingsd xsettingsd "same cursor in GTK apps"
opcional setxkbmap xorg-setxkbmap "XKB_LAYOUT in sessao.conf"
opcional pacat libpulse "God Song and the JukeBox play hymns"
opcional wpctl wireplumber "Ctrl+Alt+M mute"
opcional less less "Ctrl+Alt+B Bible"
opcional thunar thunar "Super+E file manager, with its own TempleOS theme"
opcional gcc gcc "builds the screen locker and the module that themes Thunar"
opcional dm-tool lightdm "Ctrl+Alt+L falls back to it if the locker fails; see sessao.conf"
python3 -c "import ctypes; ctypes.CDLL('libXss.so.1')" 2>/dev/null || \
  echo "  optional: libXss (libxss) - players holding the screen on, and TEMPLEOS_BLOQUEIO_MIN"
[ -e /etc/pam.d/vlock ] || [ -e /usr/lib/pam.d/vlock ] || \
  echo "  optional: PAM service vlock (kbd on Arch, vlock elsewhere) - without it Ctrl+Alt+L uses the fallback"
opcional qemu-system-x86_64 qemu-desktop "the TempleOS logo in the menu boots the real thing"

if [ "$falta" = 1 ]; then
  echo "install the missing packages above and run this again"
  exit 1
fi
echo "all required dependencies found"
[ "$1" = --check ] && exit 0

sh "$D/sessao/instalar.sh" || exit 1

# The help reader (Super+F1) shows the documents from the ISO
if [ -f "$D/iso/TempleOS.ISO" ] && [ ! -d "$D/iso-extraida" ]; then
  python3 -I "$D/extracao/redsea.py" "$D/iso/TempleOS.ISO" "$D/iso-extraida" >/dev/null || \
    echo "warning: could not extract iso/TempleOS.ISO" >&2
fi
[ -d "$D/iso-extraida" ] || echo "note: no iso-extraida/, so the help reader has nothing to show (see the README)"
cat <<EOF

Done. Last step, register the session with your login manager (needs root):

  sudo install -m644 "$D/build/templeos.desktop" /usr/share/xsessions/

Then log out and pick "TempleOS" in the session list.
Your settings live in ~/.config/templeos/ (sessao.conf, menu.json, programas.json).

Once you're in, try the screen locker with a timeout before trusting Ctrl+Alt+L:

  ~/.config/templeos/trava --timeout 60; echo \$?
EOF
