"""OpenAI (and OpenAI-compatible) clients, one per purpose.

Each purpose (story / planner / gen chat, plus STT / TTS / embeddings) can
point at its own endpoint via `config.models.<purpose>_endpoint`
(base_url + api_key). Empty endpoint = OpenAI defaults (api.openai.com +
OPENAI_API_KEY). Moderation always uses the default OpenAI endpoint.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import Config, Endpoint

_VALID_EFFORTS = {"low", "medium", "high", "xhigh"}


def reasoning_kwargs(cfg: Config, role: str) -> dict:
    """Build the ``reasoning_effort`` kwarg for ``chat.completions.create``
    based on the role's configured effort.

    Returns ``{"reasoning_effort": "<value>"}`` for valid non-"none"
    settings, else ``{}``. "none" / "" / unknown values produce no kwarg
    so older models and OpenAI-compatible local servers (Ollama, vLLM)
    that don't know the field stay untouched. The single source of
    truth for the per-role default lives in ``ModelsCfg``.
    """
    e = cfg.models.reasoning_effort_for(role)
    if e in _VALID_EFFORTS:
        return {"reasoning_effort": e}
    return {}


def chat_extras(
    cfg: Config,
    role: str,
    *,
    temperature: float | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
) -> dict:
    """Sampling kwargs to merge into ``chat.completions.create``.

    OpenAI reasoning models (gpt-5.x with ``reasoning_effort`` != none) only
    accept the default ``temperature`` / ``top_p`` / ``frequency_penalty``
    / ``presence_penalty`` — passing a custom value returns HTTP 400. So
    when reasoning is active for this role, we forward ONLY
    ``reasoning_effort`` and DROP every sampling knob. When reasoning is
    off we forward the non-None / non-zero values the caller passed.

    Use this helper EVERYWHERE you'd otherwise pass
    ``temperature=cfg.models.<x>_temperature, **reasoning_kwargs(...)``.
    """
    effort = cfg.models.reasoning_effort_for(role)
    if effort in _VALID_EFFORTS:
        return {"reasoning_effort": effort}
    out: dict = {}
    if temperature is not None:
        out["temperature"] = float(temperature)
    if frequency_penalty:
        out["frequency_penalty"] = float(frequency_penalty)
    if presence_penalty:
        out["presence_penalty"] = float(presence_penalty)
    return out


@lru_cache
def _make(api_key: str, base_url: str, timeout: float, max_retries: int) -> OpenAI:
    kwargs: dict = {"api_key": api_key, "timeout": timeout,
                    "max_retries": max_retries}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _resolve(cfg: Config, ep: Endpoint | None) -> tuple[str, str]:
    """(api_key, base_url) for an endpoint, falling back to OpenAI + the
    .env key. A custom base_url without a key uses a dummy bearer (many
    local servers accept any)."""
    base = (ep.base_url or "").strip() if ep else ""
    key = ((ep.api_key or "").strip() if ep else "") or cfg.openai_api_key
    if not key and not base:
        raise RuntimeError("OPENAI_API_KEY fehlt (.env) und keine eigene "
                           "base_url gesetzt.")
    return (key or "not-needed"), base


def _ep(cfg: Config, name: str) -> Endpoint | None:
    return getattr(cfg.models, name, None)


# -- default OpenAI client (moderation + generic) -------------------------

def get_client(cfg: Config) -> OpenAI:
    key, base = _resolve(cfg, None)
    return _make(key, base, 30.0, 5)


# -- chat / generation (story | planner | gen) ----------------------------

def get_chat_client(cfg: Config, role: str = "story") -> OpenAI:
    ep = _ep(cfg, f"{role}_endpoint")
    # Per-role endpoint fallback: if the role has no explicit endpoint
    # (default empty), fall back the way the model name does — planner ⇒
    # story; gate ⇒ planner ⇒ story. This mirrors the .planner / .gate
    # @property fallback on ModelsCfg and keeps custom-LLM setups working
    # without forcing the admin to re-paste the same URL three times.
    if role in ("planner", "gate") and ep is not None and not (ep.base_url or "").strip():
        ep = _ep(cfg, "planner_endpoint") if role == "gate" else None
        if ep is None or not (ep.base_url or "").strip():
            ep = _ep(cfg, "story_endpoint")
    key, base = _resolve(cfg, ep)
    # gen does slow big-model JSON work; the gate runs on the per-turn hot
    # path and ideally points at a small/fast model (gpt-5.4-mini, qwen2.5:7b
    # …) — but in single-GPU local setups it shares the narrator's big model,
    # so the timeout has to be generous enough that the curator doesn't fail
    # silently every turn. The others are latency-sensitive defaults.
    if role == "gen":
        timeout, retries = 180.0, 1
    elif role == "gate":
        timeout, retries = 60.0, 1
    else:
        timeout, retries = 30.0, 5
    return _make(key, base, timeout, retries)


def get_gen_client(cfg: Config) -> OpenAI:
    """Back-compat alias for the world-generation chat client."""
    return get_chat_client(cfg, "gen")


# -- speech / embeddings ---------------------------------------------------

def get_stt_client(cfg: Config) -> OpenAI:
    key, base = _resolve(cfg, _ep(cfg, "stt_endpoint"))
    return _make(key, base, 30.0, 5)


def get_tts_client(cfg: Config) -> OpenAI:
    key, base = _resolve(cfg, _ep(cfg, "tts_endpoint"))
    return _make(key, base, 30.0, 5)


def get_embedding_client(cfg: Config) -> OpenAI:
    key, base = _resolve(cfg, _ep(cfg, "embedding_endpoint"))
    return _make(key, base, 30.0, 5)
