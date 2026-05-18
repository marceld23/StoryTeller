"""Per-session transcript recorder (JSONL) for the admin view.

Captures the full played story for traceability: player input, moderation
result, every LLM tool call + its result, and the narrator replies (with
state + running cost). One file per session: data/transcripts/<session>.jsonl
"""

from __future__ import annotations

import json
import re
import time

from ..config import Config


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-")
    return s or f"session-{int(time.time())}"


class Transcript:
    def __init__(self, cfg: Config, session: str):
        d = cfg.path("data/transcripts")
        d.mkdir(parents=True, exist_ok=True)
        self.session = _slug(session)
        self.path = d / f"{self.session}.jsonl"

    def _w(self, obj: dict) -> None:
        try:
            obj = {"ts": round(time.time(), 3), **obj}
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            pass  # transcript must never break play

    def note(self, text: str) -> None:
        self._w({"type": "note", "text": text})

    def user(self, text: str) -> None:
        self._w({"type": "user", "text": text})

    def moderation(self, ok: bool, flagged: list) -> None:
        self._w({"type": "moderation", "ok": ok, "flagged": flagged})

    def tool(self, name: str, args: dict, result) -> None:
        self._w({"type": "tool", "name": name, "args": args,
                 "result": str(result)[:2000]})

    def assistant(self, text: str, state: str = "", cost: float = 0.0) -> None:
        self._w({"type": "assistant", "text": text, "state": state,
                 "cost": round(float(cost), 4)})
