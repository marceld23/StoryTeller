#!/usr/bin/env bash
# Install the phase-3 wake-word stack (openWakeWord).
# openwakeword 0.6.0 ships no py3.13 wheels via its pip deps
# (tflite-runtime), so we use --no-deps and pull the ONNX stack
# manually. Default wake word: "hey jarvis".
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

uv pip install --no-deps openwakeword
uv pip install onnxruntime requests scipy scikit-learn
uv run python -c "import openwakeword.utils as u; u.download_models(); print('openWakeWord models downloaded')"

echo "done — default wake word 'hey jarvis' is active."
echo "Custom word later: train in Colab, drop the .onnx file in,"
echo "and set config.wakeword.model to its path."
