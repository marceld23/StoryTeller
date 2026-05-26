#!/usr/bin/env bash
# Re-synthesise the cached voice-prompt WAVs under
# data/voice_prompts/<locale>/<slot>/ via the configured TTS endpoint.
# A slot is one (endpoint, model, voice) combination — switching any
# of those picks a different subdirectory, so old WAVs aren't
# clobbered and are reused when you switch back.
#
# Default: per-prompt staleness — only re-bakes prompts whose i18n
# text changed since the slot's manifest was written, or whose WAV
# is missing. Fast (one TTS call per touched prompt), free if you're
# on a local TTS server.
#
# --force      : re-bake EVERY prompt in the CURRENT slot
#                unconditionally. Other slots are untouched — they
#                keep their cached files. Use this if you suspect
#                the audio in the active slot is corrupted; a plain
#                voice / model swap doesn't need --force any more
#                (it just creates / reuses a different slot).
#
# Usage:
#   bash scripts/bake_voice_prompts.sh            # incremental
#   bash scripts/bake_voice_prompts.sh --force    # rebuild current slot

set -euo pipefail
cd "$(dirname "$0")/.."

force_arg="False"
if [[ "${1:-}" == "--force" || "${1:-}" == "-f" ]]; then
  force_arg="True"
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "error: .venv/bin/python not found. Run 'uv sync' first." >&2
  exit 1
fi

.venv/bin/python - <<PY
from storyteller_core.config import load_config
from storyteller_voice.prompts import VoicePromptCache

cfg = load_config()
pc = VoicePromptCache(cfg)
print(f"slot: {pc.dir.relative_to(cfg.root)}")
built = pc.build(force=${force_arg})
if built:
    print(f"re-baked {len(built)} prompt(s): {', '.join(built)}")
else:
    print("nothing to bake — all cached prompts are up to date.")
PY
