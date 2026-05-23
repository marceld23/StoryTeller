"""Optional GPIO push-buttons.

Two roles ship out of the box, both off by default:

- **interrupt_button** — short press: pause / resume the current
  narration (SIGSTOP / SIGCONT on the live ``aplay``); long press: open
  the spoken system menu.
- **shutdown_button** — short press: announce "Spielstand gespeichert"
  (every turn is auto-checkpointed already, so this is just feedback);
  long press: say goodbye and shut the Pi down.

Both are driven by the same ``GpioButton`` class. The class is hardware-
optional: if ``gpiozero``/``lgpio`` aren't installed, or the configured
pin can't be claimed, ``available`` is False and the app keeps running
without it — exactly like the wake word.

Wiring: button between the configured BCM pin and any GND pin. With the
internal pull-up (default) no external resistor is needed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from storyteller_core.config import Config

log = logging.getLogger("storyteller.button")


class GpioButton:
    """A single push-button with short-press and long-press callbacks.

    Reads its config from ``cfg.hardware`` using a role-specific prefix
    (``interrupt_button_*`` or ``shutdown_button_*``). Disabled by default
    (both ``*_enabled`` are False); set ``enabled = true`` + a valid pin
    to activate.
    """

    def __init__(self, cfg: Config, role: str):
        self.role = role
        self.available = False
        self._btn = None
        self._err = ""
        self._on_short: Callable[[], None] | None = None
        self._on_long: Callable[[], None] | None = None
        self._held = False

        prefix = f"{role}_button_"
        if not bool(getattr(cfg.hardware, prefix + "enabled", False)):
            return
        pin = int(getattr(cfg.hardware, prefix + "pin", 0) or 0)
        if pin <= 0:
            log.warning("%senabled=true but pin<=0 — ignored", prefix)
            return

        try:
            from gpiozero import Button

            self._btn = Button(
                pin,
                pull_up=bool(getattr(cfg.hardware, prefix + "pull_up", True)),
                bounce_time=float(getattr(cfg.hardware, prefix + "bounce_s",
                                          0.08)),
                hold_time=float(getattr(cfg.hardware, prefix + "long_press_s",
                                        2.0)),
            )
            self._btn.when_pressed = self._on_press
            self._btn.when_held = self._on_held
            self._btn.when_released = self._on_release
            self.available = True
            log.info("%s aktiv an GPIO %d (long_press=%.1fs)",
                     role, pin,
                     float(getattr(cfg.hardware, prefix + "long_press_s",
                                   2.0)))
        except Exception as exc:  # pragma: no cover - HW/lib-abhängig
            self._err = repr(exc)
            log.info("%s nicht verfügbar: %s", role, self._err)

    # --- public API ----------------------------------------------------
    def set_callbacks(self, on_short: Callable[[], None] | None = None,
                      on_long: Callable[[], None] | None = None) -> None:
        self._on_short = on_short
        self._on_long = on_long

    def close(self) -> None:
        try:
            if self._btn is not None:
                self._btn.close()
        except Exception:
            pass

    # --- gpiozero event handlers ---------------------------------------
    def _on_press(self) -> None:
        # Reset the "long press already fired" flag at the start of each
        # press; on_release decides which callback to fire.
        self._held = False

    def _on_held(self) -> None:
        # Fires once when hold_time is reached; mark held so on_release
        # doesn't fall through to the short-press callback.
        self._held = True
        cb = self._on_long
        if cb is None:
            return
        try:
            cb()
        except Exception as exc:
            log.warning("%s long-press handler failed: %r", self.role, exc)

    def _on_release(self) -> None:
        if self._held:
            # Long-press already handled in `_on_held`.
            self._held = False
            return
        cb = self._on_short
        if cb is None:
            return
        try:
            cb()
        except Exception as exc:
            log.warning("%s short-press handler failed: %r", self.role, exc)


# Back-compat alias for the previous import surface.
InterruptButton = GpioButton
