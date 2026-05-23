# Local AI Server (Windows) — LLM + STT + TTS backends for Storyteller

This folder is an **optional, fully-local AI server stack** for the
Storyteller project. It is **not** Storyteller itself — it provides the
three model APIs that Storyteller's clients (Pi, PC, web) talk to over your
LAN, so you can run the whole experience without an OpenAI key.

Three OpenAI-compatible-ish services, all on Windows:

- **LLM** — Ollama serving `qwen3-30b-32k` (a 32k-context Qwen3 30B variant)
- **STT** — Faster-Whisper Server (Docker)
- **TTS** — XTTS v2 API Server (Docker)

> ⚠️ **A capable NVIDIA GPU is REQUIRED.** This is not a CPU-friendly stack.
>
> | Component | Approx. VRAM at default settings |
> |---|---|
> | Ollama / `qwen3-30b-32k` (Q4) at 32k ctx | **~20–24 GB** |
> | Faster-Whisper large-v3 (CUDA, FP16) | ~3–4 GB |
> | XTTS v2 (FP16) | ~4–6 GB |
>
> Realistic minimums:
> - **Single GPU**: 24 GB VRAM (e.g. RTX 3090 / 4090) — workable; reduce the
>   LLM context to 16k or use a smaller model (`qwen3:14b`) for headroom.
> - **Two GPUs** (recommended, default config): one ≥ 24 GB for the LLM,
>   one ≥ 8 GB for Whisper + XTTS together.
> - Less VRAM → swap to a smaller LLM (`qwen3:14b` / `qwen2.5:7b`) and/or
>   `num_ctx 8192`. See *Reduce VRAM Usage* below.

The default configuration assumes a two-GPU machine:

- GPU `0`: intended for Ollama/Qwen
- GPU `1`: intended for Whisper STT and XTTS TTS

You can adapt this for single-GPU or different multi-GPU systems by editing the configuration blocks at the top of the scripts.

## Context — how this fits into Storyteller

After `start.bat` is running on this Windows box, point your Storyteller
client (Pi or PC) at the printed LAN endpoints. In Storyteller's admin UI
(`/settings`) or directly in `data/models.json`, set:

```json
{
  "story_llm": "qwen3-30b-32k",
  "planner_llm": "qwen3-30b-32k",
  "gen_llm": "qwen3-30b-32k",
  "stt": "deepdml/faster-whisper-large-v3-turbo-ct2",
  "tts": "marcel",   "tts_voice": "marcel",
  "embedding": "bge-m3",
  "story_endpoint":     { "base_url": "http://<windows-ip>:11434/v1" },
  "planner_endpoint":   { "base_url": "http://<windows-ip>:11434/v1" },
  "gen_endpoint":       { "base_url": "http://<windows-ip>:11434/v1" },
  "stt_endpoint":       { "base_url": "http://<windows-ip>:8001/v1" },
  "tts_endpoint":       { "base_url": "xtts://<windows-ip>:8002" },
  "embedding_endpoint": { "base_url": "http://<windows-ip>:11434/v1" }
}
```

The `xtts://` scheme tells Storyteller's TTS layer to talk to the XTTS API
format (POST `/tts_to_audio/`). See `docs/ADMIN_GUIDE.md` in the main repo
for the scheme conventions.

## Files

| File | Purpose |
| --- | --- |
| `install.bat` | Runs the setup script as administrator. |
| `install-compnents.ps1` | Pulls Docker images, pulls `qwen3:30b`, creates the `qwen3-30b-32k` Ollama model, and creates XTTS folders. |
| `Modelfile.qwen3-30b-32k` | Defines the local Qwen3 variant with a 32k context window. |
| `start.bat` | Runs the start script as administrator. |
| `run-server.ps1` | Starts Ollama, loads Qwen3, starts Faster-Whisper, and starts XTTS. |
| `stop.bat` | Runs the stop script as administrator. |
| `stop-server.ps1` | Stops STT, TTS, unloads the Ollama model, and stops Ollama. |


## Requirements

Install these first:

- Windows with PowerShell
- Docker Desktop with NVIDIA GPU support
- NVIDIA driver with CUDA support
- Ollama
- Enough free disk space for Docker images and Ollama models

Check GPU visibility:

```powershell
nvidia-smi
```

Check Ollama:

```powershell
ollama list
```

Check Docker:

```powershell
docker info
```

## First-Time Setup

Run:

```text
install.bat
```

This will:

- pull the Faster-Whisper CUDA Docker image
- pull the XTTS Docker image
- pull `qwen3:30b`
- create the local Ollama model `qwen3-30b-32k`
- create XTTS folders under `%USERPROFILE%\Documents\xtts-api-server`

## Starting

Run:

```text
start.bat
```

The scripts auto-detect a local IPv4 address for display. You can override it with:

```powershell
$env:SPEECHSERVER_LOCAL_IP = "192.168.1.50"
```

If `OLLAMA_HOST` is not already set, `run-server.ps1` sets it to:

```powershell
0.0.0.0:11434
```

This allows other devices on the LAN to reach Ollama, assuming your firewall allows it.

Endpoints after startup:

| Service | URL | Notes |
| --- | --- | --- |
| Ollama/Qwen | `http://<your-ip>:11434/v1` | OpenAI-compatible endpoint. Use model `qwen3-30b-32k`. |
| Whisper STT | `http://<your-ip>:8001/v1` | OpenAI-style transcription API. |
| XTTS TTS | `http://<your-ip>:8002` | XTTS API server. |
| XTTS Docs | `http://<your-ip>:8002/docs` | API documentation. |

