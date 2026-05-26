#!/usr/bin/env bash
# System setup for the ReSpeaker USB Mic Array v2.0 (idempotent).
# Needs root for the udev rule. Usage:  sudo bash scripts/setup_system.sh
set -euo pipefail

RULE=/etc/udev/rules.d/60-respeaker.rules
RULE_CONTENT='SUBSYSTEM=="usb", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="0018", MODE="0666", GROUP="plugdev", TAG+="uaccess"'

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash scripts/setup_system.sh" >&2
  exit 1
fi

echo "[1/3] Writing udev rule: $RULE"
echo "$RULE_CONTENT" > "$RULE"

echo "[2/3] Reloading udev"
udevadm control --reload-rules
udevadm trigger

echo "[3/3] done."
echo "  -> Unplug + replug the ReSpeaker once so the rule takes effect."
echo "  -> ALSA softvol lives in ~/.asoundrc per-user (no root needed)."
echo "  -> Test:  cd /home/pi/storyteller && uv run storyteller hw-test"
