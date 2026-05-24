# Setup — Raspberry Pi 4 + ReSpeaker USB Mic Array v2.0

Target: Raspberry Pi 4, Debian 13 (trixie), Python 3.13, ReSpeaker USB Mic
Array v2.0 (USB id `2886:0018`, ALSA card `ArrayUAC10`) with a speaker on its
3.5 mm line-out.

## Required hardware

- **Raspberry Pi 4** (4 GB+ recommended) with Raspberry Pi OS / Debian 13.
- **ReSpeaker USB Mic Array v2.0** (Seeed) — far-field mic + LED ring; also
  the audio output (a speaker on its 3.5 mm line-out).
- A small **speaker** for the ReSpeaker line-out (active or passive 3.5 mm).
- **5 V USB power bank** (or 5 V/3 A USB-C supply) to run the Pi — a power
  bank makes it portable. Use one that can power a Pi 4 (≥ 3 A / 15 W).
- microSD card (16 GB+) and Wi-Fi (the captive-portal onboarding sets it up
  if there is no known network at boot).

## 1. Prerequisites

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv (package/venv manager)
sudo apt install -y alsa-utils                     # aplay/arecord/amixer
sudo apt install -y nodejs                          # Node 20 — only to build the web UIs
```

Put your OpenAI key in `/home/pi/storyteller/.env`:

```
OPENAI_API_KEY=sk-...
```

## 2. ReSpeaker hardware + dependencies

```bash
cd /home/pi/storyteller

# udev rule (LED ring + DSP tuning, non-root) — then replug the ReSpeaker
sudo bash scripts/setup_system.sh

uv sync                                                 # workspace venv
uv run --package storyteller-cli storyteller-cli seed   # seed worlds (de + en)
```

`~/.asoundrc` is installed by this repo: playback via ALSA **softvol**
(`plug:respeaker_softvol`, the device has no hardware volume), capture via
**dsnoop** (16 kHz mono, lets the wake word + recording share the mic).
RAG indexing happens automatically when a world is first played; menu/wait
audio is synthesized and cached on first use (no separate build step).

Quick hardware check:

```bash
speaker-test -D plug:respeaker_softvol -c 1 -t sine -l 1   # line-out tone
arecord -D respeaker_capture -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav  # mic
amixer -c ArrayUAC10 sset Master 20%        # line-out is hot; default is 15 %
```

## 3. Wake word (default "hey jarvis")

openWakeWord has no Python 3.13 wheels via pip deps, so install it apart:

```bash
bash scripts/install_wakeword.sh
```

**Important:** any `uv sync` prunes these packages — re-run
`install_wakeword.sh` afterwards. Without a wake word the loop falls back to
push-to-talk / text mode (not usable under systemd, which has no stdin).

## 3b. Optional: GPIO push-buttons

Two roles ship out of the box, both off by default. Each lives in its
own `[hardware] <role>_button_*` group in `config/config.toml` — enable
only the ones you actually wire up.

| Role | Short press | Long press (≥ `long_press_s`, default 2.0 s) |
|---|---|---|
| **interrupt** | Pause / resume the current narration (SIGSTOP / SIGCONT on `aplay`). No-op if nothing is playing. | Abort the current narration and open the spoken system menu. |
| **shutdown** | Announce *„Spielstand gespeichert"* (the game is auto-checkpointed every turn — this is just audible feedback). | Say goodbye, then `sudo -n systemctl poweroff`. |

**Wiring (Pi 4, no resistor needed):**

```
   GPIO 17 (pin 11) ──┐           ┌── interrupt button → GND (pin 9)
                      │           │
   GPIO 27 (pin 13) ──┴── [btn] ──┴── shutdown button  → GND (pin 14)
