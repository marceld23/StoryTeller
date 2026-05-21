# Agent instructions — StoryTeller monorepo

This is a uv-workspace monorepo. Read this file before touching code.

> **Two hard rules:** Python → always `uv` (never pip/poetry). JS/web frontends
> → always **`yarn` 4.x** (never `npm`/`npx`/`pnpm`). No exceptions.

## Layout

```
packages/
  core/        storyteller_core      story engine (LangGraph), worlds, config, persistence
  voice/       storyteller_voice     STT/TTS/FX (API-coupled; no hardware I/O assumptions)
  hardware/    storyteller_hardware  audio backends, LEDs, ReSpeaker, voice menu, net, runtime
apps/
  cli/         storyteller_cli            PC text/voice REPL
  pi/          storyteller_pi             Pi voice loop (LEDs, wakeword, ReSpeaker)
  web-ui/      backend/ + frontend/       Player-facing web app
  web-admin/   backend/ + frontend/       Admin web app
```

## Python — always use uv

- Single shared `.venv` at the repo root, populated by `uv sync` from the workspace root `pyproject.toml`.
- Install a specific app only: `uv sync --package storyteller-pi`.
- Run a console-script: `uv run --package storyteller-cli storyteller-cli ...`.
- Never use `pip`, `pip-tools`, `poetry`, or a plain `venv`. If a workflow seems to need one, fix the workspace config instead.
- Add a dependency: edit the package's `pyproject.toml`, then `uv sync`. Never edit `uv.lock` by hand.
- Cross-package imports use the workspace package name (`from storyteller_core.story.engine import ...`), not relative paths.

## Web frontends — always use yarn

Both `apps/web-ui/frontend/` and `apps/web-admin/frontend/` are SvelteKit + TypeScript projects.

**Use yarn 4.x (Berry). Never `npm` / `npx` / `pnpm`.**

- Install: `yarn install` (creates `yarn.lock`, `.pnp.*` or `node_modules` depending on linker)
- Add a dep: `yarn add <pkg>` / `yarn add -D <pkg>`
- Run a script: `yarn <script>` (not `npm run`, not `npx`)
- Per-frontend dev: `cd apps/web-ui/frontend && yarn dev`
- If you see `npm install` or `npx` in a script or doc, replace it with the yarn equivalent.

Rationale: consistent lockfile across machines; the user has standardized on yarn for all JS work.

### Build & serve model (don't revert to adapter-auto)

Both frontends are **SPAs** built with `@sveltejs/adapter-static`
(`fallback: 'index.html'`, `+layout.ts` sets `ssr = false; prerender = false`).
The matching **FastAPI backend serves its own `build/`**: a catch-all GET,
registered after all `/api` + `/ws` routes, returns the real asset if present
else `index.html`. So production = one process per app, one port, **no Node
at runtime** (admin `:8080`, player `:8090`).

- `api.ts` `BACKEND` defaults to `window.location.origin` in the browser —
  never hard-code a host/IP; the SPA talks to whatever served it.
- Build both with `bash scripts/build_frontends.sh`; `build/` and
  `node_modules/` are gitignored (commit `yarn.lock`, not artifacts).
- Do **not** switch back to `adapter-auto` (cloud-only; produces no
  self-hostable output for the Pi).

## Story engine = LangGraph

The narrator is a compiled `langgraph.StateGraph` (see `packages/core/src/storyteller_core/story/graph.py`).

- State lives in a `TypedDict` (`state.py`), persisted via `SqliteSaver` at `data/checkpoints.db`.
- Each session has a `thread_id`. Pi/CLI use `"local"`; web uses per-session UUIDs.
- The narrator's OpenAI tool-calls are dispatched by graph nodes (`tools.py`, `nodes.py`), not by a single switch.
- Pre-narrator work (moderation, RAG retrieval, substory planning, dynamics) fans out in parallel.

When changing the engine: prefer adding/modifying nodes over inlining logic in `engine.py`. The engine module is a thin wrapper.

## Don't add backwards-compat shims

The pre-LangGraph save format (`data/saves/*.json`) is **not** supported. Don't write a migration. If a user has old saves, they archive `data/saves/` and start fresh.

## Conventions

- Type hints required on public functions.
- Pydantic v2 models for world data, substory plans, config sections.
- German is the primary locale (`de`); English is supported via `storyteller_core.i18n`.
- Tests are sparse on purpose for now — manual verify via `storyteller-cli chat` and `storyteller-pi run --text` is the contract.

## Hardware separation

- `packages/core` and `packages/voice` MUST NOT import from `storyteller_hardware`.
- `storyteller_hardware` may depend on both core and voice.
- Pi-specific drivers (`pixel_ring_v2`, `tuning`, ALSA backend) must fail gracefully on non-Pi platforms (no exceptions on import; runtime no-op if hardware is missing).

## Secrets

- `.env` at repo root holds `OPENAI_API_KEY`. Never commit it.
- `data/` holds runtime artifacts (worlds, saves, checkpoints, transcripts) — also gitignored where appropriate.
