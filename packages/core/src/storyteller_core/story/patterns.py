"""Substory beat patterns + per-world complexity.

A curated catalog of story structures (researched: Three-Act, Freytag,
Hero's Journey, Harmon Story Circle, Kishōtenketsu, Seven-Point, Fichtean,
plus interactive-friendly Try/Fail, Mystery, Heist, Monster-of-the-week,
Vignette). A per-world `complexity` (simple|standard|rich) selects which
patterns are allowed, the beat-count cap and the tension cap. A world may
also whitelist explicit patterns via `story_patterns`.

Each pattern beat = (archetype, goal hint, target tension 0-10). The
SubstoryPlanner instantiates the skeleton with world-concrete content.
"""

from __future__ import annotations

import random

# name -> {shape, beats:[(archetype, goal, tension)]}
PATTERNS: dict[str, dict] = {
    "three_act": {"shape": "Klassisch: Setup, Konfrontation, Auflösung.",
                  "beats": [("Setup", "Lage & Ziel etablieren", 2),
                            ("Konfrontation", "Hindernis zuspitzen", 7),
                            ("Auflösung", "Entscheidung & Folge", 4)]},
    "freytag": {"shape": "Fünf-Akt-Pyramide.",
                "beats": [("Exposition", "Welt & Figuren", 2),
                          ("Steigende Handlung", "Komplikation", 5),
                          ("Höhepunkt", "Wendepunkt", 9),
                          ("Fallende Handlung", "Konsequenzen", 5),
                          ("Auflösung", "neues Gleichgewicht", 3)]},
    "heros_journey": {"shape": "Verkürzte Heldenreise (innere Wandlung).",
                      "beats": [("Ruf", "Aufbruch-Anstoß", 3),
                                ("Schwelle", "Eintritt ins Unbekannte", 4),
                                ("Prüfungen", "Verbündete/Feinde", 6),
                                ("Tiefpunkt", "Niederlage/Opfer", 8),
                                ("Belohnung", "Erkenntnis/Sieg", 9),
                                ("Rückkehr", "verändert zurück", 4)]},
    "story_circle": {"shape": "Harmon-Kreis (Komfort→Bedürfnis→…→Wandel).",
                     "beats": [("Vertraut", "Status quo", 2),
                               ("Bedürfnis", "etwas fehlt", 3),
                               ("Aufbruch", "unbekannte Lage", 5),
                               ("Suche", "Anpassung/Preis", 7),
                               ("Fund", "bekommt, was es wollte", 8),
                               ("Preis", "harte Kosten", 9),
                               ("Rückkehr", "zurück, verändert", 4)]},
    "kishotenketsu": {"shape": "Vier-Akt, KONFLIKTFREI: Twist statt Konflikt.",
                      "beats": [("Ki — Einführung", "ruhig etablieren", 2),
                                ("Shō — Entwicklung", "vertiefen", 3),
                                ("Ten — Wendung", "überraschende neue Sicht",
                                 6),
                                ("Ketsu — Schluss", "harmonischer Abschluss",
                                 3)]},
    "seven_point": {"shape": "Sieben-Punkt: Hook, Turns, Pinches, Midpoint.",
                    "beats": [("Hook", "Ausgangslage", 3),
                              ("Wendepunkt 1", "in die Handlung", 5),
                              ("Pinch 1", "Druck von außen", 6),
                              ("Midpoint", "Wendung zum Aktiven", 7),
                              ("Pinch 2", "größter Druck", 8),
                              ("Wendepunkt 2", "Lösungsschlüssel", 9),
                              ("Auflösung", "Abschluss", 4)]},
    "fichtean": {"shape": "Fichtean: lauter werdende Krisen bis Klimax.",
                 "beats": [("Krise 1", "sofort mitten hinein", 5),
                           ("Krise 2", "Eskalation", 7),
                           ("Krise 3", "Zuspitzung", 8),
                           ("Klimax", "Höhepunkt", 10),
                           ("Auflösung", "kurzer Abschluss", 3)]},
    "try_fail": {"shape": "Ziel, Versuch/Fehlschlag-Zyklen, Erfolg-mit-Preis.",
                 "beats": [("Ziel", "klares Vorhaben", 3),
                           ("Versuch & Fehlschlag", "es geht schief", 6),
                           ("Erneuter Versuch", "neuer Ansatz, härter", 8),
                           ("Erfolg mit Preis", "gelingt, aber kostet", 5)]},
    "mystery": {"shape": "Rätsel: Haken, Spuren, Irrführung, Enthüllung.",
                "beats": [("Haken", "Rätsel/Anomalie", 3),
                          ("Spuren", "Hinweise sammeln", 5),
                          ("Irrführung", "falsche Fährte", 6),
                          ("Enthüllung", "Wahrheit kippt alles", 9),
                          ("Konfrontation", "Auflösung", 5)]},
    "heist": {"shape": "Coup: Plan, Ausführung, Komplikation, Twist.",
              "beats": [("Auftrag", "Ziel & Einsatz", 3),
                        ("Plan", "Vorbereitung", 4),
                        ("Ausführung", "es läuft an", 6),
                        ("Komplikation", "alles geht schief", 9),
                        ("Twist & Abgang", "Wendung, Preis", 5)]},
    "monster_of_week": {"shape": "Episodisch: Störung, Untersuchung, Lösung.",
                        "beats": [("Störung", "etwas stimmt nicht", 4),
                                  ("Untersuchung", "der Sache nachgehen", 6),
                                  ("Konfrontation", "stellen & lösen", 8),
                                  ("Abschluss", "Ruhe kehrt ein", 3)]},
    "vignette": {"shape": "Slice-of-Life: Stimmung, Moment, kleine Wandlung.",
                 "beats": [("Stimmung", "Atmosphäre & Ort", 2),
                           ("Moment", "kleine Begegnung", 3),
                           ("Kleine Wandlung", "leise Veränderung", 3)]},
}

