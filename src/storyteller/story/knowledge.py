"""Known-Facts-Tool: was der Spieler bereits KENNT (pro Spielstand)."""

from __future__ import annotations


class KnownFacts:
    def __init__(self, facts: list[dict] | None = None):
        self._facts: list[dict] = facts or []

    def remember(self, kind: str, name: str, note: str = "") -> str:
        for f in self._facts:
            if f["kind"] == kind and f["name"].lower() == name.lower():
                if note:
                    f["note"] = note
                return f"aktualisiert: {name}"
        self._facts.append({"kind": kind, "name": name, "note": note})
        return f"gemerkt: {name}"

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
