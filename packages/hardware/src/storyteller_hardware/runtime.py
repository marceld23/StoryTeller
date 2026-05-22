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

from storyteller_core.config import Config

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
    """Merge `data` into data/audio.json (keeps untouched keys)."""
    p = audio_override_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_audio_override(cfg), **data}
    p.write_text(json.dumps(merged, ensure_ascii=False, indent=2))


def effective_volume(cfg: Config) -> int:
    """Persisted playback volume (data/audio.json) or the config default."""
    v = load_audio_override(cfg).get("volume")
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return max(0, min(100, int(cfg.audio.default_volume_pct)))


@lru_cache
def _respeaker_present() -> bool:
    """ReSpeaker USB Mic Array v2.0 present? (ALSA card or USB ID)."""
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


def settings_path(cfg: Config):
    return cfg.path("data/settings.json")


def load_settings(cfg: Config) -> dict:
    """Persisted user settings (e.g. {"intro_enabled": bool})."""
    p = settings_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_settings(cfg: Config, data: dict) -> None:
    p = settings_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def model_overrides_path(cfg: Config):
    return cfg.path("data/models.json")


def load_model_overrides(cfg: Config) -> dict:
    """Runtime model override (admin-editable): subset of ModelsCfg fields."""
    p = model_overrides_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_model_overrides(cfg: Config, data: dict) -> None:
    """Merge `data` into data/models.json (keeps untouched keys)."""
    p = model_overrides_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_model_overrides(cfg), **data}
    p.write_text(json.dumps(merged, ensure_ascii=False, indent=2))


def apply_model_overrides(cfg: Config) -> None:
    """Mutate cfg.models in place with values from data/models.json.

    Called once at config load so the admin UI can change models without
    touching config.toml. Unknown / wrong-typed keys are silently ignored.
    """
    ov = load_model_overrides(cfg)
    if not ov:
        return
    for key, val in ov.items():
        if not hasattr(cfg.models, key):
            continue
        try:
            setattr(cfg.models, key, val)
        except Exception:
            continue


def resolve_profile(cfg: Config) -> str:
    """Returns 'pi' or 'pc' (auto-detected if profile=auto)."""
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
