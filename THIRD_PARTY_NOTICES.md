# Third-party notices

This project's own source code is licensed **MIT** (see `LICENSE`).
This file documents bundled/used third-party components and any caveats.

## Vendored source (redistributed in this repo)

These files were copied from Seeed Studio and are **retained under their
upstream Apache-2.0 license** (not relicensed under MIT):

- `src/storyteller/hardware/pixel_ring_v2.py`
  — from https://github.com/respeaker/pixel_ring (Apache-2.0),
  © Seeed Technology Co., Ltd.
- `src/storyteller/hardware/tuning.py`
  — from https://github.com/respeaker/usb_4_mic_array (Apache-2.0),
  © Seeed Technology Co., Ltd. Patched for Python 3.13
  (`.tostring()` → `.tobytes()`).

Apache-2.0 is permissive and compatible with shipping the rest under MIT,
provided the above attribution is preserved.

## Python dependencies (installed via pip/uv, not bundled)

Required (all permissive — do not affect this project's MIT license):

| Package | License |
|---|---|
| pydantic, rich, sounddevice, onnxruntime, sqlite-vec | MIT |
| python-dotenv, numpy, soundfile, pyusb, uvicorn, jinja2, scipy, scikit-learn | BSD-3-Clause |
| openai, requests, python-multipart, openwakeword (code) | Apache-2.0 |
| tqdm | MPL-2.0 / MIT |
| fastapi | MIT |

### Caveats

- **pedalboard — GPL-3.0.** Only used by the *optional* `audiofx` extra
  (voice reverb/distortion); imported dynamically with a graceful
  pass-through if absent, and **not** redistributed by this project. The
  project's own code remains MIT. Anyone who installs the `audiofx` extra
  and redistributes the combined work assumes GPL-3.0 obligations for that
  distribution. A non-GPL reverb can replace it if strict MIT purity is
  required.
- **openWakeWord pretrained models — CC-BY-NC-SA 4.0 (non-commercial).**
  The openWakeWord *code* is Apache-2.0, but the default models
  (e.g. "hey jarvis") are non-commercial. They are downloaded at install
  time (`scripts/install_wakeword.sh`), not shipped here. For commercial
  deployment, train and supply your own wake-word model and set
  `config.wakeword.model`.

## Service notice

OpenAI APIs (LLM, STT, TTS, embeddings, moderation) are used at runtime and
are governed by your OpenAI agreement; an API key is required.
