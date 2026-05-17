"""Abstrakte, welt-unabhängige Story-Dynamik.

Eine gecodete Zufallsfunktion, die abstrakt beschriebene Wendungen liefert
(„ein weiterer Antagonist taucht auf", „etwas Negatives/Positives Unvorher-
gesehenes" …). Wird sowohl beim PLANEN einer Substory als auch im VERLAUF
genutzt (Tool roll_story_dynamic + dezente Auto-Injection). Wichtig: immer
nur als organisch einzuwebende Komplikation — der Makro-/Substory-Bogen wird
NICHT verworfen oder zurückgesetzt.
"""

from __future__ import annotations

import random

# (Gewicht, Beschreibung). Höheres Gewicht = häufiger.
STORY_DYNAMICS: list[tuple[int, str]] = [
    (5, "Etwas Negatives, Unvorhergesehenes geschieht."),
    (4, "Etwas Positives, Unvorhergesehenes geschieht."),
    (3, "Ein weiterer Antagonist oder Rivale taucht auf."),
    (3, "Ein bekanntes Gesicht kehrt unerwartet zurück."),
    (3, "Ein Geheimnis wird (teilweise) enthüllt."),
    (3, "Eine wichtige Ressource oder Gelegenheit wird knapp."),
    (2, "Ein Verbündeter wird unzuverlässig oder hat eine eigene Agenda."),
    (2, "Ein unschuldiger Dritter gerät in Gefahr und braucht Hilfe."),
    (2, "Ein moralisches Dilemma erzwingt eine Abwägung."),
    (2, "Eine frühere Entscheidung des Spielers zeigt jetzt Folgen."),
    (2, "Ein Zeitdruck entsteht (etwas muss schnell geschehen)."),
    (3, "Ein kurzer ruhiger Moment — Gelegenheit für Charaktertiefe."),
]

INTEGRATION_RULE = (
    "Webe dies ORGANISCH und maßvoll ein, skaliert an aktuellem Beat und "
    "Spannung. Es ist eine Komplikation/Würze, KEIN Reset: Makro- und "
    "Substory-Bogen bleiben bestehen und werden nicht verworfen."
)


class StoryDynamics:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self._w = [w for w, _ in STORY_DYNAMICS]
        self._t = [t for _, t in STORY_DYNAMICS]

    def roll(self) -> str:
        return self.rng.choices(self._t, weights=self._w, k=1)[0]

    def maybe(self, prob: float) -> str | None:
        return self.roll() if self.rng.random() < max(0.0, min(1.0, prob)) else None
