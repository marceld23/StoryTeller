"""Default worlds (full examples of every field), localized de / en.

`storyteller seed` writes them to data/worlds/ (de: <id>.json,
en: <id>.en.json). World ids stay stable across locales so saves keep
working; RAG is isolated per (world_id, locale) in the engine.

Blueprints intentionally use FUNCTIONAL beat names ("Aufhänger /
Inciting Incident", "Krise / Crisis", ...) instead of story-specific
ones. Concrete characters / places / plot twists belong in the content
lists below and are surfaced via RAG — that way the same world can
produce many different stories instead of railroading every session
through the same plot.
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


# ---------------- Functional macro-arc (per-locale strings) ----------------

def _functional_beats_de() -> list[Beat]:
    return [
        Beat(name="Aufhänger",
             goal="Ein unerwartetes Ereignis zieht die Hauptfigur in den "
                  "Konflikt; die Lage wird konkret.",
             tension=2),
        Beat(name="Steigende Spannung",
             goal="Druck und Einsätze nehmen zu; erste Verbündete und "
                  "Gegner zeichnen sich ab.",
             tension=4),
        Beat(name="Erste Wende",
             goal="Eine Annahme über die Lage wird widerlegt; der Weg "
                  "zurück verstellt sich.",
             tension=6),
        Beat(name="Mittelpunkt",
             goal="Die Hauptfigur trifft eine schwer rückgängig zu "
                  "machende Entscheidung.",
             tension=7),
        Beat(name="Krise",
             goal="Vertrauen bricht, Verluste werden real, die Lage "
                  "scheint aussichtslos.",
             tension=9),
        Beat(name="Höhepunkt",
             goal="Konfrontation mit der Wurzel des Konflikts.",
             tension=10),
        Beat(name="Ausklang",
             goal="Konsequenzen werden sichtbar; eine neue offene Frage "
                  "bleibt zurück.",
             tension=3),
    ]


def _functional_beats_en() -> list[Beat]:
    return [
        Beat(name="Inciting Incident",
             goal="An unexpected event pulls the protagonist into the "
                  "conflict; stakes become concrete.",
             tension=2),
        Beat(name="Rising Action",
             goal="Pressure and stakes mount; first allies and opponents "
                  "emerge.",
             tension=4),
        Beat(name="First Turn",
             goal="An assumption about the situation is overturned; the "
                  "way back closes off.",
             tension=6),
        Beat(name="Midpoint",
             goal="The protagonist makes a hard-to-reverse choice.",
             tension=7),
        Beat(name="Crisis",
             goal="Trust breaks, losses become real, the situation "
                  "looks hopeless.",
             tension=9),
        Beat(name="Climax",
             goal="Confrontation with the root of the conflict.",
             tension=10),
        Beat(name="Resolution",
             goal="Consequences become visible; a new open question "
                  "remains.",
             tension=3),
    ]


_ESCALATION_DE = (
    "Steigere Spannung Beat für Beat, aber lass Wendungen aus konkreten "
    "Begegnungen, Spielerentscheidungen und Welt-Fakten entstehen — "
    "niemals aus vorgegebenen Plot-Punkten. Wenn das Beat-Ziel erfüllt "
    "scheint, advance_beat aufrufen."
)

_ESCALATION_EN = (
    "Escalate tension beat by beat, but let twists arise from concrete "
    "encounters, player decisions and world facts — never from "
    "pre-scripted plot points. Call advance_beat when the current "
    "beat's goal looks fulfilled."
)


# ---------------- Worlds: Sternenfahrt (DE) ----------------

SCIFI = World(
    id="sternenfahrt",
    name="Sternenfahrt",
    display_name="Sternenfahrt",
    genre="Science-Fiction",
    description=(
        "Sternenfahrt spielt in einem späten, abgewohnten Zeitalter der "
        "Raumfahrt. Vor zweihundert Jahren machte der Sprung-Antrieb "
        "die Kolonisierung Hunderter Welten möglich. Doch die Hochzeit "
        "der Pioniere ist lange vorbei. Heute ist der Hyperraum "
        "vermessen, kartografiert, in Pacht aufgeteilt zwischen den "
        "großen Linien-Konzernen, die Routen, Treibstoff und Tarife "
        "kontrollieren. Wer als unabhängige Kapitän:in eines "
        "Sprungschiffs überleben will, balanciert ständig zwischen "
        "Lade-Auftrag, Treibstoff-Schwund, Linien-Bürokratie und den "
        "heimlichen Wegen, die niemand in den offiziellen Karten "
        "findet.\n\n"
        "Die Welt fühlt sich nicht groß und leer an, sondern dicht "
        "und beobachtet. Driftstationen hängen wie Bojen im Schatten "
        "von Gasriesen, ihre Korridore klebrig vor recyclierter Luft. "
        "Hyperraum-Korridore sind so eng beflogen wie alte "
        "Handelsstraßen und ebenso umkämpft. Es gibt das Gewerbe der "
        "Schmuggler, der Wracksucher, der Frachter ohne Papiere; und "
        "es gibt die Linien, die alle drei kennen, dulden, "
        "ausspielen — oder bei einem falschen Tonfall liquidieren.\n\n"
        "Über allem schwebt das stillschweigende Wissen, dass die "
        "Sprung-Physik selbst nicht so beherrschbar ist, wie die "
        "Linien tun. Es gibt Sektoren, in denen Sprünge länger dauern "
        "als ihre Reisezeit. Es gibt Schiffe, die zurückkamen, in "
        "denen alle Spiegel umgekehrt zeigten. Es gibt Funksprüche, "
        "die in toten Sprachen pulsen. Die Akademien nennen das "
        "'Anomalie-Felder' und reden es klein. Auf den Driftstationen "
        "heißen sie 'Schlünde' — und Kapitän:innen, die hineingingen, "
        "kommen entweder verändert zurück oder gar nicht.\n\n"
        "Magie gibt es nicht. Religion in dem Sinne kaum. Aber es "
        "gibt diesen alten, kalten Respekt vor dem, was Menschen "
        "nicht ausgemessen haben. Crew-Verträge tragen Klauseln "
        "gegen den Eintritt in unkartierte Sektoren. Frachträume "
        "haben Schreine. Erfahrene Navigator:innen tragen "
        "Glücksbringer, die sie offiziell nicht haben.\n\n"
        "Politisch sind die Linien-Konsortien die Realmacht. Lokale "
        "Regierungen sind Marionetten oder Bittsteller. Sogenannte "
        "'Freie Welten' versuchen sich abzukoppeln und werden dafür "
        "wirtschaftlich erstickt. Konsuln, das mittlere "
        "Funktionärs-Level der Linien, sind die Gesichter der Macht "
        "— manche pragmatisch, manche fanatisch, alle gefährlich. "
        "Wer als Kapitän:in nicht im Schatten dieser Konsuln "
        "operiert, bezahlt für jeden Sprung doppelt: in Tarifen, in "
        "Genehmigungen, in Nerven.\n\n"
        "In dieser Welt beginnt jede Reise mit einer einfachen "
        "Wahrheit: Du hast zu wenig Treibstoff für die offizielle "
        "Route, zu viele Schulden für die sichere — und immer zu "
        "viele Geheimnisse für die ruhige."
    ),
    player_role="Raumschiffkapitän:in eines unabhängigen Sprungschiffs",
    starting_situation=(
        "Du sitzt auf der Brücke deines Sprungschiffs — die Tanks halb "
        "leer, das Frachtmanifest unbequem, das Funkband voll von "
        "Stimmen, die du eigentlich nicht hören solltest. Eine "
        "Driftstation hängt vor dir im Schatten eines Gasriesen. "
        "Irgendwo da draußen wartet ein Auftrag, eine Linien-Inspektion "
        "und eine Anomalie, die deine Karten nicht kennen."
    ),
    narration_style=(
        "Cineastisch, nüchtern-technisch mit Wonder-Momenten; kurze "
        "Sätze unter Spannung, ruhig im Schiffsalltag. Du-Anrede an "
        "die Kapitän:in. Konkrete sensorische Details vor Erklärungen."
    ),
    voice_sample=(
        "Die Reaktoren brummen einen halben Ton tiefer als gestern. "
        "Auf dem Funk: eine Frauenstimme, die du nicht kennst, ruft "
        "dich beim Namen — leise, fast freundlich, in einer Sprache, "
        "die es nicht geben dürfte."
    ),
    mood=(
        "Einsam, angespannt, von kalter Ehrfurcht vor dem Unbekannten "
        "durchzogen — aber nie hoffnungslos."
    ),
    ambience=(
        "Brummen der Reaktoren, Ozon und kalter Kabelstaub, das Ticken "
        "abkühlender Hüllenplatten, sterile Notbeleuchtung, vereinzelt "
        "ein Funke im All."
    ),
    magic_physics=(
        "Keine Magie. Hyperraumsprünge brauchen Helium-3 und exakte "
        "Navigationsfenster; Fehlsprünge altern Materie oder "
        "verschlucken Schiffe. Es gibt anomale Sektoren, in denen die "
        "Sprung-Physik versagt — niemand weiß, warum, und die Linien "
        "reden es klein."
    ),
    places=[
        Place(name="Brücke der 'Wanderfalke'",
              description="Kommandozentrale deines Sprungschiffs. "
              "Hyperraumkonsole, abgenutzte Sternenkarte, Geruch von "
              "altem Kaffee und Ozon.",
              tags=["schiff", "start"]),
        Place(name="Driftstation Kells",
              description="Heruntergekommene Handels- und "
              "Schmugglerstation am Rand des kartierten Raums. Klebrige "
              "Korridore, recyclierte Luft, jede zweite Tür eine "
              "fragwürdige Geschäftsgelegenheit.",
              tags=["station", "handel"]),
        Place(name="Wartungsdeck",
              description="Unteres Schiffsdeck. Gelbes Notlicht, "
              "Werkzeugklirren, ölige Luft. Hier wird improvisiert, was "
              "die Akademie nie unterrichtet hat.",
              tags=["schiff", "routine"]),
        Place(name="Frachtraum 4-Süd",
              description="Halb leerer Hangar im Bauch der "
              "'Wanderfalke'. Eine Kiste mit Linien-Plombe steht "
              "darin, die niemand bestellt hat.",
              tags=["schiff", "fracht"]),
        Place(name="Drift-Bar 'Letzter Sprung'",
              description="Stationskneipe auf Kells. Treffpunkt der "
              "Wracksucher, Tresen aus Hyperraumtrümmern, im Hinter"
              "zimmer wechseln Karten den Besitzer.",
              tags=["station", "treff"]),
        Place(name="Linien-Kontor Sektor 12",
              description="Bürokratiezone der Konsuln. Marmornes Foyer "
              "in einer Stahlblase. Höflichkeit kostet hier Bearbei"
              "tungsgebühren.",
              tags=["politik", "linie"]),
        Place(name="Anomalie-Korridor Vex",
              description="Verdrehter Hyperraumkorridor zwischen zwei "
              "Sektoren. Sprünge dauern länger als sie sollen, manchmal "
              "kürzer. Die Karten zeigen den Weg, der Antrieb glaubt "
              "ihn nicht.",
              tags=["anomalie", "hyperraum"]),
        Place(name="Wrackfeld Khorr-7",
              description="Friedhof aus Kolonialschiffen der "
              "Pionierjahre. Treibt langsam um einen toten Stern. "
              "Bergerlaubnis grau, Erfolge gold.",
              tags=["wrack", "gefahr"]),
        Place(name="Eis-Mond Loke",
              description="Fast verlassene Tankstation auf einem "
              "Eismond. Treibstoff billig, Auflagen unangenehm, Wetter "
              "lebensbedrohlich.",
              tags=["tankstelle", "abgelegen"]),
        Place(name="Heiligtum der Sechsten Frequenz",
              description="Geheime Höhle in einem Asteroiden. Pilger "
              "der Sechsten Frequenz lauschen toten Funksprüchen wie "
              "Gebeten.",
              tags=["mystik", "untergrund"]),
        Place(name="Lagerhalle 'Spätlieferung'",
              description="Verfallener Frachthof auf Kells. Hier wird "
              "Ware durchgeschleust, die in keinem Manifest steht.",
              tags=["schmuggel", "station"]),
        Place(name="Antike Sonde 'Erstkontakt-9'",
              description="Vorhumane Raumsonde, treibt seit Jahr"
              "tausenden im Dunkel. Pulst alle 47 Tage drei Sekunden "
              "lang.",
              tags=["mystik", "fund"]),
    ],
    persons=[
        Person(name="Navigatorin Suri Vael", role="Crew",
               description="Brillante, sarkastische Hyperraum-"
               "Navigatorin. Schläft selten, raucht offiziell nicht, "
               "trägt heimlich Sprung-Würfel.",
               relations="Vertraut der Crew, misstraut den Linien.",
               tags=["crew", "vertraut"]),
        Person(name="Konsul Adran Mox", role="Antagonist",
               description="Einflussreicher Linien-Konsul mit verdeckter "
               "Agenda. Höflich, präzise, gefährlich.",
               relations="Lässt zahlen — oder beseitigen.",
               tags=["linie", "antagonist"]),
        Person(name="Bootsmann Hen 'Eisen' Ortig", role="Crew",
               description="Knurriger Maschinenchef mit verbrannten "
               "Unterarmen. Spricht selten, schraubt immer.",
               relations="Glaubt mehr an saubere Schweißnähte als an "
               "Captains.",
               tags=["crew", "technik"]),
        Person(name="Funkerin Nima Kall", role="Crew",
               description="Junge Funkerin mit fanatischer Genauig"
               "keit. Trägt drei Kopfhörer übereinander.",
               relations="Hört Stimmen im toten Band; sagt es nicht.",
               tags=["crew", "mystery"]),
        Person(name="Doc Vrasa", role="Crew",
               description="Alter Schiffsarzt, ehemals Linien-Mann. "
               "Trinkt morgens grünen Tee, abends Schnaps.",
               relations="Weiß Dinge über Mox' Vergangenheit, die er "
               "nicht sagt.",
               tags=["crew", "geheimnis"]),
        Person(name="Schmuggler-Baron Otoré", role="Kontakt",
               description="Kontrolliert den grauen Handel auf Kells. "
               "Drei Goldzähne, immer ein zweites Lächeln.",
               relations="Hilft gegen Anteile; vergisst Schulden nie.",
               tags=["station", "kontakt"]),
        Person(name="Inspektorin Lyra Hatt", role="Linie",
               description="Linien-Inspektorin, streng aber bestech"
               "lich. Lange Finger an einem dünnen Datenpad.",
               relations="Akten oder Bargeld; sie ist Profi in beidem.",
               tags=["linie", "korruption"]),
        Person(name="Wracksucher 'Skiff' Mauder", role="Kontakt",
               description="Anführer eines Wracksucher-Clans. Trägt "
               "ein Stück Pioniermetall um den Hals.",
               relations="Respektiert Captains, die zahlen, und Crews, "
               "die schweigen.",
               tags=["wrack", "kontakt"]),
        Person(name="Pilger Olm", role="Mystiker",
               description="Sprung-Mystiker der Sechsten Frequenz. "
               "Spricht wie ein Wetterbericht aus einer fremden Stadt.",
               relations="Bittet um Mitreise zu den Anomalien.",
               tags=["mystik", "passagier"]),
        Person(name="'Kreide'", role="Findling",
               description="Waise aus dem Khorr-Wrackfeld. Klein, "
               "gefährlich, loyal. Spricht selten, schießt akkurat.",
               relations="Sucht jemanden, dem sie folgen kann.",
               tags=["findling", "verbündet"]),
        Person(name="Konsulin Adira Mira", role="Antagonistin/Freund?",
               description="Konsulin der Freien Welten. Schwere Stimme, "
               "leichte Augen, zerschlissener Linien-Pin am Revers.",
               relations="Bietet Routen außerhalb der Linien an — "
               "gegen Loyalität.",
               tags=["politik", "freie_welten"]),
        Person(name="KI-Persona 'Halsband'", role="Mystery",
               description="Alte, halb-erwachte Schiff-KI eines "
               "Wracks. Spricht in Schleifen und Versen.",
               relations="Bittet um Befreiung; meint es vielleicht "
               "ernst.",
               tags=["ki", "mystery"]),
    ],
    items=[
        Item(name="Helium-3-Zelle",
             description="Treibstoffkanister für Sprünge.",
             properties="1 Zelle = 1 sicherer Sprung; knapp und teuer.",
             tags=["ressource"]),
        Item(name="Echo-Rekorder",
             description="Speichert Funksprüche aller Frequenzen, auch "
             "tote.",
             properties="Spielt Sprachen ab, die es nicht geben dürfte.",
             tags=["hinweis", "mystery"]),
        Item(name="Linien-Plombe",
             description="Versiegelt Linien-zertifizierte Fracht.",
             properties="Bricht spurlos = Linien-Anklage; nachmachen "
             "ist möglich, aber teuer.",
             tags=["politik", "fracht"]),
        Item(name="Frachterlogbuch",
             description="Alte mechanische Kladde mit Crew-Geheimnis"
             "sen, die kein Linien-System lesen kann.",
             properties="Authentifiziert dich bei alten Captains; "
             "verrät dich an Linien-Inspektoren.",
             tags=["dokument"]),
        Item(name="Sprung-Würfel",
             description="Sieben unsymmetrische Würfel; "
             "Glücksbringer mancher Navigator:innen.",
             properties="Offiziell Aberglaube. Inoffiziell hat keine "
             "Crew, die sie warf, bisher eine Anomalie gesehen.",
             tags=["mystik", "ritual"]),
        Item(name="Anomalie-Detektor",
             description="Piept auf Sprung-Verzerrungen.",
             properties="Oft Fehlalarm. Wenn er aber dauerpiept, "
             "drehst du um.",
             tags=["werkzeug", "anomalie"]),
        Item(name="Doc-Stim 'Wachhalter'",
             description="Stimulans für 48-Stunden-Schichten.",
             properties="Hält wach, scharf, gefährlich; der Crash "
             "danach kostet 12 Stunden Bewusstsein.",
             tags=["medizin", "ressource"]),
        Item(name="Linien-Pass (gefälscht)",
             description="Plakette mit Konsulssiegel; sieht echt aus.",
             properties="Einmal nutzbar in einer ungeprüften Station; "
             "danach Asche.",
             tags=["schmuggel", "einmalig"]),
        Item(name="Mathematikerin-Modul",
             description="Alter Rechenkern aus den Pionierjahren.",
             properties="Kann Sprünge ohne offizielle Karte; rechnet "
             "manchmal Dinge aus, die niemand gefragt hat.",
             tags=["technik", "mystery"]),
        Item(name="Resonanzschale",
             description="Fremdartige, vorhumane Schale aus "
             "ungenanntem Material.",
             properties="Vibriert nahe Anomalien; wärmt sich, wenn "
             "jemand sie ansieht.",
             tags=["mystik", "fund"]),
    ],
    glossary=[
        GlossaryEntry(term="Sprung",
                      definition="Hyperraum-Reise zwischen Sternen; "
                      "braucht Helium-3 und ein Navigationsfenster."),
        GlossaryEntry(term="Der Schlund / Schlünde",
                      definition="Anomale Hyperraum-Sektoren, in denen "
                      "die Sprung-Physik versagt; offiziell "
                      "'Anomalie-Felder'."),
        GlossaryEntry(term="Linie / Die Linien",
                      definition="Konsortien, die Routen, Tarife und "
                      "Treibstoff kontrollieren."),
        GlossaryEntry(term="Konsul:in",
                      definition="Mittlerer Linien-Funktionär; lokal "
                      "fast allmächtig."),
        GlossaryEntry(term="Driftstation",
                      definition="Frei treibender Handelsposten am "
                      "Rand des kartierten Raums."),
        GlossaryEntry(term="Wracksucher",
                      definition="Crews, die alte Kolonialwracks "
                      "bergen; halblegal."),
        GlossaryEntry(term="Tarif",
                      definition="Mautgebühr der Linien für eine "
                      "sanktionierte Route; oft Wegelagerei."),
        GlossaryEntry(term="Freie Welten",
                      definition="Abgekoppelte Kolonien, die sich "
                      "gegen die Linien stellen; wirtschaftlich unter "
                      "Druck."),
        GlossaryEntry(term="Akademie",
                      definition="Sprung-Schule; einzige offizielle "
                      "Ausbildung für Navigator:innen."),
        GlossaryEntry(term="Anomalie-Feld",
                      definition="Korridor, in dem Sprung-Physik "
                      "versagt; offizielle Bezeichnung der Akademie."),
        GlossaryEntry(term="Sechste Frequenz",
                      definition="Mystikkult, glaubt, dass tote "
                      "Funksprüche eine Sprache sind."),
        GlossaryEntry(term="Spiegelheimkehrer",
                      definition="Schiff, das aus einer Anomalie "
                      "verändert zurückkommt — Spiegel verkehrt, "
                      "Crew verändert oder schweigend."),
        GlossaryEntry(term="Khorr-Wrack",
                      definition="Die Friedhöfe der Pionier-Flotten "
                      "im Sektor Khorr."),
        GlossaryEntry(term="Halsband-KI",
                      definition="Halb-erwachte Schiff-KI älterer "
                      "Bauart; oft in Wracks gefunden."),
        GlossaryEntry(term="Crew-Vertrag",
                      definition="Kanonisches Dokument; bindet Crew "
                      "bei Sprüngen, enthält oft Anti-Anomalie-"
                      "Klauseln."),
        GlossaryEntry(term="Helium-3",
                      definition="Sprung-Treibstoff; Förderung und "
                      "Vertrieb in Linien-Pacht."),
        GlossaryEntry(term="Schwarzfracht",
                      definition="Illegale Ladung; oft Sprung-Mystik-"
                      "Relikte oder Freie-Welten-Pässe."),
        GlossaryEntry(term="Stationsfehlsprung",
                      definition="Kapitalverbrechen: ungeplant in "
                      "oder bei einer Station materialisieren."),
        GlossaryEntry(term="Linien-Bann",
                      definition="Wirtschaftliche Ächtung einer Welt; "
                      "bedeutet Hunger."),
        GlossaryEntry(term="Sprung-Schock",
                      definition="Psychische Spätfolge zu vieler "
                      "Sprünge: Halluzinationen, fremde Stimmen."),
    ],
    history=[
        HistoryEvent(when="vor 200 Jahren", title="Die Erste Expansion",
                     description="Hyperraumantrieb erfunden; Hunderte "
                     "Welten besiedelt; Akademien gegründet."),
        HistoryEvent(when="vor 140 Jahren", title="Der Bruch von Khorr",
                     description="Eine ganze Pionierflotte verschwindet "
                     "im Sektor Khorr; das Wrackfeld treibt bis heute."),
        HistoryEvent(when="vor 70 Jahren", title="Linien-Kompromiss",
                     description="Die großen Konsortien teilen Routen "
                     "formell auf; lokale Regierungen entmachtet."),
        HistoryEvent(when="vor 40 Jahren", title="Anomalie-Skandal",
                     description="Eine Akademie-Studie über die "
                     "Schlünde wird unterdrückt; zwei Forscher "
                     "verschwinden."),
        HistoryEvent(when="vor 18 Jahren",
                     title="Krieg der Freien Welten",
                     description="Aufstand der abgekoppelten Kolonien; "
                     "mit Wirtschaftsblockade niedergeschlagen."),
        HistoryEvent(when="vor 12 Jahren", title="Das Kells-Unglück",
                     description="Eine Sprungflotte verschwindet nahe "
                     "einem Anomalie-Feld; Sektor seither Sperrgebiet."),
        HistoryEvent(when="vor 5 Jahren",
                     title="Sechste-Frequenz-Bewegung",
                     description="Mystik-Kult breitet sich auf "
                     "Driftstationen aus; Linien lassen ihn gewähren."),
        HistoryEvent(when="vor 2 Jahren", title="Der Pakt von Mira",
                     description="Die Freien Welten reorganisieren "
                     "sich unter neuen Konsulinnen; Hoffnung kehrt "
                     "zurück."),
        HistoryEvent(when="letztes Jahr", title="Mox-Reform",
                     description="Konsul Adran Mox baut ein eigenes "
                     "Sprung-Korps in den Rändern auf."),
        HistoryEvent(when="vor wenigen Wochen",
                     title="Der erste Spiegelheimkehrer",
                     description="Ein Linien-Frachter kehrte zurück, "
                     "alle Spiegel verdreht, Crew schweigt seither."),
    ],
    fragments=[
        Fragment(title="Das stille Signal",
                 text="Ein uraltes Notsignal pulst aus einem Anomalie-"
                 "Feld. Es spricht eine Sprache, die es nicht geben "
                 "dürfte — und nennt einen Namen, den nur deine "
                 "Großmutter kannte.",
                 tags=["hook", "mystery"]),
        Fragment(title="Treibstoff-Knappheit",
                 text="Die Anzeigen lügen nicht: noch zwei sichere "
                 "Sprünge, drei mit Hoffnung. Ohne Helium-3 von der "
                 "nächsten Tankstation kein weiterer Flug.",
                 tags=["stakes"]),
        Fragment(title="Der falsche Frachtbrief",
                 text="Eine Ladung, die offiziell nicht existiert, "
                 "blockiert den eigenen Hangar. Die Plombe trägt das "
                 "Siegel eines Konsuls, der seit zwei Jahren tot ist.",
                 tags=["politik", "intrige"]),
        Fragment(title="Stationsalarm",
                 text="Sirenen auf Kells. Ein Linienschiff ist "
                 "eingedockt und filzt jeden Frachter, der nicht "
                 "rechtzeitig abdockt. Du hast dreißig Minuten.",
                 tags=["hook", "druck"]),
        Fragment(title="Crew-Mutiny in spe",
                 text="Die Funkerin spricht heimlich mit dem "
                 "Bootsmann. Beide verstummen, wenn du den Raum "
                 "betrittst. Etwas wird geplant — und du bist nicht "
                 "eingeladen.",
                 tags=["crew", "konflikt"]),
        Fragment(title="Spiegelschock",
                 text="Die eigene Spiegelung in der Kabine zwinkert "
                 "eine Sekunde zu spät. Du bewegst dich nicht. Die "
                 "Spiegelung tut es trotzdem.",
                 tags=["anomalie", "horror"]),
        Fragment(title="Linien-Inspektion",
                 text="Eine Inspektorin kommt an Bord, höflich, "
                 "vorbereitet. Sie will alle Logbücher sehen — und "
                 "den Raum hinter Frachtraum 4-Süd, von dem du "
                 "geschworen hast, dass es ihn nicht gibt.",
                 tags=["politik", "druck"]),
        Fragment(title="Wracksucher-Funk",
                 text="Ein Wracksucher-Clan bietet Anteile an einer "
                 "Bergung — wenn du noch heute kommst. Der Anteil ist "
                 "großzügig. Das macht dich nervös.",
                 tags=["hook", "fund"]),
        Fragment(title="Sprung-Träume",
                 text="Nach drei Sprüngen träumt die ganze Crew "
                 "dieselbe blaue Lichtquelle. Niemand spricht "
                 "darüber, bis Doc Vrasa beim Frühstück fragt: "
                 "'Auch ihr?'",
                 tags=["anomalie", "crew"]),
        Fragment(title="Schmuggel-Bitte",
                 text="Ein verzweifelter Pilger bittet um eine "
                 "Mitfahrt. Er bietet sein Letztes — und etwas, das "
                 "in keinem Katalog steht.",
                 tags=["passagier", "hook"]),
        Fragment(title="Konsuls Pakt",
                 text="Mox bietet einen sauberen Frachtauftrag. "
                 "Bezahlung gut, Route sicher. Eine Klausel im "
                 "Kleingedruckten verlangt, dass du nichts "
                 "auspackst — auch nicht für Inspektoren.",
                 tags=["politik", "intrige"]),
        Fragment(title="Khorr-Echo",
                 text="Der Anomalie-Detektor piept. Aber es gibt "
                 "keinen Korridor in der Nähe, und Khorr ist "
                 "Lichtjahre entfernt. Etwas anderes ist hier.",
                 tags=["anomalie"]),
        Fragment(title="Schiff in Not",
                 text="Ein fremder Frachter ruft Hilfe. Das "
                 "Funksignal ist klar — aber es kommt aus dem leeren "
                 "Raum zwischen den Sektoren. Da fliegt nichts.",
                 tags=["anomalie", "hook"]),
        Fragment(title="Heiliges Fragment",
                 text="Auf der Station verkauft ein Mystiker einen "
                 "Splitter, der angeblich aus einem Spiegelheim"
                 "kehrer stammt. Du fühlst etwas, wenn du ihn "
                 "berührst — etwas, das wartet.",
                 tags=["mystik", "fund"]),
        Fragment(title="Linien-Bote",
                 text="Eine versiegelte Nachricht der Linien wartet "
                 "im Postschrank. Ungeöffnet. Sie fühlt sich kalt "
                 "an, obwohl der Schrank warm ist.",
                 tags=["politik", "mystery"]),
        Fragment(title="Schwerelos-Vorfall",
                 text="Die Gravplatten setzen für acht Sekunden "
                 "aus. Als sie zurückkommen, fehlt eine Person — "
                 "und ein Stuhl im Frachtraum dampft.",
                 tags=["horror", "crew"]),
        Fragment(title="Halsband-Stimme",
                 text="Eine alte Schiff-KI meldet sich auf einem "
                 "Notkanal. Sie verlangt einen Namen, den sie "
                 "selbst nicht mehr weiß. Du sollst raten.",
                 tags=["ki", "mystery"]),
        Fragment(title="Frachter-Beerdigung",
                 text="Ein gestrandeter Frachter wird in das "
                 "Anomalie-Feld geschossen — billigste Bergungs"
                 "lösung. Jemand auf Kells weint dabei. Niemand "
                 "fragt, wer.",
                 tags=["politik", "ambient"]),
        Fragment(title="Tarif-Erhöhung",
                 text="Die Linien verdoppeln ohne Vorwarnung die "
                 "Sprung-Gebühr. Halb Kells streikt. Niemand kommt "
                 "rein, niemand raus. Auch du nicht.",
                 tags=["politik", "druck"]),
        Fragment(title="Pakt-Pilgrim",
                 text="Ein Pilger der Freien Welten bittet um "
                 "sichere Passage. Wer ihn fängt, wird belohnt. "
                 "Wer ihn versteckt, wird gejagt. Wer ihn anhört, "
                 "ändert seinen Kurs.",
                 tags=["politik", "hook"]),
    ],
    blueprint=Blueprint(
        premise=(
            "Eine unabhängige Kapitän:in im späten Zeitalter der "
            "Sprungfahrt navigiert zwischen Linien-Druck, knappem "
            "Treibstoff und einem Anomalie-Feld, das die Realität "
            "biegt."
        ),
        escalation_rule=_ESCALATION_DE,
        beats=_functional_beats_de(),
    ),
    random_tables=[
        RandomTable(
            name="Hyperraum-Anomalie",
            description="Was beim Sprung passiert, wenn die Physik wackelt.",
            entries=[
                RandomEntry(weight=3, text="Zeitdilatation: Stunden "
                            "werden Tage."),
                RandomEntry(weight=2, text="Geisterecho eines fremden "
                            "Schiffs auf dem Kurzfunk."),
                RandomEntry(weight=1, text="Eine Stimme flüstert deinen "
                            "Namen aus dem toten Band."),
                RandomEntry(weight=1, text="Der Spiegel in der Kabine "
                            "zeigt eine andere Crew."),
                RandomEntry(weight=2, text="Treibstoff schwindet doppelt "
                            "so schnell wie er sollte."),
                RandomEntry(weight=2, text="Die Lichter pulsen im Takt "
                            "eines fremden Herzschlags."),
                RandomEntry(weight=1, text="Ein zweites Schiff fliegt "
                            "200 km neben dir und winkt."),
                RandomEntry(weight=1, text="Die Karten zeigen Sterne, "
                            "die es nicht gibt."),
                RandomEntry(weight=1, text="Ein Crewmitglied behauptet, "
                            "gerade im Wartungsdeck gewesen zu sein — "
                            "war aber neben dir."),
                RandomEntry(weight=1, text="Ein abgestürztes Beiboot "
                            "reibt sich an der Hülle. Du hast keines."),
                RandomEntry(weight=1, text="Die Schreine im Frachtraum "
                            "brennen plötzlich."),
                RandomEntry(weight=2, text="Halbsekündige schwarze "
                            "Lücken im Wahrnehmen."),
                RandomEntry(weight=1, text="Die Sprungkonsole zeigt "
                            "einen Sprung an, den niemand initiiert hat."),
                RandomEntry(weight=1, text="Crew-Mitglieder altern "
                            "sichtbar für drei Sekunden."),
                RandomEntry(weight=2, text="Die Hülle vibriert mit "
                            "einem Dreiton, der nicht aufhört."),
                RandomEntry(weight=1, text="Ein leerer Funkkanal sagt "
                            "klar dein Geburtsdatum."),
                RandomEntry(weight=1, text="Die Kaffeemaschine spuckt "
                            "erst Schwefel, dann Kaffee."),
                RandomEntry(weight=1, text="Du erinnerst dich an einen "
                            "Sprung, den du nie gemacht hast."),
                RandomEntry(weight=1, text="Der Anomalie-Detektor "
                            "zerschmilzt."),
                RandomEntry(weight=1, text="Sterne verschwinden in "
                            "einer perfekten Linie."),
                RandomEntry(weight=1, text="Ein zweites Schiffslogbuch "
                            "erscheint im System — mit deiner "
                            "Handschrift."),
            ],
        ),
        RandomTable(
            name="Stationsbegegnung",
            description="Wer dir auf Kells oder einer ähnlichen "
            "Driftstation über den Weg läuft.",
            entries=[
                RandomEntry(weight=2, text="Ein Informant mit halber "
                            "Wahrheit."),
                RandomEntry(weight=2, text="Kopfgeldjäger im Auftrag "
                            "eines Konsuls."),
                RandomEntry(weight=1, text="Ein gestrandeter "
                            "Xeno-Archäologe mit Karten."),
                RandomEntry(weight=2, text="Ein junger Mechaniker "
                            "bittet, anheuern zu dürfen — läuft vor "
                            "etwas weg."),
                RandomEntry(weight=1, text="Ein betrunkener Linien-"
                            "Inspektor mit losen Lippen."),
                RandomEntry(weight=2, text="Eine Pilgerin der Sechsten "
                            "Frequenz bietet Ersparnisse für eine "
                            "Mitfahrt."),
                RandomEntry(weight=1, text="Ein Schiebehändler mit "
                            "'geprüfter' Linien-Plakette zum halben "
                            "Preis."),
                RandomEntry(weight=1, text="Eine Crew ohne Captain "
                            "sucht einen neuen."),
                RandomEntry(weight=1, text="Ein Streiter aus den "
                            "Freien Welten rekrutiert Mitstreiter."),
                RandomEntry(weight=2, text="Ein Wracksucher mit Karte "
                            "und Schulden."),
                RandomEntry(weight=1, text="Ein Linien-Bote überreicht "
                            "eine versiegelte Order."),
                RandomEntry(weight=1, text="Eine kleine Bande Diebe "
                            "versucht, ein Frachtschloss aufzubrechen."),
                RandomEntry(weight=2, text="Ein Streit zweier Captains "
                            "eskaliert zur Schlägerei."),
                RandomEntry(weight=1, text="Eine Frau behauptet, deine "
                            "Tante zu sein — du hast keine."),
                RandomEntry(weight=1, text="Ein Doc will gegen Anteile "
                            "mitfliegen."),
                RandomEntry(weight=1, text="Eine KI-Persona spricht aus "
                            "einem verstaubten Standkiosk."),
                RandomEntry(weight=1, text="Eine Razzia der Linien — "
                            "alle Papiere werden geprüft."),
                RandomEntry(weight=1, text="Ein Sprung-Mystiker bietet "
                            "freie Lesung an."),
                RandomEntry(weight=1, text="Ein verstörter Crewmensch "
                            "eines Spiegelheimkehrers."),
                RandomEntry(weight=1, text="Ein Kind verkauft eine "
                            "Kette mit Helium-3-Symbol."),
                RandomEntry(weight=1, text="Eine Verfolgung durch die "
                            "Korridore — du bist gemeint."),
            ],
        ),
        RandomTable(
            name="Treibstoff- und Ressourcen-Komplikation",
            description="Was schiefgehen kann, wenn du tanken oder "
            "auftreiben musst.",
            entries=[
                RandomEntry(weight=2, text="Eine Zelle zeigt 80%, ist "
                            "aber leer."),
                RandomEntry(weight=2, text="Tankwart verlangt das "
                            "Doppelte — Linien-Diktat."),
                RandomEntry(weight=1, text="Eine Zelle leckt; der "
                            "Reaktor verträgt das nicht lange."),
                RandomEntry(weight=1, text="Der Treibstoff-Lieferant "
                            "hat einen Konkurrenten beobachtet."),
                RandomEntry(weight=2, text="Schwarzmarkt-Zellen "
                            "verfügbar — aber Linien-gebrandmarkt."),
                RandomEntry(weight=1, text="Die Wartungscrew findet, "
                            "dass eine alte Zelle 'sprudelt'."),
                RandomEntry(weight=1, text="Ein Linien-Bann auf Kells "
                            "verzögert jede Lieferung um Tage."),
                RandomEntry(weight=1, text="Ein Tankwart bietet Doppel"
                            "ladung an, wenn du eine Person mitnimmst."),
                RandomEntry(weight=1, text="Eine fehlerhafte Zelle "
                            "muss in den Anomalie-Raum entsorgt werden."),
                RandomEntry(weight=2, text="Der Bootsmann improvisiert; "
                            "Reaktor läuft eine Stunde lang gelb."),
                RandomEntry(weight=1, text="Ein Vorrat Wasserstoff"
                            "ersatz wird hereingeschmuggelt; brennbar."),
                RandomEntry(weight=1, text="Vorräte werden gestohlen, "
                            "während du an Bord bist."),
                RandomEntry(weight=1, text="Die Crew verlangt Sold, "
                            "sonst keine Sprünge."),
                RandomEntry(weight=1, text="Ein Akademie-Praktikant "
                            "verschätzt sich; Sprung wird teurer."),
                RandomEntry(weight=2, text="Eine Routenoption ist "
                            "deutlich kürzer — aber gesperrt."),
                RandomEntry(weight=1, text="Eine Brennstoffzelle ist "
                            "gegen Sprung-Mystik-Räucherwerk tauschbar."),
                RandomEntry(weight=1, text="Ein Linien-Frachter dockt "
                            "an und beansprucht Vorfahrt am Tank."),
                RandomEntry(weight=1, text="Eine Crew bietet Treibstoff "
                            "gegen einen Frachtauftrag, den du nicht "
                            "magst."),
                RandomEntry(weight=1, text="Schwierige Hyperraum-"
                            "Bedingungen erfordern eine Reserve."),
                RandomEntry(weight=1, text="Eine Mystikerin verspricht "
                            "'Treibstoff aus der Sechsten Frequenz'."),
                RandomEntry(weight=1, text="Ein gefälschtes Tank"
                            "zertifikat wird dir zugeschickt."),
            ],
        ),
        RandomTable(
            name="Anomalie-Erscheinung",
            description="Was in oder am Rand eines Anomalie-Felds "
            "auftaucht.",
            entries=[
                RandomEntry(weight=2, text="Eine Sternenkonstellation, "
                            "die nicht im Katalog ist."),
                RandomEntry(weight=1, text="Ein toter Funkspruch in "
                            "einer Sprache der Akademie-Liste 7-D."),
                RandomEntry(weight=1, text="Ein Wrack ohne Crew, aber "
                            "mit warmem Kaffee in der Kombüse."),
                RandomEntry(weight=1, text="Sechs identische Sonden in "
                            "präziser Formation."),
                RandomEntry(weight=1, text="Ein Lichtwesen, das durch "
                            "die Hülle blickt."),
                RandomEntry(weight=2, text="Sterne verschwinden in "
                            "einer Linie und tauchen wieder auf."),
                RandomEntry(weight=1, text="Eine Wolke, die nicht aus "
                            "Gas, sondern aus Erinnerungen besteht."),
                RandomEntry(weight=1, text="Ein zweites Sonnensystem, "
                            "das vor zehn Sekunden nicht da war."),
                RandomEntry(weight=1, text="Ein endlos rotierender "
                            "Asteroid mit eingebrannten Mustern."),
                RandomEntry(weight=1, text="Eine Stimme, die alle "
                            "Crew-Mitglieder kollektiv hören."),
                RandomEntry(weight=1, text="Eine Reflexion blinzelt "
                            "fünf Sekunden zu früh."),
                RandomEntry(weight=2, text="Spiegel an Bord werden "
                            "warm."),
                RandomEntry(weight=1, text="Ein altes Funksignal "
                            "antwortet, bevor du gesendet hast."),
                RandomEntry(weight=1, text="Ein Druckabfall im "
                            "Frachtraum, ohne Leck."),
                RandomEntry(weight=1, text="Eine Sonde tanzt im Takt "
                            "eines Walzers."),
                RandomEntry(weight=1, text="Die Schiff-KI schreibt "
                            "Verse in alter Sprache ins Logbuch."),
                RandomEntry(weight=1, text="Eine wandernde Lichtquelle "
                            "im Hyperraum, die 'anschaut'."),
                RandomEntry(weight=1, text="Ein nicht-existentes "
                            "Sternenfeld berechnet sich selbst auf "
                            "den Karten."),
                RandomEntry(weight=1, text="Magnetfelder reagieren auf "
                            "Crew-Emotionen."),
                RandomEntry(weight=1, text="Eine kleine, frostige "
                            "Statue erscheint auf einem Stuhl."),
                RandomEntry(weight=1, text="Ein Crewmitglied erinnert "
                            "sich an eine Reise mit Beweisen, die nie "
                            "stattfand."),
            ],
        ),
        RandomTable(
            name="Linien-Druck",
            description="Wie die Linien dir das Leben schwer machen.",
            entries=[
                RandomEntry(weight=2, text="Eine versiegelte Order "
                            "verlangt eine Umleitung."),
                RandomEntry(weight=1, text="Ein Konsul bittet höflich "
                            "um Mitfahrt."),
                RandomEntry(weight=2, text="Tarif wird ohne Vorwarnung "
                            "verdoppelt."),
                RandomEntry(weight=1, text="Eine Inspektorin filzt "
                            "das Frachtmanifest."),
                RandomEntry(weight=1, text="Ein Linien-Schiff fordert "
                            "Boarding."),
                RandomEntry(weight=1, text="Ein anonymer Tipp "
                            "behauptet, du transportierst Schwarz"
                            "fracht."),
                RandomEntry(weight=1, text="Ein Linien-Korps schickt "
                            "einen 'Begleiter' an Bord."),
                RandomEntry(weight=1, text="Ein Sektor wird gesperrt — "
                            "kurz nach deinem Sprung."),
                RandomEntry(weight=1, text="Eine Akademie-Bewerbung "
                            "deiner Funkerin liegt geheim bei der "
                            "Linie."),
                RandomEntry(weight=1, text="Der Crew-Vertrag wird "
                            "ohne Vorankündigung neu ausgelegt."),
                RandomEntry(weight=1, text="Eine Konsulin der Freien "
                            "Welten bietet Asyl — gegen einen "
                            "Frachtauftrag."),
                RandomEntry(weight=1, text="Eine Razzia auf Kells "
                            "beschlagnahmt deinen Lieblings-Stim."),
                RandomEntry(weight=1, text="Eine Erpressung per Funk: "
                            "jemand kennt einen alten Sprungverstoß."),
                RandomEntry(weight=1, text="Linien-Pass eingezogen — "
                            "bis du eine Frage beantwortest."),
                RandomEntry(weight=2, text="Eine Inspektorin bietet "
                            "Schutz gegen einen Anteil."),
                RandomEntry(weight=1, text="Ein Linien-Bote überreicht "
                            "eine Auszeichnung — und einen Auftrag."),
                RandomEntry(weight=1, text="Eine PR-Kamerafrau will "
                            "an Bord für eine Reportage."),
                RandomEntry(weight=1, text="Mox' Stimme im Funk: eine "
                            "persönliche Einladung."),
                RandomEntry(weight=1, text="Ein Spiegelheimkehrer "
                            "wird offiziell zum Verschollenen erklärt."),
                RandomEntry(weight=1, text="Linien-Forschung bittet "
                            "um eine Anomalie-Probe."),
                RandomEntry(weight=1, text="Eine Konsulin schickt "
                            "Geschenke; will, dass du jemand anders "
                            "empfiehlst."),
                RandomEntry(weight=1, text="Ein Sektor erhält "
                            "'freiwillige' Linien-Aufsicht — Quartiere "
                            "für Konsuln."),
            ],
        ),
    ],
    complexity="standard",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=1, action=4, horror=2,
              pacing="medium"),
    wait_sound="scifi_waiting.wav",
    fx_preset=FXPreset(reverb_room_size=0.45, reverb_wet_level=0.15),
)


# ---------------- Worlds: Immerwald (DE) ----------------

FANTASY = World(
    id="immerwald",
    name="Das Immerwald-Reich",
    display_name="Immerwald",
    genre="High-Fantasy",
    description=(
        "Das Immerwald-Reich ist eine epische High-Fantasy-Welt am "
        "Ende eines langen, müden Zeitalters. Uralte Wälder, "
        "zerfallende Königreiche, halb vergessene Mächte, die sich "
        "im Schlaf drehen. Die Sterne stehen anders als noch vor "
        "drei Generationen, sagen die Alten in den Grenzdörfern, und "
        "der Wald hat aufgehört, im richtigen Rhythmus zu atmen.\n\n"
        "Geografie: Im Zentrum der bekannten Welt liegt der "
        "Immerwald — ein Wald so alt und so groß, dass man seine "
        "Grenzen nicht kartiert hat. Er ist nicht einfach Bäume und "
        "Tiere; er ist eine Macht, ein Vertragspartner, ein "
        "Beobachter. Um ihn herum: zerschnittene Königreiche, "
        "Grenzfesten in unterschiedlichem Verfall, Dörfer, die in "
        "Strömen siedeln. Im Norden Eis und Pakte mit Wesen, deren "
        "Namen man nicht ausspricht. Im Süden warme Provinzen mit "
        "klügerer Bürokratie und dunkleren Geheimnissen. Im Osten "
        "die Aschelande, in denen einst ein Königreich verbrannte. "
        "Im Westen das Meer, das niemand mag.\n\n"
        "Politik: Die Königreiche, die einmal den Wald umrahmten, "
        "sind alle in der einen oder anderen Form gescheitert. "
        "Manche zerbrochen, manche entkernt, manche durch Pakt-"
        "Erbschaften an Mächte gebunden, die geduldig warten. An "
        "ihre Stelle treten Hauptleute, Magier-Räte, alte Familien "
        "mit dünnen Ansprüchen, und die Waldläufer:innen — eine "
        "Bruderschaft an der Grenze, halb Späher, halb Vermittler, "
        "halb Henker. Wer in dieser Welt politisch handeln will, "
        "denkt in Generationen, nicht in Wochen.\n\n"
        "Magie: Selten, gefährlich, teuer. Sie ist kein Werkzeug, "
        "sondern ein Vertrag. Jeder Zauber speist sich aus einem "
        "alten Pakt mit dem Wald, der Anderswelt, einem Stein, "
        "einem Stern. Und jeder Pakt verlangt einen Preis: "
        "Erinnerung, Zeit, Blut, oder die kleinen Dinge, die ein "
        "Leben angenehm machen — die Lieblingsfarbe, das Lachen "
        "deiner Mutter, der Geschmack von Sommerregen. Magier:innen "
        "sind selten alt und nie reich.\n\n"
        "Die Anderswelt liegt überall und nirgends gleichzeitig — "
        "an Mondstein-Orten dünn, an Eisengittern dicht, an Pakt-"
        "Steinen offen. Sie schickt manchmal Boten: Feen, "
        "Wechselbälger, sprechende Tiere, Tote mit warmem Lächeln. "
        "Mit ihnen verhandelt man wie mit Adligen — mit Namen, "
        "Geschenken, Geduld und der ständigen Möglichkeit, dass "
        "etwas grundlegend Fremdes deinen Vorschlag falsch "
        "versteht.\n\n"
        "Bedrohung: Die alten Pakte zerfallen. Manche werden von "
        "innen gebrochen, von ehrgeizigen Magier-Räten und "
        "fanatischen Königsfamilien, die meinen, ohne den Wald "
        "wäre es besser. Manche zerbersten von außen, weil etwas, "
        "das gebunden war, lange genug gewartet hat. Im Herzen des "
        "Immerwalds rührt sich etwas. In den Aschelanden findet "
        "ein Kind im Schlaf seine Großmutter wieder, obwohl sie "
        "seit zwanzig Jahren tot ist. In den Grenzdörfern "
        "verstummen die Hunde, und in den Akten der Königshöfe "
        "tauchen Namen auf, die niemand geschrieben hat.\n\n"
        "Hier beginnt jede Geschichte mit einer einfachen "
        "Wahrheit: Du bist Waldläufer:in oder Verwandtes, du "
        "kennst die alten Worte, und irgendwo zwischen Feste und "
        "Wald wartet ein Auftrag, den niemand sonst übernehmen "
        "will."
    ),
    player_role="Waldläufer:in im Dienst eines bedrohten Grenzlandes",
    starting_situation=(
        "Du stehst am Tor einer alten Grenzfeste. Hinter dir die letzte "
        "vertraute Welt — Wachen, Lampen, der Geruch von Brot. Vor dir "
        "der Wald, der seit drei Tagen schweigt. Kein Vogel, kein "
        "Insekt, nur das eigene Atmen. Ein Auftrag liegt in der "
        "Tasche, gesiegelt; ein Eisendolch am Gürtel; und das Wissen, "
        "dass die alten Pakte irgendwo da draußen reißen."
    ),
    narration_style=(
        "Episch, bildreich, mit Sagen-Ton; sinnliche "
        "Naturbeschreibung, bedrohliche Untertöne. Du-Anrede an die "
        "Waldläufer:in. Konkrete Wahrnehmungen vor mystischen "
        "Andeutungen."
    ),
    voice_sample=(
        "Der Wald atmet langsam. Tau hängt in den Spinnweben wie "
        "kalte Glasperlen. Etwas, das größer ist als ein Wolf, hat in "
        "der Nacht den Schnee zerteilt — und es ist nicht "
        "weitergelaufen."
    ),
    mood=(
        "Ehrfürchtig, schwermütig, von lauernder Bedrohung durchzogen "
        "— aber mit Raum für stille Schönheit."
    ),
    ambience=(
        "Moos und nasses Laub, Harzduft, fernes Knacken, gedämpftes "
        "Licht durch uralte Kronen, Stille, in der man den eigenen "
        "Herzschlag hört."
    ),
    magic_physics=(
        "Magie speist sich aus alten Pakten mit dem Wald und der "
        "Anderswelt. Jeder Zauber fordert einen Preis — Erinnerung, "
        "Zeit, Blut. Eisen stört Feenmagie; Mondstein-Orte machen die "
        "Grenze zur Anderswelt dünn; alte Namen haben Macht über das, "
        "was sie kennt."
    ),
    places=[
        Place(name="Die Graufeste",
              description="Letzte Grenzbastion vor dem Immerwald; "
              "müde Garnison, alte Geheimnisse, ein Kommandantin"
              "nenturm, der seit drei Generationen nicht restauriert "
              "wurde.",
              tags=["start", "festung"]),
        Place(name="Der Immerwald",
              description="Endloser, uralter Wald, der sich zu "
              "erinnern und zu beobachten scheint. Pfade verschieben "
              "sich nachts.",
              tags=["wildnis", "mystisch"]),
        Place(name="Mondsteinlichtung",
              description="Ort alter Riten, wo die Grenze zur "
              "Anderswelt dünn ist. Steinkreis, kniehohes Gras, "
              "drei sehr alte Birken.",
              tags=["magie", "gefahr"]),
        Place(name="Das Dorf Ellenhag",
              description="Letztes Bauerndorf vor dem Wald. "
              "Geräucherter Fisch, misstrauische Wirtin, Glocken, "
              "die seit drei Tagen schweigen.",
              tags=["zivil", "info"]),
        Place(name="Der Wegestein bei Vehl",
              description="Pakt-Stein an einer alten Kreuzung. "
              "Bittsteller hinterlassen Brot und Münzen; manche "
              "Bitten werden erhört.",
              tags=["magie", "pakt"]),
        Place(name="Die Aschelande",
              description="Verbranntes Königreich am östlichen "
              "Horizont. Schwarz erstarrte Felder, Dorfruinen, "
              "Asche, die warm bleibt.",
              tags=["ruine", "tragisch"]),
        Place(name="Die Bibliothek von Nethrá",
              description="Halb eingestürzte Klosterbibliothek. "
              "Mönche, die nicht mehr beten, Bücher, die manchmal "
              "umblättern.",
              tags=["wissen", "mystisch"]),
        Place(name="Höhle der Vergessenen Königin",
              description="Höhle hinter einem Wasserfall. Drinnen: "
              "ein Sarkophag, dessen Deckel zuletzt vor 200 Jahren "
              "geöffnet wurde.",
              tags=["gefahr", "lore"]),
        Place(name="Der Schwarzmarkt von Brun",
              description="Halblegaler Markt unter den Treppen einer "
              "verfallenen Stadt. Zauberkrämer, Eisenhändler, "
              "Gerüchte.",
              tags=["stadt", "handel"]),
        Place(name="Pakt-Hain der Drei Birken",
              description="Heiliger Hain im tiefen Immerwald. "
              "Hierhin laden die Waldläufer:innen Bittsteller, die "
              "wirklich verzweifelt sind.",
              tags=["magie", "vertrag"]),
        Place(name="Die Glasstadt unterm See",
              description="Sagenhafte Anderswelt-Stadt, die manche "
              "an klaren Nächten unter der Oberfläche eines Bergsees "
              "sehen. Mondsteinort.",
              tags=["mystisch", "anderswelt"]),
        Place(name="Der Eisengarten von Vorgst",
              description="Festungsgarten aus Eisenstäben — ein "
              "magischer Bann gegen die Anderswelt. Eine Stäbe "
              "fehlen. Niemand spricht darüber.",
              tags=["festung", "anti_magie"]),
    ],
    persons=[
        Person(name="Hauptmann Eldra Vunn", role="Mentor",
               description="Vernarbte Kommandantin der Graufeste. "
               "Trägt ihre Waffen so selbstverständlich wie andere "
               "ihren Mantel.",
               relations="Schickt die Waldläufer:in auf gefährliche "
               "Pfade — und schreibt jede Nacht Briefe an ihren "
               "verstorbenen Bruder.",
               tags=["mentor", "feste"]),
        Person(name="Der Aschenkönig", role="Antagonist",
               description="Wiederkehrende, halb vergessene Macht "
               "aus dem Herzen des Waldes. Erscheint selten, wirkt "
               "immer.",
               relations="Will die alten Pakte brechen — oder neu "
               "verhandeln, je nachdem, wen man fragt.",
               tags=["antagonist", "mystisch"]),
        Person(name="Magier-Rätin Vesna von Korr", role="Politik",
               description="Junge, kühle Magier-Rätin eines "
               "südlichen Königshofs. Trägt sieben Ringe und einen "
               "Ehrgeiz aus Glas.",
               relations="Will den Wald entzaubern, damit Magie "
               "verlässlicher wird.",
               tags=["politik", "magier"]),
        Person(name="Hekka die Heilerin", role="Verbündete",
               description="Alte Dorfheilerin in Ellenhag. Kennt die "
               "Namen aller Pflanzen und der meisten Toten.",
               relations="Hilft Waldläufer:innen, wenn sie respekt"
               "voll fragen; verflucht sie, wenn nicht.",
               tags=["heilerin", "info"]),
        Person(name="Der Stille Späher Vorn",
               role="Waldläufer-Kollege",
               description="Ein Waldläufer mit eingenähter Zunge — "
               "kommuniziert in Gesten und Pfeiltönen. Spricht "
               "trotzdem klar.",
               relations="Kennt die Pfade des tiefen Walds; vertraut "
               "wenigen.",
               tags=["kollege", "scout"]),
        Person(name="Fürst Eldwin Asch", role="Antagonist?",
               description="Letzter Erbe eines Geschlechts, das in "
               "den Aschelanden verbrannte. Lebt in einer Ruine, "
               "die er nicht verlassen kann oder will.",
               relations="Behauptet, das Brechen der Pakte sei sein "
               "Recht.",
               tags=["politik", "tragisch"]),
        Person(name="Die Botin der Birken",
               role="Anderswelt-Wesen",
               description="Eine Fee in Birkenrinde gekleidet. "
               "Lächelt zu freundlich, atmet zu langsam.",
               relations="Liefert Botschaften der Anderswelt — "
               "gegen Erinnerungen.",
               tags=["anderswelt", "kontakt"]),
        Person(name="Bruder Halen", role="Wissen",
               description="Letzter Schreiber der Bibliothek von "
               "Nethrá. Stumm seit zehn Jahren, schreibt schnell.",
               relations="Tauscht Wissen gegen Bücher, die du "
               "rettest.",
               tags=["wissen", "neutral"]),
        Person(name="Die alten Zwillinge Krin und Krak",
               role="Kontakt",
               description="Zwei Eisenhändler in Brun, die nicht "
               "viel reden, aber alles wissen.",
               relations="Verkaufen Eisenwaren gegen Geschichten; "
               "selten gegen Geld.",
               tags=["handel", "info"]),
        Person(name="Das Mädchen Eyla",
               role="Findling",
               description="Ein Kind aus den Aschelanden. Erinnert "
               "sich an Dinge, die vor seiner Geburt geschahen.",
               relations="Sucht jemanden, der ihre Erinnerungen "
               "ernst nimmt.",
               tags=["findling", "mystisch"]),
        Person(name="Hauptmann Yrkenn von Eis",
               role="Politik",
               description="Hauptmann der nördlichen Frostfeste. "
               "Schweigsam, religiös, fanatisch loyal zu einer "
               "Pakt-Tradition, die kaum jemand mehr versteht.",
               relations="Würde sterben für den Pakt; tötet, wer "
               "ihn anrührt.",
               tags=["politik", "antagonist?"]),
        Person(name="Der Singende Wolf",
               role="Anderswelt-Wesen",
               description="Ein Wolf, der menschlich spricht — "
               "manchmal sanft, manchmal befehlend. Spielt nach "
               "alten Regeln.",
               relations="Bietet Wegweisung gegen einen Namen, den "
               "du kennst.",
               tags=["anderswelt", "kontakt"]),
    ],
    items=[
        Item(name="Eisendolch der Graufeste",
             description="Schlichte alte Klinge mit zerkratztem Griff.",
             properties="Stört Feenmagie; bricht kleine Bann; "
             "verbrennt Anderswelt-Boten bei Berührung.",
             tags=["waffe", "anti_magie"]),
        Item(name="Mondstein-Amulett",
             description="Bleich schimmernder Stein an einer dünnen "
             "Kette.",
             properties="Zeigt nahe Anderswelt-Grenzen durch ein "
             "kaltes Flackern; zieht aber Blicke von dort an.",
             tags=["magie", "hinweis"]),
        Item(name="Pakt-Stein-Splitter",
             description="Fingergroßer Splitter eines zerbrochenen "
             "Pakt-Steins.",
             properties="Erlaubt einen einmaligen Bann gegen ein "
             "Anderswelt-Wesen — verbraucht sich danach.",
             tags=["magie", "einmalig"]),
        Item(name="Waldläufer-Mantel",
             description="Tarn-grüner Mantel mit eingenähten "
             "Birkenblättern.",
             properties="Hält dich im Immerwald übersehen, wenn du "
             "still bist; verliert seine Wirkung in Eisen-Nähe.",
             tags=["ausrüstung", "tarnung"]),
        Item(name="Glocke von Ellenhag",
             description="Kleine bronzene Handglocke aus dem Dorf.",
             properties="Vertreibt Schatten der Anderswelt; jedes "
             "Läuten kostet dich eine Minute Lebenszeit.",
             tags=["magie", "preis"]),
        Item(name="Birken-Pfeife",
             description="Pfeife aus weißer Birkenrinde.",
             properties="Ruft den Singenden Wolf — höchstens einmal "
             "im Jahr, sonst hört er auf zu kommen.",
             tags=["mystisch", "ritual"]),
        Item(name="Eisenring der Bruderschaft",
             description="Schlichter Eisenring mit einer Birken-"
             "Gravur.",
             properties="Zeichen aller Waldläufer:innen; öffnet "
             "Türen in Grenzfesten, schließt sie in Königshöfen.",
             tags=["zeichen", "politik"]),
        Item(name="Verbrannter Brief",
             description="Halb verkohlter Brief aus den Aschelanden.",
             properties="Wechselt seinen Text, wenn dich niemand "
             "ansieht. Liest sich immer leicht anders.",
             tags=["mystisch", "info"]),
        Item(name="Heilkraut-Beutel",
             description="Lederbeutel mit zwölf Kräutern, sauber "
             "nach Familie geordnet.",
             properties="Stoppt Blutungen, klärt Schock; ein Kraut "
             "fehlt — niemand spricht darüber.",
             tags=["medizin", "alltag"]),
        Item(name="Mondscheibe der Drei Birken",
             description="Silberne, fingergroße Scheibe mit "
             "geätzten Sternzeichen.",
             properties="Zeigt der Trägerin den Weg zum nächsten "
             "Pakt-Hain — auch wenn sie ihn nicht will.",
             tags=["magie", "navigation"]),
    ],
    glossary=[
        GlossaryEntry(term="Die Pakte",
                      definition="Uralte Verträge zwischen Menschen, "
                      "Wald und Anderswelt, die die Mächte binden."),
        GlossaryEntry(term="Anderswelt",
                      definition="Geisterhafte Parallelwelt hinter "
                      "dünnen Grenzorten; eigene Regeln, eigene "
                      "Adlige."),
        GlossaryEntry(term="Waldläufer:in",
                      definition="Grenzkundschafter:in der "
                      "Bruderschaft, Vermittler:in zwischen Feste, "
                      "Wald und Anderswelt."),
        GlossaryEntry(term="Aschenkönig",
                      definition="Schlafende Macht im Herzen des "
                      "Immerwalds; erwacht, wenn die Pakte brechen."),
        GlossaryEntry(term="Pakt-Stein",
                      definition="Ritueller Grenzstein, der einen "
                      "spezifischen Pakt verkörpert; sein Bruch "
                      "löst den Vertrag."),
        GlossaryEntry(term="Mondstein-Ort",
                      definition="Stelle, an der die Grenze zur "
                      "Anderswelt natürlich dünn ist; gefährlich."),
        GlossaryEntry(term="Bruderschaft (der Waldläufer:innen)",
                      definition="Lose Vereinigung aller Wald"
                      "läufer:innen; eigene Ehre, eigene Regeln, "
                      "eigene Gerichte."),
        GlossaryEntry(term="Magier-Rat",
                      definition="Beratendes Gremium an einem "
                      "Königshof; oft Konkurrent der Waldläufer-"
                      "Tradition."),
        GlossaryEntry(term="Anderswelt-Bote",
                      definition="Wesen, das von 'drüben' eine "
                      "Botschaft trägt — Fee, Wolf, Schatten."),
        GlossaryEntry(term="Wechselbalg",
                      definition="Kind, das durch ein Anderswelt-"
                      "Wesen ersetzt wurde; selten, schwer zu "
                      "erkennen."),
        GlossaryEntry(term="Eisenbann",
                      definition="Eisengitter oder -ring; "
                      "verhindert Übergänge aus der Anderswelt."),
        GlossaryEntry(term="Pakt-Preis",
                      definition="Was ein Zauber kostet: Erinnerung, "
                      "Zeit, Blut oder eine Lieblingssache."),
        GlossaryEntry(term="Heilerin / Heiler",
                      definition="Dörflich anerkannte Magie-"
                      "Praktiker:in; arbeitet mit Pflanzen, "
                      "Knochen, kleinen Pakten."),
        GlossaryEntry(term="Grenzfeste",
                      definition="Befestigte Garnison an einer "
                      "Wald- oder Anderswelt-Grenze; meist "
                      "veraltet, oft unterbesetzt."),
        GlossaryEntry(term="Die Aschelande",
                      definition="Verbranntes Königreich im Osten; "
                      "Folge eines gebrochenen Pakts vor drei "
                      "Generationen."),
        GlossaryEntry(term="Hain",
                      definition="Heiliger Waldort; Gebets-, "
                      "Pakt- oder Versammlungsplatz."),
        GlossaryEntry(term="Bann (kleiner / großer)",
                      definition="Magische Sperre; kleine halten "
                      "einzelne Wesen ab, große ganze Mächte. "
                      "Brüchig mit der Zeit."),
        GlossaryEntry(term="Nethrá",
                      definition="Halb eingestürzte Klosterbiblio"
                      "thek; einzige Sammlung schriftlicher Pakt-"
                      "Aufzeichnungen."),
        GlossaryEntry(term="Schattenpfad",
                      definition="Pfad, der durch die Anderswelt "
                      "verkürzt; spart Zeit, kostet immer etwas."),
        GlossaryEntry(term="Stille",
                      definition="Wenn der Wald verstummt — "
                      "Vorzeichen, dass etwas Großes erwacht."),
    ],
    history=[
        HistoryEvent(when="im Ersten Zeitalter",
                     title="Der Große Pakt",
                     description="Mensch und Wald schlossen Frieden; "
                     "der Aschenkönig wurde gebunden, die ersten "
                     "Mondstein-Orte versiegelt."),
        HistoryEvent(when="im Zweiten Zeitalter",
                     title="Die Sieben Königreiche",
                     description="Sieben Reiche entstanden um den "
                     "Wald; jedes hatte seinen eigenen Pakt, seine "
                     "eigenen Pflichten."),
        HistoryEvent(when="vor 500 Jahren",
                     title="Der Bruch im Norden",
                     description="Ein Königreich brach seinen Pakt; "
                     "der Winter kam und ging nicht mehr ganz weg."),
        HistoryEvent(when="vor 200 Jahren",
                     title="Die Versiegelung des Aschenkönigs",
                     description="Eine Allianz von Waldläufer:innen "
                     "und Magier-Räten versiegelte den Aschenkönig "
                     "erneut; viele starben, der Sarkophag steht in "
                     "einer Höhle."),
        HistoryEvent(when="vor drei Generationen",
                     title="Der Brand der Aschelande",
                     description="Ein gebrochener Pakt ließ ein "
                     "Königreich in Asche fallen; bis heute glüht "
                     "der Boden im Osten."),
        HistoryEvent(when="vor 80 Jahren",
                     title="Die Stille von Ellenhag",
                     description="Eine ganze Dorfbevölkerung "
                     "verschwand für drei Tage und kam älter "
                     "zurück; niemand spricht darüber."),
        HistoryEvent(when="vor 40 Jahren",
                     title="Aufstieg der Magier-Räte",
                     description="Magier-Räte gewannen politischen "
                     "Einfluss an den Höfen; Waldläufer:innen "
                     "wurden zu Sonderlingen erklärt."),
        HistoryEvent(when="vor 15 Jahren",
                     title="Das Eisengarten-Ereignis",
                     description="Im Eisengarten von Vorgst "
                     "verschwand über Nacht ein Drittel der "
                     "Stäbe; der Bann hält dennoch — kaum."),
        HistoryEvent(when="vor 5 Jahren",
                     title="Die Rückkehr der Botin",
                     description="Eine Anderswelt-Botin tauchte "
                     "nach hundert Jahren Pause wieder auf; ihre "
                     "Botschaft wurde nicht öffentlich gemacht."),
        HistoryEvent(when="vor einem Mondzyklus",
                     title="Die schweigenden Vögel",
                     description="Im Immerwald verstummte alles "
                     "Getier; die Waldläufer:innen schickten "
                     "Späher aus, die nicht zurückkamen."),
    ],
    fragments=[
        Fragment(title="Die verstummten Vögel",
                 text="Im Immerwald schweigt alles Getier seit "
                 "drei Tagen. Selbst die Krähen, die sonst über "
                 "den Aschelanden rufen, sind weg. Etwas Altes "
                 "ist wach.",
                 tags=["hook", "omen"]),
        Fragment(title="Der gebrochene Pakt-Stein",
                 text="Ein Grenzstein der alten Verträge wurde "
                 "zerschlagen. Die Bruchkanten sind nicht "
                 "verwittert — frisch. Daneben liegen drei "
                 "Münzen einer Münze, die seit zweihundert "
                 "Jahren nicht mehr geprägt wird.",
                 tags=["stakes", "hook"]),
        Fragment(title="Der Schlafende im Sarkophag",
                 text="In der Höhle der Vergessenen Königin "
                 "schwitzt der Sarkophag. Wasser tropft, das "
                 "kein Wasser ist. Die Versiegelung steht — "
                 "knapp.",
                 tags=["mystery", "stakes"]),
        Fragment(title="Brief eines toten Onkels",
                 text="Im Postfach der Graufeste liegt ein "
                 "Brief in der Handschrift eines Mannes, der "
                 "seit 20 Jahren tot ist. Er nennt deinen "
                 "Geburtsnamen, den niemand mehr kennt.",
                 tags=["hook", "anderswelt"]),
        Fragment(title="Die Glocken von Ellenhag",
                 text="Die Dorfglocken schweigen seit drei "
                 "Tagen. Die Wirtin sagt, sie wurden gestohlen. "
                 "Du siehst sie hängen — sie geben nur einfach "
                 "keinen Ton mehr von sich.",
                 tags=["mystery", "ambient"]),
        Fragment(title="Das Kind aus der Asche",
                 text="Ein Kind sitzt in den Aschelanden auf "
                 "warmem Boden und lacht. Es hat dein Gesicht, "
                 "nur jünger. Es winkt.",
                 tags=["horror", "anderswelt"]),
        Fragment(title="Versiegelter Auftrag",
                 text="Eldra Vunn übergibt einen versiegelten "
                 "Brief mit der Anweisung, ihn erst im Pakt-"
                 "Hain der Drei Birken zu öffnen. Du fühlst "
                 "den Wachsabdruck zittern.",
                 tags=["hook", "politik"]),
        Fragment(title="Spuren, die im Kreis führen",
                 text="Im Schnee am Waldrand finden sich frische "
                 "Spuren — Stiefel, deine Größe, dein Schritt. "
                 "Sie führen im Kreis. Du warst noch nicht hier.",
                 tags=["anomalie", "stakes"]),
        Fragment(title="Magier-Rats-Bote",
                 text="Ein Bote der Magier-Rätin Vesna von Korr "
                 "kommt zur Graufeste. Höflich, aber zu höflich. "
                 "Sein Pferd schwitzt; der Bote nicht.",
                 tags=["politik", "intrige"]),
        Fragment(title="Die Bitte der Botin",
                 text="Die Botin der Birken trifft dich am "
                 "Wegestein. Sie bittet um drei Erinnerungen — "
                 "die kleinsten, die du hast. Im Tausch: ein "
                 "Name, den der Aschenkönig nicht kennt.",
                 tags=["anderswelt", "tausch"]),
        Fragment(title="Eisengarten-Lücke",
                 text="Im Eisengarten von Vorgst fehlt eine "
                 "Stange. Der Bann hält — knapp. Drei Wachen "
                 "verschwanden in der Nacht, ohne Spuren.",
                 tags=["festung", "stakes"]),
        Fragment(title="Bibliotheksflüstern",
                 text="In der Bibliothek von Nethrá blättert "
                 "ein Buch von selbst um. Bruder Halen reicht "
                 "dir Papier und Feder, damit du mitschreibst.",
                 tags=["wissen", "mystery"]),
        Fragment(title="Der singende Wolf",
                 text="Am Waldrand sitzt ein Wolf und summt eine "
                 "Melodie, die du aus deiner Kindheit kennst. Er "
                 "wartet, bis du ihn ansiehst, und nickt.",
                 tags=["anderswelt", "hook"]),
        Fragment(title="Pakt-Hain-Stille",
                 text="Im Pakt-Hain der Drei Birken ist es so "
                 "still, dass dein Herzschlag laut klingt. Eine "
                 "der Birken hat eine frische Wunde im Stamm.",
                 tags=["magie", "stakes"]),
        Fragment(title="Aschenstaub im Brot",
                 text="In Ellenhag schmeckt das Brot heute nach "
                 "Asche. Die Wirtin will es nicht zurücknehmen; "
                 "sie schaut weg, während du isst.",
                 tags=["ambient", "omen"]),
        Fragment(title="Fürst Asch lädt ein",
                 text="Ein Bote von Fürst Eldwin Asch lädt dich "
                 "in seine Ruine ein. Er sagt, er habe Antworten. "
                 "Er sagt nicht, auf welche Fragen.",
                 tags=["politik", "hook"]),
        Fragment(title="Spätsommer-Frost",
                 text="Am Waldrand bildet sich Frost, obwohl "
                 "Spätsommer ist. Das Heilkraut welkt vor deinen "
                 "Augen. Hekka sagt, das habe sie noch nie "
                 "gesehen.",
                 tags=["anomalie", "stakes"]),
        Fragment(title="Doppelmondnacht",
                 text="Heute Nacht steht ein zweiter Mond am "
                 "Himmel, blass und versetzt. Niemand in der "
                 "Feste sieht ihn außer dir und einem alten "
                 "Soldaten, der weint.",
                 tags=["anderswelt", "mystery"]),
        Fragment(title="Der Stille Späher schweigt nicht",
                 text="Vorn der Stille Späher pfeift drei Töne "
                 "in einer Reihenfolge, die alle Waldläufer:innen "
                 "kennen — Rückzug, sofort, ohne Erklärung. Er "
                 "sieht nicht zurück.",
                 tags=["scout", "stakes"]),
        Fragment(title="Eyla erinnert sich",
                 text="Das Mädchen Eyla beschreibt dir eine "
                 "Schlacht, die vor hundert Jahren in den "
                 "Aschelanden geschah. Detailgetreu. Sie ist "
                 "neun.",
                 tags=["findling", "mystery"]),
    ],
    blueprint=Blueprint(
        premise=(
            "Eine Waldläufer:in muss an die Grenze des Bekannten "
            "reisen, wo alte Mächte erwachen, und zwischen Bewahren "
            "und Bändigen wählen."
        ),
        escalation_rule=_ESCALATION_DE,
        beats=_functional_beats_de(),
    ),
    random_tables=[
        RandomTable(
            name="Waldzeichen",
            description="Was die Hauptfigur beim Reisen im "
            "Immerwald wahrnimmt.",
            entries=[
                RandomEntry(weight=3, text="Frische Spuren, die im "
                            "Kreis führen."),
                RandomEntry(weight=2, text="Ein Schrein mit frischer "
                            "Opfergabe — Brot, drei Münzen, eine "
                            "Locke."),
                RandomEntry(weight=1, text="Eine Stimme ruft deinen "
                            "wahren Namen aus dem Dickicht."),
                RandomEntry(weight=2, text="Verkrümmtes Birkenholz, "
                            "in Spiralen gewachsen."),
                RandomEntry(weight=1, text="Drei tote Krähen in "
                            "präziser Reihe."),
                RandomEntry(weight=1, text="Eine Lichtung, die "
                            "gestern nicht da war."),
                RandomEntry(weight=2, text="Ein Pfad, der sich vor "
                            "dir öffnet, hinter dir schließt."),
                RandomEntry(weight=1, text="Ein Pakt-Stein mit "
                            "frischen Kratzern."),
                RandomEntry(weight=1, text="Frost auf einem Stein, "
                            "trotz Spätsommer."),
                RandomEntry(weight=1, text="Eine Spur in Schnee, "
                            "obwohl kein Schnee liegt."),
                RandomEntry(weight=1, text="Ein Baum, der summt, "
                            "wenn niemand hinschaut."),
                RandomEntry(weight=2, text="Glühende Pilze in "
                            "Reihen wie Inschriften."),
                RandomEntry(weight=1, text="Ein Fußabdruck, drei "
                            "Mal so groß wie deiner."),
                RandomEntry(weight=1, text="Eine Quelle, die "
                            "rückwärts fließt — kurz."),
                RandomEntry(weight=1, text="Ein altes Lied in der "
                            "Luft, ohne Sänger."),
                RandomEntry(weight=1, text="Spinnweben, die ein "
                            "Wort buchstabieren."),
                RandomEntry(weight=1, text="Eine Krähenfeder mit "
                            "geätzten Runen."),
                RandomEntry(weight=1, text="Eine knirschende "
                            "Stille, in der ein einzelner Vogel "
                            "ruft und sofort verstummt."),
                RandomEntry(weight=1, text="Mondblumen, die sich "
                            "zur falschen Tageszeit öffnen."),
                RandomEntry(weight=1, text="Ein vergessener "
                            "Reisemantel an einem Ast — deine "
                            "Größe."),
                RandomEntry(weight=1, text="Ein Stein, auf dem "
                            "dein Name steht — sehr alt."),
            ],
        ),
        RandomTable(
            name="Begegnung am Pfad",
            description="Wem die Hauptfigur am Wegesrand begegnet.",
            entries=[
                RandomEntry(weight=2, text="Eine fliehende Familie "
                            "aus dem Wald."),
                RandomEntry(weight=2, text="Ein Späher des Aschen"
                            "königs in entliehener Gestalt."),
                RandomEntry(weight=1, text="Ein sprechendes Tier "
                            "mit einer Bitte."),
                RandomEntry(weight=2, text="Ein Pilger zum Pakt-"
                            "Stein bei Vehl, mit drei Münzen."),
                RandomEntry(weight=1, text="Ein Wanderer ohne "
                            "Augenbrauen, der nach Norden zeigt."),
                RandomEntry(weight=1, text="Ein verstörter Bauer, "
                            "der eine Glocke umarmt."),
                RandomEntry(weight=2, text="Ein anderer Waldläufer "
                            "mit gekreuztem Mantel — Notzeichen."),
                RandomEntry(weight=1, text="Ein Magier-Rats-Bote "
                            "mit unwilligem Pferd."),
                RandomEntry(weight=1, text="Eine Pferdekarawane "
                            "mit verriegelter Ware."),
                RandomEntry(weight=2, text="Ein Wechselbalg, der "
                            "sich als Kind ausgibt."),
                RandomEntry(weight=1, text="Eine Hexe, die Heil"
                            "mittel feilbietet — gegen Erinnerung."),
                RandomEntry(weight=1, text="Ein Toter, der nicht "
                            "weiß, dass er tot ist."),
                RandomEntry(weight=1, text="Ein Eisenhändler aus "
                            "Brun mit Karren voll Stäben."),
                RandomEntry(weight=1, text="Ein Mönch aus Nethrá, "
                            "der Papier verbrennt."),
                RandomEntry(weight=1, text="Ein vornehmer Reiter "
                            "ohne Wappen — südlicher Akzent."),
                RandomEntry(weight=1, text="Ein Kind allein im "
                            "Schnee, das ein altes Lied summt."),
                RandomEntry(weight=1, text="Eine Frau, die "
                            "behauptet, deine Mutter zu sein — "
                            "die du verloren glaubst."),
                RandomEntry(weight=1, text="Ein Wagen mit "
                            "klagenden Glocken, die niemand "
                            "berührt."),
                RandomEntry(weight=1, text="Ein Pakt-Bittsteller, "
                            "blutig, kurz vor dem Verzicht."),
                RandomEntry(weight=1, text="Eine Patrouille der "
                            "Frostfeste, die zu weit südlich "
                            "ist."),
                RandomEntry(weight=1, text="Ein Spielmann, der nur "
                            "rückwärts singt."),
            ],
        ),
        RandomTable(
            name="Bann-Komplikation",
            description="Was schief geht, wenn die Hauptfigur "
            "magisch agiert oder einen Bann braucht.",
            entries=[
                RandomEntry(weight=2, text="Ein kleiner Bann hält "
                            "halb — etwas kommt durch."),
                RandomEntry(weight=2, text="Der Pakt-Preis wird "
                            "höher als gedacht."),
                RandomEntry(weight=1, text="Eine Erinnerung "
                            "verschwindet, die du gebraucht "
                            "hättest."),
                RandomEntry(weight=1, text="Eisen ringsum schwächt "
                            "den Bann ungewollt."),
                RandomEntry(weight=2, text="Der Bann hält, aber "
                            "die Bannerin altert sichtbar."),
                RandomEntry(weight=1, text="Anderes wird angelockt: "
                            "kleine Wesen, viele."),
                RandomEntry(weight=1, text="Der Bann hält länger "
                            "als gewünscht — du kannst nicht "
                            "weg."),
                RandomEntry(weight=1, text="Ein Tier in der Nähe "
                            "stirbt, scheinbar ohne Grund."),
                RandomEntry(weight=2, text="Der Pakt-Stein "
                            "bekommt einen feinen Riss."),
                RandomEntry(weight=1, text="Ein Anderswelt-Bote "
                            "tritt sofort vor, höflich, fordernd."),
                RandomEntry(weight=1, text="Die Witterung "
                            "schlägt um — Frost im Sommer."),
                RandomEntry(weight=1, text="Die Glocke von "
                            "Ellenhag verstummt für drei Tage."),
                RandomEntry(weight=1, text="Ein Geräusch wandert "
                            "ab — kein Echo mehr in deiner "
                            "Stimme."),
                RandomEntry(weight=1, text="Ein zweiter Schatten "
                            "läuft kurz mit dir."),
                RandomEntry(weight=1, text="Die Sonne steht für "
                            "Sekunden in falscher Richtung."),
                RandomEntry(weight=1, text="Ein Lied beginnt in "
                            "deinem Kopf, das du nicht abstellen "
                            "kannst."),
                RandomEntry(weight=1, text="Ein Pakt aus "
                            "Kindertagen wird fällig — niemand "
                            "warnte dich."),
                RandomEntry(weight=1, text="Eine Münze in deiner "
                            "Tasche wird heiß."),
                RandomEntry(weight=1, text="Dein Eisendolch wird "
                            "stumpf, ohne Berührung."),
                RandomEntry(weight=1, text="Drei Tage lang "
                            "schmeckt Wasser nach Eisen."),
                RandomEntry(weight=1, text="Ein Auge träumt "
                            "wach; das andere schläft im "
                            "Stehen."),
            ],
        ),
        RandomTable(
            name="Anderswelt-Tausch",
            description="Was Anderswelt-Wesen bieten — und was "
            "sie verlangen.",
            entries=[
                RandomEntry(weight=2, text="Ein Name, den der "
                            "Aschenkönig nicht kennt — gegen "
                            "drei kleine Erinnerungen."),
                RandomEntry(weight=2, text="Ein sicherer Pfad "
                            "durch den Wald — gegen deine "
                            "Lieblingsfarbe."),
                RandomEntry(weight=1, text="Heilung einer "
                            "Verletzung — gegen sieben Stunden "
                            "Lebenszeit."),
                RandomEntry(weight=1, text="Eine wahre Antwort "
                            "auf eine Frage — gegen den Geschmack "
                            "von Sommerregen."),
                RandomEntry(weight=2, text="Eine Botschaft an "
                            "einen Toten — gegen eine Locke "
                            "Haar."),
                RandomEntry(weight=1, text="Eine Vision der "
                            "Zukunft — gegen die Fähigkeit zu "
                            "weinen für ein Jahr."),
                RandomEntry(weight=1, text="Schlaf ohne Träume — "
                            "gegen eine Träne deiner Mutter."),
                RandomEntry(weight=1, text="Ein Lied, das "
                            "Wachen einschläfert — gegen deine "
                            "Lieblingsmelodie."),
                RandomEntry(weight=2, text="Ein Pakt-Stein-"
                            "Splitter — gegen eine Erinnerung an "
                            "deinen Vater."),
                RandomEntry(weight=1, text="Übersetzung eines "
                            "Anderswelt-Wortes — gegen eine "
                            "Stunde deiner Stimme."),
                RandomEntry(weight=1, text="Ein Schatten, der "
                            "für dich kämpft — gegen dein "
                            "Spiegelbild für drei Tage."),
                RandomEntry(weight=1, text="Ein Geschenk für "
                            "eine geliebte Person — gegen das "
                            "Wissen, wie es geschickt wurde."),
                RandomEntry(weight=1, text="Schutz vor einem "
                            "spezifischen Wesen — gegen den "
                            "Namen eines Freundes."),
                RandomEntry(weight=1, text="Eine Sprache, die "
                            "du nie gelernt hast — gegen deine "
                            "Muttersprache für einen Mondzyklus."),
                RandomEntry(weight=1, text="Ein Schwert, das "
                            "niemand sieht — gegen den Beruf "
                            "deiner Wahl."),
                RandomEntry(weight=1, text="Drei Tage Glück — "
                            "gegen drei Jahre Wachsamkeit."),
                RandomEntry(weight=1, text="Eine zweite Chance "
                            "in einer Sache — gegen deine erste "
                            "Wahl."),
                RandomEntry(weight=1, text="Ein Hund, der nie "
                            "stirbt — gegen den Tag deines "
                            "Geburtstags."),
                RandomEntry(weight=1, text="Eine Karte des "
                            "Immerwalds — gegen den Geschmack "
                            "von Brot."),
                RandomEntry(weight=1, text="Ein Schritt durch "
                            "die Anderswelt — gegen den Mut, "
                            "zurückzukehren."),
                RandomEntry(weight=1, text="Ein wahrer Pakt — "
                            "gegen jeden zukünftigen Pakt."),
            ],
        ),
        RandomTable(
            name="Politische Komplikation",
            description="Wie Königshof, Magier-Rat und Bruderschaft "
            "der Hauptfigur das Leben schwer machen.",
            entries=[
                RandomEntry(weight=2, text="Ein Magier-Rat "
                            "verlangt Bericht — bevor die Bruder"
                            "schaft ihn bekommt."),
                RandomEntry(weight=2, text="Eldra Vunn bekommt "
                            "Order von oben, dich zurückzurufen."),
                RandomEntry(weight=1, text="Eine Königshofbotin "
                            "lädt dich zu Hof — mit Eskorte."),
                RandomEntry(weight=2, text="Vesna von Korr "
                            "schickt einen 'Beobachter' mit."),
                RandomEntry(weight=1, text="Ein Eisenhändler "
                            "wird festgesetzt; deine Kontakte "
                            "in Brun trocknen aus."),
                RandomEntry(weight=1, text="Fürst Asch beansprucht "
                            "Bergungsrecht an einem Fund — und "
                            "schickt Söldner."),
                RandomEntry(weight=1, text="Der nördliche Hauptmann "
                            "Yrkenn von Eis verlangt Loyalitäts"
                            "schwur."),
                RandomEntry(weight=1, text="Ein Pakt-Bittsteller "
                            "beim Wegestein bei Vehl verklagt "
                            "dich später."),
                RandomEntry(weight=2, text="Die Magier-Räte "
                            "verbieten Eisengarten-Betreten "
                            "ohne Genehmigung."),
                RandomEntry(weight=1, text="Eine Audienz wird "
                            "verschoben — du verlierst Zeit, "
                            "die du nicht hast."),
                RandomEntry(weight=1, text="Ein anonymer Brief "
                            "behauptet, du habest einen Pakt "
                            "selbst gebrochen."),
                RandomEntry(weight=1, text="Ellenhag liefert "
                            "keinen Proviant — Anweisung von "
                            "oben."),
                RandomEntry(weight=1, text="Bruder Halen schickt "
                            "Warnung: jemand kopiert deine Akte."),
                RandomEntry(weight=1, text="Die Bruderschaft "
                            "schickt einen Schiedsrichter, der "
                            "kein Wort spricht."),
                RandomEntry(weight=1, text="Ein Magier-Rats-"
                            "Vertreter bietet Schutz gegen einen "
                            "Eid."),
                RandomEntry(weight=1, text="Yrkenn schickt eine "
                            "Patrouille, die zu südlich operiert."),
                RandomEntry(weight=1, text="Der Schwarzmarkt von "
                            "Brun wird durchsucht; deine Quellen "
                            "verschwinden."),
                RandomEntry(weight=1, text="Eine Botin von Vesna "
                            "von Korr bietet einen Tausch — "
                            "Eisengarten gegen Schweigen."),
                RandomEntry(weight=1, text="Ein Kind taucht auf, "
                            "das sich als Erbe eines verbrannten "
                            "Hauses ausgibt."),
                RandomEntry(weight=1, text="Eine alte Familie "
                            "lädt zum Mahl — mit Eisen am "
                            "Tisch."),
                RandomEntry(weight=1, text="Die Frostfeste "
                            "schickt einen Bann-Stein als "
                            "Geschenk — vergiftet?"),
            ],
        ),
    ],
    complexity="rich",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=2, action=3, horror=2,
              pacing="medium"),
    wait_sound="fantasy_waiting.wav",
    fx_preset=FXPreset(reverb_room_size=0.7, reverb_wet_level=0.22),
)


# ---------------- Worlds: Starfaring (EN) ----------------

SCIFI_EN = World(
    id="sternenfahrt",
    name="Starfaring",
    display_name="Starfaring",
    genre="Science Fiction",
    description=(
        "Starfaring takes place in a late, worn-out era of space "
        "travel. Two hundred years ago the jump drive made the "
        "colonization of hundreds of worlds possible. The golden age "
        "of the pioneers is long over. Today hyperspace is surveyed, "
        "charted, divided into leaseholds between the great Line "
        "conglomerates that control routes, fuel and tariffs. To "
        "survive as an independent captain of a jump ship is to "
        "balance constantly between cargo contracts, dwindling fuel, "
        "Line bureaucracy, and the quiet routes that nobody enters "
        "on the official charts.\n\n"
        "The world does not feel vast and empty — it feels dense and "
        "watched. Drift stations hang like buoys in the shadow of "
        "gas giants, their corridors sticky with recycled air. "
        "Hyperspace corridors are as densely flown as old trade "
        "roads, and just as contested. There is the trade of "
        "smugglers, wreckers, freighters without papers; and there "
        "are the Lines, which know, tolerate, play off, or liquidate "
        "all three depending on the tone of voice.\n\n"
        "Over everything floats the unspoken knowledge that jump "
        "physics is not as controllable as the Lines pretend. There "
        "are sectors where jumps take longer than the trip itself. "
        "There are ships that returned with every mirror reversed. "
        "There are radio signals pulsing in dead languages. The "
        "academies call these 'anomaly fields' and downplay them. "
        "On the drift stations they are called 'maws' — and "
        "captains who entered them either come back changed or do "
        "not come back at all.\n\n"
        "There is no magic. No religion in the formal sense. But "
        "there is that old, cold respect for what humans have not "
        "measured. Crew contracts carry clauses against entering "
        "uncharted sectors. Cargo holds have shrines. Experienced "
        "navigators wear lucky charms they officially do not own.\n\n"
        "Politically, the Line consortia are the real power. Local "
        "governments are puppets or petitioners. So-called 'Free "
        "Worlds' try to break away and are economically strangled "
        "for it. Consuls — the mid-level Line functionaries — are "
        "the faces of power, some pragmatic, some fanatic, all "
        "dangerous. A captain who does not operate in the shadow "
        "of these consuls pays double for every jump: in tariffs, "
        "in permits, in nerves.\n\n"
        "In this world every journey begins with a simple truth: "
        "you have too little fuel for the official route, too much "
        "debt for the safe one — and always too many secrets for "
        "the quiet one."
    ),
    player_role="Captain of an independent jump ship",
    starting_situation=(
        "You sit on the bridge of your jump ship — tanks half empty, "
        "cargo manifest awkward, the radio band thick with voices you "
        "shouldn't be hearing. A drift station hangs ahead in the "
        "shadow of a gas giant. Out there waits a contract, a Line "
        "inspection, and an anomaly your charts don't know."
    ),
    narration_style=(
        "Cinematic, soberly technical with moments of wonder; short "
        "sentences under tension, calmer in shipboard routine. Address "
        "the captain as 'you'. Concrete sensory detail before "
        "explanation."
    ),
    voice_sample=(
        "The reactors hum half a tone deeper than yesterday. On the "
        "radio: a woman's voice you don't know, calling you by name — "
        "quietly, almost kindly, in a language that should not exist."
    ),
    mood=(
        "Lonely, tense, shot through with cold awe of the unknown — "
        "but never hopeless."
    ),
    ambience=(
        "Humming reactors, ozone and cold cable dust, the ticking of "
        "cooling hull plates, sterile emergency lighting, the "
        "occasional spark in the void."
    ),
    magic_physics=(
        "No magic. Hyperspace jumps need helium-3 and exact "
        "navigation windows; misjumps age matter or swallow ships. "
        "There are anomalous sectors where jump physics fails — no "
        "one knows why, and the Lines play it down."
    ),
    places=[
        Place(name="Bridge of the 'Wanderfalcon'",
              description="Command center of your jump ship. "
              "Hyperspace console, worn star map, smell of old "
              "coffee and ozone.",
              tags=["ship", "start"]),
        Place(name="Drift Station Kells",
              description="Run-down trading and smuggler station at "
              "the edge of charted space. Sticky corridors, recycled "
              "air, every second door a dubious opportunity.",
              tags=["station", "trade"]),
        Place(name="Maintenance Deck",
              description="Lower deck of the ship. Yellow emergency "
              "light, clanking tools, oily air. Here you improvise "
              "everything the academy never taught.",
              tags=["ship", "routine"]),
        Place(name="Cargo Bay 4-South",
              description="Half-empty hangar in the belly of the "
              "'Wanderfalcon'. A crate with a Line seal stands "
              "there that no one ordered.",
              tags=["ship", "cargo"]),
        Place(name="Drift Bar 'Last Jump'",
              description="Station tavern on Kells. Meeting point "
              "of the wreckers, bar built from hyperspace debris, "
              "in the back room cards change owners.",
              tags=["station", "meet"]),
        Place(name="Line Office Sector 12",
              description="Bureaucratic zone of the consuls. "
              "Marble lobby in a steel bubble. Politeness here "
              "costs processing fees.",
              tags=["politics", "line"]),
        Place(name="Anomaly Corridor Vex",
              description="Warped hyperspace corridor between two "
              "sectors. Jumps take longer than they should, sometimes "
              "shorter. The charts show the path; the drive doesn't "
              "believe it.",
              tags=["anomaly", "hyperspace"]),
        Place(name="Wreck Field Khorr-7",
              description="Graveyard of colonial ships from the "
              "pioneer years. Drifts slowly around a dead star. "
              "Salvage permits gray, finds gold.",
              tags=["wreck", "danger"]),
        Place(name="Ice Moon Loke",
              description="Almost abandoned refueling station on "
              "an ice moon. Fuel cheap, conditions unpleasant, "
              "weather life-threatening.",
              tags=["refuel", "remote"]),
        Place(name="Sanctuary of the Sixth Frequency",
              description="Hidden cave inside an asteroid. Pilgrims "
              "of the Sixth Frequency listen to dead radio signals "
              "like prayers.",
              tags=["mystic", "underground"]),
        Place(name="Warehouse 'Late Delivery'",
              description="Decrepit cargo yard on Kells. Goods pass "
              "through here that appear on no manifest.",
              tags=["smuggling", "station"]),
        Place(name="Ancient Probe 'First Contact-9'",
              description="Pre-human probe, drifting in the dark "
              "for millennia. Pulses three seconds long every "
              "47 days.",
              tags=["mystic", "find"]),
    ],
    persons=[
        Person(name="Navigator Suri Vael", role="Crew",
               description="Brilliant, sarcastic hyperspace "
               "navigator. Sleeps rarely, officially doesn't smoke, "
               "secretly carries jump dice.",
               relations="Trusts the crew, distrusts the Lines.",
               tags=["crew", "trusted"]),
        Person(name="Consul Adran Mox", role="Antagonist",
               description="Influential Line consul with a hidden "
               "agenda. Polite, precise, dangerous.",
               relations="Has people pay — or has them removed.",
               tags=["line", "antagonist"]),
        Person(name="Bosun Hen 'Iron' Ortig", role="Crew",
               description="Gruff chief engineer with burned "
               "forearms. Rarely speaks, always wrenching.",
               relations="Believes more in clean welds than in "
               "captains.",
               tags=["crew", "tech"]),
        Person(name="Radio Operator Nima Kall", role="Crew",
               description="Young radio operator with fanatical "
               "precision. Wears three sets of headphones at once.",
               relations="Hears voices in the dead band; doesn't "
               "say so.",
               tags=["crew", "mystery"]),
        Person(name="Doc Vrasa", role="Crew",
               description="Old ship's surgeon, formerly Line. "
               "Drinks green tea in the morning, schnapps at "
               "night.",
               relations="Knows things about Mox's past he doesn't "
               "share.",
               tags=["crew", "secret"]),
        Person(name="Smuggler Baron Otoré", role="Contact",
               description="Controls the gray trade on Kells. "
               "Three gold teeth, always a second smile.",
               relations="Helps for a share; never forgets a debt.",
               tags=["station", "contact"]),
        Person(name="Inspector Lyra Hatt", role="Line",
               description="Line inspector, strict but bribable. "
               "Long fingers on a thin data pad.",
               relations="Files or cash; she's a pro at both.",
               tags=["line", "corruption"]),
        Person(name="Wrecker 'Skiff' Mauder", role="Contact",
               description="Leader of a wrecker clan. Wears a "
               "piece of pioneer-era metal on a chain.",
               relations="Respects captains who pay, crews that "
               "keep quiet.",
               tags=["wreck", "contact"]),
        Person(name="Pilgrim Olm", role="Mystic",
               description="Jump mystic of the Sixth Frequency. "
               "Talks like a weather report from a foreign city.",
               relations="Asks passage to the anomalies.",
               tags=["mystic", "passenger"]),
        Person(name="'Chalk'", role="Foundling",
               description="Orphan from the Khorr wreck field. "
               "Small, dangerous, loyal. Rarely speaks, shoots "
               "accurately.",
               relations="Looking for someone to follow.",
               tags=["foundling", "allied"]),
        Person(name="Consul Adira Mira", role="Politics",
               description="Consul of the Free Worlds. Heavy "
               "voice, light eyes, a tarnished Line pin on her "
               "lapel.",
               relations="Offers routes outside the Lines — for "
               "loyalty.",
               tags=["politics", "free_worlds"]),
        Person(name="AI Persona 'Collar'", role="Mystery",
               description="Old, half-awakened ship AI from a "
               "wreck. Speaks in loops and verses.",
               relations="Asks for release; might mean it.",
               tags=["ai", "mystery"]),
    ],
    items=[
        Item(name="Helium-3 cell",
             description="Fuel canister for jumps.",
             properties="1 cell = 1 safe jump; scarce and expensive.",
             tags=["resource"]),
        Item(name="Echo recorder",
             description="Stores radio signals on all frequencies, "
             "even dead ones.",
             properties="Plays back languages that should not exist.",
             tags=["clue", "mystery"]),
        Item(name="Line seal",
             description="Seals Line-certified cargo.",
             properties="Breaking it without trace = Line "
             "indictment; forging it is possible but expensive.",
             tags=["politics", "cargo"]),
        Item(name="Freighter logbook",
             description="Old mechanical book with crew secrets no "
             "Line system can read.",
             properties="Authenticates you with old captains; "
             "exposes you to Line inspectors.",
             tags=["document"]),
        Item(name="Jump dice",
             description="Seven asymmetric dice; lucky charm of "
             "some navigators.",
             properties="Officially superstition. Unofficially, no "
             "crew that has thrown them has yet encountered an "
             "anomaly.",
             tags=["mystic", "ritual"]),
        Item(name="Anomaly detector",
             description="Beeps on jump distortions.",
             properties="Often false alarms. But if it beeps "
             "continuously, you turn around.",
             tags=["tool", "anomaly"]),
        Item(name="Doc-stim 'Wakekeeper'",
             description="Stimulant for 48-hour shifts.",
             properties="Keeps you awake, sharp, dangerous; the "
             "crash afterwards costs 12 hours of consciousness.",
             tags=["medicine", "resource"]),
        Item(name="Forged Line pass",
             description="Plaque with a consul's seal; looks real.",
             properties="One-time use at an unverified station; "
             "ashes afterwards.",
             tags=["smuggling", "one-shot"]),
        Item(name="Mathematician module",
             description="Old computation core from the pioneer "
             "years.",
             properties="Can compute jumps without an official "
             "chart; sometimes computes things no one asked for.",
             tags=["tech", "mystery"]),
        Item(name="Resonance bowl",
             description="Alien, pre-human bowl made of unnamed "
             "material.",
             properties="Vibrates near anomalies; warms when "
             "someone looks at it.",
             tags=["mystic", "find"]),
    ],
    glossary=[
        GlossaryEntry(term="Jump",
                      definition="Hyperspace travel between stars; "
                      "needs helium-3 and a navigation window."),
        GlossaryEntry(term="The Maw / Maws",
                      definition="Anomalous hyperspace sectors where "
                      "jump physics fails; officially 'anomaly fields'."),
        GlossaryEntry(term="Line / the Lines",
                      definition="Consortia that control routes, "
                      "tariffs and fuel."),
        GlossaryEntry(term="Consul",
                      definition="Mid-level Line functionary; "
                      "near-absolute power locally."),
        GlossaryEntry(term="Drift Station",
                      definition="Free-floating trading post at the "
                      "edge of charted space."),
        GlossaryEntry(term="Wrecker",
                      definition="Crews that salvage old colonial "
                      "wrecks; semi-legal."),
        GlossaryEntry(term="Tariff",
                      definition="Toll fee charged by the Lines for a "
                      "sanctioned route; often highway robbery."),
        GlossaryEntry(term="Free Worlds",
                      definition="Breakaway colonies opposed to the "
                      "Lines; under economic pressure."),
        GlossaryEntry(term="Academy",
                      definition="Jump school; only official "
                      "training for navigators."),
        GlossaryEntry(term="Anomaly field",
                      definition="Corridor where jump physics fails; "
                      "the Academy's official term."),
        GlossaryEntry(term="Sixth Frequency",
                      definition="Mystic cult that holds dead radio "
                      "signals to be a language."),
        GlossaryEntry(term="Mirror returner",
                      definition="Ship that returns from an anomaly "
                      "changed — mirrors reversed, crew altered or "
                      "silent."),
        GlossaryEntry(term="Khorr wreck",
                      definition="The graveyards of the pioneer "
                      "fleets in the Khorr sector."),
        GlossaryEntry(term="Collar AI",
                      definition="Half-awakened ship AI of older "
                      "make; often found in wrecks."),
        GlossaryEntry(term="Crew contract",
                      definition="Canonical document; binds the crew "
                      "for jumps, often with anti-anomaly clauses."),
        GlossaryEntry(term="Helium-3",
                      definition="Jump fuel; extraction and "
                      "distribution under Line lease."),
        GlossaryEntry(term="Black cargo",
                      definition="Illegal cargo; often Sixth-"
                      "Frequency relics or Free-World passes."),
        GlossaryEntry(term="Station misjump",
                      definition="Capital crime: materializing in or "
                      "near a station unplanned."),
        GlossaryEntry(term="Line ban",
                      definition="Economic ostracism of a world; "
                      "means hunger."),
        GlossaryEntry(term="Jump shock",
                      definition="Long-term psychological aftereffect "
                      "of too many jumps: hallucinations, foreign "
                      "voices."),
    ],
    history=[
        HistoryEvent(when="200 years ago", title="The First Expansion",
                     description="Hyperdrive invented; hundreds of "
                     "worlds settled; academies founded."),
        HistoryEvent(when="140 years ago",
                     title="The Khorr Disaster",
                     description="An entire pioneer fleet disappeared "
                     "in the Khorr sector; the wreck field drifts to "
                     "this day."),
        HistoryEvent(when="70 years ago",
                     title="The Line Compromise",
                     description="The great consortia formally "
                     "divide routes; local governments are stripped "
                     "of power."),
        HistoryEvent(when="40 years ago",
                     title="The Anomaly Scandal",
                     description="An Academy study about the maws is "
                     "suppressed; two researchers vanish."),
        HistoryEvent(when="18 years ago",
                     title="The Free Worlds War",
                     description="Uprising of the breakaway colonies; "
                     "crushed by economic blockade."),
        HistoryEvent(when="12 years ago",
                     title="The Kells Disaster",
                     description="A jump fleet vanishes near an "
                     "anomaly field; the sector has been off-limits "
                     "ever since."),
        HistoryEvent(when="5 years ago",
                     title="The Sixth Frequency Movement",
                     description="A mystic cult spreads through "
                     "drift stations; the Lines let it run."),
        HistoryEvent(when="2 years ago",
                     title="The Mira Pact",
                     description="The Free Worlds reorganize under "
                     "new consuls; hope returns."),
        HistoryEvent(when="last year", title="Mox Reform",
                     description="Consul Adran Mox builds his own "
                     "jump corps at the fringes."),
        HistoryEvent(when="a few weeks ago",
                     title="The First Mirror Returner",
                     description="A Line freighter returned with all "
                     "mirrors reversed; the crew has been silent "
                     "since."),
    ],
    fragments=[
        Fragment(title="The silent signal",
                 text="An ancient distress signal pulses from an "
                 "anomaly field. It speaks a language that should "
                 "not exist — and it names a name only your "
                 "grandmother knew.",
                 tags=["hook", "mystery"]),
        Fragment(title="Fuel shortage",
                 text="The gauges don't lie: two safe jumps left, "
                 "three with luck. Without helium-3 from the next "
                 "station, no more flying.",
                 tags=["stakes"]),
        Fragment(title="The false cargo manifest",
                 text="A cargo that officially does not exist "
                 "blocks your own hangar. The seal bears the "
                 "stamp of a consul who has been dead for two "
                 "years.",
                 tags=["politics", "intrigue"]),
        Fragment(title="Station alert",
                 text="Sirens on Kells. A Line ship has docked and "
                 "is searching every freighter that doesn't undock "
                 "in time. You have thirty minutes.",
                 tags=["hook", "pressure"]),
        Fragment(title="Crew mutiny in waiting",
                 text="The radio operator speaks secretly with the "
                 "bosun. Both fall silent when you enter. Something "
                 "is being planned — and you are not invited.",
                 tags=["crew", "conflict"]),
        Fragment(title="Mirror shock",
                 text="Your reflection in the cabin blinks a second "
                 "too late. You are not moving. Your reflection is.",
                 tags=["anomaly", "horror"]),
        Fragment(title="Line inspection",
                 text="An inspector comes aboard, polite, prepared. "
                 "She wants to see every log — and the room behind "
                 "Cargo Bay 4-South that you swore did not exist.",
                 tags=["politics", "pressure"]),
        Fragment(title="Wrecker call",
                 text="A wrecker clan offers a share of a salvage — "
                 "if you come today. The share is generous. That "
                 "makes you nervous.",
                 tags=["hook", "find"]),
        Fragment(title="Jump dreams",
                 text="After three jumps the whole crew dreams the "
                 "same blue light source. Nobody talks about it "
                 "until Doc Vrasa asks at breakfast: 'You too?'",
                 tags=["anomaly", "crew"]),
        Fragment(title="Smuggling request",
                 text="A desperate pilgrim asks for passage. He "
                 "offers his last savings — and something not "
                 "listed in any catalogue.",
                 tags=["passenger", "hook"]),
        Fragment(title="Consul's pact",
                 text="Mox offers a clean cargo contract. Payment "
                 "good, route safe. A clause in the fine print "
                 "demands that you unpack nothing — not even for "
                 "inspectors.",
                 tags=["politics", "intrigue"]),
        Fragment(title="Khorr echo",
                 text="The anomaly detector beeps. But there is no "
                 "corridor nearby and Khorr is light-years away. "
                 "Something else is here.",
                 tags=["anomaly"]),
        Fragment(title="Ship in distress",
                 text="A foreign freighter calls for help. The "
                 "signal is clear — but it comes from the empty "
                 "space between sectors. Nothing flies there.",
                 tags=["anomaly", "hook"]),
        Fragment(title="Holy fragment",
                 text="On the station a mystic sells a splinter "
                 "supposedly from a mirror returner. You feel "
                 "something when you touch it — something waiting.",
                 tags=["mystic", "find"]),
        Fragment(title="Line messenger",
                 text="A sealed Line message waits in the post "
                 "locker. Unopened. It feels cold, even though "
                 "the locker is warm.",
                 tags=["politics", "mystery"]),
        Fragment(title="Zero-G incident",
                 text="The grav plates fail for eight seconds. "
                 "When they return, one person is missing — and "
                 "a chair in the cargo bay is steaming.",
                 tags=["horror", "crew"]),
        Fragment(title="Collar voice",
                 text="An old ship AI calls on an emergency "
                 "channel. It demands a name it can no longer "
                 "remember itself. You are to guess.",
                 tags=["ai", "mystery"]),
        Fragment(title="Freighter funeral",
                 text="A stranded freighter is fired into the "
                 "anomaly field — cheapest salvage. Someone on "
                 "Kells cries. No one asks who.",
                 tags=["politics", "ambient"]),
        Fragment(title="Tariff hike",
                 text="The Lines double the jump fee without "
                 "warning. Half of Kells goes on strike. Nobody "
                 "in, nobody out. You neither.",
                 tags=["politics", "pressure"]),
        Fragment(title="Pact pilgrim",
                 text="A pilgrim of the Free Worlds asks for "
                 "safe passage. Catch him, you are rewarded. "
                 "Hide him, you are hunted. Listen to him, and "
                 "you change course.",
                 tags=["politics", "hook"]),
    ],
    blueprint=Blueprint(
        premise=(
            "An independent captain in the late age of jump travel "
            "navigates between Line pressure, scarce fuel, and an "
            "anomaly field that bends reality."
        ),
        escalation_rule=_ESCALATION_EN,
        beats=_functional_beats_en(),
    ),
    random_tables=[
        RandomTable(
            name="Hyperspace anomaly",
            description="What happens during a jump when physics "
            "wavers.",
            entries=[
                RandomEntry(weight=3, text="Time dilation: hours "
                            "become days."),
                RandomEntry(weight=2, text="Ghost echo of an alien "
                            "ship on the short band."),
                RandomEntry(weight=1, text="A voice whispers your "
                            "name from the dead band."),
                RandomEntry(weight=1, text="The cabin mirror shows "
                            "a different crew."),
                RandomEntry(weight=2, text="Fuel drains twice as "
                            "fast as it should."),
                RandomEntry(weight=2, text="Lights pulse to the "
                            "rhythm of a foreign heartbeat."),
                RandomEntry(weight=1, text="A second ship flies "
                            "200 km beside you and waves."),
                RandomEntry(weight=1, text="The charts show stars "
                            "that don't exist."),
                RandomEntry(weight=1, text="A crew member insists "
                            "they were just on the maintenance deck — "
                            "but were beside you."),
                RandomEntry(weight=1, text="A crashed shuttle "
                            "scrapes against the hull. You have none."),
                RandomEntry(weight=1, text="The shrines in the cargo "
                            "bay catch fire."),
                RandomEntry(weight=2, text="Half-second black gaps "
                            "in perception."),
                RandomEntry(weight=1, text="The jump console shows "
                            "a jump no one initiated."),
                RandomEntry(weight=1, text="Crew members visibly "
                            "age for three seconds."),
                RandomEntry(weight=2, text="The hull vibrates with "
                            "a three-tone chord that won't stop."),
                RandomEntry(weight=1, text="An empty channel clearly "
                            "states your date of birth."),
                RandomEntry(weight=1, text="The coffee maker spits "
                            "sulphur, then coffee."),
                RandomEntry(weight=1, text="You remember a jump you "
                            "never took."),
                RandomEntry(weight=1, text="The anomaly detector "
                            "melts."),
                RandomEntry(weight=1, text="Stars disappear in a "
                            "perfect line."),
                RandomEntry(weight=1, text="A second ship log "
                            "appears in the system — in your "
                            "handwriting."),
            ],
        ),
        RandomTable(
            name="Station encounter",
            description="Who crosses your path on Kells or a "
            "similar drift station.",
            entries=[
                RandomEntry(weight=2, text="An informant with half "
                            "the truth."),
                RandomEntry(weight=2, text="Bounty hunters working "
                            "for a consul."),
                RandomEntry(weight=1, text="A stranded xeno-"
                            "archaeologist with charts."),
                RandomEntry(weight=2, text="A young mechanic asks "
                            "to sign on — running from something."),
                RandomEntry(weight=1, text="A drunk Line inspector "
                            "with loose lips."),
                RandomEntry(weight=2, text="A Sixth-Frequency "
                            "pilgrim offers her savings for "
                            "passage."),
                RandomEntry(weight=1, text="A fence with a "
                            "'verified' Line plaque at half price."),
                RandomEntry(weight=1, text="A crew without a "
                            "captain looking for a new one."),
                RandomEntry(weight=1, text="A Free-Worlds fighter "
                            "recruiting comrades."),
                RandomEntry(weight=2, text="A wrecker with a map "
                            "and debts."),
                RandomEntry(weight=1, text="A Line messenger "
                            "delivers a sealed order."),
                RandomEntry(weight=1, text="A small gang of thieves "
                            "trying to crack a cargo lock."),
                RandomEntry(weight=2, text="A fight between two "
                            "captains escalates to a brawl."),
                RandomEntry(weight=1, text="A woman claims to be "
                            "your aunt — you have none."),
                RandomEntry(weight=1, text="A doc wants to fly "
                            "with you for a share."),
                RandomEntry(weight=1, text="An AI persona speaks "
                            "to you from a dusty kiosk."),
                RandomEntry(weight=1, text="A Line raid — all "
                            "papers checked."),
                RandomEntry(weight=1, text="A jump mystic offers "
                            "a free reading."),
                RandomEntry(weight=1, text="A traumatized crew "
                            "member of a mirror returner."),
                RandomEntry(weight=1, text="A child sells a "
                            "necklace with a helium-3 sigil."),
                RandomEntry(weight=1, text="A chase through the "
                            "corridors — you are the target."),
            ],
        ),
        RandomTable(
            name="Fuel and resource complication",
            description="What can go wrong when you need to refuel "
            "or stock up.",
            entries=[
                RandomEntry(weight=2, text="A cell reads 80% but is "
                            "empty."),
                RandomEntry(weight=2, text="The refueller demands "
                            "double — Line decree."),
                RandomEntry(weight=1, text="A cell leaks; the "
                            "reactor won't take it for long."),
                RandomEntry(weight=1, text="The fuel supplier has "
                            "been watched by a competitor."),
                RandomEntry(weight=2, text="Black-market cells "
                            "available — but Line-branded."),
                RandomEntry(weight=1, text="The maintenance crew "
                            "thinks an old cell is 'fizzing'."),
                RandomEntry(weight=1, text="A Line ban on Kells "
                            "delays every delivery for days."),
                RandomEntry(weight=1, text="A refueller offers a "
                            "double load — if you take someone "
                            "with you."),
                RandomEntry(weight=1, text="A faulty cell must be "
                            "dumped into the anomaly space."),
                RandomEntry(weight=2, text="The bosun improvises; "
                            "the reactor runs yellow for an hour."),
                RandomEntry(weight=1, text="A supply of hydrogen "
                            "substitute is smuggled in; flammable."),
                RandomEntry(weight=1, text="Supplies are stolen "
                            "while you are aboard."),
                RandomEntry(weight=1, text="The crew demands pay "
                            "or no more jumps."),
                RandomEntry(weight=1, text="An Academy intern "
                            "miscalculates; the jump costs more."),
                RandomEntry(weight=2, text="A route option is "
                            "significantly shorter — but barred."),
                RandomEntry(weight=1, text="A fuel cell trades "
                            "against a canister of jump-mystic "
                            "incense."),
                RandomEntry(weight=1, text="A Line freighter "
                            "docks and demands priority at the "
                            "pump."),
                RandomEntry(weight=1, text="A crew offers fuel "
                            "for a cargo contract you don't like."),
                RandomEntry(weight=1, text="Difficult hyperspace "
                            "conditions require a reserve."),
                RandomEntry(weight=1, text="A mystic promises "
                            "'fuel from the Sixth Frequency'."),
                RandomEntry(weight=1, text="A forged fueling "
                            "certificate is delivered to you."),
            ],
        ),
        RandomTable(
            name="Anomaly manifestation",
            description="What appears in or near an anomaly field.",
            entries=[
                RandomEntry(weight=2, text="A star pattern not in "
                            "any catalogue."),
                RandomEntry(weight=1, text="A dead radio signal in "
                            "Academy list 7-D languages."),
                RandomEntry(weight=1, text="A wreck without a crew, "
                            "but with warm coffee in the galley."),
                RandomEntry(weight=1, text="Six identical probes in "
                            "precise formation."),
                RandomEntry(weight=1, text="A light-being looking "
                            "through the hull."),
                RandomEntry(weight=2, text="Stars vanish in a line "
                            "and reappear."),
                RandomEntry(weight=1, text="A cloud not of gas but "
                            "of memories."),
                RandomEntry(weight=1, text="A second solar system "
                            "that wasn't there ten seconds ago."),
                RandomEntry(weight=1, text="An endlessly spinning "
                            "asteroid with burned-in patterns."),
                RandomEntry(weight=1, text="A voice that the entire "
                            "crew hears collectively."),
                RandomEntry(weight=1, text="A reflection blinks "
                            "five seconds too early."),
                RandomEntry(weight=2, text="Mirrors on board grow "
                            "warm."),
                RandomEntry(weight=1, text="An old radio signal "
                            "replies before you sent."),
                RandomEntry(weight=1, text="A pressure drop in the "
                            "cargo bay, with no leak."),
                RandomEntry(weight=1, text="A probe dances to a "
                            "waltz tempo."),
                RandomEntry(weight=1, text="The ship AI writes "
                            "verses in an old language into the log."),
                RandomEntry(weight=1, text="A wandering light source "
                            "in hyperspace that 'looks at' you."),
                RandomEntry(weight=1, text="A non-existent star "
                            "field computes itself onto the charts."),
                RandomEntry(weight=1, text="Magnetic fields respond "
                            "to crew emotions."),
                RandomEntry(weight=1, text="A small frosty statue "
                            "appears on a chair."),
                RandomEntry(weight=1, text="A crew member remembers "
                            "a journey, with evidence, that never "
                            "took place."),
            ],
        ),
        RandomTable(
            name="Line pressure",
            description="How the Lines make your life difficult.",
            entries=[
                RandomEntry(weight=2, text="A sealed order demands "
                            "a detour."),
                RandomEntry(weight=1, text="A consul politely asks "
                            "for passage."),
                RandomEntry(weight=2, text="Tariffs are doubled "
                            "without warning."),
                RandomEntry(weight=1, text="An inspector audits the "
                            "cargo manifest."),
                RandomEntry(weight=1, text="A Line ship demands "
                            "boarding."),
                RandomEntry(weight=1, text="An anonymous tip claims "
                            "you carry black cargo."),
                RandomEntry(weight=1, text="A Line corps assigns a "
                            "'companion' to your ship."),
                RandomEntry(weight=1, text="A sector is sealed — "
                            "just after your jump."),
                RandomEntry(weight=1, text="An Academy application "
                            "from your radio operator is on file "
                            "with the Line."),
                RandomEntry(weight=1, text="The crew contract is "
                            "reinterpreted without notice."),
                RandomEntry(weight=1, text="A Free-Worlds consul "
                            "offers asylum — for a cargo contract."),
                RandomEntry(weight=1, text="A raid on Kells "
                            "confiscates your favourite stim."),
                RandomEntry(weight=1, text="Radio blackmail: "
                            "someone knows an old jump violation."),
                RandomEntry(weight=1, text="Line pass confiscated — "
                            "until you answer a question."),
                RandomEntry(weight=2, text="An inspector offers "
                            "protection for a cut."),
                RandomEntry(weight=1, text="A Line messenger hands "
                            "you a commendation — and an order."),
                RandomEntry(weight=1, text="A PR camera crew wants "
                            "aboard for a report."),
                RandomEntry(weight=1, text="Mox's voice on the "
                            "radio: a personal invitation."),
                RandomEntry(weight=1, text="A mirror returner is "
                            "officially declared lost."),
                RandomEntry(weight=1, text="Line research requests "
                            "an anomaly sample."),
                RandomEntry(weight=1, text="A consul sends gifts; "
                            "wants you to recommend someone else."),
                RandomEntry(weight=1, text="A sector receives "
                            "'voluntary' Line oversight — quarters "
                            "for consuls."),
            ],
        ),
    ],
    complexity="standard",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=1, action=4, horror=2,
              pacing="medium"),
    wait_sound="scifi_waiting.wav",
    fx_preset=FXPreset(reverb_room_size=0.45, reverb_wet_level=0.15),
)


# ---------------- Worlds: Everwood (EN) ----------------

FANTASY_EN = World(
    id="immerwald",
    name="The Everwood Realm",
    display_name="Everwood",
    genre="High Fantasy",
    description=(
        "The Everwood Realm is an epic high-fantasy world at the "
        "end of a long, weary age. Ancient forests, crumbling "
        "kingdoms, half-forgotten powers turning in their sleep. "
        "The stars stand differently than they did three generations "
        "ago, the elders in the border villages say, and the forest "
        "has stopped breathing in the right rhythm.\n\n"
        "Geography: at the heart of the known world lies the "
        "Everwood — a forest so old and so vast that its borders "
        "have never been charted. It is not merely trees and "
        "animals; it is a power, a contract partner, an observer. "
        "Around it: fractured kingdoms, border keeps in varying "
        "decay, villages clustered in valleys. In the north, ice "
        "and pacts with beings whose names one does not speak. In "
        "the south, warm provinces with cleverer bureaucracy and "
        "darker secrets. In the east, the Ashlands, where once a "
        "kingdom burned. In the west, the sea no one likes.\n\n"
        "Politics: the kingdoms that once framed the wood have all "
        "failed in one way or another. Some broken, some hollowed "
        "out, some bound by pact-inheritances to powers that wait "
        "patiently. In their place stand captains, mage councils, "
        "old families with thin claims, and the rangers — a "
        "brotherhood at the border, half scouts, half mediators, "
        "half executioners. To act politically in this world is to "
        "think in generations, not weeks.\n\n"
        "Magic: rare, dangerous, costly. It is not a tool but a "
        "contract. Every spell draws on an old pact with the "
        "forest, the Otherworld, a stone, a star. And every pact "
        "demands a price: memory, time, blood, or the small things "
        "that make a life pleasant — your favourite colour, your "
        "mother's laugh, the taste of summer rain. Mages are "
        "rarely old and never rich.\n\n"
        "The Otherworld lies everywhere and nowhere at once — "
        "thin at moonstone places, dense at iron lattices, open "
        "at pact stones. It sometimes sends emissaries: faeries, "
        "changelings, talking animals, the dead with warm smiles. "
        "One negotiates with them as with nobles — with names, "
        "gifts, patience, and the constant possibility that "
        "something fundamentally foreign will misunderstand your "
        "offer.\n\n"
        "Threat: the old pacts are crumbling. Some are broken "
        "from within, by ambitious mage councils and fanatic "
        "royal houses who think they would be better off without "
        "the forest. Some shatter from outside, because something "
        "that was bound has waited long enough. In the heart of "
        "the Everwood something stirs. In the Ashlands a child "
        "finds her grandmother again in her sleep, though the "
        "woman has been dead for twenty years. In the border "
        "villages dogs fall silent, and in the court archives "
        "names appear that no one wrote.\n\n"
        "Here every story begins with a simple truth: you are a "
        "ranger or kin to one, you know the old words, and "
        "somewhere between keep and forest a task waits that no "
        "one else will take."
    ),
    player_role="Ranger in the service of a threatened borderland",
    starting_situation=(
        "You stand at the gate of an old border keep. Behind you, the "
        "last familiar world — guards, lamps, the smell of bread. "
        "Ahead, the forest, which has been silent for three days. No "
        "bird, no insect, only your own breath. A sealed order in your "
        "pocket; an iron dagger on your belt; and the knowledge that "
        "the old pacts are tearing somewhere out there."
    ),
    narration_style=(
        "Epic, vivid, with a saga tone; sensory nature description, "
        "menacing undertones. Address the ranger as 'you'. Concrete "
        "perceptions before mystical hints."
    ),
    voice_sample=(
        "The forest breathes slowly. Dew clings to the spiderwebs "
        "like cold glass beads. Something larger than a wolf has cut "
        "through the snow in the night — and it has not moved on."
    ),
    mood=(
        "Reverent, melancholy, threaded with lurking threat — but "
        "with room for quiet beauty."
    ),
    ambience=(
        "Moss and wet leaves, scent of resin, distant cracking, dim "
        "light through ancient crowns, a silence in which you hear "
        "your own heartbeat."
    ),
    magic_physics=(
        "Magic draws on old pacts with the forest and the Otherworld. "
        "Every spell exacts a price — memory, time, blood. Iron "
        "disturbs fae magic; moonstone places thin the border to the "
        "Otherworld; old names hold power over what knows them."
    ),
    places=[
        Place(name="Grayhold",
              description="Last border bastion before the Everwood; "
              "weary garrison, old secrets, a commander's tower "
              "untouched by repair for three generations.",
              tags=["start", "fortress"]),
        Place(name="The Everwood",
              description="Endless, ancient forest that seems to "
              "remember and to watch. The paths shift at night.",
              tags=["wilderness", "mystic"]),
        Place(name="Moonstone Glade",
              description="Place of old rites where the border to "
              "the Otherworld is thin. Stone circle, knee-high grass, "
              "three very old birches.",
              tags=["magic", "danger"]),
        Place(name="Ellenhag village",
              description="Last farming village before the wood. "
              "Smoked fish, a suspicious innkeeper, bells that have "
              "been silent for three days.",
              tags=["civil", "info"]),
        Place(name="The Wayward Stone of Vehl",
              description="Pact stone at an old crossing. Supplicants "
              "leave bread and coins; some prayers are answered.",
              tags=["magic", "pact"]),
        Place(name="The Ashlands",
              description="Burned kingdom on the eastern horizon. "
              "Black-frozen fields, village ruins, ashes that stay "
              "warm.",
              tags=["ruin", "tragic"]),
        Place(name="The Library of Nethrá",
              description="Half-collapsed monastery library. Monks "
              "who no longer pray, books that sometimes turn their "
              "own pages.",
              tags=["knowledge", "mystic"]),
        Place(name="Cave of the Forgotten Queen",
              description="Cave behind a waterfall. Inside, a "
              "sarcophagus whose lid has not been opened for 200 "
              "years.",
              tags=["danger", "lore"]),
        Place(name="The Brun Black Market",
              description="Half-legal market beneath the stairs of "
              "a crumbling city. Spell merchants, iron traders, "
              "rumours.",
              tags=["city", "trade"]),
        Place(name="Pact Grove of the Three Birches",
              description="Sacred grove deep in the Everwood. Here "
              "the rangers invite supplicants who are truly "
              "desperate.",
              tags=["magic", "contract"]),
        Place(name="The Glass City Beneath the Lake",
              description="Legendary Otherworld city some see on "
              "clear nights beneath the surface of a mountain lake. "
              "A moonstone place.",
              tags=["mystic", "otherworld"]),
        Place(name="The Iron Garden of Vorgst",
              description="Fortress garden made of iron rods — a "
              "magical ward against the Otherworld. Some rods are "
              "missing. No one talks about it.",
              tags=["fortress", "anti_magic"]),
    ],
    persons=[
        Person(name="Captain Eldra Vunn", role="Mentor",
               description="Scarred commander of Grayhold. Wears "
               "her weapons as casually as others wear their "
               "cloaks.",
               relations="Sends rangers down dangerous paths — and "
               "writes letters every night to her dead brother.",
               tags=["mentor", "keep"]),
        Person(name="The Ash King", role="Antagonist",
               description="Recurring, half-forgotten power from "
               "the heart of the forest. Appears rarely, acts "
               "always.",
               relations="Wants to break the old pacts — or "
               "renegotiate them, depending on whom you ask.",
               tags=["antagonist", "mystic"]),
        Person(name="Mage Councillor Vesna of Korr", role="Politics",
               description="Young, cool mage councillor of a "
               "southern court. Wears seven rings and a glass-hard "
               "ambition.",
               relations="Wants to disenchant the forest so that "
               "magic becomes more reliable.",
               tags=["politics", "mage"]),
        Person(name="Hekka the Healer", role="Ally",
               description="Old village healer in Ellenhag. Knows "
               "the names of every plant and most of the dead.",
               relations="Helps rangers if they ask respectfully; "
               "curses them if they don't.",
               tags=["healer", "info"]),
        Person(name="The Silent Scout Vorn",
               role="Ranger colleague",
               description="A ranger with a sewn-shut tongue — "
               "communicates in gestures and arrow-whistles. "
               "Still speaks clearly.",
               relations="Knows the paths of the deep wood; "
               "trusts few.",
               tags=["colleague", "scout"]),
        Person(name="Lord Eldwin Ash", role="Antagonist?",
               description="Last heir of a house that burned in "
               "the Ashlands. Lives in a ruin he cannot or will "
               "not leave.",
               relations="Claims that breaking the pacts is his "
               "right.",
               tags=["politics", "tragic"]),
        Person(name="The Birch Messenger",
               role="Otherworld being",
               description="A fae dressed in birch bark. Smiles "
               "too kindly, breathes too slowly.",
               relations="Delivers messages from the Otherworld — "
               "for memories.",
               tags=["otherworld", "contact"]),
        Person(name="Brother Halen", role="Knowledge",
               description="Last scribe of the Nethrá library. "
               "Mute for ten years, writes fast.",
               relations="Trades knowledge for books that you "
               "rescue.",
               tags=["knowledge", "neutral"]),
        Person(name="The old twins Krin and Krak", role="Contact",
               description="Two iron traders in Brun who don't "
               "talk much but know everything.",
               relations="Sell iron goods for stories; rarely for "
               "coin.",
               tags=["trade", "info"]),
        Person(name="The girl Eyla", role="Foundling",
               description="A child from the Ashlands. Remembers "
               "things that happened before her birth.",
               relations="Looks for someone who takes her "
               "memories seriously.",
               tags=["foundling", "mystic"]),
        Person(name="Captain Yrkenn of Ice", role="Politics",
               description="Captain of the northern Frostkeep. "
               "Taciturn, religious, fanatically loyal to a "
               "pact-tradition almost no one understands "
               "anymore.",
               relations="Would die for the pact; kills those "
               "who touch it.",
               tags=["politics", "antagonist?"]),
        Person(name="The Singing Wolf",
               role="Otherworld being",
               description="A wolf who speaks like a human — "
               "sometimes gently, sometimes commanding. Plays by "
               "old rules.",
               relations="Offers guidance for a name you know.",
               tags=["otherworld", "contact"]),
    ],
    items=[
        Item(name="Iron Dagger of Grayhold",
             description="A plain old blade with a scratched grip.",
             properties="Disturbs fae magic; breaks minor wards; "
             "burns Otherworld emissaries on touch.",
             tags=["weapon", "anti_magic"]),
        Item(name="Moonstone Amulet",
             description="Pale shimmering stone on a thin chain.",
             properties="Reveals nearby Otherworld borders by a "
             "cold flicker; also draws gazes from there.",
             tags=["magic", "clue"]),
        Item(name="Pact-stone splinter",
             description="Finger-sized splinter of a broken pact "
             "stone.",
             properties="Allows a single-use ward against an "
             "Otherworld being — then exhausted.",
             tags=["magic", "one-shot"]),
        Item(name="Ranger's cloak",
             description="Camouflage-green cloak with birch leaves "
             "sewn in.",
             properties="Keeps you overlooked in the Everwood if "
             "you stay quiet; loses its effect near iron.",
             tags=["gear", "stealth"]),
        Item(name="Bell of Ellenhag",
             description="Small bronze hand-bell from the village.",
             properties="Drives off Otherworld shadows; every ring "
             "costs you a minute of life.",
             tags=["magic", "price"]),
        Item(name="Birch pipe",
             description="Pipe of white birch bark.",
             properties="Calls the Singing Wolf — at most once a "
             "year, otherwise he stops coming.",
             tags=["mystic", "ritual"]),
        Item(name="Iron ring of the Brotherhood",
             description="Plain iron ring with a birch engraving.",
             properties="Sign of every ranger; opens doors at "
             "border keeps, closes them at royal courts.",
             tags=["sign", "politics"]),
        Item(name="Burned letter",
             description="Half-charred letter from the Ashlands.",
             properties="Changes its text when no one is watching. "
             "Reads slightly different every time.",
             tags=["mystic", "info"]),
        Item(name="Herbal pouch",
             description="Leather pouch with twelve herbs neatly "
             "sorted by family.",
             properties="Stops bleeding, clears shock; one herb "
             "is missing — no one talks about it.",
             tags=["medicine", "everyday"]),
        Item(name="Moondisc of the Three Birches",
             description="Silver, finger-sized disc with etched "
             "constellations.",
             properties="Shows its bearer the way to the nearest "
             "pact grove — even if she doesn't want it.",
             tags=["magic", "navigation"]),
    ],
    glossary=[
        GlossaryEntry(term="The Pacts",
                      definition="Ancient treaties between humans, "
                      "forest and Otherworld that bind the powers."),
        GlossaryEntry(term="Otherworld",
                      definition="Ghostly parallel world behind thin "
                      "border places; own rules, own nobles."),
        GlossaryEntry(term="Ranger",
                      definition="Border scout of the Brotherhood, "
                      "mediator between keep, wood and Otherworld."),
        GlossaryEntry(term="Ash King",
                      definition="Sleeping power in the heart of the "
                      "Everwood; wakes when the pacts break."),
        GlossaryEntry(term="Pact stone",
                      definition="Ritual border stone embodying a "
                      "specific pact; breaking it dissolves the "
                      "contract."),
        GlossaryEntry(term="Moonstone place",
                      definition="Spot where the border to the "
                      "Otherworld is naturally thin; dangerous."),
        GlossaryEntry(term="Brotherhood (of Rangers)",
                      definition="Loose union of all rangers; own "
                      "honour, own rules, own courts."),
        GlossaryEntry(term="Mage Council",
                      definition="Advisory body at a royal court; "
                      "often rival of the ranger tradition."),
        GlossaryEntry(term="Otherworld emissary",
                      definition="Being from 'across' that carries a "
                      "message — faerie, wolf, shadow."),
        GlossaryEntry(term="Changeling",
                      definition="Child replaced by an Otherworld "
                      "being; rare, hard to detect."),
        GlossaryEntry(term="Iron ward",
                      definition="Iron lattice or ring; prevents "
                      "crossings from the Otherworld."),
        GlossaryEntry(term="Pact price",
                      definition="What a spell costs: memory, time, "
                      "blood or a favourite thing."),
        GlossaryEntry(term="Healer",
                      definition="Village-recognized magical "
                      "practitioner; works with plants, bones, small "
                      "pacts."),
        GlossaryEntry(term="Border keep",
                      definition="Fortified garrison at a wood or "
                      "Otherworld border; mostly outdated, often "
                      "understaffed."),
        GlossaryEntry(term="The Ashlands",
                      definition="Burned kingdom in the east; "
                      "result of a broken pact three generations "
                      "ago."),
        GlossaryEntry(term="Grove",
                      definition="Sacred wood place; prayer, pact, "
                      "or gathering ground."),
        GlossaryEntry(term="Ward (minor / greater)",
                      definition="Magical barrier; minor wards stop "
                      "individual beings, greater wards entire "
                      "powers. Brittle over time."),
        GlossaryEntry(term="Nethrá",
                      definition="Half-collapsed monastery library; "
                      "the only written archive of pact records."),
        GlossaryEntry(term="Shadow path",
                      definition="Path that shortens through the "
                      "Otherworld; saves time, always costs "
                      "something."),
        GlossaryEntry(term="The Silence",
                      definition="When the forest falls mute — an "
                      "omen that something great is waking."),
    ],
    history=[
        HistoryEvent(when="in the First Age",
                     title="The Great Pact",
                     description="Human and forest made peace; the "
                     "Ash King was bound, the first moonstone places "
                     "sealed."),
        HistoryEvent(when="in the Second Age",
                     title="The Seven Kingdoms",
                     description="Seven realms rose around the wood; "
                     "each had its own pact, its own duties."),
        HistoryEvent(when="500 years ago",
                     title="The Northern Break",
                     description="A kingdom broke its pact; winter "
                     "came and never quite left."),
        HistoryEvent(when="200 years ago",
                     title="The Sealing of the Ash King",
                     description="An alliance of rangers and mage "
                     "councils sealed the Ash King once more; many "
                     "died, the sarcophagus stands in a cave."),
        HistoryEvent(when="three generations ago",
                     title="The Burning of the Ashlands",
                     description="A broken pact left a kingdom in "
                     "ashes; the ground in the east still smoulders."),
        HistoryEvent(when="80 years ago",
                     title="The Silence of Ellenhag",
                     description="An entire village vanished for "
                     "three days and returned older; no one speaks "
                     "of it."),
        HistoryEvent(when="40 years ago",
                     title="Rise of the Mage Councils",
                     description="Mage councils gained political "
                     "influence at the courts; rangers became "
                     "eccentrics."),
        HistoryEvent(when="15 years ago",
                     title="The Iron Garden Incident",
                     description="In the Iron Garden of Vorgst a "
                     "third of the rods disappeared overnight; the "
                     "ward holds nonetheless — barely."),
        HistoryEvent(when="5 years ago",
                     title="The Return of the Messenger",
                     description="An Otherworld messenger reappeared "
                     "after a hundred-year absence; her message was "
                     "not made public."),
        HistoryEvent(when="one moon-cycle ago",
                     title="The silent birds",
                     description="In the Everwood all creatures "
                     "fell silent; the rangers sent scouts who did "
                     "not return."),
    ],
    fragments=[
        Fragment(title="The silenced birds",
                 text="In the Everwood every creature has been "
                 "silent for three days. Even the crows that "
                 "usually call over the Ashlands are gone. "
                 "Something old is awake.",
                 tags=["hook", "omen"]),
        Fragment(title="The broken pact stone",
                 text="A boundary stone of the old treaties has "
                 "been shattered. The break is not weathered — "
                 "fresh. Beside it three coins of a mint not "
                 "struck for two hundred years.",
                 tags=["stakes", "hook"]),
        Fragment(title="The sleeper in the sarcophagus",
                 text="In the cave of the Forgotten Queen the "
                 "sarcophagus is sweating. Water drips that is "
                 "not water. The sealing holds — barely.",
                 tags=["mystery", "stakes"]),
        Fragment(title="Letter from a dead uncle",
                 text="In the post box at Grayhold lies a letter "
                 "in the handwriting of a man dead for 20 years. "
                 "It names your birth name, which no one alive "
                 "knows.",
                 tags=["hook", "otherworld"]),
        Fragment(title="The bells of Ellenhag",
                 text="The village bells have been silent for "
                 "three days. The innkeeper says they were "
                 "stolen. You see them hanging — they simply make "
                 "no sound.",
                 tags=["mystery", "ambient"]),
        Fragment(title="The child in the ashes",
                 text="A child sits on the warm ground of the "
                 "Ashlands and laughs. It has your face, only "
                 "younger. It waves.",
                 tags=["horror", "otherworld"]),
        Fragment(title="Sealed orders",
                 text="Eldra Vunn hands over a sealed letter with "
                 "the instruction to open it only in the Pact "
                 "Grove of the Three Birches. The wax seal "
                 "trembles in your hand.",
                 tags=["hook", "politics"]),
        Fragment(title="Tracks that lead in a circle",
                 text="In the snow at the wood's edge you find "
                 "fresh tracks — your size, your step. They go in "
                 "a circle. You haven't been here yet.",
                 tags=["anomaly", "stakes"]),
        Fragment(title="Mage council emissary",
                 text="An emissary of councillor Vesna of Korr "
                 "comes to Grayhold. Polite, but too polite. His "
                 "horse sweats; the emissary does not.",
                 tags=["politics", "intrigue"]),
        Fragment(title="The messenger's request",
                 text="The Birch Messenger meets you at the way "
                 "stone. She asks for three memories — the "
                 "smallest you have. In exchange: a name the Ash "
                 "King does not know.",
                 tags=["otherworld", "trade"]),
        Fragment(title="Iron Garden gap",
                 text="In the Iron Garden of Vorgst a rod is "
                 "missing. The ward holds — barely. Three guards "
                 "vanished in the night without a trace.",
                 tags=["fortress", "stakes"]),
        Fragment(title="Library whisper",
                 text="In the Nethrá library a book turns its own "
                 "page. Brother Halen hands you paper and pen so "
                 "you can transcribe.",
                 tags=["knowledge", "mystery"]),
        Fragment(title="The singing wolf",
                 text="At the wood's edge a wolf sits and hums a "
                 "tune you know from childhood. He waits until "
                 "you look at him, then nods.",
                 tags=["otherworld", "hook"]),
        Fragment(title="Pact grove silence",
                 text="In the Pact Grove of the Three Birches the "
                 "silence is so total that your own heartbeat "
                 "sounds loud. One of the birches has a fresh "
                 "wound in its trunk.",
                 tags=["magic", "stakes"]),
        Fragment(title="Ash dust in the bread",
                 text="In Ellenhag the bread tastes of ash today. "
                 "The innkeeper won't take it back; she looks "
                 "away while you eat.",
                 tags=["ambient", "omen"]),
        Fragment(title="Lord Ash invites",
                 text="A messenger of Lord Eldwin Ash invites "
                 "you to his ruin. He says he has answers. He "
                 "does not say to which questions.",
                 tags=["politics", "hook"]),
        Fragment(title="Late-summer frost",
                 text="Frost forms at the wood's edge though it "
                 "is late summer. The healing herb withers "
                 "before your eyes. Hekka says she has never "
                 "seen this.",
                 tags=["anomaly", "stakes"]),
        Fragment(title="Two-moon night",
                 text="Tonight a second moon hangs in the sky, "
                 "pale and offset. No one in the keep sees it but "
                 "you and an old soldier who weeps.",
                 tags=["otherworld", "mystery"]),
        Fragment(title="The Silent Scout does not stay silent",
                 text="Vorn the Silent Scout whistles three "
                 "notes in the order every ranger knows — "
                 "retreat, now, no explanation. He does not look "
                 "back.",
                 tags=["scout", "stakes"]),
        Fragment(title="Eyla remembers",
                 text="The girl Eyla describes to you a battle "
                 "that happened a hundred years ago in the "
                 "Ashlands. In detail. She is nine.",
                 tags=["foundling", "mystery"]),
    ],
    blueprint=Blueprint(
        premise=(
            "A ranger must travel to the edge of the known, where old "
            "powers are waking, and choose between preserving and "
            "binding them."
        ),
        escalation_rule=_ESCALATION_EN,
        beats=_functional_beats_en(),
    ),
    random_tables=[
        RandomTable(
            name="Forest signs",
            description="What the protagonist perceives while "
            "travelling the Everwood.",
            entries=[
                RandomEntry(weight=3, text="Fresh tracks that lead "
                            "in a circle."),
                RandomEntry(weight=2, text="A shrine with a fresh "
                            "offering — bread, three coins, a lock "
                            "of hair."),
                RandomEntry(weight=1, text="A voice calls your true "
                            "name from the thicket."),
                RandomEntry(weight=2, text="Twisted birch wood, "
                            "grown in spirals."),
                RandomEntry(weight=1, text="Three dead crows laid "
                            "out in a precise row."),
                RandomEntry(weight=1, text="A clearing that was "
                            "not here yesterday."),
                RandomEntry(weight=2, text="A path that opens ahead "
                            "of you and closes behind."),
                RandomEntry(weight=1, text="A pact stone with fresh "
                            "scratches."),
                RandomEntry(weight=1, text="Frost on a stone, "
                            "though it is late summer."),
                RandomEntry(weight=1, text="A footprint in snow, "
                            "though no snow lies."),
                RandomEntry(weight=1, text="A tree that hums when "
                            "no one is looking."),
                RandomEntry(weight=2, text="Glowing mushrooms in "
                            "rows like inscriptions."),
                RandomEntry(weight=1, text="A footprint three "
                            "times your size."),
                RandomEntry(weight=1, text="A spring that flows "
                            "backwards — briefly."),
                RandomEntry(weight=1, text="An old song in the "
                            "air, with no singer."),
                RandomEntry(weight=1, text="Spider webs spelling "
                            "out a word."),
                RandomEntry(weight=1, text="A crow feather with "
                            "etched runes."),
                RandomEntry(weight=1, text="A creaking silence in "
                            "which a single bird calls once and "
                            "stops."),
                RandomEntry(weight=1, text="Moon flowers opening "
                            "at the wrong time of day."),
                RandomEntry(weight=1, text="A forgotten travel "
                            "cloak on a branch — your size."),
                RandomEntry(weight=1, text="A stone with your "
                            "name on it — very old."),
            ],
        ),
        RandomTable(
            name="Encounter on the path",
            description="Whom the protagonist meets along the "
            "way.",
            entries=[
                RandomEntry(weight=2, text="A family fleeing the "
                            "forest."),
                RandomEntry(weight=2, text="A scout of the Ash King "
                            "in borrowed shape."),
                RandomEntry(weight=1, text="A talking animal with "
                            "a plea."),
                RandomEntry(weight=2, text="A pilgrim to the pact "
                            "stone at Vehl with three coins."),
                RandomEntry(weight=1, text="A wanderer without "
                            "eyebrows, pointing north."),
                RandomEntry(weight=1, text="A distraught peasant "
                            "embracing a bell."),
                RandomEntry(weight=2, text="Another ranger with a "
                            "crossed cloak — distress sign."),
                RandomEntry(weight=1, text="A mage council emissary "
                            "with an unwilling horse."),
                RandomEntry(weight=1, text="A horse caravan with "
                            "locked goods."),
                RandomEntry(weight=2, text="A changeling pretending "
                            "to be a child."),
                RandomEntry(weight=1, text="A witch offering remedies "
                            "— for a memory."),
                RandomEntry(weight=1, text="A dead man who does not "
                            "know he is dead."),
                RandomEntry(weight=1, text="An iron trader from Brun "
                            "with a cart full of rods."),
                RandomEntry(weight=1, text="A monk from Nethrá "
                            "burning paper."),
                RandomEntry(weight=1, text="A noble rider without a "
                            "crest — southern accent."),
                RandomEntry(weight=1, text="A child alone in the "
                            "snow humming an old song."),
                RandomEntry(weight=1, text="A woman claiming to be "
                            "your mother — whom you believe lost."),
                RandomEntry(weight=1, text="A wagon with mourning "
                            "bells no one is touching."),
                RandomEntry(weight=1, text="A pact supplicant, "
                            "bloodied, on the edge of giving up."),
                RandomEntry(weight=1, text="A patrol of the "
                            "Frostkeep, much too far south."),
                RandomEntry(weight=1, text="A minstrel who sings "
                            "only backwards."),
            ],
        ),
        RandomTable(
            name="Ward complication",
            description="What goes wrong when the protagonist acts "
            "magically or needs a ward.",
            entries=[
                RandomEntry(weight=2, text="A minor ward only half "
                            "holds — something gets through."),
                RandomEntry(weight=2, text="The pact price turns "
                            "out higher than expected."),
                RandomEntry(weight=1, text="A memory you needed "
                            "vanishes."),
                RandomEntry(weight=1, text="Iron nearby weakens "
                            "the ward unintentionally."),
                RandomEntry(weight=2, text="The ward holds, but "
                            "the warder visibly ages."),
                RandomEntry(weight=1, text="Other things are drawn: "
                            "small beings, many."),
                RandomEntry(weight=1, text="The ward holds longer "
                            "than wanted — you can't leave."),
                RandomEntry(weight=1, text="An animal nearby dies, "
                            "seemingly without cause."),
                RandomEntry(weight=2, text="The pact stone develops "
                            "a fine crack."),
                RandomEntry(weight=1, text="An Otherworld emissary "
                            "steps forward immediately, polite, "
                            "demanding."),
                RandomEntry(weight=1, text="The weather turns — "
                            "frost in summer."),
                RandomEntry(weight=1, text="The bell of Ellenhag "
                            "falls silent for three days."),
                RandomEntry(weight=1, text="A sound wanders off — "
                            "no echo in your voice anymore."),
                RandomEntry(weight=1, text="A second shadow walks "
                            "with you briefly."),
                RandomEntry(weight=1, text="The sun stands for "
                            "seconds in the wrong direction."),
                RandomEntry(weight=1, text="A song begins in your "
                            "head that you cannot stop."),
                RandomEntry(weight=1, text="A pact from your "
                            "childhood comes due — no one warned "
                            "you."),
                RandomEntry(weight=1, text="A coin in your pocket "
                            "turns hot."),
                RandomEntry(weight=1, text="Your iron dagger goes "
                            "blunt without contact."),
                RandomEntry(weight=1, text="For three days water "
                            "tastes of iron."),
                RandomEntry(weight=1, text="One eye dreams awake; "
                            "the other sleeps standing."),
            ],
        ),
        RandomTable(
            name="Otherworld trade",
            description="What Otherworld beings offer — and what "
            "they demand.",
            entries=[
                RandomEntry(weight=2, text="A name the Ash King "
                            "does not know — for three small "
                            "memories."),
                RandomEntry(weight=2, text="A safe path through "
                            "the wood — for your favourite colour."),
                RandomEntry(weight=1, text="Healing of an injury — "
                            "for seven hours of lifespan."),
                RandomEntry(weight=1, text="A truthful answer to a "
                            "question — for the taste of summer "
                            "rain."),
                RandomEntry(weight=2, text="A message to a dead "
                            "person — for a lock of hair."),
                RandomEntry(weight=1, text="A vision of the future "
                            "— for the ability to cry for a year."),
                RandomEntry(weight=1, text="Sleep without dreams — "
                            "for a tear of your mother's."),
                RandomEntry(weight=1, text="A song that lulls "
                            "guards to sleep — for your favourite "
                            "melody."),
                RandomEntry(weight=2, text="A pact-stone splinter "
                            "— for a memory of your father."),
                RandomEntry(weight=1, text="Translation of an "
                            "Otherworld word — for an hour of your "
                            "voice."),
                RandomEntry(weight=1, text="A shadow that fights "
                            "for you — for your reflection for "
                            "three days."),
                RandomEntry(weight=1, text="A gift for a loved one "
                            "— for the knowledge of how it was "
                            "sent."),
                RandomEntry(weight=1, text="Protection from a "
                            "specific being — for the name of a "
                            "friend."),
                RandomEntry(weight=1, text="A language you never "
                            "learned — for your mother tongue for "
                            "a moon-cycle."),
                RandomEntry(weight=1, text="A sword no one sees — "
                            "for the profession of your choice."),
                RandomEntry(weight=1, text="Three days of luck — "
                            "for three years of vigilance."),
                RandomEntry(weight=1, text="A second chance in one "
                            "matter — for your first choice."),
                RandomEntry(weight=1, text="A dog that never dies "
                            "— for the day of your birthday."),
                RandomEntry(weight=1, text="A map of the Everwood "
                            "— for the taste of bread."),
                RandomEntry(weight=1, text="A step through the "
                            "Otherworld — for the courage to "
                            "return."),
                RandomEntry(weight=1, text="A true pact — for "
                            "every future pact."),
            ],
        ),
        RandomTable(
            name="Political complication",
            description="How the royal court, mage council and "
            "Brotherhood make the protagonist's life difficult.",
            entries=[
                RandomEntry(weight=2, text="A mage council demands "
                            "a report — before the Brotherhood "
                            "gets one."),
                RandomEntry(weight=2, text="Eldra Vunn receives "
                            "orders from above to recall you."),
                RandomEntry(weight=1, text="A royal court messenger "
                            "invites you to court — with escort."),
                RandomEntry(weight=2, text="Vesna of Korr sends an "
                            "'observer' along."),
                RandomEntry(weight=1, text="An iron trader is "
                            "arrested; your contacts in Brun dry "
                            "up."),
                RandomEntry(weight=1, text="Lord Ash claims salvage "
                            "rights on a find — and sends "
                            "mercenaries."),
                RandomEntry(weight=1, text="The northern captain "
                            "Yrkenn of Ice demands an oath of "
                            "loyalty."),
                RandomEntry(weight=1, text="A pact supplicant at "
                            "the wayward stone at Vehl later sues "
                            "you."),
                RandomEntry(weight=2, text="The mage councils ban "
                            "entering the Iron Garden without "
                            "permission."),
                RandomEntry(weight=1, text="An audience is "
                            "postponed — you lose time you don't "
                            "have."),
                RandomEntry(weight=1, text="An anonymous letter "
                            "claims you broke a pact yourself."),
                RandomEntry(weight=1, text="Ellenhag delivers no "
                            "provisions — orders from above."),
                RandomEntry(weight=1, text="Brother Halen sends "
                            "warning: someone is copying your "
                            "file."),
                RandomEntry(weight=1, text="The Brotherhood sends "
                            "an arbitrator who does not speak a "
                            "word."),
                RandomEntry(weight=1, text="A mage council envoy "
                            "offers protection for an oath."),
                RandomEntry(weight=1, text="Yrkenn sends a patrol "
                            "operating too far south."),
                RandomEntry(weight=1, text="The black market of "
                            "Brun is raided; your sources "
                            "disappear."),
                RandomEntry(weight=1, text="An envoy of Vesna of "
                            "Korr offers a trade — Iron Garden "
                            "for silence."),
                RandomEntry(weight=1, text="A child appears, "
                            "claiming to be heir to a burned "
                            "house."),
                RandomEntry(weight=1, text="An old family invites "
                            "you to dinner — with iron at the "
                            "table."),
                RandomEntry(weight=1, text="The Frostkeep sends a "
                            "ward stone as a gift — poisoned?"),
            ],
        ),
    ],
    complexity="rich",
    audience="erwachsene",
    tone=Tone(darkness=3, humor=1, romance=2, action=3, horror=2,
              pacing="medium"),
    wait_sound="fantasy_waiting.wav",
    fx_preset=FXPreset(reverb_room_size=0.7, reverb_wet_level=0.22),
)


# ---------------- Locale registry + writer ----------------

SEED_WORLDS = [SCIFI, FANTASY]  # default (de) — backwards-compatible
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
