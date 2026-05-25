# Storyteller — Docker self-host

Self-hosts the **two web services** (player UI `:8090`, admin UI `:8080`)
in containers, with a Caddy reverse proxy giving you HTTPS out of the
box. The Raspberry-Pi voice loop, CLI and local-AI server stack are
**not** in scope — they're host-coupled (audio devices, GPIO, GPU).

## What you get

| URL | Container | Purpose |
|---|---|---|
| `https://<host>/` | `storyteller-caddy` → `web-ui:8090` | Player web UI (text + tap-to-talk voice) |
| `https://<host>:8443/` | `storyteller-caddy` → `web-admin:8080` | Admin web UI (worlds, settings, transcripts) |
| `http://<host>/` | redirect | → `https://<host>/` |

A single docker image (`storyteller-web:local`) is reused for both
services — only the `CMD` differs.

## Requirements

- **Docker** ≥ 24 with the **compose** plugin (`docker compose version`)
- **x86_64** Linux / macOS / WSL2 (this image is **not** multi-arch —
  if you need ARM64, you'd build locally on an ARM host yourself)
- ~ **2 GB** disk space for the built image (+ growing `data/`)

## First run

```bash
cd docker/
cp .env.example .env
# Edit .env: set OPENAI_API_KEY (or OPENROUTER_API_KEY), set
# STORYTELLER_ADMIN_TOKEN to something non-trivial.

docker compose up --build
```

Initial build takes ~5–10 minutes (yarn install of two frontends + uv
sync of the Python workspace). Subsequent rebuilds reuse layer caches
and finish in ~30 seconds when only Python source changed.

Open `https://localhost/` in a browser. You'll see a TLS warning the
first time because Caddy uses its internal self-signed CA — accept it,
or [import Caddy's root cert](https://caddyserver.com/docs/automatic-https#local-https).

## Empty start, no Pi data

The compose file mounts `./data` into both containers. That directory
is **created empty** on first run — no seed worlds, no save games, no
transcripts, no cost ledger. Generate worlds via the admin UI's
**Generieren** page or via the player UI's `/create` page.

Persistence works across `docker compose down` / `up` (the bind mount
keeps the host dir alive). To wipe everything, delete `./data/`.

## Operations

```bash
# Logs from both backends
docker compose logs -f web-ui web-admin

# Restart just one service (e.g. after editing .env)
docker compose restart web-admin

# Tear down + rebuild
docker compose down
docker compose up --build -d
```

## Co-existing with a Pi voice-loop on the same host

The Pi's `storyteller.service` writes the same `data/` directory the
web containers read. If you run both on **one** host:

1. Stop the compose `data/` mount and point it at the Pi's data:
   ```yaml
   volumes:
     - /home/pi/storyteller/data:/app/data
   ```
2. The container user is `uid 1000` — adjust ownership on the Pi side
   if it isn't already `pi` (also uid 1000 on Raspberry Pi OS).
3. The cost ledger, transcripts and worlds are now shared — a story
   started on the Pi shows up in the web UI's session picker and vice
   versa.

The reverse — running the web containers on a different host than the
Pi — is also fine. Each side has its own `data/` and they don't talk
to each other. Players reach the web UI directly via the container's
HTTPS endpoint; the Pi continues its own voice loop independently.

## Configuration

All runtime tunables live in `data/*.json` (created by the admin UI's
**Einstellungen** page), so the image itself is config-free except for
the secrets in `.env`. Notable files that appear in `./data/` once you
start configuring:

- `models.json` — per-role LLM endpoints + temperatures
- `audio.json` — TTS / STT backends
- `moderation.json` — content thresholds
- `story.json` — narration / memory / pressure tuning
- `settings.json` — Storymodus pin (auto / planner / frei)
- `cost.json` / `cost.jsonl` — per-model prices + spend ledger

## Limitations

- No automatic Let's Encrypt — Caddy uses `tls internal` (self-signed).
  For a public-internet deployment add a real cert to the Caddyfile.
- No GPU passthrough. If your local LLM stack runs on a separate
  Windows + NVIDIA box (see `local_llm_servers_win/`), the web
  containers reach it over the LAN like the Pi does.
- `data/voice_prompts/` is **not used** by the web services — those
  WAVs are for the Pi voice-loop only. The volume can hold them safely
  if you co-host with the Pi (point 1 above), they just won't be
  played by the containers.
