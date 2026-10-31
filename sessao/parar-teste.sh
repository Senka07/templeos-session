#!/bin/sh
# Encerra o teste do testar.sh: mata so processos cujo ambiente tem o HOME
# falso, e o Xephyr :9. Nada de pkill -f (o padrao casaria com a propria linha).
T=${1:-${XDG_RUNTIME_DIR:-/tmp}/templeos-teste}
for p in /proc/[0-9]*; do
  [ -O "$p" ] || continue
  { tr '\0' '\n' < "$p/environ"; } 2>/dev/null | grep -qx "HOME=$T/home" || continue
  kill "${p#/proc/}" 2>/dev/null
done
for pid in $(pgrep -x Xephyr); do
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q '^Xephyr :9 ' && kill "$pid"
done
true
