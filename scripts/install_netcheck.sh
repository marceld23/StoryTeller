#!/usr/bin/env bash
# Install + enable the Wi-Fi onboarding service (run as root).
#   echo <rootpw> | sudo -S bash scripts/install_netcheck.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }

# NetworkManager 'shared'/hotspot DHCP+DNS needs dnsmasq-base (no hostapd).
apt-get update -qq
apt-get install -y dnsmasq-base

cp scripts/storyteller-netcheck.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable storyteller-netcheck.service

echo "enabled. At boot: Wi-Fi OK -> exits in seconds; no Wi-Fi -> AP"
echo "'storyteller-wifi' + captive portal at http://10.42.0.1 (auto-popup)."
echo "Safe check now (never starts AP):"
echo "  /home/pi/storyteller/.venv/bin/python -m storyteller.cli netcheck --check"
