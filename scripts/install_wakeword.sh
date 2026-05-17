#!/usr/bin/env bash
# Phase-3-Wake-Word (openWakeWord) installieren.
# openwakeword 0.6.0 hat keine py3.13-Wheels über pip-Deps (tflite-runtime),
# daher --no-deps + ONNX-Stack manuell. Default-Wort: "hey jarvis".
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

uv pip install --no-deps openwakeword
uv pip install onnxruntime requests scipy scikit-learn
uv run python -c "import openwakeword.utils as u; u.download_models(); print('openWakeWord-Modelle geladen')"

echo "fertig — Default-Wake-Word 'hey jarvis' aktiv."
echo "Eigenes Wort später: in Colab trainieren, .onnx ablegen, config.wakeword.model setzen."
