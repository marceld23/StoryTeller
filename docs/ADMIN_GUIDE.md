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

### Welten (`/`)
List of worlds; create a new one, open one to edit, or delete.

The **world editor** (`/worlds/<id>`) is a structured form:
- **Core fields** — name, genre, player role, description, starting
  situation, narration style, **voice sample** (a 1–2 sentence style anchor),
  mood, ambience, physics/magic.
- **Tone** — sliders 0–5 (darkness / humor / romance / action / horror),
  pacing, free-text notes.
- **Blueprint** — premise, escalation rule, and the macro beats (name, goal,
  tension).
- **Content lists** — places / persons / items / glossary / history /
  fragments via a reusable list editor; each entry has add / remove and a
  **✨ suggest** button that asks the LLM for one schema-shaped entry.
- **Random tables** — named tables with weighted entries.
- **Story patterns** — optional whitelist of substory structures.
- **Roh-JSON toggle** — an escape hatch to edit the full world JSON directly.
- **RAG reindex** — re-embeds the world after content changes (async job).

Saving validates through Pydantic; invalid worlds are rejected with a message.

### Generieren (`/generate`)
Describe a world in a few sentences → the LLM builds a complete world
(description, places/persons/items/glossary/history/fragments, blueprint,
random tables, tone, complexity, audience, voice sample). Runs as a **job**
with a live status page; on success it opens the new world. Uses the `gen`
model/endpoint (see Settings). Generation can take 1–2 minutes.

### Verläufe (`/transcripts`)
Every played session is recorded as a transcript. Open one to see, per turn:
- 🧑 player input, 🛡 moderation result,
- 🔧 **tool calls** (name, args, result) — expandable,
- 🎙 narrator reply, and planner/synopsis notes.

**Optional full-prompt logging:** set `[transcripts] capture_prompts = true`
in `config/config.toml` and restart the engine services. New turns then also
record a collapsible **📤 Prompt an LLM** entry — the exact system prompt
plus all follow-up messages (including tool round-trips) sent to the narrator
model. Off by default (it makes transcripts much larger).

### Einstellungen (`/settings`)

Three groups; each "Speichern" writes a runtime override file under `data/`
that layers on top of `config.toml`.

**Modelle** → `data/models.json`. Empty fields mean "use the config.toml
default"; `planner_llm`/`gen_llm` empty ⇒ same as `story_llm`.
- *Modellnamen:* `story_llm` (narrator), `planner_llm` (architect +
  summariser), `gen_llm` (world/content generation), `stt`, `tts`,
  `tts_voice`, `embedding`.
- *Parameter:* `llm_temperature` (narrator), `planner_temperature`,
  `gen_temperature`, `frequency_penalty`, `presence_penalty`.
- *Eigene OpenAI-kompatible Endpoints:* a `base_url` + `api_key` row per
  purpose (story / planner / gen / stt / tts / embedding). Empty = OpenAI.
  Point any of them at a self-hosted server (vLLM / llama.cpp / Ollama /
  LM Studio): `base_url` includes host:port and `/v1`, e.g.
  `http://192.168.1.50:8000/v1`. The server must support tool-calls + JSON
  mode for the story/planner/gen roles. Moderation always uses OpenAI.
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

**Audio** → `data/audio.json`: output backend (`auto` / `alsa_softvol` /
`portable` / `pipewire`) and an optional PipeWire sink.

**Moderation** → `data/moderation.json`: an **"Moderation aktiviert"
checkbox** (uncheck to fully disable the OpenAI moderation gate — inputs
then go straight to the narrator) plus per-category thresholds as JSON
(e.g. `{"default": 0.5, "categories": {"violence": 0.7}}`). The engine
re-reads this file each turn, so it takes effect immediately (no restart).

## When changes take effect

The admin process picks up its own display immediately. The **engine**
processes read the config at start, so after changing models/endpoints/audio
restart them:

```bash
sudo systemctl restart storyteller storyteller-web-ui
```

## See also
- [README.md](../README.md) — install, deploy, ports.
- [ARCHITECTURE.md](../ARCHITECTURE.md) — how it all fits together.
- [USER_GUIDE.md](USER_GUIDE.md) — playing the game.
