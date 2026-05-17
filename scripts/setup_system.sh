#!/usr/bin/env bash
# System-Setup für den ReSpeaker USB Mic Array v2.0 (idempotent).
# Braucht root für die udev-Regel. Aufruf:  sudo bash scripts/setup_system.sh
set -euo pipefail

RULE=/etc/udev/rules.d/60-respeaker.rules
RULE_CONTENT='SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="0018", MODE="0666", GROUP="plugdev", TAG+="uaccess"'

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo bash scripts/setup_system.sh" >&2
  exit 1
fi

echo "[1/3] udev-Regel schreiben: $RULE"
echo "$RULE_CONTENT" > "$RULE"

echo "[2/3] udev neu laden"
udevadm control --reload-rules
udevadm trigger

echo "[3/3] fertig."
echo "  -> ReSpeaker einmal aus-/einstecken (replug), damit die Regel greift."
echo "  -> ALSA softvol liegt user-scoped in ~/.asoundrc (kein root nötig)."
echo "  -> Test:  cd /home/pi/storyteller && uv run storyteller hw-test"
