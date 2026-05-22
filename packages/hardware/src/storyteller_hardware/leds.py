"""High-level LED ring control with graceful fallback.

States: idle / wake / listen / think / speak / error.
No device / pyusb missing / no permission -> no-op (app still runs; PC mode).
udev rule: scripts/setup_system.sh (60-respeaker.rules).
"""

from __future__ import annotations

VID = 0x2886
PID = 0x0018


class LedRing:
    def __init__(self) -> None:
        self._ring = None
        self.available = False
        try:
            from .pixel_ring_v2 import find  # vendored

            self._ring = find(vid=VID, pid=PID)
            if self._ring is not None:
                self._ring.set_brightness(10)
                self.available = True
        except Exception as exc:  # pragma: no cover - hardware/permission dependent
            self._last_error = repr(exc)

    def _safe(self, method: str, *args) -> None:
        if not self.available:
            return
        try:
            getattr(self._ring, method)(*args)
        except Exception:
            pass

    # Semantic states -> pixel_ring patterns
    def idle(self) -> None: self._safe("off")
    def wake(self) -> None: self._safe("wakeup")
    def listen(self) -> None: self._safe("listen")
    def think(self) -> None: self._safe("think")
    def speak(self) -> None: self._safe("speak")
    def error(self) -> None: self._safe("set_color", 0xFF0000)
    def off(self) -> None: self._safe("off")
