"""WorldDesignInterview + classify_play_mode unit tests.

No network. The LLM client is monkeypatched; we just verify the brief
assembly, the cap-check propagation, transcript persistence, and the
helper that branches "existing world" vs "create new world" from a
free-form spoken answer.
"""

from __future__ import annotations

import json
import types

import storyteller_core.story.world_design as wd_mod
from storyteller_core.config import load_config
from storyteller_core.i18n import classify_play_mode
from storyteller_core.story.cost import DailyCapExceeded
from storyteller_core.story.world_design import WorldDesignInterview


def _fake_client(reply_text: str):
    def create(**kw):
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content=reply_text))],
            usage=types.SimpleNamespace(prompt_tokens=20,
                                          completion_tokens=15))
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))


def test_classify_play_mode_branches():
    # Play branch: bare "spielen" + English equivalents.
    assert classify_play_mode("ich möchte spielen") == "play"
    assert classify_play_mode("bestehende welt spielen") == "play"
    assert classify_play_mode("play existing") == "play"
    # Manage branch: explicit verwalten + any of the sub-action words
    # (so "neue Welt erstellen" / "Welt löschen" / "kopieren" all route
    # straight into management even without "verwalten" being said).
    assert classify_play_mode("welten verwalten") == "manage"
    assert classify_play_mode("eine neue Welt") == "manage"
    assert classify_play_mode("kopier mir die welt") == "manage"
    assert classify_play_mode("welt löschen") == "manage"
    assert classify_play_mode("new world please") == "manage"
    # Fallback.
    assert classify_play_mode("hmm") == "unclear"
    assert classify_play_mode("") == "unclear"


def test_classify_manage_action_branches():
    from storyteller_core.i18n import classify_manage_action

    assert classify_manage_action("neue welt erstellen") == "create_world"
    assert classify_manage_action("kopier die welt") == "copy"
    assert classify_manage_action("welt umbenennen") == "rename"
    assert classify_manage_action("welt löschen") == "delete"
    assert classify_manage_action("abbrechen") == "cancel"
    assert classify_manage_action("zurück") == "cancel"
    assert classify_manage_action("hmm") == "unclear"
    assert classify_manage_action("") == "unclear"
    # Disambiguation: "kopier die neue welt" => copy wins over create_world.
    assert classify_manage_action("kopier die neue welt") == "copy"


def test_interview_brief_and_history():
    cfg = load_config()
    iv = WorldDesignInterview(cfg, locale="de")
    iv.add_question(iv.opening_question())
    iv.add_user("Eine Stadt unter Wasser, vor 200 Jahren versunken.")
    iv.add_question("Wer ist der Spieler dort?")
    iv.add_user("Ein Taucher mit altem Schiff.")
    brief = iv.as_brief()
    assert "Frage:" in brief
    assert "Antwort des Spielers:" in brief
    assert "Taucher" in brief
    assert "Welt-Brief" in brief
    assert len(iv.history) == 4


def test_interview_next_question_records_cost(monkeypatch):
    cfg = load_config()
    monkeypatch.setattr(wd_mod, "get_chat_client",
                        lambda c, role="gen": _fake_client(
                            "Wie soll der Spieler heißen?"))
    captured: dict = {}
    real = wd_mod.CostLedger.record_chat_usage

    def fake_record(self, *, role, model, usage, thread_id=None,
                    world_id=None):
        captured["role"] = role
        captured["model"] = model
        captured["usage"] = usage
        return real(self, role=role, model=model, usage=usage,
                    thread_id=thread_id, world_id=world_id)
    monkeypatch.setattr(wd_mod.CostLedger, "record_chat_usage", fake_record)

    iv = WorldDesignInterview(cfg, locale="de")
    iv.add_user("Eine versunkene Stadt.")
    q = iv.next_question()
    assert q == "Wie soll der Spieler heißen?"
    assert captured["role"] == "gen"
    assert captured["usage"] is not None


def test_interview_falls_back_on_llm_error(monkeypatch):
    cfg = load_config()
    def boom(c, role="gen"):
        raise RuntimeError("network down")
    monkeypatch.setattr(wd_mod, "get_chat_client", boom)
    iv = WorldDesignInterview(cfg, locale="de")
    iv.add_user("Eine Idee.")
    q = iv.next_question()
    # Fallback text from DESIGN_PROMPTS
    assert q
    assert isinstance(q, str)


def test_interview_propagates_daily_cap(monkeypatch):
    cfg = load_config()
    def over_cap(self):
        raise DailyCapExceeded(99.0, 5.0)
    monkeypatch.setattr(wd_mod.CostLedger, "assert_under_cap", over_cap)
    iv = WorldDesignInterview(cfg, locale="de")
    try:
        iv.next_question()
    except DailyCapExceeded:
        return
    raise AssertionError("expected DailyCapExceeded")


def test_save_transcript_writes_jsonl(tmp_path, monkeypatch):
    cfg = load_config()
    # Config is a frozen-ish pydantic model — instead of patching the
    # bound method, redirect the module-level ROOT so cfg.path() resolves
    # under the tmp dir for this test.
    monkeypatch.setattr("storyteller_core.config.ROOT", tmp_path)
    iv = WorldDesignInterview(cfg, locale="en")
    iv.add_question("Where does it start?")
    iv.add_user("In a coastal lighthouse town.")
    p = iv.save_transcript()
    assert p.exists()
    # Sanity: the transcript landed under the tmp dir, not the real repo.
    assert str(p).startswith(str(tmp_path))
    lines = [json.loads(line) for line in p.read_text().splitlines()
             if line.strip()]
    assert lines[0]["kind"] == "world_design.meta"
    assert lines[0]["locale"] == "en"
    assert lines[1]["role"] == "assistant"
    assert lines[2]["role"] == "user"
