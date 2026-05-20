"""Known-facts tool: what the player already KNOWS (per save game)."""

from __future__ import annotations


class KnownFacts:
    def __init__(self, facts: list[dict] | None = None):
        self._facts: list[dict] = facts or []

    def remember(self, kind: str, name: str, note: str = "",
                 cap: int = 0) -> str:
        for f in self._facts:
            if f["kind"] == kind and f["name"].lower() == name.lower():
                if note:
                    f["note"] = note
                return f"aktualisiert: {name}"
        self._facts.append({"kind": kind, "name": name, "note": note})
        msg = f"gemerkt: {name}"
        if cap and len(self._facts) > cap:
            # evict the oldest entry without a note first; else the oldest
            idx = next((i for i, x in enumerate(self._facts) if not x["note"]),
                       0)
            evicted = self._facts.pop(idx)
            msg += f" (geräumt: {evicted['name']})"
        return msg

    def forget(self, name: str, kind: str | None = None) -> str:
        nm = (name or "").strip().lower()
        for i, f in enumerate(self._facts):
            if f["name"].lower() == nm and (kind is None or f["kind"] == kind):
                self._facts.pop(i)
                return f"vergessen: {f['name']}"
        return "(nicht gefunden)"

    def query(self, kind: str | None = None) -> list[dict]:
        return [f for f in self._facts if kind is None or f["kind"] == kind]

    def summary(self) -> str:
        if not self._facts:
            return "(noch nichts bekannt)"
        return "; ".join(
            f"{f['name']} [{f['kind']}]" + (f" — {f['note']}" if f["note"] else "")
            for f in self._facts
        )

    def to_list(self) -> list[dict]:
        return list(self._facts)