Localhost also works on the same PC:

```text
http://localhost:11434/v1
http://localhost:8001/v1
http://localhost:8002
```

## Stopping

Run:

```text
stop.bat
```

By default this:

- stops the Whisper container
- stops the XTTS container
- unloads `qwen3-30b-32k`
- stops Ollama

## XTTS speaker samples

XTTS clones the voice from a reference WAV. Drop your speaker WAVs into:

```text
%USERPROFILE%\Documents\xtts-api-server\speakers
```

The filename (without `.wav`) becomes the `speaker_wav` / `tts_voice`
identifier — e.g. `marcel.wav` → set `tts_voice = "marcel"` in
Storyteller. A clean ~10 s mono recording works well.

## Adapting To Different Hardware

Most changes are in the configuration sections at the top of:

- `install-compnents.ps1`
- `run-server.ps1`
- `stop-server.ps1`
- `Modelfile.qwen3-30b-32k`

### Change The Local IP

The scripts use `$env:SPEECHSERVER_LOCAL_IP` if it is set. Otherwise they auto-detect a non-loopback IPv4 address.

Temporary override for the current PowerShell session:

```powershell
$env:SPEECHSERVER_LOCAL_IP = "192.168.1.50"
```

Permanent user-level override:

```powershell
[Environment]::SetEnvironmentVariable("SPEECHSERVER_LOCAL_IP", "192.168.1.50", "User")
```

This only changes printed endpoint URLs. Docker and Ollama still listen on their configured interfaces.

To override the Ollama bind address:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
```

Use `127.0.0.1:11434` if you want Ollama to be local-only.

### Change GPU Assignment

Check GPU IDs:

```powershell
nvidia-smi
```

Whisper and XTTS are pinned in `run-server.ps1`:

```powershell
$WhisperGpu = "1"
$XTTSGpu = "1"
```

For a single-GPU machine, use:

```powershell
$WhisperGpu = "0"
$XTTSGpu = "0"
```

These variables are passed into Docker as:

```powershell
"-e", "CUDA_VISIBLE_DEVICES=$WhisperGpu"
"-e", "CUDA_VISIBLE_DEVICES=$XTTSGpu"
```

If you want Docker containers to see only one GPU at Docker level, you can also replace:

```powershell
"--gpus", "all"
```

with:

```powershell
"--gpus", "device=0"
```

or:

```powershell
"--gpus", "device=1"
```

Keep the Docker device and `CUDA_VISIBLE_DEVICES` settings consistent.

### Change The LLM

The LLM is configured as:

```powershell
$OllamaBaseModel = "qwen3:30b"
$OllamaModel = "qwen3-30b-32k"
```

in `install-compnents.ps1`, and:

```powershell
$OllamaModel = "qwen3-30b-32k"
$OllamaContext = 32768
```

in `run-server.ps1`.

To use a smaller model, for example:

```powershell
$OllamaBaseModel = "qwen3:14b"
$OllamaModel = "qwen3-14b-32k"
```

Create a matching Modelfile:

```text
FROM qwen3:14b

PARAMETER num_ctx 32768
```

Then update:

```powershell
$OllamaModelfile = ".\Modelfile.qwen3-14b-32k"
```

Also update `$OllamaModel` in `stop-server.ps1` if you change the model name.

### Reduce VRAM Usage

The main lever is context size.

Current file:

```text
Modelfile.qwen3-30b-32k
```

Current setting:

```text
PARAMETER num_ctx 32768
```

For less VRAM usage, use:

```text
PARAMETER num_ctx 16384
```

or:

```text
PARAMETER num_ctx 8192
```

Also update `$OllamaContext` in `run-server.ps1` to the same value:

```powershell
$OllamaContext = 16384
```

Then rerun:

```powershell
ollama create qwen3-30b-32k -f .\Modelfile.qwen3-30b-32k
```

### Use CPU Instead Of GPU For Whisper

This setup is intended for CUDA. For CPU-only Whisper, remove the GPU-related Docker arguments from the Whisper section in `run-server.ps1`:

```powershell
"--gpus", "all"
"-e", "CUDA_VISIBLE_DEVICES=$WhisperGpu"
```

You may also need a non-CUDA Faster-Whisper image depending on the image tags available at the time.

### Change Ports

Edit Docker port mappings in `run-server.ps1`.

Whisper:

```powershell
"-p", "8001:8000"
```

XTTS:

```powershell
"-p", "8002:8020"
```

The first number is the host port. The second number is the container port.

Example, expose XTTS on host port `8012`:

```powershell
"-p", "8012:8020"
```

Also update printed endpoint text if you change ports.

## Useful Commands

Show installed Ollama models:

```powershell
ollama list
```

Show loaded Ollama models:

```powershell
ollama ps
```

Unload the active LLM:

```powershell
ollama stop qwen3-30b-32k
```

Inspect model metadata:

```powershell
ollama show qwen3-30b-32k
```

Show running containers:

```powershell
docker ps
```

Show container logs:

```powershell
docker logs faster-whisper-server
docker logs xtts-api-server
```

## Notes

The `.ps1` files are saved as UTF-8 with BOM so Windows PowerShell handles German umlauts correctly.

For tool calling with Qwen3, your client should read `tool_calls` from the OpenAI-compatible response. Qwen3 may also return a `reasoning` field. Ignore `reasoning` in the engine unless you explicitly want to inspect it.
