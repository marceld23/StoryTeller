"""Input moderation (OpenAI Moderation API, omni-moderation-latest).

The player's input is checked BEFORE the story LLM answers. Per-category
thresholds live in data/moderation.json (admin-editable) and override the
config defaults. Fails OPEN on API error (a moderation hiccup must not break
the game), but a flagged category at/above its threshold blocks the turn.
"""

from __future__ import annotations

import json
import logging

from ..config import Config
from ..oai import get_client

log = logging.getLogger("storyteller.moderation")


def overrides_path(cfg: Config):
    return cfg.path("data/moderation.json")


def load_overrides(cfg: Config) -> dict:
    p = overrides_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as exc:
            log.warning("moderation overrides unreadable (%s): %r", p, exc)
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
        # Layered thresholds: code-level baseline per category (from
        # cfg.moderation.category_thresholds, tuned for adventure
        # narration) → admin overrides from data/moderation.json on top.
        baseline = {str(k): float(v)
                    for k, v in (cfg.moderation.category_thresholds or {}).items()}
        overrides = {str(k): float(v)
                     for k, v in (ov.get("categories") or {}).items()}
        self.cats = {**baseline, **overrides}

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
        except Exception as exc:
            # fail-open: never break play on an API hiccup, but make it visible
            log.warning("moderation check failed, allowing turn: %r", exc)
            return True, [], {}
        # Cost ledger: omni-moderation-latest is currently FREE in OpenAI
        # pricing, so the default rate (cfg.cost.usd_per_1m_moderation_chars
        # = 0.0) keeps the ledger silent. If OpenAI ever starts charging,
        # set the rate and the ledger picks it up — no other code change.
        chars = len(text or "")
        rate = float(getattr(self.cfg.cost,
                              "usd_per_1m_moderation_chars", 0.0) or 0.0)
        usd = chars / 1e6 * rate if (chars and rate) else 0.0
        if usd > 0:
            from .ledger import CostLedger
            try:
                CostLedger(self.cfg).record(
                    kind="moderation", usd=usd,
                    model=self.cfg.moderation.model)
            except Exception as ledger_exc:                # pragma: no cover
                log.warning("moderation ledger write failed: %r",
                            ledger_exc)
        flagged = [
            {"category": c, "score": round(float(s), 4),
             "threshold": self.threshold(c)}
            for c, s in scores.items()
            if s is not None and float(s) >= self.threshold(c)
        ]
        alls = {c: round(float(s or 0.0), 4) for c, s in scores.items()}
        return (len(flagged) == 0), flagged, alls
