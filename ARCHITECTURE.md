# Storyteller — Architecture

How the system is built. For conventions see [AGENTS.md](AGENTS.md), for
setup/usage [README.md](README.md) + [docs/](docs/), for open work
[PLAN.md](PLAN.md).

---

## 1. Overview

Storyteller is an interactive, voice-controlled narrator powered by the OpenAI
API and a [LangGraph](https://langchain-ai.github.io/langgraph/) story engine.
The **engine and all OpenAI calls run on a host** (Raspberry Pi or PC); the
ways to interact with it are separate apps:

| Mode | App / entry point | Notes |
|---|---|---|
| Pi voice appliance | `storyteller-pi run` | ReSpeaker + wake word + LED ring + ALSA |
| PC text REPL | `storyteller-cli chat` | keyboard, no audio |
| Browser play | `storyteller-web-ui` (`:8090`) | text or tap-to-talk voice (WebSocket) |
| Admin | `storyteller-web-admin` (`:8080`) | world editor, generation, transcripts, settings |

All four share the same `storyteller_core` engine and worlds; only the I/O
shell differs.

---

## 2. Monorepo layout

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/): one root
`.venv`, one `uv.lock`. Layering is strict — **apps depend on packages, and
within packages `hardware`/`voice` depend on `core`, never the reverse.**

```
packages/
  core/      storyteller_core       engine (LangGraph), worlds, config, i18n, RAG, persistence
  voice/     storyteller_voice      STT / TTS / FX, wait-loop, wake word, prompt cache  (API-coupled, no HW I/O)
  hardware/  storyteller_hardware   audio backends, LED ring, ReSpeaker, voice menu, Wi-Fi onboarding, runtime profile
apps/
  cli/       storyteller_cli              text REPL: chat / info / worlds / seed / history / prune
  pi/        storyteller_pi               Pi voice loop (run) + Wi-Fi onboarding (netcheck)
  web-ui/    backend (FastAPI+WS) + frontend (SvelteKit SPA)   player
  web-admin/ backend (FastAPI JSON) + frontend (SvelteKit SPA) admin
```

Python: **uv only**. Frontends: **yarn 4 only**, built static (see §7).

---

## 3. Story engine (`storyteller_core.story`)

A thin façade [`StoryEngine`](packages/core/src/storyteller_core/story/engine.py)
wraps a compiled `langgraph.StateGraph`. The engine holds **no story state of
its own** — per-session state lives in the LangGraph checkpointer, keyed by
`thread_id`; non-serializable handles (Config, World, RAG, Transcript) travel
in an `EngineContext` via `RunnableConfig.configurable`.

```python
engine = StoryEngine(cfg, world, rag=rag, transcript=tr, thread_id="pi-immerwald")
engine.opening()          # first narration
engine.turn(user_text)    # -> narration string
engine.undo_last()        # roll back one turn (checkpoint rewind)
engine.history() / engine.rewind_to(cp_id)   # branching ("what if…")
```

### Graph topology ([graph.py](packages/core/src/storyteller_core/story/graph.py), [nodes.py](packages/core/src/storyteller_core/story/nodes.py))

```
START → init_turn → moderate ──blocked──→ blocked_finalize → END
                            └──ok──→ fanout
   fanout ─┬→ ensure_substory ─┐
           ├→ retrieve_rag ─────┤  (pre-narrator phase, in parallel)
           ├→ roll_dynamic ─────┤
           └→ compute_flags ────┘
                                 ↓
                              curate (gate: small LLM call, picks per-turn reveals)
                                 ↓
                          build_prompt → narrate
   narrate ─tool_calls?─→ dispatch_tools ─complete_substory?─→ replan → narrate
           └─text────────→ finalize → END
```

The pre-narrator fan-out (moderation already done; substory ensure, RAG
retrieval, dynamic roll, flags) runs **concurrently** — wall-clock latency is
`max()` not `sum()`. After the narrator calls `complete_substory`, an in-turn
`replan` node plans the next substory before narrating again.

**Per-turn latency optimizations:**

