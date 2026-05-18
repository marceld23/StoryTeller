# Storyteller

Interactive, voice-controlled storyteller. Runs on a Raspberry Pi 4 with a
ReSpeaker USB Mic Array v2.0, or on a normal PC (no special hardware). Powered
by the OpenAI API. Localized for German and English.

➡ **Architecture, decisions & roadmap: [PLAN.md](PLAN.md)**

## Quick start

```bash
cd /home/pi/storyteller

# Pi only, once: udev rule (LED ring & DSP tuning); replug the ReSpeaker after
sudo bash scripts/setup_system.sh

# core dependencies
uv sync

# check configuration
uv run storyteller info

# write seed worlds (de + en): Sci-Fi "Starfaring" + Fantasy "Everwood Realm"
uv run storyteller seed

# Pi only: test hardware (volume, line-out, mic, LED ring, DSP tuning)
uv run storyteller hw-test
```

## Running on a PC (no Pi / no ReSpeaker)

The runtime profile is auto-detected (`config [runtime] profile = auto`):
Linux + ReSpeaker ⇒ `pi` (ALSA softvol, LED ring); anything else ⇒ `pc`
(portable `sounddevice` backend, software volume, no LED needed).

```bash
uv run storyteller chat                        # text REPL — best for testing
uv run storyteller run --profile pc            # PC mic + speakers
uv run storyteller run --text                  # keyboard input (no mic)
uv run storyteller run --text --silent         # pure text, no audio at all
```

`chat` is the simplest way to test the story engine: a plain text REPL, no
STT/TTS/audio/menu/wake-word. Type your action; `save` / `load` / `quit`
(or Ctrl-D) work. `--world`, `--locale`, `--load` supported.

## Volume

- Pi (ALSA softvol — the ReSpeaker has no hardware control):
  `amixer -c ArrayUAC10 sset Master 60%`
- PC: software gain via `config [audio] default_volume_pct`.

## Localization (de / en)

`config [general] locale = de | en` (override per run with `--locale`).
It controls the narration language, the static voice-prompt audio, the menu
keywords, STT language and the world content. **German prompts are kept
verbatim**; English equivalents were added. Worlds exist in both languages
(`data/worlds/<id>.json` for de, `<id>.en.json` for en) with isolated RAG.

```bash
uv run storyteller voice-prompts build --all-locales   # render de + en audio
uv run storyteller run --locale en                     # play in English
```

## Commands

```bash
uv run storyteller info                          # configuration
uv run storyteller seed                          # write seed worlds (de+en)
uv run storyteller hw-test                        # Pi hardware (quiet)
uv run storyteller rag build [--force]            # index worlds (per locale)
uv run storyteller voice-prompts build [--all-locales]
uv run storyteller wait-sounds build              # per-world ambience loops
uv run storyteller chat [--world ID] [--locale de|en] [--load NAME]
                                                 # text REPL, no STT/TTS/audio
uv run storyteller demo --world sternenfahrt [--locale en] --text "…"
uv run storyteller run [--world ID] [--ptt] [--text] [--silent] \
                       [--profile pi|pc] [--locale de|en] [--load NAME]
uv run storyteller netcheck [--check]             # Wi-Fi onboarding (--check: read-only)
uv run storyteller admin                          # web admin (uv sync --extra web)
```

`run` without `--world` starts the voice menu (wake-word gated); without a
wake word it falls back to push-to-talk (Enter). During a story say
**"Hey Jarvis" → "System"** for the spoken system menu (save / quit / undo /
load / close). Install the wake word: `bash scripts/install_wakeword.sh`.
Bluetooth (later): `bash scripts/setup_bluetooth.sh` + `[audio] backend="pipewire"`.

## Documentation

- [docs/SETUP_PI.md](docs/SETUP_PI.md) — Raspberry Pi 4 + ReSpeaker setup
- [docs/SETUP_PC.md](docs/SETUP_PC.md) — running on a normal PC
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — how to play (voice & text)
- [PLAN.md](PLAN.md) — architecture, decisions, roadmap
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — dependency licenses

## Story logic

The narrator actively involves the player (free speech, no menu), follows a
**macro arc** and a dynamically planned **substory**: once resolved, the
architect plans the next one (RAG + context); the plan is adjustable via
tool / prompt injection. An abstract **story dynamic** (new antagonist /
unforeseen event …) spices planning and play without derailing the arc.
Per-session cost cap (graceful wrap-up). Follow-up questions get short answers.

## Safety

Every player input is sent to the OpenAI moderation model
(`omni-moderation-latest`) **before** the narrator answers; on a threshold
hit the turn is politely refused. Thresholds are configurable in the admin
website (**Moderation**). Played stories are recorded as transcripts
(player input, moderation result, every LLM tool call + result, narrator
replies) and viewable in the admin (**Verläufe**).

## License

This project's own source is **MIT** (see [LICENSE](LICENSE)). All required
Python dependencies are permissive (MIT/BSD/Apache/MPL). Notable caveats —
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):

- **`pedalboard` is GPLv3** — only the *optional* `audiofx` extra (voice
  reverb), dynamically imported with a pass-through fallback; not bundled.
  Without it the project stays MIT-clean; if you enable and redistribute it,
  GPLv3 applies to that combined work.
- **openWakeWord** code is Apache-2.0, but its default pretrained models
  (e.g. "hey jarvis") are **CC-BY-NC-SA 4.0 (non-commercial)**. Models are
  downloaded at install, not shipped; for commercial use train/replace them.
- Vendored ReSpeaker drivers (`hardware/pixel_ring_v2.py`,
  `hardware/tuning.py`) are from Seeed Studio under **Apache-2.0**, retained
  with attribution (not relicensed).

Note: MIT permits commercial use; it cannot restrict commercial use to
"by permission only" — that would require a non-open source-available
license (e.g. PolyForm Noncommercial) instead.
