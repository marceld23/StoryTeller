"""Default worlds (full examples of every field), localized de / en.

`storyteller seed` writes them to data/worlds/ (de: <id>.json,
en: <id>.en.json). World ids stay stable across locales so saves keep
working; RAG is isolated per (world_id, locale) in the engine.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..i18n import LOCALES, norm
from .schema import (
    Beat,
    Blueprint,
    Fragment,
    FXPreset,
    GlossaryEntry,
    HistoryEvent,
    Item,
    Person,
    Place,
    RandomEntry,
    RandomTable,
    Tone,
    World,
)

# ---------------- DE (verbatim, unverändert) ----------------

SCIFI = World(
    id="sternenfahrt",
    name="Sternenfahrt",
    display_name="Sternenfahrt",
    genre="Science-Fiction",
    description=(
        "Die Menschheit reist mit Hyperraum-Technologie durch ein Netz aus "
        "vielen besiedelten und unentdeckten Welten. Sprünge sind riskant, "
        "Treibstoff und Crew-Vertrauen sind knapp."
    ),
    player_role="Raumschiffkapitän:in eines unabhängigen Sprungschiffs",
    starting_situation=(
        "Die 'Wanderfalke' liegt mit fast leeren Tanks an Driftstation Kells. "
        "Ein altes, unmögliches Notsignal pulst aus dem Schlund — und Konsul "
        "Mox' Leute sind bereits unterwegs."
    ),
    narration_style=(
        "Cineastisch, nüchtern-technisch mit Wonder-Momenten; kurze Sätze in "
        "Spannung, ruhiger im Schiffsalltag. Du-Anrede an den Kapitän."
    ),
    mood="Einsam, angespannt, von kalter Ehrfurcht vor dem Unbekannten durchzogen.",
    ambience=(
        "Brummen der Reaktoren, Ozon und kalter Kabelstaub, das Ticken "
        "abkühlender Hüllenplatten, sterile Notbeleuchtung, Funken im All."
    ),
    magic_physics=(
        "Keine Magie. Hyperraumsprünge brauchen Helium-3 und exakte "
        "Navigationsfenster; Fehlsprünge altern Materie oder verschlucken "
        "Schiffe. Der 'Schlund' verletzt diese Regeln — niemand weiß, warum."
    ),
    places=[
        Place(name="Brücke der 'Wanderfalke'", description="Kommandozentrale; "
              "Hyperraumkonsole, Sternenkarte.", tags=["schiff", "start"]),
        Place(name="Driftstation Kells", description="Heruntergekommene "
              "Handels- und Schmugglerstation am Rand des kartierten Raums.",
              tags=["station", "handel"]),
        Place(name="Der Schlund", description="Anomales Hyperraum-Gebiet, aus "
              "dem Schiffe verändert oder gar nicht zurückkehren.",
              tags=["anomalie", "gefahr"]),
    ],
    persons=[
        Person(name="Navigatorin Suri Vael", role="Crew",
                description="Brillante, sarkastische Hyperraum-Navigatorin.",
                relations="vertraut dem Kapitän, misstraut der Reederei."),
        Person(name="Konsul Adran Mox", role="Antagonist",
                description="Einflussreicher Reederei-Konsul mit verdeckter "
                            "Agenda.", relations="will die Route zum Schlund."),
    ],
    items=[
        Item(name="Helium-3-Zelle", description="Treibstoffkanister für Sprünge.",
             properties="1 Zelle = 1 sicherer Sprung; knapp und teuer.",
             tags=["ressource"]),
        Item(name="Echo-Rekorder", description="Speichert das stille Signal.",
             properties="Spielt eine Sprache ab, die es nicht geben dürfte.",
             tags=["hinweis", "mystery"]),
    ],
    glossary=[
        GlossaryEntry(term="Sprung", definition="Hyperraum-Reise zwischen "
                      "Sternen; benötigt Helium-3 und ein Navigationsfenster."),
        GlossaryEntry(term="Der Schlund", definition="Anomalie, in der die "
                      "Hyperraum-Regeln versagen."),
        GlossaryEntry(term="Reederei", definition="Mächtiges Konsortium, das "
                      "Routen und Treibstoff kontrolliert."),
        GlossaryEntry(term="Driftstation", definition="Frei treibender "
                      "Handelsposten am Rand des kartierten Raums."),
    ],
    history=[
        HistoryEvent(when="vor 200 Jahren", title="Die Erste Expansion",
                     description="Hyperraumantrieb erfunden; Hunderte Welten "
                                 "besiedelt."),
        HistoryEvent(when="vor 12 Jahren", title="Das Kells-Unglück",
                     description="Eine Sprungflotte verschwand nahe dem "
                                 "Schlund; seither Sperrgebiet."),
    ],
    fragments=[
        Fragment(title="Das stille Signal", text="Ein uraltes Notsignal pulst "
                 "aus dem Schlund — in einer Sprache, die es nicht geben "
                 "dürfte.", tags=["hook", "mystery"]),
        Fragment(title="Treibstoff-Knappheit", text="Ohne Helium-3 von Kells "
                 "kein weiterer Sprung.", tags=["stakes"]),
    ],
    blueprint=Blueprint(
        premise="Der Kapitän muss dem stillen Signal folgen, bevor Konsul Mox "
                "den Schlund für sich vereinnahmt.",
        beats=[
            Beat(name="Aufbruch", goal="Schiff & Crew etablieren, Hook setzen",
                 tension=2),
            Beat(name="Komplikation", goal="Treibstoffnot, Mox' Druck",
                 tension=4),
            Beat(name="Wendung", goal="Wahrheit hinter dem Signal andeuten",
                 tension=6),
            Beat(name="Krise", goal="Sprung in den Schlund, Verrat", tension=8),
            Beat(name="Höhepunkt", goal="Entscheidung mit Konsequenzen",
                 tension=10),
            Beat(name="Ausklang", goal="Folgen, Haken für Fortsetzung",
                 tension=3),
        ],
    ),
    random_tables=[
        RandomTable(name="Hyperraum-Anomalie", description="Beim Sprung",
                    entries=[
                        RandomEntry(weight=3, text="Zeitdilatation: Stunden "
                                    "werden Tage."),
                        RandomEntry(weight=2, text="Geisterecho eines fremden "
                                    "Schiffs."),
                        RandomEntry(weight=1, text="Der Schlund flüstert einen "
                                    "Namen."),
                    ]),
        RandomTable(name="Stationsbegegnung", description="Auf Kells",
                    entries=[
                        RandomEntry(weight=2, text="Ein Informant mit halber "
                                    "Wahrheit."),
                        RandomEntry(weight=2, text="Kopfgeldjäger im Auftrag "
                                    "von Mox."),
                        RandomEntry(weight=1, text="Ein gestrandeter "
                                    "Xeno-Archäologe."),
                    ]),
    ],
    complexity="standard",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=1, action=4, horror=2,
              pacing="medium"),
    wait_sound="scifi_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.45, reverb_wet_level=0.15),
)

FANTASY = World(
    id="immerwald",
    name="Das Immerwald-Reich",
    display_name="Immerwald",
    genre="High-Fantasy",
    description=(
        "Eine epische High-Fantasy-Welt: uralte Wälder, zerfallende "
        "Königreiche, schlafende Mächte. Magie ist selten, gefährlich, teuer."
    ),
    player_role="Waldläufer:in im Dienst eines bedrohten Grenzlandes",
    starting_situation=(
        "Im Immerwald schweigt plötzlich alles Getier. Hauptmann Eldra Vunn "
        "schickt dich von der Graufeste los, um herauszufinden, wer die alten "
        "Pakte bricht — bevor der Aschenkönig erwacht."
    ),
    narration_style=(
        "Episch, bildreich, mit Sagen-Ton; sinnliche Naturbeschreibung, "
        "bedrohliche Untertöne. Du-Anrede an den Waldläufer."
    ),
    mood="Ehrfürchtig, schwermütig, von lauernder Bedrohung durchzogen.",
    ambience=(
        "Moos und nasses Laub, Harzduft, fernes Knacken, gedämpftes Licht "
        "durch uralte Kronen, Stille, in der man den eigenen Herzschlag hört."
    ),
    magic_physics=(
        "Magie speist sich aus alten Pakten mit dem Wald und der Anderswelt. "
        "Jeder Zauber fordert einen Preis (Erinnerung, Zeit, Blut). Eisen "
        "stört Feenmagie; Mondsteinorte machen die Grenze zur Anderswelt dünn."
    ),
    places=[
        Place(name="Die Graufeste", description="Letzte Grenzbastion vor dem "
              "Immerwald; müde Garnison, alte Geheimnisse.",
              tags=["start", "festung"]),
        Place(name="Der Immerwald", description="Endloser, uralter Wald, der "
              "sich zu erinnern und zu beobachten scheint.",
              tags=["wildnis", "mystisch"]),
        Place(name="Mondsteinlichtung", description="Ort alter Riten, wo die "
              "Grenze zur Anderswelt dünn ist.", tags=["magie", "gefahr"]),
    ],
    persons=[
        Person(name="Hauptmann Eldra Vunn", role="Mentor",
                description="Vernarbte Kommandantin der Graufeste.",
                relations="schickt den Waldläufer auf gefährliche Pfade."),
        Person(name="Der Aschenkönig", role="Antagonist",
                description="Wiederkehrende, halb vergessene Macht aus dem "
                            "Herzen des Waldes.",
                relations="will die alten Pakte brechen."),
    ],
    items=[
        Item(name="Eisendolch der Graufeste", description="Schlichte alte "
             "Klinge.", properties="Stört Feenmagie; bricht kleine Bann.",
             tags=["waffe"]),
        Item(name="Mondstein-Amulett", description="Bleich schimmernder Stein.",
             properties="Zeigt nahe Anderswelt-Grenzen; zieht aber Blicke "
                        "von dort an.", tags=["magie", "hinweis"]),
    ],
    glossary=[
        GlossaryEntry(term="Die Pakte", definition="Uralte Verträge zwischen "
                      "Menschen, Wald und Anderswelt, die die Mächte binden."),
        GlossaryEntry(term="Anderswelt", definition="Geisterhafte Parallelwelt "
                      "hinter dünnen Grenzorten."),
        GlossaryEntry(term="Waldläufer", definition="Grenzkundschafter, "
                      "Vermittler zwischen Feste und Wildnis."),
        GlossaryEntry(term="Aschenkönig", definition="Schlafende Macht im "
                      "Herzen des Immerwalds; erwacht, wenn die Pakte brechen."),
    ],
    history=[
        HistoryEvent(when="im Ersten Zeitalter", title="Der Große Pakt",
                     description="Mensch und Wald schlossen Frieden; der "
                                 "Aschenkönig wurde gebunden."),
        HistoryEvent(when="vor drei Generationen", title="Der Brand der "
                     "Westmark", description="Ein gebrochener Pakt ließ ein "
                                 "Königreich in Asche fallen."),
    ],
    fragments=[
        Fragment(title="Die verstummten Vögel", text="Im Immerwald schweigt "
                 "alles Getier — etwas Altes erwacht.", tags=["hook", "omen"]),
        Fragment(title="Der gebrochene Pakt", text="Ein Grenzstein der alten "
                 "Verträge wurde zerschlagen.", tags=["stakes"]),
    ],
    blueprint=Blueprint(
        premise="Der Waldläufer muss herausfinden, wer die alten Pakte "
                "bricht, bevor der Aschenkönig erwacht.",
        beats=[
            Beat(name="Ruf", goal="Grenzland & Omen etablieren", tension=2),
            Beat(name="Schwelle", goal="Aufbruch in den Immerwald", tension=4),
            Beat(name="Prüfung", goal="Verbündete/Feinde, Spur des Paktbruchs",
                 tension=6),
            Beat(name="Abgrund", goal="Mondsteinlichtung, Verrat/Opfer",
                 tension=8),
            Beat(name="Höhepunkt", goal="Konfrontation mit dem Aschenkönig",
                 tension=10),
            Beat(name="Heimkehr", goal="Preis des Sieges, neue Bedrohung",
                 tension=3),
        ],
    ),
    random_tables=[
        RandomTable(name="Waldzeichen", description="Beim Reisen im Immerwald",
                    entries=[
                        RandomEntry(weight=3, text="Frische Spuren, die im "
                                    "Kreis führen."),
                        RandomEntry(weight=2, text="Ein Schrein mit frischer "
                                    "Opfergabe."),
                        RandomEntry(weight=1, text="Eine Stimme ruft deinen "
                                    "wahren Namen."),
                    ]),
        RandomTable(name="Begegnung am Pfad",
                    entries=[
                        RandomEntry(weight=2, text="Eine fliehende Familie aus "
                                    "dem Wald."),
                        RandomEntry(weight=2, text="Ein Späher des "
                                    "Aschenkönigs."),
                        RandomEntry(weight=1, text="Ein sprechendes Tier mit "
                                    "einer Bitte."),
                    ]),
    ],
    complexity="rich",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=2, action=3, horror=2,
              pacing="medium"),
    wait_sound="fantasy_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.7, reverb_wet_level=0.22),
)

# ---------------- EN (translations; ids unchanged) ----------------

SCIFI_EN = World(
    id="sternenfahrt",
    name="Starfaring",
    genre="Science Fiction",
    description=(
        "Humanity travels by hyperspace technology through a web of many "
        "settled and undiscovered worlds. Jumps are risky; fuel and crew "
        "trust are scarce."
    ),
    player_role="Captain of an independent jump ship",
    starting_situation=(
        "The 'Wanderfalcon' sits with nearly empty tanks at Drift Station "
        "Kells. An old, impossible distress signal pulses from the Maw — and "
        "Consul Mox's people are already on their way."
    ),
    narration_style=(
        "Cinematic, soberly technical with moments of wonder; short sentences "
        "under tension, calmer in shipboard routine. Address the captain as "
        "'you'."
    ),
    mood="Lonely, tense, shot through with cold awe of the unknown.",
    ambience=(
        "Humming reactors, ozone and cold cable dust, the ticking of cooling "
        "hull plates, sterile emergency lighting, sparks in the void."
    ),
    magic_physics=(
        "No magic. Hyperspace jumps need helium-3 and exact navigation "
        "windows; misjumps age matter or swallow ships. The 'Maw' breaks "
        "these rules — no one knows why."
    ),
    places=[
        Place(name="Bridge of the 'Wanderfalcon'", description="Command "
              "center; hyperspace console, star map.",
              tags=["ship", "start"]),
        Place(name="Drift Station Kells", description="Run-down trading and "
              "smuggler station at the edge of charted space.",
              tags=["station", "trade"]),
        Place(name="The Maw", description="Anomalous hyperspace region from "
              "which ships return changed, or not at all.",
              tags=["anomaly", "danger"]),
    ],
    persons=[
        Person(name="Navigator Suri Vael", role="Crew",
                description="Brilliant, sarcastic hyperspace navigator.",
                relations="trusts the captain, distrusts the Line."),
        Person(name="Consul Adran Mox", role="Antagonist",
                description="Influential shipping-Line consul with a hidden "
                            "agenda.", relations="wants the route to the Maw."),
    ],
    items=[
        Item(name="Helium-3 cell", description="Fuel canister for jumps.",
             properties="1 cell = 1 safe jump; scarce and expensive.",
             tags=["resource"]),
        Item(name="Echo recorder", description="Stores the silent signal.",
             properties="Plays back a language that should not exist.",
             tags=["clue", "mystery"]),
    ],
    glossary=[
        GlossaryEntry(term="Jump", definition="Hyperspace travel between "
                      "stars; needs helium-3 and a navigation window."),
        GlossaryEntry(term="The Maw", definition="Anomaly where the "
                      "hyperspace rules fail."),
        GlossaryEntry(term="The Line", definition="Powerful consortium that "
                      "controls routes and fuel."),
        GlossaryEntry(term="Drift Station", definition="Free-floating trading "
                      "post at the edge of charted space."),
    ],
    history=[
        HistoryEvent(when="200 years ago", title="The First Expansion",
                     description="Hyperdrive invented; hundreds of worlds "
                                 "settled."),
        HistoryEvent(when="12 years ago", title="The Kells Disaster",
                     description="A jump fleet vanished near the Maw; a "
                                 "no-go zone ever since."),
    ],
    fragments=[
        Fragment(title="The silent signal", text="An ancient distress signal "
                 "pulses from the Maw — in a language that should not exist.",
                 tags=["hook", "mystery"]),
        Fragment(title="Fuel shortage", text="Without helium-3 from Kells, no "
                 "further jump.", tags=["stakes"]),
    ],
    blueprint=Blueprint(
        premise="The captain must follow the silent signal before Consul Mox "
                "claims the Maw for himself.",
        beats=[
            Beat(name="Departure", goal="Establish ship & crew, set the hook",
                 tension=2),
            Beat(name="Complication", goal="Fuel crisis, Mox's pressure",
                 tension=4),
            Beat(name="Turn", goal="Hint at the truth behind the signal",
                 tension=6),
            Beat(name="Crisis", goal="Jump into the Maw, betrayal", tension=8),
            Beat(name="Climax", goal="A decision with consequences",
                 tension=10),
            Beat(name="Aftermath", goal="Fallout, hook for a sequel",
                 tension=3),
        ],
    ),
    random_tables=[
        RandomTable(name="Hyperspace Anomaly", description="During a jump",
                    entries=[
                        RandomEntry(weight=3, text="Time dilation: hours "
                                    "become days."),
                        RandomEntry(weight=2, text="Ghost echo of an alien "
                                    "ship."),
                        RandomEntry(weight=1, text="The Maw whispers a name."),
                    ]),
        RandomTable(name="Station Encounter", description="On Kells",
                    entries=[
                        RandomEntry(weight=2, text="An informant with half "
                                    "the truth."),
                        RandomEntry(weight=2, text="Bounty hunters working "
                                    "for Mox."),
                        RandomEntry(weight=1, text="A stranded xeno-"
                                    "archaeologist."),
                    ]),
    ],
    complexity="standard",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=1, action=4, horror=2,
              pacing="medium"),
    wait_sound="scifi_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.45, reverb_wet_level=0.15),
)

FANTASY_EN = World(
    id="immerwald",
    name="The Everwood Realm",
    genre="High Fantasy",
    description=(
        "An epic high-fantasy world: ancient forests, crumbling kingdoms, "
        "sleeping powers. Magic is rare, dangerous and costly."
    ),
    player_role="Ranger in the service of a threatened borderland",
    starting_situation=(
        "In the Everwood all creatures suddenly fall silent. Captain Eldra "
        "Vunn sends you out from Grayhold to find who is breaking the old "
        "pacts — before the Ash King wakes."
    ),
    narration_style=(
        "Epic, vivid, with a saga tone; sensory nature description, "
        "menacing undertones. Address the ranger as 'you'."
    ),
    mood="Reverent, melancholy, threaded with lurking threat.",
    ambience=(
        "Moss and wet leaves, scent of resin, distant cracking, dim light "
        "through ancient crowns, a silence in which you hear your own "
        "heartbeat."
    ),
    magic_physics=(
        "Magic draws on old pacts with the forest and the Otherworld. Every "
        "spell exacts a price (memory, time, blood). Iron disturbs fae "
        "magic; moonstone places thin the border to the Otherworld."
    ),
    places=[
        Place(name="Grayhold", description="Last border bastion before the "
              "Everwood; weary garrison, old secrets.",
              tags=["start", "fortress"]),
        Place(name="The Everwood", description="Endless, ancient forest that "
              "seems to remember and to watch.",
              tags=["wilderness", "mystic"]),
        Place(name="Moonstone Glade", description="Place of old rites where "
              "the border to the Otherworld is thin.",
              tags=["magic", "danger"]),
    ],
    persons=[
        Person(name="Captain Eldra Vunn", role="Mentor",
                description="Scarred commander of Grayhold.",
                relations="sends the ranger down dangerous paths."),
        Person(name="The Ash King", role="Antagonist",
                description="Recurring, half-forgotten power from the heart "
                            "of the forest.",
                relations="wants to break the old pacts."),
    ],
    items=[
        Item(name="Iron Dagger of Grayhold", description="A plain old blade.",
             properties="Disturbs fae magic; breaks minor wards.",
             tags=["weapon"]),
        Item(name="Moonstone Amulet", description="Pale shimmering stone.",
             properties="Reveals nearby Otherworld borders; but draws gazes "
                        "from there.", tags=["magic", "clue"]),
    ],
    glossary=[
        GlossaryEntry(term="The Pacts", definition="Ancient treaties between "
                      "humans, forest and Otherworld that bind the powers."),
        GlossaryEntry(term="Otherworld", definition="Ghostly parallel world "
                      "behind thin border places."),
        GlossaryEntry(term="Ranger", definition="Border scout, mediator "
                      "between fort and wilderness."),
        GlossaryEntry(term="Ash King", definition="Sleeping power in the "
                      "heart of the Everwood; wakes when the pacts break."),
    ],
    history=[
        HistoryEvent(when="in the First Age", title="The Great Pact",
                     description="Human and forest made peace; the Ash King "
                                 "was bound."),
        HistoryEvent(when="three generations ago", title="The Burning of the "
                     "Westmark", description="A broken pact left a kingdom in "
                                 "ashes."),
    ],
    fragments=[
        Fragment(title="The silenced birds", text="In the Everwood all "
                 "creatures fall silent — something ancient awakens.",
                 tags=["hook", "omen"]),
        Fragment(title="The broken pact", text="A boundary stone of the old "
                 "treaties was shattered.", tags=["stakes"]),
    ],
    blueprint=Blueprint(
        premise="The ranger must find out who is breaking the old pacts "
                "before the Ash King wakes.",
        beats=[
            Beat(name="Call", goal="Establish borderland & omen", tension=2),
            Beat(name="Threshold", goal="Set out into the Everwood",
                 tension=4),
            Beat(name="Trial", goal="Allies/enemies, trail of the pact-breaking",
                 tension=6),
            Beat(name="Abyss", goal="Moonstone Glade, betrayal/sacrifice",
                 tension=8),
            Beat(name="Climax", goal="Confrontation with the Ash King",
                 tension=10),
            Beat(name="Homecoming", goal="Price of victory, new threat",
                 tension=3),
        ],
    ),
    random_tables=[
        RandomTable(name="Forest Sign", description="When traveling the "
                    "Everwood",
                    entries=[
                        RandomEntry(weight=3, text="Fresh tracks that lead in "
                                    "a circle."),
                        RandomEntry(weight=2, text="A shrine with a fresh "
                                    "offering."),
                        RandomEntry(weight=1, text="A voice calls your true "
                                    "name."),
                    ]),
        RandomTable(name="Encounter on the Path",
                    entries=[
                        RandomEntry(weight=2, text="A family fleeing the "
                                    "forest."),
                        RandomEntry(weight=2, text="A scout of the Ash King."),
                        RandomEntry(weight=1, text="A talking animal with a "
                                    "plea."),
                    ]),
    ],
    complexity="rich",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=2, action=3, horror=2,
              pacing="medium"),
    wait_sound="fantasy_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.7, reverb_wet_level=0.22),
)

SEED_WORLDS = [SCIFI, FANTASY]  # default (de) — Rückwärtskompatibilität
_BY_LOCALE = {
    "de": [SCIFI, FANTASY],
    "en": [SCIFI_EN, FANTASY_EN],
}


def seed_worlds(locale: str = "de") -> list[World]:
    return _BY_LOCALE.get(norm(locale), _BY_LOCALE["de"])


def _fname(world_id: str, locale: str) -> str:
    return f"{world_id}.json" if norm(locale) == "de" \
        else f"{world_id}.{norm(locale)}.json"


def write_seed(worlds_dir: Path) -> list[Path]:
    """Writes all locales: <id>.json (de) and <id>.<loc>.json (others)."""
    worlds_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for loc in LOCALES:
        for w in seed_worlds(loc):
            p = worlds_dir / _fname(w.id, loc)
            p.write_text(json.dumps(w.model_dump(), ensure_ascii=False,
                                    indent=2))
            written.append(p)
    return written
