"""Zufallsereignisse: welt-spezifische, gewichtete Zufallstabellen."""

from __future__ import annotations

import random


class RandomEvents:
    def __init__(self, world, rng: random.Random | None = None):
        self.world = world
        self.rng = rng or random.Random()
        self._tables = {t.name: t for t in world.random_tables}

    def table_names(self) -> list[str]:
        return list(self._tables)

    def roll(self, table_name: str) -> str:
        t = self._tables.get(table_name)
        if t is None:
            # Fallback: nimm irgendeine Tabelle, sonst neutrales Ereignis
            if not self._tables:
                return "Nichts Besonderes geschieht."
            t = self.rng.choice(list(self._tables.values()))
        if not t.entries:
            return "Nichts Besonderes geschieht."
        weights = [max(1, e.weight) for e in t.entries]
        return self.rng.choices(t.entries, weights=weights, k=1)[0].text
