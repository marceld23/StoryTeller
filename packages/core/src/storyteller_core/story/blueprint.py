"""Macro-arc control ("blueprint").

Knows the current beat, gives the LLM guard rails (position/escalation)
without railroading the player. advance() moves one beat forward.
"""

from __future__ import annotations


class BlueprintTracker:
    def __init__(self, blueprint, index: int = 0):
        self.blueprint = blueprint
        self.index = index

    def current(self):
        return self.blueprint.beats[self.index]

    @property
    def at_end(self) -> bool:
        return self.index >= len(self.blueprint.beats) - 1

    def advance(self) -> None:
        self.index = min(self.index + 1, len(self.blueprint.beats) - 1)

    def guidance(self) -> str:
        b = self.current()
        n = len(self.blueprint.beats)
        # We deliberately do NOT name the next beat — the narrator must not
        # know what's coming next or it will foreshadow specifics. We only
        # reveal position (X of N) and the *current* beat's goal.
        progress = ("(letzter Beat — steuere auf einen befriedigenden "
                    "Abschluss zu)" if self.at_end
                    else "(weitere Beats folgen — nicht vorgreifen, der "
                    "Erzähler kennt sie nicht im Voraus)")
        return (
            f"PRÄMISSE: {self.blueprint.premise}\n"
            f"AKTUELLER BEAT {self.index + 1}/{n}: {b.name} — Ziel: {b.goal} "
            f"(Spannung {b.tension}/10) {progress}.\n"
            f"ESKALATION: {self.blueprint.escalation_rule}\n"
            "Bleibe im Spannungsbogen, aber greife die Ideen des Spielers aktiv "
            "auf und webe sie ein. Wenn das Beat-Ziel erreicht scheint, rufe das "
            "Tool advance_beat auf."
        )
