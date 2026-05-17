"""Zwei Default-Welten (Vollbeispiele aller Felder).
`storyteller seed` schreibt sie nach data/worlds/."""

from __future__ import annotations

import json
from pathlib import Path

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
    World,
)

SCIFI = World(
    id="sternenfahrt",
    name="Sternenfahrt",
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
    wait_sound="scifi_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.45, reverb_wet_level=0.15),
)

FANTASY = World(
    id="immerwald",
    name="Das Immerwald-Reich",
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
    wait_sound="fantasy_ambient.wav",
    fx_preset=FXPreset(reverb_room_size=0.7, reverb_wet_level=0.22),
)

SEED_WORLDS: list[World] = [SCIFI, FANTASY]


def write_seed(worlds_dir: Path) -> list[Path]:
    worlds_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for w in SEED_WORLDS:
        p = worlds_dir / f"{w.id}.json"
        p.write_text(json.dumps(w.model_dump(), ensure_ascii=False, indent=2))
        written.append(p)
    return written
