"""Player-added world facts ("Vermerken: …" voice command).

A `UserNote` is a fact the PLAYER introduced mid-session and wants to
persist across sessions. Storage is per-world JSONL (append-only +
mutation through markers), so:

* The kanonical world.json (kuratiert) stays untouched.
* Each note is independently revisitable / promotable / dismissable by
  the admin without re-saving the whole world.
* Every note is also indexed into the RAG vector store with a
  `user_<kind>` fact_type, so the narrator can retrieve it the next
  time the player or substory planner asks for related material.

Lifecycle:
    voice command  ─►  UserNoteStore.append(...)  ─►  RAG.index_single_fact
    admin promote  ─►  store.mark_promoted(...)    + writes into world.json
    admin discard  ─►  store.delete(...)           + RAG.remove_facts_by_content
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ..config import Config

log = logging.getLogger("storyteller.user_notes")

ALLOWED_KINDS = ("person", "place", "item", "fact")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_id() -> str:
    return secrets.token_hex(6)


class UserNote(BaseModel):
    id: str
    ts: str
    world_id: str
    locale: str
    kind: str            # "person" | "place" | "item" | "fact"
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    raw_text: str = ""
    thread_id: str | None = None
    promoted: bool = False
    deleted: bool = False

    def as_rag_text(self) -> str:
        """Render a single human-readable line for embedding + retrieval."""
        if self.kind == "person":
            head = f"PERSON {self.name}"
        elif self.kind == "place":
            head = f"ORT {self.name}"
        elif self.kind == "item":
            head = f"GEGENSTAND {self.name}"
        else:
            head = self.name
        body = self.description or self.raw_text
        return f"{head}: {body}".strip().rstrip(":")

    def rag_fact_type(self) -> str:
        return f"user_{self.kind}" if self.kind in ALLOWED_KINDS else "user_fact"


class UserNoteStore:
    """Append-only JSONL store at `data/worlds/<world_id>.user_notes.jsonl`.

    State mutations (promotion, deletion) are written as new lines with the
    same `id` and merged client-side. Last write wins per `id`.
    """

    def __init__(self, cfg: Config, world_id: str):
        self.cfg = cfg
        self.world_id = world_id
        self.path = cfg.path(
            f"{cfg.paths.worlds_dir}/{world_id}.user_notes.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- write -------------------------------------------------

    def _append_raw(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            log.warning("user-notes write failed (%s): %r", self.path, exc)

    def append(self, *, locale: str, kind: str, name: str,
               description: str = "", tags: list[str] | None = None,
               raw_text: str = "",
               thread_id: str | None = None) -> UserNote:
        kind = kind if kind in ALLOWED_KINDS else "fact"
        note = UserNote(
            id=_new_id(), ts=_now_iso(),
            world_id=self.world_id, locale=locale,
            kind=kind, name=(name or "").strip(),
            description=(description or "").strip(),
            tags=list(tags or []),
            raw_text=(raw_text or "").strip(),
            thread_id=thread_id,
        )
        self._append_raw(note.model_dump())
        return note

    def mark_promoted(self, note_id: str) -> bool:
        note = self.get(note_id)
        if note is None:
            return False
        note.promoted = True
        note.ts = _now_iso()
        self._append_raw(note.model_dump())
        return True

    def update(self, note_id: str, **fields) -> UserNote | None:
        note = self.get(note_id)
        if note is None:
            return None
        for k, v in fields.items():
            if k in {"kind", "name", "description", "tags",
                     "promoted"} and hasattr(note, k):
                setattr(note, k, v)
        note.ts = _now_iso()
        self._append_raw(note.model_dump())
        return note

    def delete(self, note_id: str) -> bool:
        note = self.get(note_id)
        if note is None:
            return False
        note.deleted = True
        note.ts = _now_iso()
        self._append_raw(note.model_dump())
        return True

    # ---------------- read --------------------------------------------------

    def _iter_raw(self):
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    def _by_id(self) -> dict[str, UserNote]:
        """Latest version per id, in order of first appearance."""
        latest: dict[str, dict] = {}
        order: list[str] = []
        for e in self._iter_raw():
            nid = e.get("id")
            if not nid:
                continue
            if nid not in latest:
                order.append(nid)
            latest[nid] = e
        out: dict[str, UserNote] = {}
        for nid in order:
            try:
                out[nid] = UserNote.model_validate(latest[nid])
            except Exception:
                continue
        return out

    def get(self, note_id: str) -> UserNote | None:
        return self._by_id().get(note_id)

    def list(self, *, include_deleted: bool = False,
             promoted: bool | None = None) -> list[UserNote]:
        out: list[UserNote] = []
        for n in self._by_id().values():
            if n.deleted and not include_deleted:
                continue
            if promoted is not None and n.promoted != promoted:
                continue
            out.append(n)
        # newest first
        out.sort(key=lambda n: n.ts, reverse=True)
        return out


# ---------------- end-to-end: extract + store + index --------------------

def create_user_note(cfg: Config, world_id: str, locale: str,
                     raw_text: str, *,
                     thread_id: str | None = None,
                     rag=None) -> UserNote:
    """Take a piece of free-form text spoken by the player, extract a
    structured note, persist it in the per-world store, AND index it in
    RAG so the running narrator (and future sessions) can retrieve it.

    `rag` is optional: when provided we add a single fact entry; when
    `None` the note is stored but not yet retrievable from RAG until
    the next index_world.
    """
    from .note_extract import extract_note

    data = extract_note(cfg, raw_text, locale=locale)
    store = UserNoteStore(cfg, world_id)
    note = store.append(
        locale=locale, kind=data["kind"], name=data["name"],
        description=data["description"], tags=data["tags"],
        raw_text=raw_text, thread_id=thread_id)
    if rag is not None:
        try:
            rag.index_single_fact(world_id, locale,
                                  note.rag_fact_type(),
                                  note.as_rag_text())
        except Exception as exc:
            log.warning("user-note RAG insert failed: %r", exc)
    return note
