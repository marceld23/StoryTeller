# Storyteller

<p align="center">
  <img src="docs/assets/storyteller_logo.png" alt="Storyteller — your voice, infinite stories." width="320">
</p>

**Storyteller tells you a story — and pulls you into it.** The narrator
listens, asks what you do, weaves your answers *and the world-facts you
drop along the way* back into the tale — while a planner LLM keeps a
multi-act arc intact behind the scenes. You're not just answering
prompts; you're co-building a world.

Worlds can be **picked**, **generated from a one-page brief** (1–3 min —
full setting, characters, items, glossary, blueprint, random tables),
and **replayed with structurally different arcs** thanks to multi-
blueprint worlds.

**Two ways to run it — same engine, same worlds, same save-state:**

- **As an appliance** — a Raspberry Pi 4 with a ReSpeaker mic and LED
  ring, boots into voice mode, *"Hey Jarvis"* to wake. The original
  prototype hid the Pi inside a hollow book at a kid's birthday party;
  that's still the design intent.
- **As a self-hosted web service** — run the backend on any machine
  (a laptop, a NAS, a Mini-PC), and kids reach it in any browser at
  `https://your-host/`. Text mode or tap-to-talk voice, no Pi or
  mic-array needed.

Plus a PC text REPL (CLI) for prompt-engineering / debugging the same
engine without the audio layer.

Under the hood: a **LangGraph** story engine with a planner, an anti-
spoiler curator gate, and per-session RAG over world content + player-
introduced facts. The engine talks to **any OpenAI-compatible endpoint**
— the OpenAI API by default, or self-hosted backends like Ollama /
vLLM / llama.cpp (LLM + embeddings), faster-whisper (STT), and Piper
(Wyoming/TCP) or XTTS v2 for TTS. Endpoints are configurable **per role**
(story / planner / gen / gate / STT / TTS / embeddings), so you can run
fully local, fully cloud, or mix and match. A **daily cost cap** plus
per-world / per-model spend rollup prevents a forgotten cloud key from
running into a surprise bill, and **endpoint health monitoring** lets
the appliance differentiate "internet is down" from "my local server
is off" from "API key is wrong" — surfaced both via spoken prompt and
in the admin UI. Localized for German and English.

Want to go **fully local** with no API key at all? The repo ships a
turn-key Windows + NVIDIA-GPU server stack in
[`local_llm_servers_win/`](local_llm_servers_win/) (Ollama + Faster-Whisper
+ XTTS v2). Point your Storyteller client (Pi or PC) at it over the LAN —
guide in [docs/SETUP_LOCAL_AI_SERVER.md](docs/SETUP_LOCAL_AI_SERVER.md).
**Requires a capable NVIDIA GPU with enough VRAM** (≥ 24 GB recommended).

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

- **Player**: pick a world, play by text, or `/voice` for tap-to-talk —
  click or spacebar starts the recording, the next click/spacebar stops
  and sends (browser `MediaRecorder` → WS `/ws/voice/{thread_id}` →
  server STT/TTS).
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

## HTTPS for remote phones / PCs

Browsers gate `navigator.mediaDevices` behind HTTPS or localhost — so
opening the player web-ui's voice page from a phone over plain LAN
HTTP fails with a TypeError. `scripts/install_https.sh` sets up a
local CA (via mkcert) plus Caddy as a TLS reverse proxy in front of
both backends:

```bash
bash scripts/install_https.sh        # one-shot, idempotent
```

After installing the generated `/etc/storyteller/mkcert/rootCA.pem` on
each remote device once (per-device steps in
[docs/SETUP_HTTPS.md](docs/SETUP_HTTPS.md)), you get:

* `https://story.local/`           → player text/voice/`/create`
* `https://story.local:8443/`      → admin
* `http://story.local/`            → 301 → https

