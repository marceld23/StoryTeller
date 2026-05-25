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


# Known paid-cloud endpoints actually wired into Storyteller. Calls
# hitting these hosts MUST be cost-tracked even though they have a
# non-empty base_url — otherwise the OpenRouter setup would record
# every call as 0 USD and silently disable the daily cap.
#
# Storyteller does NOT have a direct Anthropic or Google integration;
# those models are reached via OpenRouter and so are covered by the
# `openrouter.ai` entry below. If a direct integration is added later,
# add the matching host(s) here.
_PAID_CLOUD_HOSTS: set[str] = {
    "api.openai.com",
    "openrouter.ai",
}
# Suffix matches catch regional / shard variants (e.g. eu.openai.com).
_PAID_CLOUD_HOST_SUFFIXES: tuple[str, ...] = (
    ".openai.com", ".openai.azure.com",
    ".openrouter.ai",
)


def _host_of(base_url: str) -> str:
    if not base_url:
        return ""
    from urllib.parse import urlparse
    return (urlparse(base_url).hostname or "").lower()


def is_paid_cloud(base_url: str) -> bool:
    """True if `base_url` points at a known commercial inference host.
    These calls are billed by the provider, so they MUST cost-track
    regardless of having a non-empty base_url."""
    host = _host_of(base_url)
    if not host:
        return False
    if host in _PAID_CLOUD_HOSTS:
        return True
    return any(host.endswith(suf) for suf in _PAID_CLOUD_HOST_SUFFIXES)


def is_local_role(cfg: Config, role: str) -> bool:
    """`True` when the endpoint for this role is a self-hosted server
    (Ollama / vLLM / XTTS / faster-whisper on the LAN, etc.) — calls
    there are taken to have no per-token cost.

    Decision:
      * Empty base_url → OpenAI default → paid → False.
      * base_url on OpenAI or OpenRouter → paid → False.
      * Any other base_url → assumed self-hosted → True.

    Roles correspond to ModelsCfg attributes: ``story``, ``planner``,
    ``gen``, ``gate``, ``stt``, ``tts``, ``embedding``. Unknown roles
    or missing endpoints default to "remote" (paid).
    """
    ep = getattr(cfg.models, f"{role}_endpoint", None)
    if ep is None:
        return False
    base = (getattr(ep, "base_url", "") or "").strip()
    if not base:
        return False               # OpenAI default = paid
    if is_paid_cloud(base):
        return False               # OpenRouter = paid
    return True                    # everything else: self-hosted = free


def chat_unit_prices(cfg: Config, model: str | None) -> tuple[float, float]:
    """Resolve (input_price, output_price) per 1M tokens for a chat
    model. Looks the model up in `cfg.cost.model_prices` first; falls
    back to the global `usd_per_1m_input` / `_output`. Missing or
    malformed entries silently fall through to the global default —
    bad data shouldn't crash a turn."""
    table = getattr(cfg.cost, "model_prices", None) or {}
    entry = table.get(model) if model else None
    if isinstance(entry, dict):
        pin = entry.get("input")
        pout = entry.get("output")
        if isinstance(pin, (int, float)) and isinstance(pout, (int, float)):
            return float(pin), float(pout)
    return float(cfg.cost.usd_per_1m_input), float(cfg.cost.usd_per_1m_output)


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

    def record_chat(self, usage, *, role: str = "story",
                    model: str | None = None) -> float:
        if usage is None:
            return 0.0
        pin = int(getattr(usage, "prompt_tokens", 0) or 0)
        pout = int(getattr(usage, "completion_tokens", 0) or 0)
        self.input += pin
        self.output += pout
        if is_local_role(self.cfg, role):
            return 0.0
        in_price, out_price = chat_unit_prices(self.cfg, model)
        return pin / 1e6 * in_price + pout / 1e6 * out_price

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
        """Approximate session spend in USD across paid endpoints only.
        For per-call accuracy use the ledger (data/cost.jsonl) — this
        roll-up aggregates input/output tokens across whatever chat
        model touched the session and prices them with the narrator's
        model rate as a proxy."""
        c = self.cfg.cost
        total = 0.0
        if not is_local_role(self.cfg, "story"):
            # Use the narrator's model price (looked up in
            # cfg.cost.model_prices) as the chat-side proxy. In a mixed
            # setup the ledger keeps per-call accuracy; this property is
            # a rough running tally.
            in_price, out_price = chat_unit_prices(
                self.cfg, getattr(self.cfg.models, "story_llm", None))
            total += (self.input / 1e6 * in_price
                      + self.output / 1e6 * out_price)
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
