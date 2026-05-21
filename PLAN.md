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
  FastAPI backend and a SvelteKit + TypeScript frontend (yarn 4, built as a
  static SPA and served by the backend).
- **Save format**: clean cut. Pre-LangGraph `data/saves/*.json` are NOT
  migrated. The LangGraph checkpointer owns session state now.

---

## Open

### Voice in the web Play-UI — DONE (push-to-talk)
Browser `MediaRecorder` → WS (`/ws/voice/{thread_id}`) → server-side STT
(OpenAI Whisper) → `engine.turn` → server-side TTS → WAV frame back to the
browser → `<audio>`. Frontend page `/voice` with a hold-to-talk button.

Verified: STT/TTS round-trip works standalone (synthesize → transcribe gives
the phrase back). Browser end (mic capture + playback) is best tested on a
real PC with a microphone.

Possible follow-up: streaming STT/TTS (lower latency than push-to-talk),
client-side VAD so the user doesn't have to hold a button, barge-in.

### `apps/pi` voice loop — DONE (ported to the LangGraph engine)
`storyteller-pi run` is the full voice loop: greeting + optional intro,
voice world-menu, wake word + follow-up window, `record_until_silence`,
wait-sound loop under TTS, spoken system menu (quit/undo/audio/intro/
close; "save" is implicit now), per-world `thread_id` ("pi-<world>") so a
story auto-resumes across restarts (`--new` forces a fresh branch).
`storyteller-pi netcheck` wraps the Wi-Fi onboarding. No snapshot/restore
or SaveManager any more — the checkpointer owns state.

systemd units updated to the new console scripts (`storyteller-pi run`,
`storyteller-web-admin`, `storyteller-web-ui`, `storyteller-pi netcheck`).

Verified on the Pi: imports + WakeWord availability + clean service start
(reaches greeting/menu). End-to-end spoken play still wants a person at
the ReSpeaker; mic/TTS round-trip itself is already covered.

### Admin endpoints — DONE
Now live on the new admin backend, with frontend pages:
- `POST /api/worlds/generate` — async LLM world generation (JobRegistry) →
  `/generate` page with job polling, redirects to the new world on success
- `POST /api/worlds/{id}/reindex` — async RAG reindex → button on the
  world detail page
- `GET /api/transcripts`, `GET /api/transcripts/{name}` — transcript list +
  parsed-event viewer → `/transcripts` and `/transcripts/[name]` pages

Per-piece "suggest" is also ported: `POST /api/worlds/{id}/suggest`
{kind, prompt} returns one schema-shaped content piece from the gen model.

### Admin frontend — structured forms — DONE
The world editor at `/worlds/[id]` is now a structured form:
- core scalars (name/genre/role/description/situation/style/voice/mood/…)
- tone (darkness/humor/romance/action/horror sliders, pacing, notes)
- blueprint (premise, escalation rule, beats with tension)
- content lists (places/persons/items/glossary/history/fragments) via the
  reusable `ContentList` component, each with add / remove / ✨ suggest
- random tables with nested weighted entries
- story patterns
- a "Roh-JSON" toggle remains as an escape hatch (fx_preset etc.)

Verified round-trip: GET → edit → PUT validates through Pydantic.

Possible follow-up: settings page grouping/labels; drag-reorder for beats
and list items.

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
