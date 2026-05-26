#!/usr/bin/env bash
# Phase 8: set up PipeWire + Bluetooth audio output.
# Afterwards set backend = "pipewire" in config.toml [audio] (and
# optionally pw_sink).
set -euo pipefail

echo "[1/4] Installing PipeWire + Bluetooth packages (sudo)…"
sudo apt update
sudo apt install -y pipewire pipewire-pulse wireplumber pipewire-audio \
                    bluez libspa-0.2-bluetooth

echo "[2/4] Enabling PipeWire as a user service…"
systemctl --user enable --now pipewire pipewire-pulse wireplumber || true
# Keep user services running without an active login session (headless
# appliance use):
sudo loginctl enable-linger "$USER" || true

echo "[3/4] Pair the Bluetooth speaker — interactive:"
cat <<'EOF'
  bluetoothctl
    power on
    agent on
    default-agent
    scan on            # power on the speaker / put it in pairing mode
    pair   <MAC>
    trust  <MAC>
    connect <MAC>
    quit
EOF

echo "[4/4] Verify sink:  wpctl status   (name -> config [audio] pw_sink)"
echo "done. ALSA softvol (ReSpeaker) is still usable as backend=\"alsa_softvol\"."
