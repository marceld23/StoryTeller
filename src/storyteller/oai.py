"""Gemeinsamer OpenAI-Client (aus config/.env)."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import Config


@lru_cache
def _client(api_key: str) -> OpenAI:
    # SDK macht automatisch Backoff-Retries bei 408/409/429/5xx + Netzfehlern.
    return OpenAI(api_key=api_key, max_retries=5, timeout=30.0)


def get_client(cfg: Config) -> OpenAI:
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt (.env).")
    return _client(cfg.openai_api_key)
