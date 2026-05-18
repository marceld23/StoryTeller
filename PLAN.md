# Storyteller — Implementation Plan

Interactive, voice-controlled storyteller. Runs on a Raspberry Pi 4 with a
ReSpeaker USB Mic Array v2.0, or on a normal PC; OpenAI API; local wake-word
detection; localized for German and English.

> Status of this document: **living plan**, implemented iteratively.
> Decisions are recorded under "Fixed decisions".

---

## 1. Fixed decisions

| Topic | Decision | Rationale |
|---|---|---|
| Audio architecture | Separate **STT → LLM → TTS** pipeline (not the Realtime API) | Only this allows deterministic RAG injection + a reverb effect on the voice |
| Audio output | **Pluggable backend**: ALSA `softvol` (Pi/ReSpeaker line-out), `portable` (PC/sounddevice), `pipewire` (Bluetooth, later) | Pi line-out volume now; PC support; Bluetooth later without rework |
| Runtime profile | `runtime.profile = auto\|pi\|pc`; auto-detect ReSpeaker | Same code on Pi and PC |
| Wake word | **openWakeWord** (self-hosted, no account) | Fully local/independent; PTT/text fallback |
| STT | **Provider abstraction**; default `gpt-4o-mini-transcribe` (OpenAI); optional **local Whisper** later | Low latency; local only on Pi 5 + AI HAT |
| TTS | **Provider abstraction**; default `gpt-4o-mini-tts` PCM (OpenAI); optional **local TTS** later | Whisper is **not** TTS; PCM stream ideal for reverb |
| Story LLM (default) | `gpt-5.4-mini` | User's choice; configurable |
| Embeddings (default) | `text-embedding-3-small` (dim 512) | Price/quality; small on the Pi |
| RAG store | **sqlite-vec** (one DB file, `world_id` partition key, per-locale) | Tiny, aarch64/py3.13 wheels, clean world/locale isolation |
| Audio effect | **Spotify `pedalboard`** (reverb/distortion) | Prebuilt aarch64/py3.13 wheels, cheap, in-process |
| Packaging / env | **uv** + Python 3.13 | User's choice |
| Web admin | FastAPI (lightweight) | Small enough for the Pi |
| Voice-menu audio | **Voice-prompt cache**: render fixed prompts once, play without API, per locale | Save tokens + latency |
| Substory system | Macro blueprint + dynamically planned **substories** (state machine), plan adjustable via tool/injection | Hold the arc, involve the player, don't derail |
| Story dynamic | Abstract random twists (tool + auto-injection + planning), arc-faithful | Surprise "without toppling the story" |
| Localization | **de / en**; German prompts kept **verbatim**, English added; worlds in both languages | User's choice; prompts must stay German for German |
| All model names | **configurable** in `config/config.toml` | User's choice |

---

## 2. Hardware setup (ReSpeaker USB Mic Array v2.0)

USB id `2886:0018`, ALSA `card ArrayUAC10`. **No** hardware volume control →
ALSA `softvol` plugin (officially recommended by Seeed for exactly this device).

1. **udev rule** `/etc/udev/rules.d/60-respeaker.rules` (once, root, via
   `scripts/setup_system.sh`) — non-root access for LED ring + DSP tuning.
2. **ALSA softvol** via `~/.asoundrc` (userland, no root):
   `plug:respeaker_softvol` playback with `amixer` control `Master` on
   `card ArrayUAC10`; capture via `dsnoop` (16 kHz, mono).
3. **pixel_ring v2** vendored (`hardware/pixel_ring_v2.py`) — the official lib
   is unmaintained since 2021 but the v2 USB path is simple & py3.13-clean.
4. **tuning.py** vendored + py3.13 patch (`.tostring()` → `.tobytes()`).
5. Default firmware (1-channel, beamformed mono) is optimal for STT → **no
   reflash** needed.

Volume API (Pi): `amixer -c ArrayUAC10 sset Master <pct>%`.
On PC: software gain in the portable backend.

---

## 3. Architecture

