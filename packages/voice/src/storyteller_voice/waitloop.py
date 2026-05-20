"""Per-world wait sound, GAPLESS loop, while the LLM 'thinks'.

Loads the file (paths.wait_sounds_dir/<World.wait_sound>) once and lets the
audio backend (Pi: aplay stream, PC: sounddevice) play it endlessly until the
reply arrives. Sets the LED ring to 'think'. File missing -> LED only.
"""

from __future__ import annotations

import threading

import numpy as np

from storyteller_core.config import Config


class WaitLoop:
    def __init__(self, cfg: Config, backend, sound_file: str, leds=None):
        self.cfg = cfg
        self.backend = backend
        self.leds = leds
        self._raw = b""
        self._sr = 24000
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        if sound_file:
            p = cfg.path(cfg.paths.wait_sounds_dir) / sound_file
            if p.exists():
                try:
                    import soundfile as sf

                    data, sr = sf.read(str(p), dtype="int16",
                                       always_2d=False)
                    if getattr(data, "ndim", 1) > 1:
                        data = data[:, 0]
                    self._raw = np.ascontiguousarray(data).tobytes()
                    self._sr = int(sr)
                except Exception:
                    self._raw = b""

    def _loop(self) -> None:
        try:
            self.backend.loop_play(self._raw, self._sr, self._stop)
        except Exception:
            pass

    def __enter__(self):
        if self.leds:
            self.leds.think()
        if self._raw:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)
        return False
