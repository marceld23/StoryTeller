# Storyteller — Roadmap (open items)

The system is built and in use. The design is documented in
[ARCHITECTURE.md](ARCHITECTURE.md); setup and usage in [README.md](README.md),
[AGENTS.md](AGENTS.md) and [docs/](docs/). This file tracks **only what's
still open** — finished work has been moved to ARCHITECTURE.md.

---

## Open

### Voice latency (web Play-UI)
Push-to-talk works (`/ws/voice` → server STT → engine → server TTS).
Open: streaming STT/TTS for lower latency, client-side VAD (no hold-to-talk
button), barge-in. Also: the `/voice` page has no auto-reconnect yet (the
text `/` page does).

### Multi-user web UX
Optional shared-token auth exists (`STORYTELLER_WEB_TOKEN`) and the player
resumes the last session per world. Open for real multi-user use: per-user
identity (cookie / PIN), a "your sessions" list, named sessions.

### Bluetooth audio output (unverified here)
`PipeWireBackend` + `scripts/setup_bluetooth.sh` exist and the output backend
is switchable at runtime (admin Settings / system menu → Audio). The actual
PipeWire/Bluetooth path is **unverified on this Pi** (no PipeWire). On
suitable hardware: run the script, pair a speaker, select `pipewire`. (Mic
capture stays on the ReSpeaker.)

### Custom (German) wake word
Default is the English openWakeWord model "hey jarvis". A custom phrase
(e.g. "Hey Saga") needs a one-off Colab training; drop the `.onnx` under
`models/` and set `config.wakeword.model` (or `model_de` / `model_en`).
See the analysis in chat / openWakeWord's `automatic_model_training.ipynb`.

### Polish (nice-to-have)
- Admin: drag-reorder beats and content-list items; settings page grouping.
- Tighten typing (mypy is advisory in CI) and widen tests beyond the current
  core suite (engine turn against a mocked client, RAG, web endpoints).

---

## Standing operational caveats

- **`uv sync` prunes the wake-word stack** (openwakeword / onnxruntime — no
  py3.13 wheels for tflite-runtime). Re-run `scripts/install_wakeword.sh`
  after any `uv sync`, then restart `storyteller`. (A missing wake word under
  systemd now fails fast with a clear log instead of an audible error loop.)
- ALSA capture must be `dsnoop` (wake word + capture share the mic); the app
  addresses devices via the audio-backend abstraction.
- Cost: STT + LLM + TTS per turn. A per-session cost cap triggers a graceful
  wrap-up, and player/prompt input length is capped. Keep an eye on usage.
- Checkpointer DB (`data/checkpoints.db`) grows with use. Run
  `storyteller-cli prune` periodically (e.g. cron); the keep-per-thread bound
  is configurable (`story.checkpoint_keep_per_thread`, default 100).