```
                    ┌─────────────── Voice loop (play mode) ───────────────┐
                    │                                                      │
  Mic ──────────────┤ openWakeWord ──► STT (OpenAI) ──► Story engine ──┐   │
  (ReSpeaker / PC)  │     ▲                                  │         │   │
                    │     │                                  ▼         │   │
  LED ring ◄────────┤  LED state machine            RAG (sqlite-vec)   │   │
                    │  (wake/listen/think/speak)    blueprint/substory │   │
  Wait-sound loop ◄─┤                               known-facts tool   │   │
                    │                               random / dynamics  │   │
  Speaker ◄─────────┤ Audio backend ◄─ reverb (pedalboard) ◄─ TTS ◄────┘   │
  (line-out/PC/BT)  │ (alsa_softvol / portable / pipewire)                 │
                    └──────────────────────────────────────────────────────┘

  Web admin (FastAPI) ──► worlds / facts / persons / places / blueprints /
                          random tables (LLM-assisted fact writing)
```

### 3.1 Modules (`src/storyteller/`)

| Module | Content |
|---|---|
| `config.py` | Load/validate `config.toml` + `.env`; all model names, paths, audio backend, locale, runtime profile, FX params |
| `runtime.py` | Profile detection (Pi vs PC) and backend resolution |
| `i18n.py` | Localization (de verbatim / en): voice prompts, menu keywords, guidance, directives, command keywords |
| `audio/backend.py` | `AudioBackend` ABC + `AlsaSoftvolBackend` (Pi), `PortableBackend` (PC/sounddevice), `PipeWireBackend` (Bluetooth). `loop_play`/`mic_frames` keep WaitLoop/WakeWord platform-neutral |
| `audio/player.py` | Play a PCM/array via the backend (temp WAV) |
| `audio/ambient.py` | Procedural, seamlessly loopable per-world ambience (mood: space/forest), offline; `storyteller wait-sounds build` |
| `hardware/pixel_ring_v2.py` | Vendored LED driver (USB) |
| `hardware/leds.py` | High-level LED states `idle/wake/listen/think/speak/error` (graceful no-op without device) |
| `hardware/tuning.py` | Vendored + py3.13 patch; DSP params (DOA/AGC/NS) |
| `voice/wakeword.py` | openWakeWord wrapper; mic via backend; PTT/text fallback |
| `voice/stt.py` | STT provider abstraction: `OpenAISTT` (default), `LocalWhisperSTT` (later); language follows locale |
| `voice/tts.py` | TTS provider abstraction: `OpenAITTS` PCM (default), `LocalTTS` (later) |
| `voice/fx.py` | pedalboard reverb/distortion, per-world configurable |
| `voice/waitloop.py` | Per-world wait sound, gapless loop via backend, while the LLM "thinks" |
| `voice/prompts.py` | Voice-prompt cache, per locale (data/voice_prompts/<locale>/) |
| `story/engine.py` | Orchestration v2: co-creation prompt, tool calls, substory state machine, cost cap, snapshot/restore, follow-up-question short mode, locale |
| `story/substory.py` | `SubstoryPlan` + `SubstoryPlanner` + `NarrativeState` |
| `story/dynamics.py` | Abstract story dynamic (tool + auto-injection + planning), arc-faithful |
| `story/cost.py` | Token/cost estimate + session cap (graceful wrap-up) |
| `story/rag.py` | sqlite-vec, retrieval per (world_id, locale), metadata filter |
| `story/blueprint.py` | Macro arc beats; keeps the story on track |
| `story/knowledge.py` | Tool: track/query what the player knows |
| `story/random_events.py` | World-specific random tables, callable as a tool |
| `util/log.py` | Logging (file + console) |
| `worlds/schema.py` | Pydantic models World/Place/Person/Item/Glossary/History/Fragment/Blueprint/RandomTable |
| `worlds/seed.py` | 2 default worlds (Sci-Fi / High-Fantasy), de + en |
| `worlds/registry.py` | Locale-aware world load/save |
| `menu/voice_menu.py` | Voice menu: pick world, load, save (localized) |
| `persistence/saves.py` | Save games (JSON snapshot) |
| `web/app.py` | Admin frontend: worlds/facts CRUD + LLM-assisted fact writing |
| `cli.py` | Entrypoints: `run` / `demo` / `admin` / `seed` / `rag` / `voice-prompts` / `wait-sounds` / `hw-test` / `info` |

### 3.2 Data model (world)

