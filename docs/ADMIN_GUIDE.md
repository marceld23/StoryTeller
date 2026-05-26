# Admin frontend guide

The admin web app manages worlds, generation, transcripts and model/endpoint
settings. It is a SvelteKit SPA served by its FastAPI backend
(`storyteller-web-admin`), so there's nothing extra to run.

## Reaching it

- **URL:** `http://<host>:8080` (e.g. `http://192.168.178.71:8080` or
  `http://story.local:8080` on the Pi; `http://localhost:8080` on a PC).
- It must be built once and the service running:
  `bash scripts/build_frontends.sh` → `sudo systemctl restart storyteller-admin`
  (or `uv run --package storyteller-web-admin-backend storyteller-web-admin`).
- **Theme:** ☀️/🌙 toggle (bottom-right); dark is the default.

## Access control (admin password)

Set **`STORYTELLER_ADMIN_TOKEN`** in `.env` to require a password for the
admin frontend; every `/api/*` call then needs it. The SPA prompts for it on
the first 401 and remembers it in the browser. Empty/unset = open on the LAN
(falls back to `STORYTELLER_WEB_TOKEN` if only that is set). The player UI
(:8090) uses `STORYTELLER_WEB_TOKEN` separately. Changes take effect
immediately — no restart. See [README](../README.md#production-deploy-systemd).

## Pages

### Worlds (`/`)
Table of every world with **Copy / Rename / Delete** per row (DE:
**Kopieren / Umbenennen / Löschen**), plus an Edit link into the
structured editor. Use the *Generate* (DE: *Generieren*) page below
to build a brand-new world from a free-form prompt.

- **Copy** opens an inline form: pick a new name, the id is auto-
  derived (slugified, lowercase, `[a-z0-9_]`) but stays editable.
  The copy is a fresh world definition — saved games stay attached
  to the source. RAG is rebuilt for the copy automatically so it's
  queryable from the first turn.
- **Rename** does the same but in place: the old JSON file moves
  to the new id (per locale), the RAG partition is repointed
  server-side (no costly re-embed), and saved Pi sessions migrate
  along (`pi-<old>` → `pi-<new>` thread_ids in
  `data/checkpoints.db`). Web-UI sessions use UUID thread_ids and
  are unaffected.
- **Delete** removes everything for that world in one shot: JSON
  file(s) per locale, the matching `world_facts` rows in the RAG
  database (`data/rag.<slot>.db` — one file per embedding-config
  slot, see [RAG slots](#rag-database-slots) below), and every Pi
  save (`pi-<id>`, plus the `-<ts>` variants from `--new`). A
  confirmation dialog spells out what's about to disappear. The
  same actions are also reachable via voice on the Pi — see
  [USER_GUIDE → Managing worlds](USER_GUIDE.md#managing-worlds).

The **world editor** (`/worlds/<id>`) is a structured form:
- **Core fields** — name, genre, player role, description, starting
  situation, narration style, **voice sample** (a 1–2 sentence style anchor),
  mood, ambience, physics/magic.
- **Wait sound** (DE: *Wartesound*) — dropdown that lists every
  audio file in `data/wait_sounds/` (`.wav` / `.flac` / `.ogg` /
  `.mp3`). Plays gaplessly while the narrator "thinks". Drop a new
  file into that directory and reload the page; it appears in the
  dropdown. *— none —* (DE: *— kein —*) turns the ambience off.
  The repo ships `fantasy_ambient.wav` and `scifi_ambient.wav`.
- **Tone** — sliders 0–5 (darkness / humor / romance / action / horror),
  pacing, free-text notes.
- **Blueprint variants** (DE: *Blueprint-Varianten*) — every world
  ships with up to 4 macro arcs ("Variant 1 / 2 / 3 …" / DE:
  "Variante 1 / 2 / 3 …") shown as sub-tabs in *Tone & arc* (DE:
  *Ton & Bogen*). Each variant has its own length (short / medium
  / long / epic), structure (linear / parallel / spiral / frame /
  mosaic), twist_kind (betrayal / revelation / sacrifice /
  hidden_enemy / red_herring / role_reversal / circular / "" for
  no twist), trigger_hints (when this variant feels right),
  description, premise, escalation rule and beats list. The
  substory planner picks the best-fitting variant for each new
  arc, so the same world can play structurally different on a
  replay. Single-variant worlds (the legacy seed worlds today)
  keep working unchanged — the editor hoists the legacy single
  blueprint into `variants[0]` so the same UI handles both.
  "+ Variant" / "Delete variant" (DE: "+ Variante" / "Variante
  löschen") inside the sub-tab nav add or remove arcs.
- **Content lists** — places / persons / items / glossary / history /
  fragments / regions / factions / creatures via a reusable list
  editor; each entry has add / remove and a **✨ suggest** button
  that asks the `gen` model for one schema-shaped entry.

  **What context the LLM sees on a ✨-click:** the suggest endpoint
  bundles a rich world-context block into the system prompt — every
  cross-cutting world field (name, genre, description, player role,
  starting situation, mood, ambience, narration style, free-text
  magic/physics summary AND the structured `tech_magic` rules),
  plus the cross-cutting registries (all regions and all factions —
  the LLM is instructed to reference them VERBATIM instead of
  inventing new ones), plus the existing entries of the kind being
  suggested (so it can't accidentally duplicate one). A **CANON
  RULE** at the top of the system message enforces all of this. On
  big worlds (50+ entries of one kind) the catalogue is capped at
  the first 50 plus a "(… and N more)" marker (DE: "(… und N
  weitere)") so the prompt stays bounded.

  **Your text input** (the "Suggestion hint (optional)" / DE:
  "Vorschlag-Hinweis (optional)" field next to the ✨ button) goes
  in as the user message — so a hint like *"a blind healer"* or
  *"a smuggler hangout in the Vex Anomaly Corridor"* steers the
  suggestion precisely while the world context keeps it
  consistent with everything else.
- **Random tables** — named tables with weighted entries.
- **Story patterns** — optional whitelist of substory structures.
- **Roh-JSON toggle** — an escape hatch to edit the full world JSON directly.
- **RAG reindex** — re-embeds the world after content changes (async job).

Saving validates through Pydantic; invalid worlds are rejected with a message.

### Generate (`/generate`)
Describe a world in a few sentences → the LLM builds a complete world
(description, places/persons/items/glossary/history/fragments, blueprint,
random tables, tone, complexity, audience, voice sample). Runs as a **job**
with a live status page; on success it opens the new world. Uses the `gen`
model/endpoint (see Settings). Generation can take 1–2 minutes.

### Transcripts (`/transcripts`)
Every played session is recorded as a transcript. Open one to see, per turn:
- 🧑 player input, 🛡 moderation result,
- 🔧 **tool calls** (name, args, result) — expandable,
- 🎙 narrator reply, and planner/synopsis notes.

**Optional full-prompt logging:** set `[transcripts] capture_prompts = true`
in `config/config.toml` and restart the engine services. New turns then also
record a collapsible **📤 Prompt to LLM** entry — the exact system prompt
plus all follow-up messages (including tool round-trips) sent to the narrator
model. Off by default (it makes transcripts much larger).

**Delete.** Each transcript has a 🗑 icon at the right of its list
row — one click arms the button (red "really? 🗑"), a second click
within 5 s deletes the file. **Automatic cleanup:** transcripts of
a world are also removed when the world itself is deleted or its
save state is reset (Pi sysmenu "Reset world", or `engine.reset()`).
There is **no** time-based auto-pruning — only the explicit paths.
Old transcripts stay until you remove them.

### Einstellungen (`/settings`)

Three groups; each "Speichern" writes a runtime override file under `data/`
that layers on top of `config.toml`.

**Modelle** → `data/models.json`. Empty fields mean "use the config.toml
default"; `planner_llm`/`gen_llm` empty ⇒ same as `story_llm`,
`gate_llm` empty ⇒ same as `planner_llm`.
- *Modellnamen:* `story_llm` (narrator), `planner_llm` (architect +
  summariser), `gen_llm` (world/content generation),
  **`gate_llm`** (per-turn narration gate — see *Narration gate* below),
  `stt`, `tts`, `tts_voice`, `embedding`.
- *Parameter:* `llm_temperature` (narrator), `planner_temperature`,
  `gen_temperature`, **`gate_temperature`** (default `0.3`),
  `frequency_penalty`, `presence_penalty`.
- *Reasoning-Effort* (per Rolle): controls the chain-of-thought budget
  for gpt-5.x / o-series models. Allowed values: `none`, `low`,
  `medium`, `high`, `xhigh`, `""` (empty). Defaults: `story=low`,
  `planner=medium`, `gen=medium`, `gate=""` (inherits from planner →
  story). `none` explicitly turns reasoning OFF — useful on gpt-5.5+
  (where the model otherwise defaults to medium) or to suppress
  reasoning cost on a specific role. Local OpenAI-compatible servers
  (Ollama/vLLM with qwen3) silently ignore the parameter, so a non-
  `none` value is safe to leave configured.
- *Eigene OpenAI-kompatible Endpoints:* a `base_url` + `api_key` row per
  purpose (story / planner / gen / **gate** / stt / tts / embedding).
  Empty = OpenAI. An empty `gate_endpoint` falls back to `planner_endpoint`
  → `story_endpoint`, so local-LLM setups don't have to set it explicitly.
  Point any of them at a self-hosted server (vLLM / llama.cpp / Ollama /
  LM Studio): `base_url` includes host:port and `/v1`, e.g.
  `http://192.168.1.50:8000/v1`. The server must support tool-calls + JSON
  mode for the story/planner/gen/gate roles. Moderation always uses OpenAI.
  For a **turn-key fully-local stack** (Ollama + Faster-Whisper + XTTS v2
  on Windows, requires NVIDIA GPU), see
  [SETUP_LOCAL_AI_SERVER.md](SETUP_LOCAL_AI_SERVER.md).
- *Non-OpenAI TTS servers (auto-detected by URL scheme):*
  - **Wyoming / Piper** — `tcp://host:port` (or `wyoming://host:port`).
    `tts_voice` is the Piper voice (e.g. `de_DE-thorsten-high`).
  - **XTTS** (`daswer123/xtts-api-server`) — `xtts://host:port`.
    `tts_voice` is the registered speaker name (e.g. `marcel`); the
    language follows the effective `general.locale`.
  - Everything else (empty or plain `http(s)://…/v1`) → the OpenAI-compatible
    client (used for OpenAI itself and for self-hosted servers that mimic
    `/v1/audio/speech`, e.g. kokoro).
- *Roh-JSON* toggle for the whole models override object.

  Example `data/models.json` (only the keys you want to override):
  ```json
  {
    "story_llm": "qwen2.5:14b-instruct",
    "llm_temperature": 0.8,
    "planner_temperature": 0.5,
    "story_endpoint":   { "base_url": "http://192.168.1.50:8000/v1", "api_key": "sk-local" },
    "planner_endpoint": { "base_url": "http://192.168.1.50:8000/v1", "api_key": "sk-local" }
  }
  ```

### Provider mix: OpenRouter chat + OpenAI audio (hybrid)

Storyteller resolves each role's API key independently, so you can
mix providers freely. The typical hybrid setup runs cheap DeepSeek /
Claude / etc. via [OpenRouter](https://openrouter.ai/) for the narrator
+ planner + world generation, and keeps OpenAI for STT / TTS /
embeddings (where there's no good drop-in alternative).

1. Add both keys to `.env`:

   ```bash
   OPENAI_API_KEY=sk-...
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

   No per-endpoint `api_key` is needed in `data/models.json` — endpoints
   whose `base_url` contains `openrouter.ai` auto-resolve to
   `OPENROUTER_API_KEY`; everything else falls back to
   `OPENAI_API_KEY`. (Explicit `api_key` per endpoint still wins.)

2. Point the chat endpoints at OpenRouter (`data/models.openrouter.bak.json`
   ships as a starter — copy / symlink to `data/models.json`):

   ```json
   {
     "story_llm":   "deepseek/deepseek-v4-pro",
     "planner_llm": "deepseek/deepseek-v4-flash",
     "gen_llm":     "deepseek/deepseek-v4-pro",
     "stt":         "gpt-4o-mini-transcribe",
     "tts":         "gpt-4o-mini-tts",
     "embedding":   "text-embedding-3-small",
     "story_endpoint":   { "base_url": "https://openrouter.ai/api/v1" },
     "planner_endpoint": { "base_url": "https://openrouter.ai/api/v1" },
     "gen_endpoint":     { "base_url": "https://openrouter.ai/api/v1" }
   }
   ```

3. Reasoning effort works on OpenRouter too — `chat_extras` auto-
   detects OpenRouter endpoints and switches the request payload
   from OpenAI's flat `reasoning_effort: "low"` to OpenRouter's
   nested `reasoning: { effort: "low" }`, so all per-role
   `*_reasoning_effort` settings keep working unchanged.

4. Restart `storyteller`, `storyteller-admin`, `storyteller-web-ui`
   (config hot-reloads `data/models.json`; only the *.env* changes
   need a process restart since dotenv is loaded once).

**Audio** → `data/audio.json`: output backend (`auto` / `alsa_softvol` /
`portable` / `pipewire`) and an optional PipeWire sink.

**Narration & memory** — section in the Settings page (also
backed by `data/story.json`). Overrides any field of `[story]`
from `config.toml`; empty fields fall back to the default
(placeholder shows what that default is). Hot-reloaded — changes
apply on the next turn, no service restart.

Knobs the UI exposes:

| Knob | Default | When to tune |
|---|---:|---|
| `short_term_memory_turns` | **24** | Cloud (gpt-5.x, claude, gemini): 24–48 fits every model trivially. Local 32k-ctx (qwen3-30b-32k): 12–16. Tiny 8k-ctx local: 6–8. Higher = better continuity at the cost of more input tokens per turn. |
| `synopsis_max_chars` | 900 | Longer rolling summary for very long sessions (1200–1800). |
| `synopsis_batch` | 8 | How many old messages get folded away per pass — larger = fewer LLM calls, coarser synopsis. |
| `rag_top_k` | 4 | Inject more world facts per turn. |
| `beat_nudge_after` | 3 | Turns on the same sub-beat before the narrator gets a polite `advance_beat` nudge (0 = off). |
| `known_facts_cap` | 30 | Cap on the KnownFacts list; the oldest entries without a note are evicted first. |
| `narration_gate_max_reveals` | 3 | Max authored reveals per turn from the curator. |
| `long_term_memory` (checkbox) | ✓ | Off = no synopsis folding (only sensible for very short sessions). |
| `narration_gate_enabled` (checkbox) | ✓ | Off = curator LLM call skipped (algorithm-only spoiler protection). |

Example `data/story.json` for a local-32k setup with somewhat
sparser reveals:

```json
{ "short_term_memory_turns": 12, "narration_gate_max_reveals": 2 }
```

**Synopsis hardening** — when the summariser LLM produces a
significantly shorter summary than the previous one (`< 70 %` of
the old length, with `old ≥ 300 chars`), the engine retries once
with a tightened correction instruction; if that also fails, it
falls back to a lossless heuristic fold (old synopsis + extract
of the dropped messages, concatenated). Established context from
the prior synopsis is never lost, even when the model truncates.

**Moderation** → `data/moderation.json`: an **"Moderation aktiviert"
checkbox** (uncheck to fully disable the OpenAI moderation gate — inputs
then go straight to the narrator) plus per-category thresholds as JSON
(e.g. `{"default": 0.5, "categories": {"violence": 0.7}}`). The engine
re-reads this file each turn, so it takes effect immediately (no restart).

## Narration gate (anti-spoiler curator)

A small per-turn LLM call decides which **pre-authored** reveals the narrator
may weave in this turn, and which **authored** topics must still stay hidden.
Player-driven improvisation, spontaneous new facts, and freely invented
details are **not gated** — only the curated parts (world *fragments*,
*history* entries, substory *resolution_hint*, future macro-beats).

State knobs (in `config.toml [story]`):
- `narration_gate_enabled` — toggle the per-turn LLM call. With it off,
  algorithmic spoiler guards (next-beat / `resolution_hint` hidden in the
  narrator's prompt, sanitized `get_substory_plan` tool) still apply.
- `narration_gate_max_reveals` — cap on permitted reveals per turn (default 3).

Model & endpoint (in `data/models.json`, same shape as the other roles):
- `gate_llm` — keep this **small and fast**; default empty falls back to
  `planner_llm`. Per turn cost = one short JSON call.
- `gate_endpoint` — falls back to `planner_endpoint` → `story_endpoint`.
- `gate_temperature` — kept low (default `0.3`) for stable JSON.

What the narrator sees as a result, when the gate is active:
```
KURATOR-LEITLINIE FÜR DIESEN ZUG: …
Szenen-Ziel:        <one-sentence intent>
Permitted reveals:  <up to N authored reveals OK today>
Forbidden topics:   <authored topics the narrator must not hint at today>
Ton-Hinweis:        <optional style nudge>
```

Tools (`retrieve_world_fact`, `lookup_glossary`) honour the gate too — they
won't return authored-fragment / history results that aren't permitted or
already known to the player.

## Storymodus — soft plot-pressure

Replaces the older binary "with plot vs. without plot" intuition with a
continuous **plot-pressure** dial (0..1) that the engine carries per
session. The dial governs five things, all faded smoothly:

| Layer | What happens as pressure drops |
|---|---|
| Curator gate (`gate_llm`) | At ≥ `pressure_gate_strict` (0.70) → full strictness (max_reveals from `narration_gate_max_reveals`). Between 0.10 and 0.70 → linearly fewer reveals + the call still runs. Below 0.10 → call is **skipped** entirely (no LLM cost, no forbidden_topics). |
| Substory in narrator prompt | ≥ 0.70 → full block (premise, hook, beats, current beat, transition hint). 0.30–0.70 → **ambient** one-liner (hook + current beat name; explicitly tells the narrator *not* to push). < 0.30 → **free-exploration** block (no substory at all). |
| Substory tools (`advance_beat`, `complete_substory`, `get/adjust_substory_plan`) | Hidden from the tool list when pressure < 0.30. |
| Beat-nudge | Threshold scales inverse: at 1.0 → after `beat_nudge_after` turns; at 0.5 → twice as long; at 0 → never. |
| Planner (`ensure_substory` / `replan`) | Below `pressure_substory_plan` (0.20) the planner doesn't run. The active substory is **parked** as `dormant_substory` (status `dormant`) so a future pressure spike can revive that arc instead of forcing a new plan. |

### Driving the pressure

By default a small heuristic in `pressure.py` builds a per-turn
`TurnSignal` from already-existing telemetry: tools fired (e.g.
`advance_beat` → strong on-arc), lexical match between player input
and the substory's `involved_persons` / `involved_places` / current
beat goal, off-arc world queries (`retrieve_world_fact` on
`fact_type=history|fragment`), and two phrase patterns (`explicit_free`
like "lass uns einfach…" / "kein plot"; `explicit_plot` like "was war
nochmal die mission?"). Six-turn sliding window, recency-weighted,
EMA-smoothed via `pressure_ema_alpha` (default 0.4).

An optional **tiebreaker** (`cfg.story.engagement_tiebreaker_enabled`,
default on) fires ONE planner-LLM call when the score has stayed in
the uncertain band [0.30, 0.60] for 3 consecutive turns; the JSON
verdict `{direction: on_arc | lateral | off_arc, confidence: 0..1}`
overrides that turn's heuristic signal when confidence ≥ 0.7.

### The `story_mode` setting

`data/settings.json` field `story_mode` pins the pressure:

| Value | Effect |
|---|---|
| `auto` *(default)* | Heuristic drives — pressure follows the EMA-smoothed target. |
| `planner` | Pinned at **1.0** — full plot machinery always. |
| `frei` | Pinned at **0.0** — no plot machinery; narrator reacts only to the player. |

Edit it in **Einstellungen → Storymodus** in the admin UI, on the Pi
via the sysmenu's *"Storymodus"* entry, or directly mid-story by saying
*"Storymodus frei / Plan / Auto"*. The change applies on the very next
turn — no restart.

### Tuning thresholds

All thresholds live in `config.toml [story]` and override per-machine
via `data/story.json` (PUT `/api/settings/story`):

| Field | Default | Meaning |
|---|---|---|
| `pressure_ema_alpha` | 0.4 | Smoothing factor; higher = faster reaction to the per-turn target. |
| `pressure_gate_min` | 0.10 | Curator skipped below. |
| `pressure_gate_strict` | 0.70 | Curator uses full `max_reveals` above. |
| `pressure_substory_ambient` | 0.30 | Ambient one-liner above; free-exploration below. |
| `pressure_substory_full` | 0.70 | Full substory block above. |
| `pressure_substory_tools` | 0.30 | Substory-tools visible above. |
| `pressure_substory_plan` | 0.20 | Planner runs above; below = park as dormant. |
| `engagement_tiebreaker_enabled` | true | Run the one-call tiebreaker in the uncertain band. |

### Watching what the heuristic does

Every turn emits a transcript marker (visible in **Transcripts** as a small
blue inline line):

```
[pressure] mode=auto signal=on_arc target=0.78 smoothed=0.74 effective=0.74
```

* `mode` — current `story_mode` setting at decision time.
* `signal` — dominant per-turn kind: `advanced` / `on_arc` / `lateral` /
  `off_arc` / `explicit_plot` / `explicit_free`.
* `target` — raw target from the sliding-window aggregate.
* `smoothed` — actual pressure after EMA.
* `effective` — what each layer reads (= smoothed for `auto`, pinned
  value for `planner`/`frei`).

Additional markers appear at transition points:
- `[pressure] parking substory '<title>' — pressure=0.18`
- `[pressure] reviving dormant substory '<title>' — pressure=0.42`
- `[pressure] gate skipped (pressure=0.07)`
- `[pressure] replan skipped (pressure=0.15); completed substory parked as dormant`

## When changes take effect

The admin process picks up its own display immediately. The **engine**
processes read the config at start, so after changing models/endpoints/audio
restart them:

```bash
sudo systemctl restart storyteller storyteller-web-ui
```

## RAG database slots

The RAG index lives at `data/rag.<slot>.db`, one DB file per
embedding-config slot. A slot key is built from
`(endpoint_host, embedding_model, embedding_dim)`. Switching any of
those (e.g. moving `models.embedding` from `text-embedding-3-small`
to `text-embedding-3-large`, or pointing `models.embedding_endpoint`
at a self-hosted server) picks a different file; the previously
indexed worlds stay on disk and are reused the next time you switch
back.

Consequences:

- After a model/dim/endpoint swap, **the new slot starts empty**.
  The first `index_world` call for each world re-embeds it via the
  new endpoint. This costs whatever the new endpoint charges; on
  cloud endpoints it's a one-time burst of OpenAI / OpenRouter
  spend.
- The legacy `data/rag.db` (pre-multi-slot installs) is
  auto-migrated **once** to the slot path matching the *current*
  config. If you simultaneously changed the embedding model with
  the upgrade, the migrated DB still contains the OLD model's
  vectors and produces semantic nonsense at retrieval time — use
  the per-world *Reindex* button or `force=True` to refill it.
- Old slots are kept indefinitely (one DB file ≈ 1–5 MB per world).
  Manual cleanup if you want to reclaim disk: `rm
  data/rag.<old-slot>.db`.

The same slot pattern applies to the voice-prompt WAV cache (see
[SETUP_PI.md](SETUP_PI.md) → after-code-changes section).

## See also
- [README.md](../README.md) — install, deploy, ports.
- [ARCHITECTURE.md](../ARCHITECTURE.md) — how it all fits together.
- [USER_GUIDE.md](USER_GUIDE.md) — playing the game.
