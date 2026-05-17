# Storyteller

Interaktiver, sprachgesteuerter Geschichtenerzähler auf Raspberry Pi 4 mit
ReSpeaker USB Mic Array v2.0 + OpenAI.

➡ **Architektur, Entscheidungen & Phasenplan: [PLAN.md](PLAN.md)**

## Schnellstart

```bash
cd /home/pi/storyteller

# einmalig: udev-Regel (für LED-Ring & DSP-Tuning), danach ReSpeaker neu einstecken
sudo bash scripts/setup_system.sh

# Abhängigkeiten (Core)
uv sync

# Konfiguration prüfen
uv run storyteller info

# Seed-Welten schreiben (Sci-Fi "Sternenfahrt" + Fantasy "Immerwald")
uv run storyteller seed

# Hardware testen: Lautstärke, Line-Out, Mikrofon, LED-Ring, DSP-Tuning
uv run storyteller hw-test
```

## Lautstärke (ALSA softvol)

Der ReSpeaker hat keinen Hardware-Regler -> Software-Volume via `~/.asoundrc`:

```bash
amixer -c ArrayUAC10 sset Master 60%
```

## Befehle

```bash
uv run storyteller info                       # Konfiguration
uv run storyteller seed                       # 2 Seed-Welten schreiben
uv run storyteller hw-test                    # Hardware (leise)
uv run storyteller rag build [--force]        # Welten in sqlite-vec indexieren
uv run storyteller voice-prompts build        # feste Menü-Ansagen cachen
uv run storyteller demo --world sternenfahrt --text "…"   # 1 Zug (Test)
uv run storyteller run [--world ID] [--ptt] [--load NAME] # voller Sprach-Loop
uv run storyteller admin                      # Web-Admin (uv sync --extra web)
```

`run` ohne `--world` startet das Sprachmenü; ohne Wake-Word automatisch
Push-to-talk (Enter). Im Loop per Sprache: „speichern", „laden", „beenden".
Wake-Word installieren: `bash scripts/install_wakeword.sh`.
Bluetooth später: `bash scripts/setup_bluetooth.sh` + `[audio] backend="pipewire"`.

## Story-Logik

Der Erzähler bindet den Spieler aktiv ein (freie Sprache, kein Menü), folgt
einem **Makro-Spannungsbogen** und einer dynamisch geplanten **Substory**:
ist sie aufgelöst, plant der Architekt (RAG+Kontext) die nächste; der Plan ist
per Tool/Prompt-Injection anpassbar. Eine abstrakte **Story-Dynamik**
(Antagonist/Unvorhergesehenes …) würzt Planung & Verlauf, ohne den Bogen zu
kippen. Kostendeckel je Sitzung (sanfter Abschluss).

## Status

Erledigt & getestet: **Phase 0–9** — Setup/HW, Voice-Pipeline (STT→LLM→TTS→
Reverb→Line-Out, Wartesound, LED), Wake-Word (Default + PTT-Fallback), RAG,
**Story-Engine v2** (Substory-Statusmaschine, Co-Creation, Story-Dynamik,
Tools), Sprachmenü, Spielstände, Web-Admin, Kostendeckel, Logging, systemd.

🟡 **Phase 8 (Bluetooth)** ist implementiert, aber auf diesem Pi nicht testbar
(kein PipeWire aktiv). ⏳ **Phase 10** (lokale Modelle) braucht Pi 5 + AI HAT.
Details: [PLAN.md](PLAN.md).
