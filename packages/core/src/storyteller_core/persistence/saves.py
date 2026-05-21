"""Save games: world id, blueprint index, short-term memory, known facts."""

from __future__ import annotations

import json
import re
import time

from ..config import Config


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or f"save_{int(time.time())}"


class SaveManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dir = cfg.path(cfg.paths.saves_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, state: dict) -> str:
        p = self.dir / f"{_slug(name)}.json"
        state = {**state, "_name": name, "_saved_at": time.time()}
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        return str(p)

    def load(self, name: str) -> dict:
        p = self.dir / f"{_slug(name)}.json"
        if not p.exists():
            raise FileNotFoundError(name)
        return json.loads(p.read_text())

    def list_saves(self) -> list[str]:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text()).get("_name", p.stem))
            except Exception:
                out.append(p.stem)
        return out

    def latest(self) -> str | None:
        files = sorted(self.dir.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        try:
            return json.loads(files[0].read_text()).get("_name", files[0].stem)
        except Exception:
            return files[0].stem
