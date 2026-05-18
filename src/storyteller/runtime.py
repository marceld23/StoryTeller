"""Runtime profile detection (Pi vs PC) and backend resolution.

Lets Storyteller run on a normal PC without a Pi/ReSpeaker:
- profile `pi`: Linux + ReSpeaker detected -> ALSA softvol backend, LED ring.
- profile `pc`: anything else -> portable sounddevice backend, no LED.
"""

from __future__ import annotations

import json
import platform
from functools import lru_cache
from pathlib import Path

from .config import Config

_AUDIO_BACKENDS = ("auto", "alsa_softvol", "portable", "pipewire")


def audio_override_path(cfg: Config):
    return cfg.path("data/audio.json")


def load_audio_override(cfg: Config) -> dict:
    """Runtime audio override (admin/voice editable): {backend, pw_sink}."""
    p = audio_override_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_audio_override(cfg: Config, data: dict) -> None:
    p = audio_override_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


@lru_cache
def _respeaker_present() -> bool:
    """ReSpeaker USB Mic Array v2.0 vorhanden? (ALSA-Card oder USB-ID)."""
    try:
        cards = Path("/proc/asound/cards")
        if cards.exists():
            txt = cards.read_text(errors="ignore")
            if "ArrayUAC10" in txt or "ReSpeaker" in txt:
                return True
    except Exception:
        pass
    try:
        for p in Path("/sys/bus/usb/devices").glob("*/idProduct"):
            try:
                pid = p.read_text().strip().lower()
                vid = (p.parent / "idVendor").read_text().strip().lower()
                if vid == "2886" and pid == "0018":
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def resolve_profile(cfg: Config) -> str:
    """Liefert 'pi' oder 'pc' (auto-erkannt, falls profile=auto)."""
    p = (cfg.runtime.profile or "auto").lower()
    if p in ("pi", "pc"):
        return p
    if platform.system() == "Linux" and _respeaker_present():
        return "pi"
    return "pc"


def resolve_backend_name(cfg: Config) -> str:
    """Concrete audio backend. Runtime override (data/audio.json) wins,
    then config.audio.backend, then 'auto' -> by profile."""
    ov = load_audio_override(cfg)
    b = str(ov.get("backend") or cfg.audio.backend or "auto").lower()
    if b in _AUDIO_BACKENDS and b != "auto":
        return b
    return "alsa_softvol" if resolve_profile(cfg) == "pi" else "portable"
