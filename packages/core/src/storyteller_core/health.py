"""Endpoint health: classify LLM/TTS/STT failures and persist per-role status.

Storyteller talks to seven independent OpenAI-compatible endpoints
(story / planner / gen / gate / stt / tts / embedding). Anything from the
provider — connection refused, auth error, rate limit, 5xx, malformed
request — used to bubble up as a generic `Exception` and either get
swallowed deep in the engine or trigger the Pi's single generic
`error_retry.wav` prompt.

This module gives those failures structure:

  * `EndpointError`  — strongly-typed exception with `role`, `kind`,
    `http_status`, `base_url`, `model`, `detail`.
  * `classify(exc)` — map `openai.*Error` / `httpx.*Error` / bare 4xx/5xx
    to one of: unreachable, auth, rate_limit, server, bad_request, unknown.
  * `HealthRegistry`  — in-memory + on-disk (`data/health.json`) per-role
    status (last_ok_ts, last_err_ts, last_err_kind, consecutive_failures).
    The Pi voice loop updates it after every call; the admin backend
    reads it to render banners and the health page.

Keep this dependency-light: imports only `openai`, `httpx`, stdlib.
Engine + voice modules can import it without circular pain.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .config import Config

log = logging.getLogger("storyteller.health")

Kind = Literal[
    "unreachable",   # ConnectError / DNS / TCP refused / timeout connecting
    "timeout",       # request sent but response didn't arrive in time
    "auth",          # 401 / invalid API key
    "rate_limit",    # 429
    "server",        # 5xx
    "bad_request",   # 400 (incl. "model not found")
    "unknown",       # anything else
]

# Subset that means "Admin must act now" — surfaces as a red banner in
# the admin UI and selects the `error_auth.wav` prompt on voice.
ACTION_REQUIRED: tuple[Kind, ...] = ("auth", "bad_request")
# Subset that means "transient — try again soon".
TRANSIENT: tuple[Kind, ...] = ("rate_limit", "server", "timeout")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class EndpointError(Exception):
    """A structured failure from an LLM / TTS / STT / embedding call.

    Always carries enough context for the admin UI to point at the right
    endpoint (`role` + `base_url` + `model`) and for the Pi voice loop
    to pick the right pre-recorded announcement (`kind`).
    """

    def __init__(
        self,
        *,
        role: str,
        kind: Kind,
        http_status: int | None = None,
        base_url: str = "",
        model: str | None = None,
        detail: str = "",
        original: BaseException | None = None,
    ) -> None:
        msg = (f"[{role}] {kind}"
               + (f" http={http_status}" if http_status else "")
               + (f" model={model}" if model else "")
               + (f" — {detail}" if detail else ""))
        super().__init__(msg)
        self.role = role
        self.kind: Kind = kind
        self.http_status = http_status
        self.base_url = base_url or ""
        self.model = model
        self.detail = detail
        self.__cause__ = original


# ---------------- classifier -----------------------------------------------


def _http_status(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction across openai-python and httpx."""
    for attr in ("status_code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(exc, "response", None)
    if resp is not None:
        v = getattr(resp, "status_code", None)
        if isinstance(v, int):
            return v
    return None


def classify(exc: BaseException) -> tuple[Kind, int | None, str]:
    """Map a raw exception to `(kind, http_status, short_detail)`.

    Recognises openai-python's exception hierarchy AND raw httpx errors —
    self-hosted servers (Ollama, XTTS, Wyoming) often raise httpx
    directly because they bypass the OpenAI SDK.
    """
    detail = str(exc)[:200] or exc.__class__.__name__
    # Importing inside the function keeps health.py importable from
    # contexts that don't have openai/httpx installed (unlikely on the
    # Pi, but cheap insurance).
    try:
        import openai
    except Exception:
        openai = None  # type: ignore
    try:
        import httpx
    except Exception:
        httpx = None  # type: ignore

    status = _http_status(exc)

    # openai.AuthenticationError + 401
    if openai is not None and isinstance(exc, openai.AuthenticationError):
        return "auth", status or 401, detail
    if openai is not None and isinstance(exc, openai.RateLimitError):
        return "rate_limit", status or 429, detail
    if openai is not None and isinstance(exc, openai.APITimeoutError):
        return "timeout", status, detail
    if openai is not None and isinstance(exc, openai.APIConnectionError):
        return "unreachable", status, detail
    if openai is not None and isinstance(exc, openai.BadRequestError):
        return "bad_request", status or 400, detail
    if openai is not None and isinstance(exc, openai.InternalServerError):
        return "server", status or 500, detail

    # httpx (raised by xtts/wyoming/probe paths)
    if httpx is not None:
        if isinstance(exc, httpx.ConnectError):
            return "unreachable", status, detail
        if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout,
                            httpx.WriteTimeout, httpx.PoolTimeout)):
            return "timeout", status, detail
        if isinstance(exc, httpx.HTTPStatusError):
            s = exc.response.status_code
            if s == 401:
                return "auth", s, detail
            if s == 429:
                return "rate_limit", s, detail
            if 500 <= s < 600:
                return "server", s, detail
            if 400 <= s < 500:
                return "bad_request", s, detail

    # Fallback: HTTP-status code based heuristics
    if status == 401:
        return "auth", status, detail
    if status == 429:
        return "rate_limit", status, detail
    if status is not None and 500 <= status < 600:
        return "server", status, detail
    if status is not None and 400 <= status < 500:
        return "bad_request", status, detail

    return "unknown", status, detail


