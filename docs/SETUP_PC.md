# Setup — normal PC (no Pi, no ReSpeaker)

Storyteller runs on any Linux/macOS/Windows PC with Python 3.13. The runtime
profile is auto-detected: no ReSpeaker ⇒ profile `pc` ⇒ portable
`sounddevice` backend (software volume), LED ring is a harmless no-op.

## 1. Install

```bash
git clone https://github.com/marceld23/StoryTeller.git
cd StoryTeller
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv not installed
uv sync
echo "OPENAI_API_KEY=sk-..." > .env
uv run storyteller seed
uv run storyteller rag build
```

## 2. Ways to run on a PC

```bash
# Plain text REPL — best for testing, NO STT/TTS/audio needed:
uv run storyteller chat
uv run storyteller chat --world immerwald --locale en

# One scripted turn (text in, spoken out):
uv run storyteller demo --world sternenfahrt --text "Ich öffne die Luke."

# Full voice loop with the PC mic + speakers:
uv run storyteller run --profile pc

# Keyboard input but no microphone:
uv run storyteller run --text
# Pure text, no audio at all:
uv run storyteller run --text --silent
```

For voice on the PC you need a working mic/speaker (PortAudio is bundled with
the `sounddevice` wheel). Volume is a software gain:
`config [audio] default_volume_pct`.

## 3. Wake word on PC (optional)

`uv run storyteller run --profile pc` uses the wake word if installed
(`bash scripts/install_wakeword.sh`), otherwise it auto-falls back to
push-to-talk. For quick testing prefer `storyteller chat` (no audio at all).

## 4. Admin website

```bash
uv sync --extra web
uv run storyteller admin        # http://localhost:8080
```

See [USER_GUIDE.md](USER_GUIDE.md) for gameplay, and the README for the
command reference.
