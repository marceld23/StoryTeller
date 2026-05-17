"""Lokale Wake-Word-Erkennung (openWakeWord, Default-Modell).

Default jetzt, später änderbar (config.wakeword.model). openWakeWord hat keine
py3.13-Wheels über pip-Deps -> Installation separat:
  uv pip install --no-deps openwakeword
  uv pip install onnxruntime
Ist openWakeWord nicht verfügbar -> .available == False; der Aufrufer nutzt
dann Push-to-talk (Enter).
"""

from __future__ import annotations

import subprocess

import numpy as np

from ..config import Config

DEFAULT_MODEL = "hey_jarvis"  # mitgeliefertes openWakeWord-Modell (Default)


class WakeWord:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model = None
        self.available = False
        try:
            from openwakeword.model import Model

            name = cfg.wakeword.model or DEFAULT_MODEL
            kw = {"inference_framework": "onnx"}
            if name and not name.endswith((".onnx", ".tflite")):
                kw["wakeword_models"] = [name]
            elif name:
                kw["wakeword_models"] = [name]
            self.model = Model(**kw)
            self.available = True
        except Exception as exc:  # pragma: no cover - install-/hardware-abhängig
            self._err = repr(exc)

    def listen_blocking(self) -> bool:
        """Blockiert bis Wake-Word erkannt. False wenn nicht verfügbar."""
        if not self.available:
            return False
        sr = 16000
        chunk = 1280  # 80 ms @ 16 kHz (openWakeWord-Frame)
        proc = subprocess.Popen(
            ["arecord", "-q", "-D", self.cfg.audio.input_alsa_pcm,
             "-f", "S16_LE", "-r", str(sr), "-c", "1", "-t", "raw"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            while True:
                raw = proc.stdout.read(chunk * 2)
                if not raw:
                    return False
                audio = np.frombuffer(raw, dtype=np.int16)
                scores = self.model.predict(audio)
                if any(s >= self.cfg.wakeword.threshold for s in scores.values()):
                    return True
        finally:
            # Capture-Gerät sicher freigeben, bevor die 6s-Aufnahme öffnet
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                proc.kill()
