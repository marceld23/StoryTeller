"""Gemeinsamer OpenAI-Client (aus config/.env)."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import Config


@lru_cache
def _client(api_key: str) -> OpenAI:
    # Latency-sensitive client for the live narration loop.
    # SDK macht automatisch Backoff-Retries bei 408/409/429/5xx + Netzfehlern.
    return OpenAI(api_key=api_key, max_retries=5, timeout=30.0)


@lru_cache
def _gen_client(api_key: str) -> OpenAI:
    # World/content generation: big-model JSON-mode calls take 60-90 s.
    # Longer per-call timeout, fewer retries -> no 5x silent stack-up.
    return OpenAI(api_key=api_key, max_retries=1, timeout=180.0)


def get_client(cfg: Config) -> OpenAI:
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt (.env).")
    return _client(cfg.openai_api_key)


def get_gen_client(cfg: Config) -> OpenAI:
    """Client for slow generator/suggestion calls (admin only)."""
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt (.env).")
    return _gen_client(cfg.openai_api_key)
