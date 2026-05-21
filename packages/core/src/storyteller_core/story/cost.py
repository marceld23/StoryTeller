"""Rough cost tracking + session cap.

Counts tokens from OpenAI usage and estimates USD per config.cost. When
story.cost_cap_usd_per_session is exceeded, `over_cap` becomes True; the
engine then steers toward a calm wrap-up.
"""

from __future__ import annotations

from ..config import Config


class CostTracker:
    def __init__(self, cfg: Config, input_tok: int = 0, output_tok: int = 0,
                 embed_tok: int = 0):
        self.cfg = cfg
        self.input = input_tok
        self.output = output_tok
        self.embed = embed_tok

    def record_chat(self, usage) -> None:
        if usage is not None:
            self.input += getattr(usage, "prompt_tokens", 0) or 0
            self.output += getattr(usage, "completion_tokens", 0) or 0

    def record_embedding(self, usage) -> None:
        if usage is not None:
            self.embed += getattr(usage, "prompt_tokens", 0) or 0

    @property
    def usd(self) -> float:
        c = self.cfg.cost
        return (self.input / 1e6 * c.usd_per_1m_input
                + self.output / 1e6 * c.usd_per_1m_output
                + self.embed / 1e6 * c.usd_per_1m_embedding)

    @property
    def over_cap(self) -> bool:
        cap = self.cfg.story.cost_cap_usd_per_session
        return bool(self.cfg.cost.enforce and cap > 0 and self.usd >= cap)

    def snapshot(self) -> dict:
        return {"input": self.input, "output": self.output, "embed": self.embed}

    @classmethod
    def restore(cls, cfg: Config, d: dict) -> CostTracker:
        d = d or {}
        return cls(cfg, d.get("input", 0), d.get("output", 0), d.get("embed", 0))
