"""Local wake-word detection (openWakeWord, default model).

Reads mic frames via the audio backend (Pi: arecord, PC: sounddevice)
-> platform-neutral. Default word for now, changeable later via
config.wakeword.model. Install the py3.13 packages: scripts/install_wakeword.sh.
If openWakeWord is unavailable -> .available == False; the caller falls back
to push-to-talk or text mode.
"""

from __future__ import annotations

import threading

from ..config import Config

DEFAULT_MODEL = "hey_jarvis"
FRAME_LEN = 1280  # 80 ms @ 16 kHz (openWakeWord-Frame)


class WakeWord:
    def __init__(self, cfg: Config, backend):
        self.cfg = cfg
        self.backend = backend
        self.model = None
        self.available = False
        try:
            from openwakeword.model import Model

            name = cfg.wakeword.model or DEFAULT_MODEL
            self.model = Model(inference_framework="onnx",
                               wakeword_models=[name])
            self.available = True
        except Exception as exc:  # pragma: no cover - install-/HW-abhängig
            self._err = repr(exc)

    def listen_blocking(self) -> bool:
        """Blockiert bis Wake-Word erkannt. False wenn nicht verfügbar."""
        if not self.available:
            return False
        stop = threading.Event()
        try:
            for frame in self.backend.mic_frames(16000, FRAME_LEN, stop):
                scores = self.model.predict(frame)
                if any(s >= self.cfg.wakeword.threshold
                       for s in scores.values()):
                    return True
        finally:
            stop.set()
        return False
