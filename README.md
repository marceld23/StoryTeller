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
uv run storyteller run --profile pc            # PC mic + speakers
uv run storyteller run --text                  # keyboard input (no mic)
uv run storyteller run --text --silent         # pure text, no audio at all
```

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
uv run storyteller demo --world sternenfahrt [--locale en] --text "…"
uv run storyteller run [--world ID] [--ptt] [--text] [--silent] \
                       [--profile pi|pc] [--locale de|en] [--load NAME]
uv run storyteller admin                          # web admin (uv sync --extra web)
```

`run` without `--world` starts the voice menu; without a wake word it falls
back to push-to-talk (Enter). In-loop voice commands: save / load / quit
(localized). Install the wake word: `bash scripts/install_wakeword.sh`.
Bluetooth (later): `bash scripts/setup_bluetooth.sh` + `[audio] backend="pipewire"`.

## Story logic

The narrator actively involves the player (free speech, no menu), follows a
**macro arc** and a dynamically planned **substory**: once resolved, the
architect plans the next one (RAG + context); the plan is adjustable via
tool / prompt injection. An abstract **story dynamic** (new antagonist /
unforeseen event …) spices planning and play without derailing the arc.
Per-session cost cap (graceful wrap-up). Follow-up questions get short answers.

## Status

Done & tested: **Phases 0–9** — setup/HW, voice pipeline (STT→LLM→TTS→reverb→
output, wait sound, LED), wake word (default + PTT fallback), RAG, **story
engine v2** (substory state machine, co-creation, story dynamic, tools),
voice menu, save games, web admin, cost cap, logging, systemd autostart,
**PC mode** and **de/en localization**.

🟡 **Phase 8 (Bluetooth)** is implemented but not testable on this Pi (no
PipeWire active). ⏳ **Phase 10** (local STT/TTS models) needs a Pi 5 + AI HAT.
Details: [PLAN.md](PLAN.md).