```
World
 ├─ id, name, genre
 ├─ description            (game/world description)
 ├─ player_role
 ├─ starting_situation
 ├─ narration_style        (narration tone, technical)
 ├─ mood
 ├─ ambience               (sensory impressions / atmosphere)
 ├─ magic_physics          (physics or magic system, rules)
 ├─ places[]      (name, description, tags)
 ├─ persons[]     (name, role, description, relations, tags)
 ├─ items[]       (name, description, properties, tags)
 ├─ glossary[]    (term, definition)            ← terminology
 ├─ history[]     (when, title, description)
 ├─ fragments[]   (title, text, tags)           ← lore / hooks
 ├─ blueprint     (premise, beats[name,goal,tension], escalation_rule)
 ├─ random_tables[] (name, description, entries[weight,text])  ← concrete, used
 └─ wait_sound, fx_preset
places/persons/items/glossary/history/fragments + mood/ambience/magic
 → embedded in sqlite-vec (RAG), filtered by (world_id, locale) + fact_type
   (place|person|item|glossary|history|fragment|system).
All fields creatable/editable in the backend (also LLM-assisted).
Worlds exist per locale: data/worlds/<id>.json (de), <id>.en.json (en).
```

### 3.3 Story engine — "not on rails"

- The player speaks **freely** (no action menu). STT → engine.
- The engine builds the prompt from: world context (description, mood,
  ambience, physics/magic, glossary excerpt, random-table names) + macro
  blueprint + current substory + RAG hits + short-term memory + known facts +
  a language instruction (de/en).
- The LLM is the narrator **with tools for targeted world access**:
  `get_world_overview`, `retrieve_world_fact(fact_type)`, `lookup_glossary`,
  `roll_random_event` (world tables), `roll_story_dynamic` (abstract),
  `remember_fact`, `advance_beat`, `complete_substory`,
  `get_/adjust_substory_plan`.
- Substory state machine: in-substory → drive toward resolution; once the
  narrator calls `complete_substory`, the architect plans the next substory
  (RAG + context) and it is injected; the plan is queryable/adjustable via
  tools (player going off-script redirects the plan without discarding the arc).
- Follow-up questions are detected and answered briefly without advancing
  the plot.

---

## 4. Phase plan (iterative)

- **Phase 0 — Setup & scaffold**: uv project, config, schema, seed worlds,
  audio-backend abstraction, vendored hardware modules, `hw-test`, ALSA
  softvol, udev script.
- **Phase 1 — Hardware bring-up**: softvol/amixer, mic capture, LED ring,
  tuning verified.
- **Phase 2 — Audio pipeline**: recorder → STT → TTS → reverb → backend,
  wait-sound loop + LED states.
- **Phase 3 — Wake word**: openWakeWord, default model, mic gating, fallback.
- **Phase 4 — RAG & worlds**: sqlite-vec, embeddings, per-world retrieval.
- **Phase 5 — Story engine**: prompt building, tools, blueprint, known facts,
  random events, substory state machine, story dynamic.
- **Phase 6 — Voice menu & persistence**: pick/load/save world by voice; all
  static menu prompts via the voice-prompt cache.
- **Phase 7 — Web admin**: CRUD + LLM-assisted fact writing.
- **Phase 8 — Bluetooth backend**: PipeWire sink behind the existing
  abstraction (+ `scripts/setup_bluetooth.sh`).
- **Phase 9 — Polish**: systemd autostart, error/reconnect handling, cost cap,
  logging.
- **Phase 9b — PC mode & localization**: portable sounddevice backend,
  runtime profiles, text/silent modes; full de/en localization (audio,
  worlds, narration, menu, STT).
- **Phase 10 — Local speech models (optional, hardware-dependent)**: local
  Whisper STT + local TTS behind the provider abstraction.
  **Requires a Raspberry Pi 5 + AI HAT (NPU)** — not latency-viable on the
  current Pi 4. Switchable via config (OpenAI ↔ local).
