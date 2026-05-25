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
FRAME_LEN = 1280  # 80 ms @ 16 kHz (openWakeWord frame)
# Number of frames to feed the model AT THE START of each listen_blocking
# call WITHOUT checking the score. Two purposes:
#   1) Flush the openWakeWord feature buffer of stale audio left over
#      from the previous mic close (the player's "Nein", the TTS tail of
#      a just-played prompt). Without this, the FIRST predict() of the
#      new stream can fire on residual phonemes from the last second
#      before the previous return — surfacing as "the question loops
#      after I said no" even though no real wake-word was spoken.
#   2) Give room reverberation time to die. 6 frames × 80 ms = 480 ms.
_WARMUP_FRAMES = 6
# Require this many consecutive frames at/above threshold before firing.
# Single-frame trigger had a measurable false-positive rate on real-world
# audio (room noise spikes, distant speech). 2 frames = ~160 ms of
# continuous match — still well under human reaction time.
_CONSECUTIVE_HITS = 2


class WakeWord:
    def __init__(self, cfg: Config, backend):
        self.cfg = cfg
        self.backend = backend
        self.model = None
        self.available = False
        try:
            from openwakeword.model import Model
            from storyteller_core.i18n import norm

            loc = norm(cfg.general.locale)
            name = (getattr(cfg.wakeword, f"model_{loc}", "")
                    or cfg.wakeword.model or DEFAULT_MODEL)
            self.model = Model(inference_framework="onnx",
                               wakeword_models=[name])
            self.available = True
        except Exception as exc:  # pragma: no cover - install-/HW-dependent
            self._err = repr(exc)

    def _reset_model_state(self) -> None:
        """Drop the model's internal feature buffer + prediction history.

        Without this, residual audio from BEFORE the previous return
        sits in the feature window across listen_blocking() calls and
        can trigger the very first new predict() — surfacing as the
        "after-no question loops" bug. The exact reset API varies by
        openWakeWord version; we try the cheap, in-place options that
        DO exist across recent releases. Best-effort — never raises.
        """
        m = self.model
        if m is None:
            return
        # openWakeWord 0.6+ exposes a `reset` method that clears
        # `prediction_buffer` + zeros the internal feature ringbuffer.
        try:
            reset_fn = getattr(m, "reset", None)
            if callable(reset_fn):
                reset_fn()
                return
        except Exception:
            pass
        # Fallback: clear the visible state we know about. Internal
        # streaming buffers in onnxruntime layers will still hold a
        # frame or two, which the warm-up loop below handles.
        try:
            if hasattr(m, "prediction_buffer"):
                for k in list(m.prediction_buffer.keys()):
                    try:
                        m.prediction_buffer[k].clear()
                    except Exception:
                        m.prediction_buffer[k] = type(
                            m.prediction_buffer[k])()
        except Exception:
            pass

    def listen_blocking(self) -> bool:
        """Block until the wake word is detected.

        Resilient: if the mic stream ends (arecord closed) it re-opens and
        keeps listening, so it truly blocks. Returns False only if the model
        is unavailable or the mic keeps failing (caller then backs off).

        Two safety nets against the "phantom trigger right after the
        previous return" bug (visible as "möchtest du loslegen?" looping
        even when the player clearly said no): a model-state reset at
        the start of each call, plus a warm-up window where the first
        `_WARMUP_FRAMES` frames feed the model but their scores are
        ignored. After warm-up we additionally require the score to
        cross the threshold in `_CONSECUTIVE_HITS` frames in a row, so
        a single noisy spike can't fire.
        """
        if not self.available:
            return False
        import time

        threshold = float(self.cfg.wakeword.threshold)
        fails = 0
        while fails < 30:
            stop = threading.Event()
            got_any = False
            # Fresh stream → fresh model state. Anything left from the
            # previous call (the player's "nein", the TTS tail of a
            # prompt picked up via speaker→mic echo) is gone.
            self._reset_model_state()
            frames_seen = 0
            hits_in_a_row = 0
            try:
                for frame in self.backend.mic_frames(16000, FRAME_LEN, stop):
                    got_any = True
                    frames_seen += 1
                    scores = self.model.predict(frame)
                    if frames_seen <= _WARMUP_FRAMES:
                        # Feed the model so the buffer fills with fresh
                        # audio, but don't act on the score yet.
                        hits_in_a_row = 0
                        continue
                    if any(s >= threshold for s in scores.values()):
                        hits_in_a_row += 1
                        if hits_in_a_row >= _CONSECUTIVE_HITS:
                            return True
                    else:
                        hits_in_a_row = 0
                fails = 0 if got_any else fails + 1
                time.sleep(0.3)
            except Exception:
                fails += 1
                time.sleep(0.5)
            finally:
                stop.set()
        return False
