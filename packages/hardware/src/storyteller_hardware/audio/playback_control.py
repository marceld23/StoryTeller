"""Process-level pause/resume + abort for the currently playing audio.

The audio backend opens an `aplay` / `pw-play` subprocess for each
narration chunk and for the wait-loop ambient. The interrupt button
needs to be able to *pause* that subprocess (SIGSTOP) and *resume* it
(SIGCONT) without aborting it — and the existing barge-in path needs to
terminate it. Both paths go through this single registry so there is
exactly one place that knows about the live playback process at any
time.

Thread-safe: pause/resume/clear/set are all guarded by the same lock.
The registry stores at most ONE process; the player guarantees that
playback runs serially (`max_workers=1` for XTTS, sequential `aplay`
calls in `play_stream`).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading

log = logging.getLogger("storyteller.playback")


class PlaybackControl:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._paused = False

    # --- lifecycle (called by the backend) -------------------------------
    def set_proc(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._proc = proc
            self._paused = False

    def clear_proc(self) -> None:
        with self._lock:
            self._proc = None
            self._paused = False

    # --- queries ---------------------------------------------------------
    def is_playing(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def is_paused(self) -> bool:
        return self._paused

    # --- control (called by the button) ----------------------------------
    def pause(self) -> bool:
        """SIGSTOP the active proc. No-op if nothing is playing / already
        paused. Returns True if a pause actually happened."""
        with self._lock:
            if (self._proc is None
                    or self._proc.poll() is not None
                    or self._paused):
                return False
            try:
                os.kill(self._proc.pid, signal.SIGSTOP)
                self._paused = True
                log.info("playback paused (pid=%d)", self._proc.pid)
                return True
            except OSError as exc:
                log.warning("playback pause failed: %r", exc)
                return False

    def resume(self) -> bool:
        with self._lock:
            if (self._proc is None
                    or self._proc.poll() is not None
                    or not self._paused):
                return False
            try:
                os.kill(self._proc.pid, signal.SIGCONT)
                self._paused = False
                log.info("playback resumed (pid=%d)", self._proc.pid)
                return True
            except OSError as exc:
                log.warning("playback resume failed: %r", exc)
                return False

    def toggle(self) -> str:
        """Convenience for a single button press: pause if playing,
        resume if paused, no-op if nothing. Returns 'paused' | 'resumed'
        | 'noop'."""
        if self.resume():
            return "resumed"
        if self.pause():
            return "paused"
        return "noop"


# Module-level singleton — the backend registers/clears, the button reads.
PLAYBACK = PlaybackControl()
