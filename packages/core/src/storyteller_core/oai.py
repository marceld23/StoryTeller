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
    key, base = _resolve(cfg, _ep(cfg, f"{role}_endpoint"))
    # gen does slow big-model JSON work; the others are latency-sensitive.
    timeout, retries = (180.0, 1) if role == "gen" else (30.0, 5)
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