- **Phase 11 — Wi-Fi onboarding (designed; feasible on this Pi)**

  Goal: if the Pi cannot reach a known Wi-Fi at boot, it opens its own AP
  `storyteller-wifi`; a phone connects, sees a page listing nearby Wi-Fis,
  picks one + enters the key; the Pi stores it, switches/reboots and uses it,
  and keeps it for future boots.

  **Feasibility (verified on this device):** NetworkManager is active
  (`nmcli` 1.52), `wlan0` supports **AP mode** (`iw list`), nmcli-created
  connections persist (`/etc/NetworkManager/system-connections`,
  autoconnect). So the whole flow is `nmcli`-only — no hostapd needed. One
  extra package: **`dnsmasq-base`** (NM "shared"/hotspot DHCP).

  **Components:**
  - `net/onboarding.py` + a systemd unit `storyteller-netcheck.service`
    (`Before=storyteller.service`, `After=NetworkManager.service`).
  - A tiny separate FastAPI app (own port, e.g. `:80`), isolated from the
    story web admin, only running while in AP mode.

  **Boot flow (`storyteller-netcheck`):**
  1. Wait up to ~`netcheck.timeout_s` for connectivity
     (`nmcli -t -f STATE general` == connected / `nmcli networking
     connectivity` == full).
  2. Connected → exit 0; normal services start.
  3. Not connected → **scan first in station mode** and cache results
     (`nmcli -t -f SSID,SIGNAL,SECURITY device wifi list`) to a temp file
     (single radio: can't scan while in AP mode).
  4. Start AP: `nmcli device wifi hotspot ifname wlan0 ssid storyteller-wifi
     password <cfg>` (WPA2; password configurable, default printed/in config;
     gateway `10.42.0.1`). Start the setup web app.
  5. User connects phone to `storyteller-wifi`, opens `http://10.42.0.1`
     (manual MVP) → page shows cached SSID list (dropdown) + manual SSID +
     password field + submit. Optional later: real captive portal (own
     `dnsmasq` DNS-hijack + OS probe URLs `/generate_204`,
     `/hotspot-detect.html` → redirect) so it auto-pops.
  6. POST `/connect`: `nmcli device wifi connect "<ssid>" password "<key>"`
     → on success the connection is saved (autoconnect=yes, persists) →
     tear down AP (`nmcli connection down Hotspot`) → `sudo reboot` (clean,
     reuses saved Wi-Fi on next boot). On failure → back to AP with an error
     (never echo/log the key).

  **Caveats / decisions:**
  - One radio ⇒ scan-before-AP + cached list + manual SSID entry; a "rescan"
    button briefly drops the AP.
  - `nmcli`-created keyfile connections persist independent of netplan; do
    NOT manage them via netplan to avoid re-render wipes.
  - Setup AP is WPA2 (configurable password); the *target* key is only
    passed to `nmcli`, never logged or rendered back.
  - Needs `sudo` for `nmcli`/reboot ⇒ the netcheck service runs as root (or
    a tight sudoers rule for `nmcli`/`reboot`).
  - New config block `[netcheck]`: `enabled`, `timeout_s`, `ap_ssid`,
    `ap_password`, `web_port`.
  - References for the captive-portal polish: balena `wifi-connect`,
    `comitup`, `RaspiWiFi` (we stay nmcli-native, no hostapd).

---

## 5. Risks / open points

- openWakeWord runs with the **default word "hey jarvis"** (ONNX). Install
  reproducibly via `scripts/install_wakeword.sh` (`--no-deps openwakeword` +
  `onnxruntime requests scipy scikit-learn` + model download; tflite-runtime
  avoided, no py3.13 wheels). **`uv sync` prunes these** — re-run the script
  after any `uv sync`. A custom German word needs one-off Colab training.
- OpenAI latency: hidden by the wait-sound loop + LED; the loop now covers
  the whole post-selection prep.
- Per-world reverb: keep defaults subtle, avoid over-driven distortion.
- Cost: STT+LLM+TTS per turn — session cost cap + logging.
- ALSA: capture must be `dsnoop` (wake word + 6 s capture concurrently);
  the app addresses devices explicitly via the backend abstraction.
- Run the loop via `.venv/bin/python -m storyteller.cli run`, not `uv run`
  (concurrent `uv run` can cause a spawn race). systemd unit does this.
- Local speech models (Phase 10) need a **Pi 5 + AI HAT**; the abstraction
  exists so no rework is needed later.

---

## 6. Default worlds (seed)

1. **"Starfaring" / "Sternenfahrt" (Sci-Fi)** — humans travel by hyperspace
   through many worlds. Player = **starship captain**.
2. **"The Everwood Realm" / "Das Immerwald-Reich" (High-Fantasy)** — epic
   high-fantasy world. Player = **ranger**.

Both exist in de and en. Details/seed facts/blueprints: `worlds/seed.py`.
