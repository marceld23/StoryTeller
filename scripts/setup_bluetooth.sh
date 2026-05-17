#!/usr/bin/env bash
# Phase 8: PipeWire + Bluetooth-Audio-Ausgang einrichten.
# Danach in config.toml [audio] backend = "pipewire" setzen (optional pw_sink).
set -euo pipefail

echo "[1/4] PipeWire + Bluetooth-Pakete (sudo)…"
sudo apt update
sudo apt install -y pipewire pipewire-pulse wireplumber pipewire-audio \
                    bluez libspa-0.2-bluetooth

echo "[2/4] PipeWire als User-Dienst aktivieren…"
systemctl --user enable --now pipewire pipewire-pulse wireplumber || true
# Damit User-Dienste ohne aktive Login-Session laufen (Appliance/headless):
sudo loginctl enable-linger "$USER" || true

echo "[3/4] Bluetooth-Lautsprecher koppeln — interaktiv:"
cat <<'EOF'
  bluetoothctl
    power on
    agent on
    default-agent
    scan on            # Gerät einschalten/in Pairing-Modus
    pair   <MAC>
    trust  <MAC>
    connect <MAC>
    quit
EOF

echo "[4/4] Sink prüfen:  wpctl status   (Name -> config [audio] pw_sink)"
echo "fertig. ALSA-softvol (ReSpeaker) bleibt als backend=\"alsa_softvol\" nutzbar."
