"""High-level LED ring control with graceful fallback.

States: idle / wake / listen / think / speak / error.
No device / pyusb missing / no permission -> no-op (app still runs; PC mode).
udev rule: scripts/setup_system.sh (60-respeaker.rules).
"""

from __future__ import annotations

import math
import threading
import time

VID = 0x2886
PID = 0x0018

# A clear "I'm listening — talk now" cue: the ring glows green up and fades
# back down in a slow breathing rhythm. The vendor firmware has no built-in
# breathing pattern, so we animate it from a background thread by holding
# the colour at green and modulating set_brightness.
_LISTEN_COLOR = 0x00FF00      # pure green
_LISTEN_PERIOD_S = 1.8        # full breath cycle (glow up + fade down)
_LISTEN_FPS = 12              # USB-friendly tick rate
_LISTEN_BRIGHT_MIN = 2        # never fully off — keeps the ring "alive"
_LISTEN_BRIGHT_MAX = 20       # firmware default is 10, 20 is a clear "on"
_DEFAULT_BRIGHTNESS = 10


class LedRing:
    def __init__(self) -> None:
        self._ring = None
        self.available = False
        self._lock = threading.Lock()         # serialises USB control transfers
        self._anim_stop = threading.Event()
        self._anim_thread: threading.Thread | None = None
        try:
            from .pixel_ring_v2 import find  # vendored

            self._ring = find(vid=VID, pid=PID)
            if self._ring is not None:
                self._ring.set_brightness(_DEFAULT_BRIGHTNESS)
                self.available = True
        except Exception as exc:  # pragma: no cover - hardware/permission dependent
            self._last_error = repr(exc)

    # --- internal helpers ------------------------------------------------
    def _safe(self, method: str, *args) -> None:
        if not self.available:
            return
        with self._lock:
            try:
                getattr(self._ring, method)(*args)
            except Exception:
                pass

    def _stop_anim(self) -> None:
        """Halt any running breathing animation before the next state."""
        if self._anim_thread is not None and self._anim_thread.is_alive():
            self._anim_stop.set()
            self._anim_thread.join(timeout=0.5)
        self._anim_thread = None

    def _start_anim(self, target) -> None:
        self._stop_anim()
        self._anim_stop = threading.Event()
        t = threading.Thread(target=target, daemon=True)
        self._anim_thread = t
        t.start()

    def _breathe_green(self) -> None:
        """Run until _anim_stop: hold the ring green, pulse the brightness."""
        # Set the colour once; afterwards we only push brightness changes —
        # cheap and avoids fighting the firmware patterns.
        self._safe("set_color", _LISTEN_COLOR)
        period = _LISTEN_PERIOD_S
        tick = 1.0 / _LISTEN_FPS
        span = _LISTEN_BRIGHT_MAX - _LISTEN_BRIGHT_MIN
        t0 = time.monotonic()
        try:
            while not self._anim_stop.is_set():
                phase = (time.monotonic() - t0) * 2 * math.pi / period
                # 0.5 * (1 + sin) goes 0..1 — bright at the top of the breath
                level = int(_LISTEN_BRIGHT_MIN + span * 0.5 * (1 + math.sin(phase)))
                self._safe("set_brightness", level)
                if self._anim_stop.wait(tick):
                    break
        finally:
            self._safe("set_brightness", _DEFAULT_BRIGHTNESS)

    # --- semantic states -> pixel_ring patterns --------------------------
    def idle(self) -> None:
        self._stop_anim()
        self._safe("off")

    def wake(self) -> None:
        self._stop_anim()
        self._safe("wakeup")

    def listen(self) -> None:
        """Green breathing pulse: signals "I'm listening — talk now"."""
        if not self.available:
            return
        self._start_anim(self._breathe_green)

    def think(self) -> None:
        self._stop_anim()
        self._safe("think")

    def speak(self) -> None:
        self._stop_anim()
        self._safe("speak")

    def error(self) -> None:
        self._stop_anim()
        self._safe("set_color", 0xFF0000)

    def off(self) -> None:
        self._stop_anim()
        self._safe("off")
