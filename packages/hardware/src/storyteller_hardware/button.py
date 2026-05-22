"""Optional GPIO push-button to interrupt the narration (barge-in).

Uses gpiozero (Pi-only, optional). If the dependency or hardware is missing,
`available` is False and the caller simply runs without a button — exactly
like the wake word. Install on the Pi:  uv pip install gpiozero lgpio

Wiring (Pi 4, BCM numbering): one leg of the button to the configured GPIO
pin, the other leg to GND. With the internal pull-up (default) no resistor is
needed — pressing pulls the pin to ground. See docs/ADMIN_GUIDE.md.
"""

from __future__ import annotations

import logging
import threading

from storyteller_core.config import Config

log = logging.getLogger("storyteller.button")


class InterruptButton:
    """A debounced GPIO button that sets the *armed* Event when pressed.

    The caller `arm(event)`s it right before interruptible playback and
    `disarm()`s it afterwards, so a press only counts while the narrator is
    actually speaking.
    """

    def __init__(self, cfg: Config):
        self.available = False
        self._event: threading.Event | None = None
        self._btn = None
        self._err = ""
        pin = int(getattr(cfg.hardware, "button_pin", 0) or 0)
        if pin <= 0:
            return  # disabled
        try:
            from gpiozero import Button

            self._btn = Button(
                pin,
                pull_up=bool(cfg.hardware.button_pull_up),
                bounce_time=float(cfg.hardware.button_bounce_s),
            )
            self._btn.when_pressed = self._on_press
            self.available = True
            log.info("Interrupt-Taster aktiv an GPIO %d", pin)
        except Exception as exc:  # pragma: no cover - HW/lib-abhängig
            self._err = repr(exc)
            log.info("Interrupt-Taster nicht verfügbar: %s", self._err)

    def arm(self, event: threading.Event) -> None:
        self._event = event

    def disarm(self) -> None:
        self._event = None

    def _on_press(self) -> None:
        ev = self._event
        if ev is not None:
            ev.set()

    def close(self) -> None:
        try:
            if self._btn is not None:
                self._btn.close()
        except Exception:
            pass
