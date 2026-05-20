# Storyteller

Interactive, voice-controlled storyteller. Runs on a Raspberry Pi 4 with a
ReSpeaker USB Mic Array v2.0, on a normal PC (text or PC audio), or in a
browser (text now, voice next). Powered by the OpenAI API and a LangGraph
story engine. Localized for German and English.

➡ **Architecture, decisions & roadmap: [PLAN.md](PLAN.md)**
➡ **Conventions for working on the codebase: [AGENTS.md](AGENTS.md)**

---

## Monorepo layout

This is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/).
One `.venv` at the root, one `uv.lock`, every member built together.

```
packages/
  core/        storyteller_core      story engine (LangGraph), worlds, config, persistence
  voice/       storyteller_voice     STT/TTS/FX (API-coupled, no hardware I/O)
  hardware/    storyteller_hardware  audio backends, LEDs, ReSpeaker, voice menu, net
apps/
  cli/         storyteller_cli            PC text REPL (chat / info / worlds / seed / history)
  pi/          storyteller_pi             Pi voice loop (skeleton — port in progress)
  web-ui/      backend/ + frontend/       Player-facing web app (FastAPI + SvelteKit)
  web-admin/   backend/ + frontend/       Admin web app (FastAPI + SvelteKit)
```

Python: **always `uv`**, never `pip`. Web frontends: **always `yarn` 4.x**,
never `npm`/`npx`/`pnpm`. See [AGENTS.md](AGENTS.md).

---

## Quick start — text REPL on any machine

```bash
uv sync                                              # install everything
uv run --package storyteller-cli storyteller-cli seed   # write seed worlds (once)
uv run --package storyteller-cli storyteller-cli chat --world sternenfahrt
```

The CLI uses the same LangGraph engine as the web/Pi apps; per-session state
is checkpointed in `data/checkpoints.db`. Use `--new` to start a fresh branch,
`/undo` mid-chat to roll back one turn, `/state` to inspect.

---

## Web — play in the browser

Two processes: the **play backend** (FastAPI + WebSocket) and the
**SvelteKit play UI**.

```bash
# 1) backend on :8090
uv run --package storyteller-web-ui-backend storyteller-web-ui

# 2) frontend on :5173 (separate terminal)
cd apps/web-ui/frontend
yarn install        # first run only
yarn dev
```

Then open <http://localhost:5173>. Voice in the browser (mic + server-side
STT/TTS) is the next iteration; the WS channel `/ws/voice/{thread_id}` is
reserved but currently returns "not implemented".

## Web — admin

```bash
# 1) admin backend on :8080
uv run --package storyteller-web-admin-backend storyteller-web-admin

# 2) admin frontend on :5174
cd apps/web-admin/frontend
yarn install
yarn dev
```

Then open <http://localhost:5174>. Worlds list / detail (JSON editor),
settings (models / audio backend / moderation thresholds). World generation,
transcripts, and RAG reindex are stubbed (501) — being ported from the
previous inline-HTML admin (see `legacy_app.py`).

---

## Raspberry Pi voice loop

The Pi app (`apps/pi/storyteller_pi`) is currently a stub. The pre-migration
voice loop lives at `apps/cli/src/storyteller_cli/_legacy.py` and is being
ported against the new LangGraph engine. Until then, the Pi runs the same
text REPL with `storyteller-cli chat`.

Hardware setup (once per Pi):

```bash
sudo bash scripts/setup_system.sh      # udev rule (LED ring & DSP tuning)
bash scripts/install_wakeword.sh       # openWakeWord (py3.13 packages)
```

See [docs/SETUP_PI.md](docs/SETUP_PI.md) for the full Pi setup.

---

## Story engine — at a glance

The narrator actively involves the player (free speech, no menus), follows
a **macro arc** and a dynamically planned **substory**. Substory resolved
→ the architect (planner LLM) plans the next one in the *same* turn
(LangGraph replan node). An abstract **story dynamic** (new antagonist,
unforeseen event …) spices planning and play without derailing the arc.

Per-session state — memory, substory plan, known facts, character status,
synopsis, cost — lives in the LangGraph `SqliteSaver` at
`data/checkpoints.db`, keyed by `thread_id`. Branching ("what if I had
done X?") works natively via `engine.history()` / `engine.rewind_to(cp_id)`.

Pre-narrator phase (moderation, RAG retrieval, substory ensure, dynamics
roll) fans out **in parallel** — wall-clock latency = max() instead of sum.

Per-session cost cap (graceful wrap-up). Follow-up questions get short
answers and don't advance beats.

---

## Localization (de / en)

`config [general] locale = de | en` (per-run via `--locale`). Controls
narration language, voice-prompt audio, menu keywords, STT language and
world content. **German prompts are kept verbatim**; English equivalents
added. Worlds exist in both languages (`data/worlds/<id>.json` for de,
`<id>.en.json` for en) with isolated RAG.

---

## Safety

Every player input is sent to the OpenAI moderation model
(`omni-moderation-latest`) **before** the narrator answers; on a threshold
hit the turn is politely refused. Thresholds are editable in the admin UI
(`/settings`). Played stories are recorded as transcripts (player input,
moderation result, every LLM tool call + result, narrator replies) — the
admin transcripts viewer is being ported (501 stub today).

---

## Documentation

- [AGENTS.md](AGENTS.md) — monorepo conventions (uv, yarn, package boundaries)
- [PLAN.md](PLAN.md) — what's done, what's open, in what order
- [docs/SETUP_PI.md](docs/SETUP_PI.md) — Raspberry Pi + ReSpeaker
- [docs/SETUP_PC.md](docs/SETUP_PC.md) — PC setup (no Pi/no ReSpeaker)
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — how to play
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — dependency licenses

---

## License

This project's own source is **MIT** ([LICENSE](LICENSE)). All required
Python dependencies are permissive (MIT/BSD/Apache/MPL). Notable caveats —
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):

- **`pedalboard` is GPLv3** — only the *optional* `audiofx` extra (voice
  reverb), dynamically imported with a pass-through fallback. Without it
  the project stays MIT-clean; enabling it for distribution triggers GPLv3
  for that combined work.
- **openWakeWord** code is Apache-2.0, but its default pretrained models
  (e.g. "hey jarvis") are **CC-BY-NC-SA 4.0 (non-commercial)**. Models are
  downloaded at install, not shipped; for commercial use train/replace them.
- Vendored ReSpeaker drivers (`storyteller_hardware/pixel_ring_v2.py`,
  `tuning.py`) are from Seeed Studio under **Apache-2.0**, retained with
  attribution (not relicensed).
