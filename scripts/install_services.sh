#!/usr/bin/env bash
# Installiert + aktiviert die systemd-System-Services (als root ausführen):
#   echo <rootpw> | sudo -S bash scripts/install_services.sh
# oder:  sudo bash scripts/install_services.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(id -u)" -eq 0 ] || { echo "Bitte als root (sudo) ausführen." >&2; exit 1; }

cp scripts/storyteller.service scripts/storyteller-admin.service \
   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now storyteller-admin.service storyteller.service

echo "--- Status ---"
systemctl --no-pager --lines=0 status storyteller-admin storyteller || true
echo "Logs: journalctl -u storyteller -f   /   journalctl -u storyteller-admin -f"
