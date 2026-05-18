# Setup — Raspberry Pi 4 + ReSpeaker USB Mic Array v2.0

Target: Raspberry Pi 4, Debian 13 (trixie), Python 3.13, ReSpeaker USB Mic
Array v2.0 (USB id `2886:0018`, ALSA card `ArrayUAC10`) with a speaker on its
3.5 mm line-out.

## 1. Prerequisites

```bash
# uv (package/venv manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
# alsa-utils provides aplay/arecord/amixer (usually present)
sudo apt install -y alsa-utils
```

Put your OpenAI key in `/home/pi/storyteller/.env`:

```
OPENAI_API_KEY=sk-...
```

## 2. ReSpeaker hardware

```bash
cd /home/pi/storyteller

# udev rule (LED ring + DSP tuning, non-root) — then replug the ReSpeaker
sudo bash scripts/setup_system.sh

# core dependencies
uv sync
```

`~/.asoundrc` is installed by this repo: playback via ALSA **softvol**
(`plug:respeaker_softvol`, the device has no hardware volume), capture via
**dsnoop** (16 kHz mono, lets wake-word + recording share the mic).

Volume: `amixer -c ArrayUAC10 sset Master 20%` (the line-out is hot; default
is 15 %).

## 3. Verify hardware

```bash
uv run storyteller hw-test     # volume, line-out tone, mic, LED ring, tuning
uv run storyteller seed        # write the seed worlds (de + en)
uv run storyteller rag build   # index worlds for retrieval (per locale)
uv run storyteller voice-prompts build --all-locales   # cache menu audio
uv run storyteller wait-sounds build                    # per-world ambience
```

## 4. Wake word (default "hey jarvis")

openWakeWord has no Python 3.13 wheels via pip deps, so install it apart:

```bash
bash scripts/install_wakeword.sh
```

**Important:** any `uv sync` prunes these packages — re-run
`install_wakeword.sh` afterwards. Without a wake word the loop falls back to
push-to-talk / text mode.

## 5. Autostart (systemd)

```bash
sudo bash scripts/install_services.sh    # storyteller + storyteller-admin
sudo bash scripts/install_netcheck.sh    # Wi-Fi onboarding (see USER_GUIDE)
```

Both run on boot (`Restart=always`). Update after code changes:

```bash
sudo systemctl restart storyteller storyteller-admin
# only if dependencies changed: uv sync && bash scripts/install_wakeword.sh
```

Logs: `journalctl -u storyteller -f` (also `data/storyteller.log`).
Admin website: `http://<pi-ip>:8080`.

## 6. Run manually

```bash
uv run storyteller run            # voice loop (wake word "hey jarvis")
uv run storyteller run --ptt      # push-to-talk (Enter) instead
```

See [USER_GUIDE.md](USER_GUIDE.md) for how to play.