- *Moderation skip* — trivially short benign inputs (`Ja`, `Vielen Dank`) bypass
  the OpenAI moderations call, saving ~1.3 s on those turns.
- *Narration gate* ([curator.py](packages/core/src/storyteller_core/story/curator.py))
  — one cheap LLM call per turn that picks which AUTHORED reveals the narrator
  may use. Configured via `gate_llm` (empty → fall back to `planner_llm` →
  `story_llm`). Empty gate output = no extra constraints; player improvisation
  is never gated.
- *TTS streaming* — XTTS chunks are fetched in **parallel** (ThreadPoolExecutor)
  and consumed by a streaming player ([play_stream](packages/hardware/src/storyteller_hardware/audio/player.py))
  that starts the first chunk while later ones are still rendering. Wall-clock
  TTS latency drops from `sum(chunks)` to roughly `max(chunks)` + the playback
  duration of the first chunk masks the rest.

### State ([state.py](packages/core/src/storyteller_core/story/state.py))

`StoryState` (a `TypedDict`, persisted by `SqliteSaver`):
- **Long-lived**: `locale`, `memory` (chat messages), `substory`, `macro_index`,
  `known_facts`, `synopsis`, `char_state`, `beat_turns`, `cost`, `pending_fold`.
- **Turn-scoped** (reset by `init_turn`): `user_text`, `moderation_ok`,
  `retrieved`, `dyn_hint`, `brief`, `wrap_up`, `transition`, `response`,
  `system_prompt`, `pending_tool_calls`, `narrate_iter`, `just_completed_substory`.

### Dramaturgy

