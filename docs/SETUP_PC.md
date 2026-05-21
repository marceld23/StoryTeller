# Setup — normal PC (no Pi, no ReSpeaker)

Storyteller runs on any Linux/macOS/Windows PC with Python 3.13 and
[uv](https://docs.astral.sh/uv/). On a PC you mainly use the **text REPL**
and/or the **web apps** in the browser. The runtime profile is auto-detected:
no ReSpeaker ⇒ profile `pc` ⇒ portable `sounddevice` backend (software
volume), the LED ring is a harmless no-op.

## 1. Install

```bash
git clone https://github.com/marceld23/StoryTeller.git
cd StoryTeller
curl -LsSf https://astral.sh/uv/install.sh | sh    # if uv not installed
uv sync                                            # workspace venv (one .venv)
echo "OPENAI_API_KEY=sk-..." > .env
uv run --package storyteller-cli storyteller-cli seed   # write seed worlds (once)
```

## 2. Text REPL — best for testing (no audio)

```bash
uv run --package storyteller-cli storyteller-cli chat
uv run --package storyteller-cli storyteller-cli chat --world immerwald --locale en
```

In-chat: `/undo` rolls back a turn, `/state` inspects the session, `/quit`
exits. Flags: `--new` (fresh session/thread), `--no-rag`. Session state is
checkpointed in `data/checkpoints.db` (keyed by `thread_id`), so re-running
`chat` for the same world resumes it. Other CLI commands: `info`, `worlds`,
`seed`, `history`.

## 3. Play & admin in the browser

Each web app's FastAPI backend serves its SvelteKit UI as a static SPA.
Build the frontends once (needs Node 20 + yarn 4), then run the backend(s):

```bash
bash scripts/build_frontends.sh        # writes apps/*/frontend/build/

uv run --package storyteller-web-ui-backend    storyteller-web-ui     # play  -> :8090
uv run --package storyteller-web-admin-backend  storyteller-web-admin  # admin -> :8080
```

Open <http://localhost:8090> (play: text or hold-to-talk voice) and
<http://localhost:8080> (admin: world editor, generation, transcripts,
settings). **Frontend dev** with hot reload: `cd apps/web-ui/frontend &&
yarn dev` (talks to the running backend via `VITE_BACKEND`).

## 4. Voice loop on the PC (optional)

There is no separate PC voice app; the Pi loop runs on a PC too, using the OS
default mic/speakers:

```bash
uv run --package storyteller-pi storyteller-pi run --profile pc
uv run --package storyteller-pi storyteller-pi run --text     # keyboard, no mic
uv run --package storyteller-pi storyteller-pi run --text --silent  # pure text
```

The wake word is used if installed (`bash scripts/install_wakeword.sh`),
otherwise it auto-falls back to push-to-talk. Volume is a software gain
(`config [audio] default_volume_pct`). For quick testing prefer the text
REPL or the browser.

See [USER_GUIDE.md](USER_GUIDE.md) for gameplay and the
[README](../README.md) for the full command reference.