```

- Each button has one leg on its configured BCM pin and one leg on any
  GND. The internal pull-up (default `pull_up = true`) replaces an
  external resistor — the pin idles HIGH, pressing pulls to GND.
- Any normally-open momentary button works. Polarity doesn't matter.
- Default BCM pins: **17** (interrupt, physical pin 11), **27** (shutdown,
  physical pin 13). Both are safe — no boot-time conflicts. Pin reference:
  `pinout` on the Pi or pinout.xyz.

**Install the GPIO libs** (Pi-only, like the wake word):

```bash
sudo apt-get install -y swig python3-dev liblgpio-dev   # build deps
uv pip install gpiozero lgpio
```

**Enable in `config/config.toml`:**

```toml
[hardware]
interrupt_button_enabled       = true
interrupt_button_pin           = 17
interrupt_button_long_press_s  = 2.0     # hold this long for the menu

shutdown_button_enabled        = true
shutdown_button_pin            = 27
shutdown_button_long_press_s   = 2.0
```

Restart the voice service; the log shows
`storyteller.button: interrupt aktiv an GPIO 17 (long_press=2.0s)`
(and the same for `shutdown`) when each is up.

**Sudoers for the shutdown button** — the long-press handler runs
`sudo -n systemctl poweroff` (`-n` = non-interactive: no password
prompt). Allow that for the user the service runs as (`pi` by default):

```
# /etc/sudoers.d/storyteller-poweroff  (visudo -f to edit)
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
```

Without that line the button will say goodbye but the Pi stays on.

Pause/resume note: pause/resume only acts on the **narration**, not the
ambient wait-loop sound. Pressing the interrupt button while the
narrator hasn't started yet (LLM still thinking) is a no-op; a long
press in that window still works (abort + menu).

Restart the voice service; the log shows `Interrupt-Taster aktiv an GPIO 17`.
Works with any audio output (ReSpeaker line-out **and** Bluetooth) since the
button is independent of the sound path. (`uv pip install` survives until the
next `uv sync` — re-run it afterwards, same as the wake word.)

## 4. Build the web UIs (admin + player)

The two web backends serve their SvelteKit SPAs as static files, so build
them once (Node 20 + yarn 4 via corepack):

```bash
bash scripts/build_frontends.sh        # writes apps/*/frontend/build/
```

## 5. Autostart (systemd)

```bash
sudo bash scripts/install_services.sh    # storyteller + storyteller-admin + storyteller-web-ui
sudo bash scripts/install_netcheck.sh    # Wi-Fi onboarding (see USER_GUIDE)
```

Services (all `Restart=always`):

| Service | Command | Port |
|---|---|---|
| `storyteller.service`        | `storyteller-pi run`    | — (voice) |
| `storyteller-admin.service`  | `storyteller-web-admin` | `:8080` |
| `storyteller-web-ui.service` | `storyteller-web-ui`    | `:8090` |

After code changes:

```bash
sudo systemctl restart storyteller storyteller-admin storyteller-web-ui
# if Python deps changed:  uv sync && bash scripts/install_wakeword.sh
# if a frontend changed:   bash scripts/build_frontends.sh
# if voice / TTS swapped:  bash scripts/bake_voice_prompts.sh --force
```

The Pi voice loop auto-re-bakes any voice prompt whose i18n text
changed at boot (per-prompt staleness — only the touched ones cost
TTS time). Run `bash scripts/bake_voice_prompts.sh` to force this
incremental rebuild from outside the loop, or `--force` for a full
rebuild after switching `models.tts_voice` / `models.tts` /
`models.tts_endpoint`.

Logs: `journalctl -u storyteller -f` (also `data/storyteller.log`).
Admin: `http://<pi-ip>:8080` · Player: `http://<pi-ip>:8090`.

## 6. Run manually

```bash
uv run --package storyteller-pi storyteller-pi run         # voice loop ("hey jarvis")
uv run --package storyteller-pi storyteller-pi run --ptt   # push-to-talk (Enter)
uv run --package storyteller-pi storyteller-pi run --text  # keyboard, no mic
```

See [USER_GUIDE.md](USER_GUIDE.md) for how to play.
