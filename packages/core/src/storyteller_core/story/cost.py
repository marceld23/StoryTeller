"""Rough cost tracking + daily cap.

`CostTracker` accumulates per-session usage (chat tokens, embedding tokens,
TTS characters, STT seconds) and computes a USD estimate from the unit
prices in `[cost]`. It is restored from / written to the LangGraph
checkpoint each turn so a service restart does not reset the counter.

Local endpoints (Ollama / XTTS / faster-whisper / local embeddings —
anything where `cfg.models.<role>_endpoint.base_url` is non-empty) are
treated as FREE: the token / character / second counters still rise so
the admin can see throughput, but the USD contribution stays at zero
and the daily cap is never triggered.

`DailyCapExceeded` is the hard-cap signal: when the daily ledger total
hits `cost.daily_cap_usd`, the engine refuses any new turn so the story
is paused (state already on disk) instead of being rushed to a wrap-up.
"""

from __future__ import annotations

from ..config import Config


class DailyCapExceeded(Exception):
    """Raised by the engine when a new turn would exceed the daily cap.

    The current story state is left untouched — the next wake-word
    activation greets the player with the same announcement until an
    admin resets the day.
    """

    def __init__(self, usd_today: float, cap_usd: float):
        super().__init__(
            f"daily cap reached: {usd_today:.4f} USD >= {cap_usd:.4f} USD")
        self.usd_today = float(usd_today)
        self.cap_usd = float(cap_usd)


def is_local_role(cfg: Config, role: str) -> bool:
    """`True` when the endpoint for this role points at a custom (i.e.
    non-OpenAI) base_url — taken to mean "self-hosted, no per-token cost".

    Roles correspond to ModelsCfg attributes: ``story``, ``planner``,
    ``gen``, ``gate``, ``stt``, ``tts``, ``embedding``. Unknown roles or
    missing endpoints default to "remote" (paid).
    """
    ep = getattr(cfg.models, f"{role}_endpoint", None)
    if ep is None:
        return False
    return bool((getattr(ep, "base_url", "") or "").strip())


class CostTracker:
    def __init__(self, cfg: Config, input_tok: int = 0, output_tok: int = 0,
                 embed_tok: int = 0, tts_chars: int = 0,
                 stt_sec: float = 0.0):
        self.cfg = cfg
        self.input = int(input_tok)
        self.output = int(output_tok)
        self.embed = int(embed_tok)
        self.tts_chars = int(tts_chars)
        self.stt_sec = float(stt_sec)

    # --------------- recording (mutates counters, returns USD delta) ---

    def record_chat(self, usage, *, role: str = "story") -> float:
        if usage is None:
            return 0.0
        pin = int(getattr(usage, "prompt_tokens", 0) or 0)
        pout = int(getattr(usage, "completion_tokens", 0) or 0)
        self.input += pin
        self.output += pout
        if is_local_role(self.cfg, role):
            return 0.0
        c = self.cfg.cost
        return (pin / 1e6 * c.usd_per_1m_input
                + pout / 1e6 * c.usd_per_1m_output)

    def record_embedding(self, usage) -> float:
        if usage is None:
            return 0.0
        tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        self.embed += tok
        if is_local_role(self.cfg, "embedding"):
            return 0.0
        return tok / 1e6 * self.cfg.cost.usd_per_1m_embedding

    def record_tts(self, chars: int) -> float:
        chars = max(0, int(chars or 0))
        self.tts_chars += chars
        if is_local_role(self.cfg, "tts"):
            return 0.0
        return chars / 1e6 * self.cfg.cost.usd_per_1m_tts_chars

    def record_stt(self, seconds: float) -> float:
        seconds = max(0.0, float(seconds or 0.0))
        self.stt_sec += seconds
        if is_local_role(self.cfg, "stt"):
            return 0.0
        return seconds / 60.0 * self.cfg.cost.usd_per_minute_stt

    # --------------- derived ----------------------------------------------

    @property
    def usd(self) -> float:
        """Approximate session spend in USD across paid endpoints only."""
        c = self.cfg.cost
        total = 0.0
        if not is_local_role(self.cfg, "story"):
            # Use the narrator/story endpoint as the proxy for chat-side
            # locality; in mixed setups (e.g. local story but cloud
            # planner) the ledger has per-call resolution while this
            # roll-up stays a rough upper bound.
            total += (self.input / 1e6 * c.usd_per_1m_input
                      + self.output / 1e6 * c.usd_per_1m_output)
        if not is_local_role(self.cfg, "embedding"):
            total += self.embed / 1e6 * c.usd_per_1m_embedding
        if not is_local_role(self.cfg, "tts"):
            total += self.tts_chars / 1e6 * c.usd_per_1m_tts_chars
        if not is_local_role(self.cfg, "stt"):
            total += self.stt_sec / 60.0 * c.usd_per_minute_stt
        return total

    # --------------- (de)serialization ------------------------------------

    def snapshot(self) -> dict:
        return {"input": self.input, "output": self.output,
                "embed": self.embed, "tts_chars": self.tts_chars,
                "stt_sec": self.stt_sec}

    @classmethod
    def restore(cls, cfg: Config, d: dict) -> CostTracker:
        d = d or {}
        return cls(cfg,
                   d.get("input", 0), d.get("output", 0), d.get("embed", 0),
                   d.get("tts_chars", 0), d.get("stt_sec", 0.0))
