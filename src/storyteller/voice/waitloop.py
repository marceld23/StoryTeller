"""Welt-spezifischer Wartesound, GAPLESS in Schleife, während LLM-/TTS-Wartezeit.

Lädt die Datei (paths.wait_sounds_dir/<World.wait_sound>) einmal und streamt
den Puffer endlos roh in `aplay` (kein Neustart pro Loop => keine Lücke).
Setzt den LED-Ring auf 'think'. Datei fehlt -> nur LED 'think'.
"""

from __future__ import annotations

import shutil
import subprocess
import threading

import numpy as np

from ..config import Config


class WaitLoop:
    def __init__(self, cfg: Config, sound_file: str, leds=None):
        self.cfg = cfg
        self.leds = leds
        self._raw = b""
        self._sr = 24000
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        if sound_file and shutil.which("aplay"):
            p = cfg.path(cfg.paths.wait_sounds_dir) / sound_file
            if p.exists():
                try:
                    import soundfile as sf

                    data, sr = sf.read(str(p), dtype="int16", always_2d=False)
                    if getattr(data, "ndim", 1) > 1:
                        data = data[:, 0]
                    self._raw = np.ascontiguousarray(data).tobytes()
                    self._sr = int(sr)
                except Exception:
                    self._raw = b""

    def _loop(self) -> None:
        proc = subprocess.Popen(
            ["aplay", "-q", "-D", self.cfg.audio.output_alsa_pcm,
             "-f", "S16_LE", "-r", str(self._sr), "-c", "1", "-t", "raw", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        chunk = self._sr * 2 // 4  # ~0.25 s Blöcke
        try:
            pos = 0
            while not self._stop.is_set():
                end = pos + chunk
                proc.stdin.write(self._raw[pos:end])
                pos = end
                if pos >= len(self._raw):
                    pos = 0  # nahtloser Re-Loop (Datei ist selbst loopbar)
        except (BrokenPipeError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.terminate()

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
