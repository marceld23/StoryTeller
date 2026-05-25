"""Long-term memory: synopsis-fold robustness.

Covers the protection added against a lazy summariser dropping the
prior synopsis content. The fold function should:

- accept a proper merge that retains the old synopsis;
- on a suspicious shrink (new < 70% of old when old >= 300 chars),
  retry once with a sharper corrective prompt;
- if the retry also shrinks, fall back to NOT writing the new
  synopsis (caller queues into pending_fold, eventually heuristic_fold
  concatenates lossless — old synopsis is never lost).
"""

from __future__ import annotations

import types

import storyteller_core.story.nodes as nodes
from storyteller_core.config import load_config


def _mock_client(reply_texts: list[str]):
    """OpenAI-shaped client that returns `reply_texts` in order."""
    calls: list[dict] = []

    def create(**kw):
        idx = len(calls)
        calls.append(kw)
        txt = reply_texts[idx] if idx < len(reply_texts) else ""
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content=txt))],
            usage=types.SimpleNamespace(prompt_tokens=10,
                                         completion_tokens=10))

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))
    return client, calls


def _dropped_messages(n: int = 6) -> list[dict]:
    """A small synthetic conversation segment to fold in."""
    out: list[dict] = []
    for i in range(n // 2):
        out.append({"role": "user",
                    "content": f"Spieler-Aktion {i+1} — etwas geschah."})
        out.append({"role": "assistant",
                    "content": f"Erzähler-Antwort {i+1} — die Welt reagiert."})
    return out


def test_normal_fold_accepted(monkeypatch) -> None:
    """Healthy case: summariser returns a synopsis at least as long
    as the old one. Pipeline accepts it on the first call."""
    cfg = load_config()
    old = "Etablierter Kontext " * 30  # ~600 chars
    new_synopsis_text = old + " Plus neue Ereignisse: ..."
    client, calls = _mock_client([new_synopsis_text])
    monkeypatch.setattr(nodes, "get_chat_client",
                        lambda cfg, role="planner": client)

    ok, result = nodes._fold_into_synopsis(
        cfg, old, _dropped_messages(), transcript=None)
    assert ok is True
    assert len(calls) == 1
    assert result.startswith("Etablierter Kontext")


def test_suspicious_shrink_retries_then_accepts(monkeypatch) -> None:
    """First reply is too short -> the function retries once with the
    sharper corrective, and if the retry returns a long-enough answer
    that one wins."""
    cfg = load_config()
    old = "Wichtiger Kontext " * 30  # ~540 chars
    # 1st reply: too short (< 70% of old)
    # 2nd reply: passes the floor
    short_reply = "Knappe Notiz nur."
    long_reply = old + " Und das Neue dazu."
    client, calls = _mock_client([short_reply, long_reply])
    monkeypatch.setattr(nodes, "get_chat_client",
                        lambda cfg, role="planner": client)

    ok, result = nodes._fold_into_synopsis(
        cfg, old, _dropped_messages(), transcript=None)
    assert ok is True
    assert len(calls) == 2          # one initial + one retry
    assert result == long_reply[:int(cfg.story.synopsis_max_chars)]


def test_double_shrink_falls_back_to_old(monkeypatch) -> None:
    """Both initial and retry shrink suspiciously -> return False so
    the caller queues into pending_fold + heuristic_fold preserves the
    old synopsis lossless."""
    cfg = load_config()
    old = "Etablierter Kontext " * 30  # ~600 chars
    client, calls = _mock_client(["Zu kurz.", "Immer noch zu kurz."])
    monkeypatch.setattr(nodes, "get_chat_client",
                        lambda cfg, role="planner": client)

    ok, result = nodes._fold_into_synopsis(
        cfg, old, _dropped_messages(), transcript=None)
    assert ok is False
    # The old synopsis is preserved untouched by this function — the
    # caller (_trim_and_fold) then queues into pending_fold and uses
    # heuristic_fold for a lossless concat later.
    assert result == old
    assert len(calls) == 2          # one initial + one retry, then gives up


def test_tiny_old_synopsis_does_not_trigger_floor(monkeypatch) -> None:
    """When the old synopsis is shorter than _SYNOPSIS_FLOOR_MIN_OLD
    (300 chars), the shrink check is bypassed — early-session
    synopses should be allowed to get reshaped freely."""
    cfg = load_config()
    old = "Kurzer Anfangs-Kontext."   # ~24 chars
    very_short = "Ok."
    client, calls = _mock_client([very_short])
    monkeypatch.setattr(nodes, "get_chat_client",
                        lambda cfg, role="planner": client)

    ok, result = nodes._fold_into_synopsis(
        cfg, old, _dropped_messages(), transcript=None)
    assert ok is True
    assert len(calls) == 1          # no retry
    assert result == very_short


def test_empty_llm_response_returns_false(monkeypatch) -> None:
    """Empty body from the summariser is a real failure (not a shrink
    suspicion) → caller falls back to pending_fold / heuristic_fold."""
    cfg = load_config()
    old = "Etablierter Kontext " * 30
    client, _ = _mock_client([""])
    monkeypatch.setattr(nodes, "get_chat_client",
                        lambda cfg, role="planner": client)

    ok, result = nodes._fold_into_synopsis(
        cfg, old, _dropped_messages(), transcript=None)
    assert ok is False
    assert result == old             # unchanged
