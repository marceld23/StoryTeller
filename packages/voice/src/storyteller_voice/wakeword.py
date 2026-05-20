"""Local wake-word detection (openWakeWord, default model).

Reads mic frames via the audio backend (Pi: arecord, PC: sounddevice)
-> platform-neutral. Default word for now, changeable later via
config.wakeword.model. Install the py3.13 packages: scripts/install_wakeword.sh.
If openWakeWord is unavailable -> .available == False; the caller falls back
to push-to-talk or text mode.
"""

from __future__ import annotations

import threading

from storyteller_core.config import Config

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

            from ..i18n import norm

            loc = norm(cfg.general.locale)
            name = (getattr(cfg.wakeword, f"model_{loc}", "")
                    or cfg.wakeword.model or DEFAULT_MODEL)
            self.model = Model(inference_framework="onnx",
                               wakeword_models=[name])
            self.available = True
        except Exception as exc:  # pragma: no cover - install-/HW-abhängig
            self._err = repr(exc)

    def listen_blocking(self) -> bool:
        """Block until the wake word is detected.

        Resilient: if the mic stream ends (arecord closed) it re-opens and
        keeps listening, so it truly blocks. Returns False only if the model
        is unavailable or the mic keeps failing (caller then backs off).
        """
        if not self.available:
            return False
        import time

        fails = 0
        while fails < 30:
            stop = threading.Event()
            got_any = False
            try:
                for frame in self.backend.mic_frames(16000, FRAME_LEN, stop):
                    got_any = True
                    scores = self.model.predict(frame)
                    if any(s >= self.cfg.wakeword.threshold
                           for s in scores.values()):
                        return True
                fails = 0 if got_any else fails + 1
                time.sleep(0.3)
            except Exception:
                fails += 1
                time.sleep(0.5)
            finally:
                stop.set()
        return False
