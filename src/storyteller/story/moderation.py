"""Input moderation (OpenAI Moderation API, omni-moderation-latest).

The player's input is checked BEFORE the story LLM answers. Per-category
thresholds live in data/moderation.json (admin-editable) and override the
config defaults. Fails OPEN on API error (a moderation hiccup must not break
the game), but a flagged category at/above its threshold blocks the turn.
"""

from __future__ import annotations

import json

from ..config import Config
from ..oai import get_client


def overrides_path(cfg: Config):
    return cfg.path("data/moderation.json")


def load_overrides(cfg: Config) -> dict:
    p = overrides_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_overrides(cfg: Config, data: dict) -> None:
    p = overrides_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


class Moderator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        ov = load_overrides(cfg)
        self.enabled = bool(ov.get("enabled", cfg.moderation.enabled))
        self.default = float(ov.get("default",
                                    cfg.moderation.default_threshold))
        self.cats = {str(k): float(v)
                     for k, v in (ov.get("categories") or {}).items()}

    def threshold(self, category: str) -> float:
        return self.cats.get(category, self.default)

    def check(self, text: str) -> tuple[bool, list[dict], dict]:
        """Returns (ok, flagged[{category,score,threshold}], all_scores)."""
        if not self.enabled or not (text or "").strip():
            return True, [], {}
        try:
            r = get_client(self.cfg).moderations.create(
                model=self.cfg.moderation.model, input=text)
            res = r.results[0]
            cs = res.category_scores
            scores = cs.model_dump() if hasattr(cs, "model_dump") else dict(cs)
        except Exception:
            return True, [], {}  # fail-open: never break play on API error
        flagged = [
            {"category": c, "score": round(float(s), 4),
             "threshold": self.threshold(c)}
            for c, s in scores.items()
            if s is not None and float(s) >= self.threshold(c)
        ]
        alls = {c: round(float(s or 0.0), 4) for c, s in scores.items()}
        return (len(flagged) == 0), flagged, alls
