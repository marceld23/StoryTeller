"""Voice FX: light reverb / optional distortion (Spotify pedalboard).

Params from config.fx, overridable per world via World.fx_preset.
Install: `uv sync --extra audiofx`. If pedalboard is missing -> pass-through.
"""

from __future__ import annotations

import numpy as np

from storyteller_core.config import Config


class VoiceFX:
    def __init__(self, cfg: Config, fx_preset=None):
        self.cfg = cfg
        self._board = None
        f = cfg.fx
        if not f.enabled:
            return
        try:
            from pedalboard import Distortion, Pedalboard, Reverb
        except Exception:
            return  # pedalboard nicht installiert -> Pass-through

        def ov(attr, default):
            v = getattr(fx_preset, attr, None) if fx_preset else None
            return default if v is None else v

        chain = [
            Reverb(
                room_size=ov("reverb_room_size", f.reverb_room_size),
                damping=ov("reverb_damping", f.reverb_damping),
                wet_level=ov("reverb_wet_level", f.reverb_wet_level),
                dry_level=ov("reverb_dry_level", f.reverb_dry_level),
            )
        ]
        drive = ov("distortion_drive_db", f.distortion_drive_db)
        if drive and drive > 0:
            chain.append(Distortion(drive_db=float(drive)))
        self._board = Pedalboard(chain)

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if self._board is None:
            return audio
        return self._board(audio.astype(np.float32), sample_rate)
