"""Endpoint health: classify + registry + paid-vs-local routing.

These tests don't hit any real network — they fabricate exceptions /
mock the openai client and assert that the classifier picks the right
`kind` and that the registry persists status atomically.
"""

import json

import httpx
import openai
import storyteller_core.config as cfgmod
from storyteller_core.config import load_config
from storyteller_core.health import (
    ACTION_REQUIRED,
    EndpointError,
    HealthRegistry,
    classify,
    is_paid_cloud_role,
    known_roles,
    wrap,
)

# --------------------------------------------------------------------------
# classifier
# --------------------------------------------------------------------------


def _mk_openai_err(cls, status):
    """openai.* errors take (message, *, response, body) — fabricate enough."""
    req = httpx.Request("GET", "https://api.openai.com/v1/models")
    resp = httpx.Response(status, request=req)
    return cls(message="x", response=resp, body=None)


def test_classify_openai_auth():
    exc = _mk_openai_err(openai.AuthenticationError, 401)
    kind, status, _ = classify(exc)
    assert kind == "auth"
    assert status == 401


def test_classify_openai_rate_limit():
    exc = _mk_openai_err(openai.RateLimitError, 429)
    kind, status, _ = classify(exc)
    assert kind == "rate_limit"
    assert status == 429


def test_classify_openai_bad_request():
    exc = _mk_openai_err(openai.BadRequestError, 400)
    kind, status, _ = classify(exc)
    assert kind == "bad_request"
    assert status == 400


def test_classify_openai_server():
    exc = _mk_openai_err(openai.InternalServerError, 503)
    kind, status, _ = classify(exc)
    assert kind == "server"
    assert status == 503


def test_classify_httpx_connect_error():
    exc = httpx.ConnectError("nope")
    kind, _, _ = classify(exc)
    assert kind == "unreachable"


def test_classify_httpx_timeout():
    exc = httpx.ReadTimeout("slow")
    kind, _, _ = classify(exc)
    assert kind == "timeout"


def test_classify_httpx_http_status_5xx():
    req = httpx.Request("GET", "http://x/")
    resp = httpx.Response(502, request=req)
    exc = httpx.HTTPStatusError("bad gateway", request=req, response=resp)
    kind, status, _ = classify(exc)
    assert kind == "server"
    assert status == 502


def test_classify_unknown_falls_through():
    kind, _, _ = classify(RuntimeError("???"))
    assert kind == "unknown"


def test_action_required_set():
    assert "auth" in ACTION_REQUIRED
    assert "bad_request" in ACTION_REQUIRED
    assert "unreachable" not in ACTION_REQUIRED
    assert "rate_limit" not in ACTION_REQUIRED


# --------------------------------------------------------------------------
# wrap()
# --------------------------------------------------------------------------


def test_wrap_passes_through_endpoint_error():
    orig = EndpointError(role="story", kind="auth", http_status=401,
                         base_url="https://api.openai.com/v1",
                         model="gpt-5.4-mini")
    out = wrap("story")(orig)
    assert out is orig


def test_wrap_classifies_unknown():
    out = wrap("story", base_url="x", model="m")(RuntimeError("boom"))
    assert isinstance(out, EndpointError)
    assert out.role == "story"
    assert out.kind == "unknown"
    assert out.model == "m"


# --------------------------------------------------------------------------
# HealthRegistry
# --------------------------------------------------------------------------


def test_registry_record_ok_then_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    # Force a fresh registry — singleton might be polluted from another test
    HealthRegistry._instance = None
    reg = HealthRegistry.get(cfg)

    reg.record_ok("story", base_url="https://openrouter.ai/api/v1",
                  model="gpt-5.4-mini")
    snap = reg.snapshot()
    assert snap["story"]["ok"] is True
    assert snap["story"]["consecutive_failures"] == 0
    assert snap["story"]["base_url"] == "https://openrouter.ai/api/v1"

    # Three consecutive errors -> counter increases, ok flips
    for _ in range(3):
        err = EndpointError(role="story", kind="auth", http_status=401,
                            base_url="https://openrouter.ai/api/v1",
                            model="gpt-5.4-mini", detail="bad key")
        reg.record_error(err)
    snap = reg.snapshot()
    assert snap["story"]["ok"] is False
    assert snap["story"]["consecutive_failures"] == 3
    assert snap["story"]["last_err_kind"] == "auth"
    assert snap["story"]["last_err_http"] == 401

    # A success resets the counter
    reg.record_ok("story")
    snap = reg.snapshot()
    assert snap["story"]["ok"] is True
    assert snap["story"]["consecutive_failures"] == 0


def test_registry_persists_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    HealthRegistry._instance = None
    reg = HealthRegistry.get(cfg)
    reg.record_ok("tts", base_url="", model="gpt-4o-mini-tts")

    # File should exist + be parseable
    path = tmp_path / "data" / "health.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "tts" in data["roles"]
    assert data["roles"]["tts"]["ok"] is True

    # A fresh registry loads the previous state
    HealthRegistry._instance = None
    reg2 = HealthRegistry.get(cfg)
    snap = reg2.snapshot()
    assert snap["tts"]["ok"] is True
    assert snap["tts"]["model"] == "gpt-4o-mini-tts"


# --------------------------------------------------------------------------
# is_paid_cloud_role
# --------------------------------------------------------------------------


def test_is_paid_cloud_role_openai_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert is_paid_cloud_role(cfg, "story") is True
    assert is_paid_cloud_role(cfg, "tts") is True


def test_is_paid_cloud_role_openrouter(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text(json.dumps({
        "story_endpoint": {"base_url": "https://openrouter.ai/api/v1"},
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert is_paid_cloud_role(cfg, "story") is True


def test_is_paid_cloud_role_self_hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text(json.dumps({
        "story_endpoint": {"base_url": "http://192.168.1.50:8000/v1"},
        "tts_endpoint": {"base_url": "tcp://192.168.1.50:10200"},
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert is_paid_cloud_role(cfg, "story") is False
    assert is_paid_cloud_role(cfg, "tts") is False


# --------------------------------------------------------------------------
# known_roles is the canonical list used by the admin endpoint
# --------------------------------------------------------------------------


def test_known_roles_covers_seven_endpoints():
    r = set(known_roles())
    assert r == {"story", "planner", "gen", "gate", "stt", "tts", "embedding"}
