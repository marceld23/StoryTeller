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

## 3b. Optional: interrupt button (barge-in)

A momentary push-button on a GPIO pin lets the player **interrupt the
narration** while it speaks — the system stops, listens, and figures out what
you want (system menu or a story turn). Optional: without it the player uses
the wake word / web button / CLI instead.

**Wiring (Pi 4, very simple — no resistor needed):**

```
   GPIO17 (pin 11) ──┐
                     [ push-button ]
   GND    (pin 9)  ──┘
```

- Connect one leg of the button to a free GPIO pin (default **BCM 17** =
  physical pin 11) and the other leg to any **GND** pin (e.g. physical pin 9
  or 6).
- No external resistor: the firmware enables the chip's internal pull-up, so
  the pin idles HIGH and pressing pulls it to GND.
- Any normally-open momentary button works (breadboard tactile switch,
  arcade button, …). Polarity doesn't matter.

Pin reference: run `pinout` on the Pi, or see pinout.xyz. Avoid pins with
special boot functions (GPIO 0/1, 14/15); 17, 22, 23, 24, 27 are safe choices.

**Enable it** — install the GPIO libs (Pi-only, like the wake word) and flip
the toggle in `config/config.toml`:

```bash
sudo apt-get install -y swig python3-dev liblgpio-dev   # build deps
uv pip install gpiozero lgpio
```

```toml
[hardware]
interrupt_button_enabled  = true   # default false — no GPIO claim unless this is true
interrupt_button_pin      = 17     # BCM pin (default 17 = physical pin 11)
interrupt_button_pull_up  = true   # internal pull-up: button wires pin -> GND
interrupt_button_bounce_s = 0.08
```

Each button role uses its own `<role>_button_*` group (so additional buttons
— menu, save, … — can be added later without breaking existing config).

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
```

Logs: `journalctl -u storyteller -f` (also `data/storyteller.log`).
Admin: `http://<pi-ip>:8080` · Player: `http://<pi-ip>:8090`.

## 6. Run manually

```bash
uv run --package storyteller-pi storyteller-pi run         # voice loop ("hey jarvis")
uv run --package storyteller-pi storyteller-pi run --ptt   # push-to-talk (Enter)
uv run --package storyteller-pi storyteller-pi run --text  # keyboard, no mic
```

See [USER_GUIDE.md](USER_GUIDE.md) for how to play.
