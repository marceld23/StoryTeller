"""Extract a structured user-note from free-form spoken text.

The player says something like:

    "Vermerken: Otkar ist ein blinder Bibliothekar aus Nethrá."

The main loop strips the keyword and hands the rest to `extract_note`.
A small JSON-mode call against `cfg.models.gen` resolves it into
`{kind, name, description, tags}`. On any failure (cap exhausted,
endpoint down, malformed JSON) we fall back to a `fact`-typed note
with the raw text — so the note ALWAYS lands; only the structure may
be coarser.
"""

from __future__ import annotations

import json
import logging

from ..config import Config
from ..oai import get_chat_client
from .cost import DailyCapExceeded
from .ledger import CostLedger

log = logging.getLogger("storyteller.note_extract")


_SYS_DE = (
    "Du analysierst eine kurze, vom Spieler diktierte Notiz für eine "
    "Geschichten-Welt. Klassifiziere und extrahiere strukturierte Daten. "
    "Antworte JSON-ONLY:\n"
    '{"kind":"person|place|item|fact",'
    '"name":"kurzer Hauptbegriff/Name",'
    '"description":"1–3 Sätze, vollständig, im erzählerischen Ton",'
    '"tags":["wenige","kurze","stichworte"]}\n'
    "Regeln:\n"
    "- kind=person für eine benannte Figur, place für einen Ort, "
    "item für einen Gegenstand, fact für alles andere (Sitte, Regel, "
    "Gerücht, Lore-Fakt).\n"
    "- name höchstens ~50 Zeichen; description vollständige Sätze.\n"
    "- Niemals Felder erfinden, die der Spieler nicht erwähnt hat — "
    "lieber knapp halten."
)

_SYS_EN = (
    "You analyse a short spoken note from a player about a story world. "
    "Classify and extract structured data. Respond JSON ONLY:\n"
    '{"kind":"person|place|item|fact",'
    '"name":"short main term/name",'
    '"description":"1–3 sentences, complete prose tone",'
    '"tags":["few","short","keywords"]}\n'
    "Rules:\n"
    "- kind=person for a named character, place for a location, item "
    "for an object, fact for everything else (custom, rule, rumor, "
    "lore fact).\n"
    "- name at most ~50 chars; description in complete sentences.\n"
    "- Never invent fields the player did not mention — stay concise."
)


def _fallback(raw: str) -> dict:
    return {
        "kind": "fact",
        "name": (raw or "").strip()[:80] or "Notiz",
        "description": (raw or "").strip(),
        "tags": [],
    }


def extract_note(cfg: Config, raw_text: str, locale: str = "de") -> dict:
    """Returns `{kind, name, description, tags}`. Always succeeds — falls
    back to a `fact` note containing the raw text on any error. Raises
    `DailyCapExceeded` if the daily budget is already exhausted (the
    main loop catches and pauses)."""
    raw = (raw_text or "").strip()
    if not raw:
        return _fallback("")

    ledger = CostLedger(cfg)
    ledger.assert_under_cap()       # surfaces DailyCapExceeded upstream

    sys_prompt = _SYS_DE if locale.startswith("de") else _SYS_EN
    try:
        client = get_chat_client(cfg, "gen")
        r = client.chat.completions.create(
            model=cfg.models.gen,
            temperature=0.2,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": raw},
            ],
            response_format={"type": "json_object"},
        )
        ledger.record_chat_usage(role="gen", model=cfg.models.gen,
                                 usage=r.usage)
        data = json.loads(r.choices[0].message.content or "{}")
    except DailyCapExceeded:
        raise
    except Exception as exc:
        log.warning("note extraction failed, using fallback: %r", exc)
        return _fallback(raw)

    kind = (data.get("kind") or "").strip().lower()
    if kind not in {"person", "place", "item", "fact"}:
        kind = "fact"
    name = (data.get("name") or "").strip()
    if not name:
        return _fallback(raw)
    desc = (data.get("description") or "").strip() or raw
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return {
        "kind": kind,
        "name": name[:80],
        "description": desc,
        "tags": [str(t)[:30] for t in tags][:6],
    }