def wrap(role: str, *, base_url: str = "", model: str | None = None):
    """Decorator/contextmanager-lite helper: call inside a `try/except`
    block to convert any raised exception into a properly-classified
    `EndpointError`. Returns the new exception — the caller decides
    whether to `raise from` or report-and-continue.
    """
    def _wrap(exc: BaseException) -> EndpointError:
        if isinstance(exc, EndpointError):
            return exc
        kind, status, detail = classify(exc)
        return EndpointError(role=role, kind=kind, http_status=status,
                             base_url=base_url, model=model,
                             detail=detail, original=exc)
    return _wrap


# ---------------- registry -------------------------------------------------


@dataclass
class RoleStatus:
    role: str
    ok: bool = True                       # most recent call succeeded
    last_ok_ts: str | None = None
    last_err_ts: str | None = None
    last_err_kind: Kind | None = None
    last_err_http: int | None = None
    last_err_detail: str = ""
    base_url: str = ""
    model: str | None = None
    consecutive_failures: int = 0


_KNOWN_ROLES: tuple[str, ...] = (
    "story", "planner", "gen", "gate", "stt", "tts", "embedding"
)


class HealthRegistry:
    """Singleton holding per-role status + writing it atomically to
    `data/health.json` whenever it changes.

    The Pi voice loop owns the writer side (records ok/fail after every
    call); the admin backend reads the file passively. Both sides can
    instantiate this — the file is the source of truth.
    """

    _instance: HealthRegistry | None = None
    _instance_lock = threading.Lock()

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.path: Path = cfg.path("data/health.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._roles: dict[str, RoleStatus] = {}
        self._load()

    @classmethod
    def get(cls, cfg: Config) -> HealthRegistry:
        with cls._instance_lock:
            if cls._instance is None or cls._instance.cfg is not cfg:
                cls._instance = cls(cfg)
            return cls._instance

    # ---- persistence -------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("health.json unreadable (%s): %r", self.path, exc)
            return
        roles = data.get("roles") or {}
        for name, raw in roles.items():
            if not isinstance(raw, dict):
                continue
            raw = {**raw, "role": name}
            try:
                self._roles[name] = RoleStatus(**{
                    k: raw.get(k) for k in RoleStatus.__dataclass_fields__
                })
            except Exception:
                continue

    def _write(self) -> None:
        payload = {
            "updated_at": _now_iso(),
            "roles": {name: asdict(rs) for name, rs in self._roles.items()},
        }
        line = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            # Atomic: write to a sibling tmp, fsync, rename. Otherwise a
            # reader picks up a half-written file during the next poll.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8",
                dir=str(self.path.parent),
                prefix=".health-", suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(line)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name
            os.replace(tmp_path, self.path)
        except OSError as exc:
            log.warning("health.json write failed (%s): %r", self.path, exc)

    # ---- mutation ----------------------------------------------------

    def _get_or_create(self, role: str) -> RoleStatus:
        rs = self._roles.get(role)
        if rs is None:
            rs = RoleStatus(role=role)
            self._roles[role] = rs
        return rs

    def record_ok(self, role: str, *, base_url: str = "",
                  model: str | None = None) -> None:
        """Mark a successful call. Resets the consecutive-failure counter."""
        with self._lock:
            existed = role in self._roles
            rs = self._get_or_create(role)
            # Write whenever something a reader cares about changed: the
            # role just appeared, the ok flag flipped, the failure counter
            # was non-zero, or we learned a new base_url / model.
            changed = (not existed
                       or not rs.ok
                       or rs.consecutive_failures > 0
                       or (base_url and rs.base_url != base_url)
                       or (model and rs.model != model))
            rs.ok = True
            rs.last_ok_ts = _now_iso()
            rs.consecutive_failures = 0
            if base_url:
                rs.base_url = base_url
            if model:
                rs.model = model
            if changed:
                self._write()

    def record_error(self, err: EndpointError) -> None:
        """Mark a failed call. Increments consecutive_failures."""
        with self._lock:
            rs = self._get_or_create(err.role)
            rs.ok = False
            rs.last_err_ts = _now_iso()
            rs.last_err_kind = err.kind
            rs.last_err_http = err.http_status
            rs.last_err_detail = err.detail[:200] if err.detail else ""
            if err.base_url:
                rs.base_url = err.base_url
            if err.model:
                rs.model = err.model
            rs.consecutive_failures += 1
            self._write()

    # ---- read --------------------------------------------------------

    def snapshot(self) -> dict[str, dict]:
        """Per-role status as plain dicts — for API responses."""
        with self._lock:
            return {name: asdict(rs) for name, rs in self._roles.items()}

    def roles_with_problems(self) -> list[RoleStatus]:
        with self._lock:
            return [rs for rs in self._roles.values() if not rs.ok]


# ---------------- active probing -------------------------------------------


def probe_role(cfg: Config, role: str, *, timeout: float = 3.0) -> dict:
    """Active reachability check for one role's endpoint.

    For chat / embedding / stt / tts roles we issue a cheap GET against
    a path the server typically exposes (OpenAI-compatible: `/models`).
    Self-hosted servers that don't implement `/models` will look
    "unreachable" — that's fine: the passive `health.json` is the real
    source of truth for actual usage. Probing is an opt-in extra for
    the admin's "test now" button.
    """
    from .oai import _ep, _resolve  # internal helpers — health is privileged
    ep = _ep(cfg, f"{role}_endpoint")
    base = (ep.base_url or "").strip() if ep else ""
    # OpenAI default
    if not base:
        base = "https://api.openai.com/v1"
    try:
        key, _ = _resolve(cfg, ep)
    except Exception as exc:
        return {"role": role, "ok": False, "kind": "auth",
                "http_status": None, "detail": str(exc)[:200],
                "base_url": base}

    # Wyoming (TCP) isn't HTTP-pingable; mark "skipped" so the UI shows
    # "n/a" rather than a false-positive "unreachable".
    if base.startswith(("tcp://", "wyoming://")):
        return {"role": role, "ok": True, "kind": None,
                "http_status": None, "detail": "wyoming/tcp — not probed",
                "base_url": base, "skipped": True}

    # XTTS uses a custom path
    if base.startswith(("xtts://", "xtts+http://", "xtts+https://")):
        ping_url = (base.replace("xtts+https://", "https://")
                        .replace("xtts+http://", "http://")
                        .replace("xtts://", "http://")
                        .rstrip("/") + "/get_tts_settings")
    else:
        ping_url = base.rstrip("/") + "/models"

    import httpx
    try:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        r = httpx.get(ping_url, timeout=timeout, headers=headers)
        if r.status_code >= 400:
            kind, status, detail = classify(
                httpx.HTTPStatusError("probe failed", request=r.request,
                                      response=r))
            return {"role": role, "ok": False, "kind": kind,
                    "http_status": status, "detail": detail,
                    "base_url": base}
        return {"role": role, "ok": True, "kind": None,
                "http_status": r.status_code, "detail": "", "base_url": base}
    except Exception as exc:
        kind, status, detail = classify(exc)
        return {"role": role, "ok": False, "kind": kind,
                "http_status": status, "detail": detail, "base_url": base}


def known_roles() -> tuple[str, ...]:
    return _KNOWN_ROLES


def is_paid_cloud_role(cfg: Config, role: str) -> bool:
    """True when this role's endpoint points at OpenAI / OpenRouter.

    The Pi loop uses this to decide between two unreachable prompts:
      * paid cloud unreachable → "the internet is down" (error_offline_cloud)
      * self-hosted unreachable → "my computer at home isn't answering"
        (error_offline_local)

    Falls back to the same role-chain logic as oai.get_chat_client
    (gate → planner → story) so a derived endpoint is interpreted
    correctly.
    """
    from .oai import _endpoint_for_role, _ep
    from .story.cost import is_paid_cloud
    # Chat roles use the layered fallback (gate→planner→story).
    if role in ("story", "planner", "gen", "gate"):
        ep = _endpoint_for_role(cfg, role)
    else:
        ep = _ep(cfg, f"{role}_endpoint")
    base = (getattr(ep, "base_url", "") or "").strip() if ep else ""
    # Empty base = OpenAI default = paid.
    if not base:
        return True
    return is_paid_cloud(base)
