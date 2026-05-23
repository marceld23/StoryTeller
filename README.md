# Storyteller

<p align="center">
  <img src="docs/assets/storyteller_logo.png" alt="Storyteller — your voice, infinite stories." width="320">
</p>

**Storyteller tells you a story — and pulls you into it.** It narrates, asks
what you do, listens to you, and weaves your answers back into the tale.
You're not reading a story; you're living one together with the narrator —
your choices, your questions, your hints all bend where it goes next.

Interactive, voice-controlled storyteller. Runs on a Raspberry Pi 4 with a
ReSpeaker USB Mic Array v2.0, on a normal PC (text REPL), or in a browser
(text or hold-to-talk voice). Built on a LangGraph story engine that talks
to **any OpenAI-compatible endpoint** — the OpenAI API by default, or
self-hosted backends like Ollama / vLLM / llama.cpp (LLM + embeddings),
faster-whisper (STT), and Piper (Wyoming/TCP) or XTTS v2 for TTS. Endpoints
are configurable per role (story / planner / gen / STT / TTS / embeddings),
so you can run fully local, fully cloud, or mix and match. Localized for
German and English.

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
  pi/          storyteller_pi             Pi voice loop (ReSpeaker + wake word + LEDs)
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

## Web — play & admin

Each web app is a FastAPI backend that **also serves its SvelteKit UI** as a
static SPA — one process, one port, no Node at runtime. Build the frontends
once, then run the backend:

```bash
bash scripts/build_frontends.sh        # Node 20 + yarn 4; writes apps/*/frontend/build/

uv run --package storyteller-web-ui-backend    storyteller-web-ui     # player  -> :8090
uv run --package storyteller-web-admin-backend  storyteller-web-admin  # admin   -> :8080
```

Open the **player UI** at <http://localhost:8090> and the **admin UI** at
<http://localhost:8080>. The SPA talks to the backend on its own origin, so
the same build works via `localhost`, the Pi's IP, or a hostname.

- **Player**: pick a world, play by text, or `/voice` for hold-to-talk
  (browser `MediaRecorder` → WS `/ws/voice/{thread_id}` → server STT/TTS).
- **Admin**: structured world editor (core fields, tone sliders, blueprint,
  content lists with ✨ per-piece LLM suggest, random tables), world
  generation (async job + polling), RAG reindex, transcripts viewer, and
  settings — per-role models + temperatures and per-purpose **custom
  OpenAI-compatible endpoints** (self-hosted LLM/STT/TTS/embeddings), audio
  backend, moderation thresholds. Full walkthrough:
  [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md).

**Frontend development** (hot reload, talks to the running backend via
`VITE_BACKEND`): `cd apps/web-ui/frontend && yarn dev` (port 5173;
admin: 5174). Rebuild for production with `scripts/build_frontends.sh`.

---

## Raspberry Pi voice loop

`storyteller-pi run` is the full voice appliance: spoken greeting + optional
intro, a voice world-menu, wake word ("hey jarvis" by default) with a
follow-up window, speech capture that ends on a pause, a wait-sound loop
under TTS, and a spoken system menu (save / quit / undo / reset world /
audio / intro / close). Per-world session state auto-resumes across restarts
(LangGraph checkpointer, `thread_id = pi-<world>`); `--new` starts a fresh
branch. Resuming a saved world plays a short spoken recap of where you are.

**Barge-in** — the narrator can be interrupted any time:
- **Pi** — an optional GPIO push-button (see [docs/SETUP_PI.md](docs/SETUP_PI.md));
  off by default, configurable per-button via `[hardware]` in `config.toml`.
- **Web** — a *Stopp* button on the voice page pauses playback.
- **CLI** — `Ctrl+C` during a turn aborts that turn.

When interrupted, the system stops, listens, and decides what you want
(system menu vs. a new story input).

```bash
sudo bash scripts/setup_system.sh      # udev rule (LED ring & DSP tuning), once
bash scripts/install_wakeword.sh       # openWakeWord (re-run after every `uv sync`)

uv run --package storyteller-pi storyteller-pi run            # full voice loop
uv run --package storyteller-pi storyteller-pi run --text     # keyboard, no mic
uv run --package storyteller-pi storyteller-pi run --ptt      # push-to-talk (no wake word)
```

`storyteller-pi netcheck` opens the Wi-Fi captive portal if offline at boot.
See [docs/SETUP_PI.md](docs/SETUP_PI.md) for the full Pi setup.

---

## Production deploy (systemd)

Three long-running services (unit files in `scripts/`):

| Service | Command | Purpose |
|---|---|---|
| `storyteller.service`         | `storyteller-pi run`      | Pi voice loop |
| `storyteller-admin.service`   | `storyteller-web-admin`   | admin backend + UI, `:8080` |
| `storyteller-web-ui.service`  | `storyteller-web-ui`      | player backend + UI, `:8090` |
| `storyteller-netcheck.service`| `storyteller-pi netcheck` | Wi-Fi onboarding at boot |

```bash
uv sync                                # workspace venv
bash scripts/install_wakeword.sh       # re-run: uv sync prunes the wake-word stack
bash scripts/build_frontends.sh        # build both SPAs
sudo bash scripts/install_services.sh  # install + enable the long-running units
sudo bash scripts/install_netcheck.sh  # optional: Wi-Fi onboarding service
```

After pulling changes: re-run `uv sync` + `install_wakeword.sh` (Python),
`build_frontends.sh` (web), then `sudo systemctl restart storyteller
storyteller-admin storyteller-web-ui`.

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
moderation result, every LLM tool call + result, narrator replies) and
viewable in the admin UI (`/transcripts`).

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the system is built (engine, apps, data)
- [AGENTS.md](AGENTS.md) — monorepo conventions (uv, yarn, package boundaries)
- [PLAN.md](PLAN.md) — what's still open
- [docs/SETUP_PI.md](docs/SETUP_PI.md) — Raspberry Pi + ReSpeaker
- [docs/SETUP_PC.md](docs/SETUP_PC.md) — PC setup (no Pi/no ReSpeaker)
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — how to play
- [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) — admin frontend (worlds, generation, transcripts, model/endpoint settings)
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
