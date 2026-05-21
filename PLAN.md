# Storyteller — Roadmap

The system is implemented and in use. Architecture, setup and usage are
documented in [README.md](README.md), [AGENTS.md](AGENTS.md) and
[docs/](docs/). This file tracks **what's still open** after the
monorepo + LangGraph migration.

---

## What changed in the migration (for context)

- **Monorepo**: uv workspace with `packages/{core,voice,hardware}` and
  `apps/{cli,pi,web-ui,web-admin}`. Single `.venv`, single `uv.lock`.
- **Engine**: rewritten as a `langgraph.StateGraph` with `SqliteSaver`
  checkpointer at `data/checkpoints.db`. Per-session `thread_id`. Pre-narrator
  fan-out runs moderate / ensure_substory / retrieve_rag / roll_dynamic in
  parallel. In-turn replan after `complete_substory`. Branching via
  `engine.history()` / `engine.rewind_to(...)`.
- **Web**: two separate apps — `web-ui` (play) and `web-admin`. Each has a
  FastAPI backend and a SvelteKit + TypeScript frontend (yarn 4). The
  legacy inline-HTML admin is preserved as `legacy_app.py` for porting
  reference.
- **Save format**: clean cut. Pre-LangGraph `data/saves/*.json` are NOT
  migrated. The LangGraph checkpointer owns session state now.

---

## Open

### Voice in the web Play-UI
Browser MediaRecorder → WS (`/ws/voice/{thread_id}`) → server-side STT
(OpenAI Whisper) → `engine.turn` → server-side TTS → binary audio frames
back to the browser → `<audio>`. The WS endpoint is reserved and currently
returns "not implemented".

Approx. work: 1-2 sessions. Hardest part is jitter-tolerant streaming on
both ends.

### `apps/pi` voice loop
Skeleton in place; raises on `main()`. The pre-migration voice loop lives
at `apps/cli/src/storyteller_cli/_legacy.py` and needs porting against the
new engine API (`StoryEngine.turn(text)` returns a string; no more
`snapshot`/`restore`). Wakeword + LEDs + ALSA backend + voice menu all
stay as-is from `storyteller_hardware`.

Needs Pi hardware on hand for end-to-end testing (ReSpeaker + ALSA + LEDs).

### Admin endpoints — DONE (ported from `legacy_app.py`)
Now live on the new admin backend, with frontend pages:
- `POST /api/worlds/generate` — async LLM world generation (JobRegistry) →
  `/generate` page with job polling, redirects to the new world on success
- `POST /api/worlds/{id}/reindex` — async RAG reindex → button on the
  world detail page
- `GET /api/transcripts`, `GET /api/transcripts/{name}` — transcript list +
  parsed-event viewer → `/transcripts` and `/transcripts/[name]` pages

Still legacy-only: per-piece "suggest" (LLM suggestions for a single
place/person/etc) — see `world_suggest` in `legacy_app.py`.

### Admin frontend — structured forms
The world editor at `/worlds/[id]` is currently a raw JSON textarea (round-trips
through Pydantic on save). Replace with structured forms for the common
shapes: places / persons / items / glossary / history / fragments /
random tables / blueprint beats / story patterns / tone. Settings page is
also bare; could group + label more clearly.

### Web auth / multi-session UX
Today the backend supports per-session `thread_id`, but the play UI just
generates a fresh UUID per "Geschichte beginnen" and has no resume / session
list. Once multi-user matters (web deployment beyond the Pi network),
add: cookie-based session id, "your sessions" list, optionally name+PIN.

### Bluetooth output (carried over from before the migration)
`PipeWireBackend` + `scripts/setup_bluetooth.sh` exist and the backend is
switchable at runtime via the admin `/settings` page (writes `data/audio.json`)
or via voice (system menu → "Audio"). Only the actual PipeWire/Bluetooth
path is **unverified here** because this Pi has no PipeWire; on suitable
hardware run the script, pair a BT speaker, then select `pipewire` in
admin. (Mic capture stays on the ReSpeaker.)

### Custom German wake word (optional)
Currently the default English model "hey jarvis" (openWakeWord). A custom
German phrase needs a one-off Colab training; drop the `.onnx` and set
`config.wakeword.model`. Without a wake word the loop falls back to
push-to-talk / text mode.

---

## Standing operational caveats

- **`uv sync` prunes the wake-word packages** (openwakeword/onnxruntime/…
  no py3.13 wheels for tflite-runtime). Re-run `scripts/install_wakeword.sh`
  after any `uv sync` (only relevant once `apps/pi` is implemented).
- ALSA capture must be `dsnoop` (wake word + 6 s capture share the mic);
  the app addresses devices via the backend abstraction.
- Cost: STT + LLM + TTS per turn — session cost cap + logging are in place;
  keep an eye on usage. Cap triggers a graceful wrap-up in the narrator.
- Secrets: never commit `.env`; the GitHub token and the OpenAI key were
  shared in chat at some point and should be rotated.
- Checkpointer DB (`data/checkpoints.db`) grows with usage. No retention
  policy yet; for production-ish use, periodically prune old threads.
