#!/usr/bin/env bash
# Re-synthesise the cached voice-prompt WAVs under
# data/voice_prompts/<locale>/ via the configured TTS endpoint.
#
# Default: per-prompt staleness — only re-bakes prompts whose i18n text
# changed, or whose WAV is missing. Fast (one TTS call per touched
# prompt), free if you're on a local TTS server.
#
# --force      : re-bake EVERY prompt unconditionally. Use this after
#                changing the voice (models.tts_voice) or the TTS model
#                (models.tts / models.tts_endpoint), since voice swaps
#                make the WAVs sound inconsistent with what the prompt
#                cache thinks it has.
#
# Usage:
#   bash scripts/bake_voice_prompts.sh            # incremental
#   bash scripts/bake_voice_prompts.sh --force    # full rebuild

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
built = pc.build(force=${force_arg})
if built:
    print(f"re-baked {len(built)} prompt(s): {', '.join(built)}")
else:
    print("nothing to bake — all cached prompts are up to date.")
PY
