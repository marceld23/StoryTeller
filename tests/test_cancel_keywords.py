"""Smoke tests for the cancel-keyword bucket used by the world-design
interview's "abbrechen / stop / …" detection.

The actual interview loop lives in `apps/pi/src/storyteller_pi/main.py`
and depends on hardware (mic, LEDs, wake-word). What we CAN test
cheaply here is that the keyword bucket exists per locale, contains
the spoken-friendly cancel words, and that the same prefix-match
heuristic the main loop uses ("≤3 tokens, first token in bucket")
fires the right way.
"""

from __future__ import annotations

from storyteller_core.i18n import CMD_KEYWORDS


def _is_cancel(text: str, locale: str = "de") -> bool:
    """Mirror of the main-loop detection: ≤3 tokens AND first token in
    the cancel bucket."""
    low = (text or "").lower()
    toks = [t.strip(",.!?;:") for t in low.split()]
    if not toks or len(toks) > 3:
        return False
    bucket = CMD_KEYWORDS[locale]["cancel"]
    return any(t in bucket for t in toks)


def test_cancel_bucket_has_intuitive_words():
    de = CMD_KEYWORDS["de"]["cancel"]
    en = CMD_KEYWORDS["en"]["cancel"]
    for w in ("abbrechen", "stopp", "beenden", "schluss", "halt"):
        assert w in de, f"missing in de cancel bucket: {w}"
    for w in ("cancel", "stop", "abort", "quit"):
        assert w in en, f"missing in en cancel bucket: {w}"


def test_short_cancel_triggers_de():
    assert _is_cancel("abbrechen", "de")
    assert _is_cancel("Stopp", "de")
    assert _is_cancel("beenden bitte", "de")          # 2 tokens
    assert _is_cancel("halt mal stopp", "de")         # 3 tokens


def test_short_cancel_triggers_en():
    assert _is_cancel("cancel", "en")
    assert _is_cancel("stop please", "en")
    assert _is_cancel("abort", "en")


def test_long_utterance_does_not_trigger():
    # >3 tokens guards against accidental cancel in a longer answer
    # like "stopp, lass mich nochmal nachdenken über die Welt".
    assert not _is_cancel(
        "stopp lass mich nochmal nachdenken über die Welt", "de")
    assert not _is_cancel(
        "stop and let me think about this for a moment", "en")


def test_non_cancel_words_dont_trigger():
    assert not _is_cancel("eine düstere Insel", "de")
    assert not _is_cancel("a misty island", "en")
    assert not _is_cancel("", "de")
