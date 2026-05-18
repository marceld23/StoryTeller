# Storyteller — Open items / roadmap

The system is implemented and in use. Architecture, setup and usage are
documented in [README.md](README.md) and [docs/](docs/). This file now tracks
**only what is still open** — everything already done was removed.

---

## Open

### Phase 8 — Bluetooth output (built; not testable on this Pi)
`PipeWireBackend` + `scripts/setup_bluetooth.sh` exist behind the audio
abstraction, and the backend is switchable at runtime — via the admin
`/audio` page or by voice (system menu → "Audio"), persisted in
`data/audio.json` (also `[audio] backend = "pipewire"` / `pw_sink` in
config). Only the actual PipeWire/Bluetooth path is **unverified here**
because this Pi has no PipeWire: on suitable hardware run the script, pair a
BT speaker, then select `pipewire`. (Mic capture stays on the ReSpeaker.)

### Custom German wake word (optional)
Currently the default English model "hey jarvis" (openWakeWord). A custom
German phrase needs a one-off Colab training; drop the `.onnx` and set
`config.wakeword.model`. Without a wake word the loop falls back to
push-to-talk / text mode.

---

## Standing operational caveats

- **`uv sync` prunes the wake-word packages** (openwakeword/onnxruntime/…,
  no py3.13 wheels for tflite-runtime). Re-run `scripts/install_wakeword.sh`
  after any `uv sync`.
- Run the loop via `.venv/bin/python -m storyteller.cli run`, **not**
  `uv run` (concurrent `uv run` can cause a spawn race). The systemd unit
  already does this.
- ALSA capture must be `dsnoop` (wake word + 6 s capture share the mic);
  the app addresses devices via the backend abstraction.
- Cost: STT+LLM+TTS per turn — session cost cap + logging are in place;
  keep an eye on usage.
- Secrets: never commit `.env`; the GitHub token used for pushes and the
  OpenAI key were shared in chat and should be rotated.
