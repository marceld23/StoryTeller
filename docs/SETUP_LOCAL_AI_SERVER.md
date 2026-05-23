# Setup — fully local AI server (Windows + GPU)

Storyteller talks to **OpenAI-compatible endpoints** for every role
(narrator / planner / gen / STT / TTS / embeddings). The default is the
OpenAI API; this guide is the **alternative**: run the entire model stack
yourself, on your own LAN, with no API key — and point the Storyteller
client (Pi or PC) at it.

> 📁 This setup lives in [`local_llm_servers_win/`](../local_llm_servers_win/) at the repo root.
> The detailed how-to and per-script reference is the README inside that
> folder; this page gives you the overview and the decision context.

It is **not** the same as [SETUP_PC.md](SETUP_PC.md) — that one is about
running the *Storyteller client* on a regular PC (text REPL or browser).
The local AI server is the *backend*: the LLM/STT/TTS APIs the client talks
to. You can mix and match:

| Client lives on… | Server can live on… |
|---|---|
| Raspberry Pi (`storyteller-pi run`) | the same Windows box on the LAN |
| Normal PC (`storyteller-cli chat`, web UIs) | the same machine or another box |
| Browser (`/voice`) | anywhere reachable from the server-serving backend |

## What it includes

Three services started by one `start.bat`:

- **LLM** — Ollama serving a 32k-context Qwen3 30B (`qwen3-30b-32k`)
- **STT** — Faster-Whisper Server (Docker, CUDA)
- **TTS** — XTTS v2 API Server (Docker, CUDA) — `xtts://` provider scheme

## Hard requirements

⚠️ **NVIDIA GPU with enough VRAM is mandatory.** This stack is CUDA-only at
the default settings; CPU fallback is possible only for Whisper and is
documented in the inner README, but the LLM and XTTS need GPU.

| Component | Approx. VRAM at default settings |
|---|---|
| `qwen3-30b-32k` (Q4) at 32k context | **~20–24 GB** |
| Faster-Whisper large-v3 (FP16) | ~3–4 GB |
| XTTS v2 (FP16) | ~4–6 GB |

Realistic minimums:

- **Single GPU**: 24 GB VRAM (e.g. RTX 3090 / 4090). Workable — drop the
  LLM to 16k context or use `qwen3:14b` for headroom.
- **Two GPUs** (the default config): one ≥ 24 GB for the LLM, one ≥ 8 GB
  for Whisper + XTTS combined.
- Less VRAM → swap to a smaller LLM (`qwen3:14b` or `qwen2.5:7b`) and/or
  lower `num_ctx`. See *Reduce VRAM Usage* in the inner README.

Plus on the Windows host:

- Docker Desktop with NVIDIA GPU support
- An NVIDIA driver new enough for the chosen CUDA images
- Ollama (Windows native; not in Docker)
- Disk space for Ollama models (~18 GB for a 30B Q4) and Docker images.

## Run it

From `local_llm_servers_win/` on the Windows box (administrator
PowerShell / double-click `.bat` files):

```text
install.bat   # one-time: pulls Docker images, pulls qwen3:30b, creates qwen3-30b-32k
start.bat     # start everything; prints LAN endpoints
stop.bat      # tear down cleanly
```

Endpoints after startup (replace `<ip>` with the printed LAN address):

| Service | URL | Storyteller config |
|---|---|---|
| LLM | `http://<ip>:11434/v1` | `story_endpoint` / `planner_endpoint` / `gen_endpoint` / `embedding_endpoint` |
| STT | `http://<ip>:8001/v1` | `stt_endpoint` |
| TTS | `http://<ip>:8002` | `tts_endpoint` with **`xtts://<ip>:8002`** (scheme triggers the XTTS provider) |

## Wire it to Storyteller

In the admin UI under *Einstellungen → Modelle*, or directly in
`data/models.json`:

```json
{
  "story_llm":   "qwen3-30b-32k",
  "planner_llm": "qwen3-30b-32k",
  "gen_llm":     "qwen3-30b-32k",
  "gate_llm":    "qwen3-30b-32k",
  "stt":         "deepdml/faster-whisper-large-v3-turbo-ct2",
  "tts":         "marcel",   "tts_voice": "marcel",
  "embedding":   "bge-m3",
  "story_endpoint":     { "base_url": "http://192.168.178.95:11434/v1" },
  "planner_endpoint":   { "base_url": "http://192.168.178.95:11434/v1" },
  "gen_endpoint":       { "base_url": "http://192.168.178.95:11434/v1" },
  "stt_endpoint":       { "base_url": "http://192.168.178.95:8001/v1" },
  "tts_endpoint":       { "base_url": "xtts://192.168.178.95:8002" },
  "embedding_endpoint": { "base_url": "http://192.168.178.95:11434/v1" }
}
```

(`gate_endpoint` is optional — empty falls back to `planner_endpoint`.)
Changes hot-reload in the client — no restart of Storyteller needed.

## Sanity check from the client

```bash
/home/pi/storyteller/.venv/bin/python /home/pi/remote-check/check_setup.py
```

Should print *llm / embed / tts / stt = OK*. The first STT call loads the
Whisper model and is slow; subsequent calls are fast.

## Tuning

Lever your way down the VRAM ladder — see *Reduce VRAM Usage* in
[`local_llm_servers_win/README.md`](../local_llm_servers_win/README.md):

- LLM size: `qwen3:30b` → `qwen3:14b` → `qwen2.5:7b`
- Context: 32k → 16k → 8k (update `Modelfile` + `run-server.ps1`)
- Two-GPU → single-GPU: set `$WhisperGpu`/`$XTTSGpu = "0"`
- The Storyteller narration gate (`gate_llm`) appreciates a *small* model
  — point its endpoint at a 7B/14B variant if you keep a bigger one for
  the narrator.

For everything else (port changes, CUDA-less Whisper, GPU pinning, model
swaps), see the per-script reference in
[`local_llm_servers_win/README.md`](../local_llm_servers_win/README.md).
