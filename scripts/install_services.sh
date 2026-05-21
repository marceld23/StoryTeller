#!/usr/bin/env bash
# Installiert + aktiviert die systemd-System-Services (als root ausführen):
#   echo <rootpw> | sudo -S bash scripts/install_services.sh
# oder:  sudo bash scripts/install_services.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(id -u)" -eq 0 ] || { echo "Bitte als root (sudo) ausführen." >&2; exit 1; }

cp scripts/storyteller.service \
   scripts/storyteller-admin.service \
   scripts/storyteller-web-ui.service \
   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now \
    storyteller-admin.service \
    storyteller-web-ui.service \
    storyteller.service

echo "--- Status ---"
systemctl --no-pager --lines=0 status \
    storyteller-admin storyteller-web-ui storyteller || true
echo "Logs:"
echo "  journalctl -u storyteller -f          # Pi voice loop"
echo "  journalctl -u storyteller-admin -f    # admin backend (:8080)"
echo "  journalctl -u storyteller-web-ui -f   # player web backend (:8090)"
