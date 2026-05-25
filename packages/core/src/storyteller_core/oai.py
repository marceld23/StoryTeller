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


def _endpoint_for_role(cfg: Config, role: str) -> Endpoint | None:
    """Pick the Endpoint a chat role actually talks to, mirroring the
    fallback chain in get_chat_client (gate → planner → story). Used
    by chat_extras to decide which provider's reasoning wire format
    to emit."""
    ep = _ep(cfg, f"{role}_endpoint")
    if role in ("planner", "gate") and ep is not None and not (ep.base_url or "").strip():
        if role == "gate":
            ep = _ep(cfg, "planner_endpoint")
        if ep is None or not (ep.base_url or "").strip():
            ep = _ep(cfg, "story_endpoint")
    return ep


def chat_extras(
    cfg: Config,
    role: str,
    *,
    temperature: float | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    tools: bool = False,
) -> dict:
    """Sampling kwargs to merge into ``chat.completions.create``.

    Two OpenAI constraints to navigate at once:
      * Reasoning models (gpt-5.x with ``reasoning_effort`` != none) only
        accept the default ``temperature`` / ``top_p`` /
        ``frequency_penalty`` / ``presence_penalty`` — any custom value
        returns HTTP 400.
      * ``/v1/chat/completions`` does NOT support ``tools=`` together
        with ``reasoning_effort`` for gpt-5.x; that combination returns
        "Function tools with reasoning_effort are not supported for
        gpt-5.4 in /v1/chat/completions. Please use /v1/responses
        instead." So when the caller will be passing function tools we
        MUST suppress reasoning_effort, and instead forward normal
        sampling knobs (temperature / penalties).

    Plus one provider quirk: OpenRouter's chat completions endpoint
    expects the reasoning knob in NESTED form (``reasoning: {effort:
    "<v>"}``), not OpenAI's flat ``reasoning_effort``. We auto-detect
    the route from the role's endpoint base_url and emit the right
    shape so the same per-role *_reasoning_effort settings work on
    either backend.

    Behaviour:
      * tools=False + reasoning active + OpenAI/local route
            -> {"reasoning_effort": "<v>"}
      * tools=False + reasoning active + OpenRouter route
            -> {"reasoning": {"effort": "<v>"}}
      * tools=False + reasoning off
            -> {"temperature": …, plus non-zero penalties}
      * tools=True (any reasoning)
            -> {"temperature": …, plus non-zero penalties}
               (reasoning dropped — tools+reasoning is unsupported on
               chat completions for gpt-5.x; OpenRouter passes tools
               with reasoning for some providers but to keep behaviour
               uniform we still drop reasoning when tools are present.)
    """
    effort = cfg.models.reasoning_effort_for(role)
    if effort in _VALID_EFFORTS and not tools:
        ep = _endpoint_for_role(cfg, role)
        if ep is not None and _is_openrouter(ep.base_url):
            return {"reasoning": {"effort": effort}}
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


def _is_openrouter(base_url: str) -> bool:
    """True when a base_url points at OpenRouter — used to swap the
    default API-key fallback and the reasoning-effort wire format."""
    return "openrouter.ai" in (base_url or "").lower()


def _resolve(cfg: Config, ep: Endpoint | None) -> tuple[str, str]:
    """(api_key, base_url) for an endpoint, falling back to the right
    .env key based on the base_url:
      * openrouter.ai → cfg.openrouter_api_key (OPENROUTER_API_KEY)
      * everything else (incl. empty base_url = OpenAI default) →
        cfg.openai_api_key (OPENAI_API_KEY)
    An explicit api_key on the Endpoint object always wins. A custom
    base_url without a resolvable key uses a dummy bearer (many local
    servers accept any)."""
    base = (ep.base_url or "").strip() if ep else ""
    key = (ep.api_key or "").strip() if ep else ""
    if not key:
        key = (cfg.openrouter_api_key if _is_openrouter(base)
               else cfg.openai_api_key)
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
    # Per-role timeouts and SDK retries. The story-engine sits in a tight
    # per-turn hot path, so the trade-off is "how long do we wait for ONE
    # attempt vs. how many SDK auto-retries do we burn on its tail".
    #   * gen      — world generation, off the hot path; can take minutes
    #   * gate     — runs every turn, must stay snappy; small model
    #   * planner  — JSON-heavy substory plan, reasoning_effort=medium →
    #                legitimately 30–90 s on frontier reasoning models.
    #                We give it 90 s for ONE attempt and disable the SDK's
    #                own retry layer (max_retries=0) because plan_next has
    #                its own retry-with-transcript-logging on top, and
    #                stacking both would mean 5 × 90 s = 7.5 min before
    #                the player sees ANY feedback. With this config:
    #                attempt 1 = up to 90 s, attempt 2 = up to 90 s, then
    #                fallback. Spieler-Wartezeit beschränkt auf ≤180 s.
    #   * story    — per-turn narration; retries help against transient
    #                network blips
    if role == "gen":
        timeout, retries = 180.0, 1
    elif role == "gate":
        timeout, retries = 60.0, 1
    elif role == "planner":
        timeout, retries = 90.0, 0
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