- **Macro arc — multi-variant** ([blueprint.py](packages/core/src/storyteller_core/story/blueprint.py), [schema.py](packages/core/src/storyteller_core/worlds/schema.py)) — every world carries up to 4 `BlueprintVariant` arcs (`world.blueprints`), each with its own length (short / medium / long / epic), structure (linear / parallel / spiral / frame / mosaic) and twist_kind (betrayal / revelation / sacrifice / hidden_enemy / red_herring / role_reversal / circular / ""). At every new substory the planner calls `substory.choose_blueprint_variant()` — ONE planner-LLM call that sees the variant catalog + the player's recent context and returns the variant index — written to `state.blueprint_choice`. Engine code dispatches through `World.active_blueprint(state.blueprint_choice)` instead of touching `world.blueprint` directly, so single-variant worlds (the legacy field) keep working unchanged. `macro_index` continues to track position within the currently active variant's beats; switching to a different variant resets `macro_index = 0`.
- **Substory** ([substory.py](packages/core/src/storyteller_core/story/substory.py)) — a mini-arc planned by the *architect* (planner LLM) from a beat skeleton chosen by world `complexity` ([patterns.py](packages/core/src/storyteller_core/story/patterns.py): three-act, mystery, hero's journey, kishōtenketsu, …).
- **Story dynamics** ([dynamics.py](packages/core/src/storyteller_core/story/dynamics.py)) — abstract twists ("a new antagonist", "an unforeseen event") woven in subtly, never resetting the arc.
- **Soft plot-pressure / Storymodus** ([pressure.py](packages/core/src/storyteller_core/story/pressure.py)) — a continuous `plot_pressure ∈ [0, 1]` in state, EMA-smoothed from a sliding window of per-turn `TurnSignal`s (tools fired, lexical match against the active arc, two phrase patterns). Five threshold-based consumers gradually fade the plot machinery in and out: the **gate** is skipped below `pressure_gate_min` (0.10) and scales `max_reveals` linearly between there and `pressure_gate_strict` (0.70); the narrator's **substory block** has three tiers — full → ambient (hook + current-beat-name only, no goal/tension push) → free-exploration; the **substory-tools** (`advance_beat`, `complete_substory`, `get/adjust_substory_plan`) drop out of the tool list below `pressure_substory_tools` (0.30); the **beat-nudge** threshold scales inversely (lower pressure = nudge after more turns; 0 = never); and `ensure_substory`/`replan` themselves are short-circuited below `pressure_substory_plan` (0.20) — the live substory then gets parked into `dormant_substory` (status `dormant`) so a future spike can revive the same arc instead of forcing a fresh plan. An optional one-call planner-LLM **tiebreaker** ([nodes._engagement_tiebreaker](packages/core/src/storyteller_core/story/nodes.py)) fires only when the heuristic stays in the uncertain band [0.30, 0.60] for 3 turns straight; its `{on_arc | lateral | off_arc, confidence}` verdict overrides that turn's signal when confidence ≥ 0.7. An admin-pinnable `story_mode` setting in `data/settings.json` (values: `auto` | `planner` | `frei`) overrides the heuristic — `planner` pins pressure to 1.0, `frei` to 0.0, `auto` lets the heuristic drive. Surfacing: every pressure decision lands in the transcript as `[pressure] mode=… signal=… target=… smoothed=… effective=…` so the admin UI can render the decision history alongside the gate / planner traces.
- **Memory model** — two-tier. The short window is `cfg.story.short_term_memory_turns` (default **24** = 48 messages) inline in the narrator's system prompt. When the window plus a `synopsis_batch` (default 8) of overflow accumulates, the oldest batch is folded into a rolling `synopsis` (max `synopsis_max_chars`, default 900) by a single `planner`-LLM call that sees BOTH the prior synopsis and the dropped messages — so the new synopsis is a merge, not a replacement (the system prompt sharpens this with "never drop established content"). A defensive shrink-floor (`new < 70% × old` when `old ≥ 300 chars`) retries once with a corrective prompt and falls back to a lossless `_heuristic_fold` (concat) on a second failure — the old synopsis is never lost. Anything queued during transient API failures lives in `pending_fold` and gets re-tried next turn.
- **Known facts / character state** — `remember_fact`/`forget_fact`/`list_known_facts` and `track_character` tools ([tools.py](packages/core/src/storyteller_core/story/tools.py)); both bounded and injected into the system prompt.

### Tools the narrator LLM can call ([tools.py](packages/core/src/storyteller_core/story/tools.py))
`retrieve_world_fact`, `lookup_glossary`, `get_world_overview`,
`roll_random_event`, `roll_story_dynamic`, `remember_fact`, `forget_fact`,
`list_known_facts`, `track_character`, `advance_beat`, `complete_substory`,
`get_/adjust_substory_plan`.

### RAG ([rag.py](packages/core/src/storyteller_core/story/rag.py))
Per-`(world, locale)` retrieval with **sqlite-vec** + OpenAI embeddings
(`data/rag.db`, partition key `<world_id>:<locale>`). The retrieval query
blends the player utterance with recent narration.

### Moderation & cost
Every external player input is checked by the OpenAI moderation model **before**
the narrator answers ([moderation.py](packages/core/src/storyteller_core/story/moderation.py); per-category thresholds in `data/moderation.json`, fail-open + logged).
A per-session USD cost cap ([cost.py](packages/core/src/storyteller_core/story/cost.py)) triggers a graceful wrap-up. Played sessions are recorded as JSONL transcripts ([transcript.py](packages/core/src/storyteller_core/story/transcript.py)).

---

## 4. Voice pipeline (`storyteller_voice`)

- **STT / TTS** ([stt.py](packages/voice/src/storyteller_voice/stt.py), [tts.py](packages/voice/src/storyteller_voice/tts.py)) — OpenAI; TTS returns PCM for direct playback.
- **FX** ([fx.py](packages/voice/src/storyteller_voice/fx.py)) — optional `pedalboard` reverb (GPLv3 `audiofx` extra, dynamically imported with a pass-through fallback → MIT-clean without it).
- **Wait-loop** ([waitloop.py](packages/voice/src/storyteller_voice/waitloop.py)) — per-world ambience plays (LED *think*) while the LLM/TTS run.
- **Wake word** ([wakeword.py](packages/voice/src/storyteller_voice/wakeword.py)) — openWakeWord (ONNX). `config.wakeword.model` (+ `model_de`/`model_en`) selects a built-in name or a custom `.onnx`.
- **Prompt cache** ([prompts.py](packages/voice/src/storyteller_voice/prompts.py)) — fixed menu/intro lines rendered once via TTS and cached to `data/voice_prompts/<locale>/*.wav` (token/latency saver; live fallback + re-render on text change).

---

## 5. Hardware abstraction (`storyteller_hardware`)

- **Audio backends** ([audio/backend.py](packages/hardware/src/storyteller_hardware/audio/backend.py)) — one ABC, three impls: `AlsaSoftvolBackend` (Pi, `amixer` softvol + aplay/arecord), `PortableBackend` (PC, `sounddevice`, software gain), `PipeWireBackend` (Bluetooth). All expose `loop_play`, `mic_frames`, `record_until_silence` (VAD: stops on a trailing pause), `set/get_volume`. `get_backend(cfg)` resolves the concrete backend and applies the persisted volume.
- **Runtime profile** ([runtime.py](packages/hardware/src/storyteller_hardware/runtime.py)) — auto-detects `pi` vs `pc` (ReSpeaker present?); reads/writes the `data/*.json` runtime overrides (audio, settings).
- **LED ring** ([leds.py](packages/hardware/src/storyteller_hardware/leds.py)) + vendored ReSpeaker drivers (`pixel_ring_v2.py`, `tuning.py`, Seeed, Apache-2.0). LED is a no-op off-Pi.
- **Boot flow** (in [apps/pi/.../main.py](apps/pi/src/storyteller_pi/main.py), `cmd_run`) — plays the cached `welcome` greeting (toggleable via `intro_enabled` in `data/settings.json`). The longer in-story command briefing (`intro_commands`, with wake-hint + repeat-command mention) is deferred to AFTER world selection, so a cold start no longer dumps a wall of commands on a player who might not start a story at all. Then the device **idles silently** until *"Hey Jarvis"* fires. On wake-word it asks `start_question` (*"Möchtest du eine Geschichte starten?"*) and only on a *yes* hands off to the voice menu. *No* / unclear (after one re-ask) drops back to the wake-word wait.
- **Per-story sub-loop** (`_play_one_story()` inside `cmd_run`) — one world-selection + engine build + opening + STT loop per call; returns either `"shutdown"` (player asked to power the appliance off → outer loop runs `goodbye` + `sudo systemctl poweroff`) or `"next_story"` (player said *"Geschichte beenden"* → outer loop runs the wake-word gate + world menu again, fresh engine). KeyboardInterrupt is treated as shutdown. The outer `while True:` loop in `cmd_run` is what makes the appliance survive end-of-story without a systemd restart.
- **Mode branch & Welten-Verwaltung** — after `_await_start_yes` the loop asks `mode_question` ("Welt spielen oder Welten verwalten?") via `classify_play_mode()`. *Play* hands off to the regular voice world menu; *Manage* hands off to `_manage_worlds_interactively()` (apps/pi/.../main.py). The manage sub-menu dispatches on `classify_manage_action()` into **new world** (delegates to `_design_world_interactively` → [`WorldDesignInterview`](packages/core/src/storyteller_core/story/world_design.py) + [`generate_world`](packages/core/src/storyteller_core/worlds/generate.py) under a neutral `generic_waiting.wav` ambient), **copy / rename / delete world** (each: pick a world via the same `classify_world_choice` LLM classifier the play-menu uses, then live-TTS confirm with the world name, then call `worlds.registry.copy_world` / `rename_world` / `delete_world`). Each registry helper cleans up JSON + RAG (`WorldRAG.purge_world` / `move_world`) + Pi checkpoints (`graph.delete_threads_matching` / `migrate_thread_prefix`) atomically. Single action per session → returns to wake-word idle. The voice-design interview is persisted as `data/transcripts/_world_design-<utc-ts>.jsonl` for audit.
- **Voice menu** ([menu/voice_menu.py](packages/hardware/src/storyteller_hardware/menu/voice_menu.py)) — LLM-classified world selection; once entered it listens twice before gating on the wake word.
- **Wi-Fi onboarding** ([net/onboarding.py](packages/hardware/src/storyteller_hardware/net/onboarding.py)) — if offline at boot, opens an AP + captive portal (`storyteller-pi netcheck`).

---

## 6. Web apps

Both backends are **FastAPI** processes that **also serve their SvelteKit SPA**
as static files (built with `@sveltejs/adapter-static`, SPA fallback). A
catch-all route returns the asset if present, else `index.html` — so client
deep links work. One process, one port, no Node at runtime.

- **web-ui** (`:8090`, [main.py](apps/web-ui/backend/src/storyteller_web_ui_backend/main.py)) — REST: `/api/worlds`, `/api/sessions`, session state/undo, `/api/sessions/<thread>/replay` (one-shot TTS of the last narration — backs the text mode's 🔊 line buttons and the voice mode's "Sag das nochmal"); WebSocket: `/ws/play/{thread}` (text) and `/ws/voice/{thread}` (browser `MediaRecorder` → server STT → `engine.turn` → server TTS → WAV frame back). Frontend: card-grid world picker with resume highlight, header showing the active world's name + genre, shared bubbles + spinner via [lib/ui.css](apps/web-ui/frontend/src/lib/ui.css) and components in [lib/components/](apps/web-ui/frontend/src/lib/components/) (`WorldCard`, `ChatLine`, `MicMeter`). Text chat has autoscroll + new-message pill, live char-counter, opt-in per-line TTS replay, and a confirm step before ending. `/voice` tap-to-talk has a live mic-level meter, recording-time counter, **browser-side VAD** (auto-stop after ~1.5 s of silence following ≥350 ms of speech), wait-sound toggle (persisted), and separate **⏸ Pause** vs. **✋ Unterbrechen** controls (local-only vs. server `interrupt`). Errors from the backend are filtered to friendly one-liners before being shown to the player.
- **web-admin** (`:8080`, [main.py](apps/web-admin/backend/src/storyteller_web_admin_backend/main.py)) — REST JSON for worlds (CRUD), settings (models/audio/moderation overrides), async jobs (world **generation** + RAG **reindex** via an in-process [JobRegistry](apps/web-admin/backend/src/storyteller_web_admin_backend/jobs.py)), per-piece LLM **suggest**, **transcripts**. Frontend: structured world editor, generation with job polling, transcript viewer, settings.

**Security** (both): an HTTP middleware gates `/api/*` (except `/api/health`)
with an optional shared bearer token (`STORYTELLER_WEB_TOKEN`; empty = open
LAN, the default). WebSockets authenticate via `?token=`. CORS is restricted
to `web.allowed_origins` (the SPA is same-origin and needs none). Player turn
and generation-prompt lengths are capped. Both frontends attach the token and
prompt for it on a 401. Theme: dark default + light, toggle persisted.

---

## 7. Configuration & overrides ([config.py](packages/core/src/storyteller_core/config.py))

- `config/config.toml` — all tunables (models, audio, story, capture,
  moderation, netcheck, web, …), validated by Pydantic.
- `.env` — `OPENAI_API_KEY`, optional `STORYTELLER_WEB_TOKEN`.
- **Runtime overrides** (admin- or voice-editable, gitignored) layered on top
  at load time: `data/models.json` (model names + penalties), `data/audio.json`
  (backend, sink, volume), `data/moderation.json` (thresholds),
  `data/settings.json` (intro on/off).
- `ROOT` is auto-found (the dir with `pyproject.toml` + `packages/`), so all
  apps resolve `data/`, `config/` and worlds consistently.

---

## 8. Persistence & data (`data/`, all gitignored except seed worlds)

| Path | What |
|---|---|
| `checkpoints.db` | LangGraph `SqliteSaver` — per-`thread_id` session state. Bound with `storyteller-cli prune`. |
| `worlds/<id>.json`, `<id>.en.json` | World definitions (seed worlds are committed; generated ones are not) |
| `rag.db` | sqlite-vec embeddings, per `(world, locale)` |
| `transcripts/*.jsonl` | played sessions (input, moderation, tool calls, narration) |
| `voice_prompts/<locale>/*.wav` | cached menu/intro audio |
| `*.json` (models/audio/moderation/settings) | runtime overrides |

---

## 9. External services (OpenAI)

[oai.py](packages/core/src/storyteller_core/oai.py) builds **one client per
purpose** (`get_chat_client(role)` for story/planner/gen, plus
`get_stt/tts/embedding_client`; `get_client` for moderation + default). The
`gen` client uses a long timeout (180 s, 1 retry); the rest are
latency-tuned (30 s, 5 retries). Models (all configurable, with admin
overrides in `data/models.json`): `story_llm` (narrator), `planner_llm`
(architect + summariser; default = story_llm), `gen_llm` (world/content
generation; default the larger model), `stt`, `tts`, `embedding`,
`moderation`; **temperature per role** (narrator/planner/gen), plus
**reasoning effort per role** (`story_reasoning_effort` / `planner_…`
/ `gen_…` / `gate_…`; values `none|low|medium|high|xhigh|""`; defaults
`low` for the narrator, `medium` for planner + world gen, gate
inherits from planner). The kwarg is only forwarded when set to a
non-`none` value, so older models + local servers stay untouched.

**Custom endpoints:** each purpose has an optional `<purpose>_endpoint`
(`base_url` + `api_key`, empty = OpenAI), so any call type can point at a
self-hosted OpenAI-compatible server (vLLM / llama.cpp / Ollama / LM Studio)
independently. Moderation always uses OpenAI. Client cache keys on
`(api_key, base_url, timeout, retries)`. See
[docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md).

---

## 10. Deployment

### Option A — systemd on a host (Pi or PC)

| Service | Runs | Port |
|---|---|---|
| `storyteller.service` | `storyteller-pi run` | — (voice) |
| `storyteller-admin.service` | `storyteller-web-admin` | `:8080` |
| `storyteller-web-ui.service` | `storyteller-web-ui` | `:8090` |
| `storyteller-netcheck.service` | `storyteller-pi netcheck` | boot Wi-Fi onboarding |

Bring-up: `uv sync` → `scripts/install_wakeword.sh` (re-run after every
`uv sync`) → `scripts/build_frontends.sh` → `scripts/install_services.sh`.
See [docs/SETUP_PI.md](docs/SETUP_PI.md).

### Option B — Docker (web services only)

A docker/ folder ships a self-host stack for the two web services. The
Pi voice-loop, CLI and local-AI server stacks stay outside (they're
host-coupled — audio devices, GPIO, GPU). The Docker layout:

| File | Purpose |
|---|---|
| `docker/Dockerfile.web` | 3-stage build: node-build (yarn 4 → static frontends) → python-deps (uv sync workspace) → runtime (python:3.13-slim + venv + sources, no Node) |
| `docker/docker-compose.yml` | Orchestrates `web-ui:8090` + `web-admin:8080` + Caddy. Both backends share **one** image; only the CMD differs. |
| `docker/Caddyfile` | TLS via `tls internal` (self-signed). `:443` → web-ui, `:8443` → admin, `:80` → 301 redirect. |
| `docker/.env.example` | OPENAI / OPENROUTER keys + admin/player tokens. |

x86_64 only (no multi-arch buildx in compose). `./data/` is bind-
mounted from the host so persistence survives `compose down`. Empty
on first run — generate worlds via the admin UI. Pi co-host on the
same machine: bind-mount `/home/pi/storyteller/data:/app/data` and
both sides share state. Full walkthrough:
[docker/README.md](docker/README.md).

---

## 11. Tooling, tests, CI

- `ruff` (lint) + `pytest` + `mypy` (advisory) configured in the root
  `pyproject.toml` `[dependency-groups] dev`.
- `tests/` — offline tests (mocked OpenAI client): config overrides, KnownFacts,
  world-generation hardening, checkpoint prune, smoke.
- `.github/workflows/ci.yml` — `uv sync --frozen` → ruff → pytest → mypy.

---

## 12. Localization

`config.general.locale` (`de` | `en`, per-run `--locale`) drives narration
language, voice-prompt audio, menu keywords, STT language and world content.
German prompts are authored verbatim; worlds exist per locale
(`<id>.json` / `<id>.en.json`) with isolated RAG partitions.