COMPLEXITY: dict[str, dict] = {
    "simple": {"patterns": ["vignette", "three_act", "kishotenketsu",
                            "monster_of_week"],
               "max_beats": 4, "tension_cap": 6},
    "standard": {"patterns": ["three_act", "kishotenketsu", "try_fail",
                              "mystery", "seven_point", "fichtean",
                              "monster_of_week"],
                 "max_beats": 6, "tension_cap": 8},
    "rich": {"patterns": ["heros_journey", "story_circle", "freytag",
                          "seven_point", "fichtean", "heist", "mystery",
                          "try_fail"],
             "max_beats": 99, "tension_cap": 10},
}

COMPLEXITIES = tuple(COMPLEXITY)


def norm_complexity(c: str | None) -> str:
    c = (c or "standard").lower()
    return c if c in COMPLEXITY else "standard"


def world_tone_line(world) -> str:
    """Compact tone + audience line for narrator/planner prompts."""
    t = getattr(world, "tone", None)
    aud = getattr(world, "audience", "") or "—"
    if t is None:
        return f"ZIELGRUPPE: {aud}"
    extra = f" {t.notes}" if getattr(t, "notes", "") else ""
    return (f"TON: düster {t.darkness}/5, Humor {t.humor}/5, "
            f"Romanze {t.romance}/5, Action {t.action}/5, "
            f"Horror {t.horror}/5, Tempo {t.pacing}.{extra} "
            f"ZIELGRUPPE: {aud} (Inhalt & Wortwahl entsprechend anpassen).")


def choose_pattern(world, cfg, rng: random.Random | None = None) -> dict:
    """Pick a pattern for this world; return name/shape/beats/caps."""
    rng = rng or random.Random()
    comp = norm_complexity(getattr(world, "complexity", None)
                           or cfg.story.default_complexity)
    spec = COMPLEXITY[comp]
    allowed = [p for p in (getattr(world, "story_patterns", None) or [])
               if p in PATTERNS] or spec["patterns"]
    name = rng.choice(allowed)
    pat = PATTERNS[name]
    cap = min(int(cfg.story.max_substory_beats), spec["max_beats"])
    beats = pat["beats"][:cap] if len(pat["beats"]) > cap else pat["beats"]
    return {"name": name, "shape": pat["shape"], "beats": beats,
            "tension_cap": spec["tension_cap"], "complexity": comp,
            "n_beats": len(beats)}