The plain-HTTP listeners on 8080/8090 stay bound (so existing curl /
smoke / tunnel workflows aren't disturbed).

## Feature parity across entry points

The same gameplay features are available in all three player-facing
entry points — `storyteller-pi run` (voice), `storyteller-cli chat`
(text REPL) and the player web UI at `/` + `/voice`:

| Feature | Pi voice | CLI | Web UI |
|---|:-:|:-:|:-:|
| Existing-world selection | ✓ voice menu | ✓ numbered picker | ✓ dropdown |
| **World generation** from a player brief | ✓ voice interview + "Generieren" | ✓ `/create <prompt>` | ✓ `/create` page (text) |
| **Welten verwalten** (copy / rename / delete) | ✓ voice ("verwalten" → kopieren / umbenennen / löschen + ja/nein) | — | ✓ buttons in worlds list (Admin) |
| **Multi-Blueprint-Varianten** (replay value: same world, structurally different arc) | engine + planner pick per new substory | engine + planner pick per new substory | ✓ sub-tabs in Ton & Bogen tab (Admin) |
| **Vermerken / world notes** (player-introduced facts → RAG) | ✓ "Vermerken: …" | ✓ `/note <text>` | ✓ "+ Notiz" button (text + voice pages) |
| **Wiederhole / Repeat** (re-play last narration, TTS only) | ✓ "Wiederhole" / "Repeat" | scroll up | ✓ "Wiederhole" in voice page (STT-matched) |
| **Geschichte beenden** → back to world picker | ✓ voice command | ✓ `/end` | ✓ "Geschichte beenden" button |
| **Daily cost cap** pause + player message | ✓ `daily_cap_pause` prompt | ✓ rich-text cap notice | ✓ red banner + WS `daily_cap_exceeded` |
| Wait-sound under LLM thinking | ✓ per-world / generic ambient | — (text) | ✓ voice page loops `generic_waiting.wav` |
| Barge-in / interrupt | ✓ GPIO button long-press | ✓ Ctrl-C | ✓ ⏹ button (voice page) |

## Raspberry Pi voice loop

`storyteller-pi run` is the full voice appliance. Boot flow:

1. Short spoken greeting (*"Hallo, ich bin dein Erzähler. Wenn du
   bereit bist, weck mich mit Hey Jarvis."*) — toggleable in the system
   menu (`intro`).
2. **Idle wait** for the *"Hey Jarvis"* wake word — the Pi stays silent
   until you call it.
3. On wake-word: *"Would you like to get started?"* — yes continues, no
   / silent / unclear (after one re-ask) goes back to idle.
4. *"Existing world or new one?"* — branches into either:
   * the voice world-menu (free-form phrasing, LLM-classified) → load
     the picked world, **or**
   * a guided **voice-mode world design**: a short Q&A interview drives
     [generate_world](packages/core/src/storyteller_core/worlds/generate.py)
     live on-device. The interview obeys the same idle / silence
     contract as the story loop (silence → *"sag Hey Jarvis"* + replay
     last question on wake) and accepts short cancel commands
     (*"abbrechen / stopp / beenden"*). Player ends the interview by
     saying *"Generieren / Generate"*; a neutral wait-sound covers the
     1–3 min generation, then the new world is saved and started.
5. **Once a world is picked, before the first narration** the in-story
   command briefing plays (Vermerken / Wiederhole / Menü / Geschichte
   beenden / Schluss + the wake-hint). Toggleable in the system menu
   (`commands info`).

In-session: wake word with a follow-up window, speech capture that ends
on a pause, a wait-sound loop under TTS, and a spoken system menu
(save / end story / shutdown / undo / reset world / audio / intro /
commands info / close). Voice commands during play: **"Vermerken / Note"**
to add a player-introduced world fact (RAG-indexed live), **"Wiederhole
/ Repeat / Sag das nochmal"** to re-play the last narration (TTS only,
no LLM call), **"Geschichte beenden / End story"** to save + return to
the wake-word idle for the next world, **"Schluss / Ausschalten /
Shutdown"** to power the device off. Per-world session state auto-
resumes across restarts (LangGraph checkpointer, `thread_id =
pi-<world>`); `--new` starts a fresh branch.
Resuming a saved world plays a short spoken recap of where you are.

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
Moderation is skipped for trivially short benign inputs (`Ja`, `Vielen
Dank`) so those turns don't pay the OpenAI round-trip. TTS chunks are
fetched in parallel and played in a **streaming pipeline** — the player
starts speaking the first chunk while later ones are still rendering, so
most of the TTS latency happens *behind* the audio rather than before it.

**Anti-spoiler narration gate** — a small per-turn LLM call (`gate_llm`,
defaults to the same endpoint as the planner) curates which *authored*
reveals (fragments, history, substory resolution, future beats) the
narrator may weave in this turn. Player-driven improvisation and
spontaneous new facts stay free — only the pre-written plot points are
gated. Toggle: `[story] narration_gate_enabled` in `config.toml`. See
[docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md#narration-gate-anti-spoiler-curator).

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

## How this project came to be

I had my *"bam, AI is real"* moment in 2023. So I built a python
storyteller bot on a Raspberry Pi with a ReSpeaker mic, hid it
inside a dummy book, and let it loose on my son's Harry-Potter
themed birthday party. The "magical book" played a ghost trapped
inside, dropping plot hooks and silly side-quests for the kids
all afternoon. Under the hood: gpt-3.5-turbo with tool calls. The
kids were the experience; the model was just the engine.

A year later it was a Star-Wars-themed birthday, and the same
hardware became a *"rebel field radio"* the kids could call into
to talk to "headquarters" and pick up mission updates. Same north
star: the experience of the kids comes first; the tech disappears.

In 2026 I rewrote the whole thing from scratch with Claude Opus 4.7
as my pair-programmer. The new system is what you see in this repo:
a proper LangGraph engine, multi-step world generation, per-role
LLM endpoints, a structured admin UI, voice + text + Pi-as-
appliance. At my side throughout: my son **Justus (10)** — tireless
tester, ruthless feedback-giver, "feature wisher" and "world
builder". Many of the rough edges that got smoothed out here got
caught because Justus said *"das ist doof"* at exactly the right
moment.

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the system is built (engine, apps, data)
- [AGENTS.md](AGENTS.md) — monorepo conventions (uv, yarn, package boundaries)
- [PLAN.md](PLAN.md) — what's still open
- [docs/SETUP_PI.md](docs/SETUP_PI.md) — Raspberry Pi + ReSpeaker
- [docs/SETUP_PC.md](docs/SETUP_PC.md) — PC setup (no Pi/no ReSpeaker)
- [docs/SETUP_LOCAL_AI_SERVER.md](docs/SETUP_LOCAL_AI_SERVER.md) — optional fully-local AI backends (Ollama + Whisper + XTTS) on a Windows + NVIDIA GPU host
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
