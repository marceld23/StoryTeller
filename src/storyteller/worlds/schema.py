"""Datenmodell einer Spielwelt.

Alle inhaltlichen Teile (Orte, Personen, Gegenstände, Fragmente, Historie,
Glossar) werden in sqlite-vec embeddet und beim Erzählen per RAG (gefiltert
nach world_id + Typ) eingespeist. Blueprint hält den Makro-Spannungsbogen
(„Bauplan"). random_tables sind KONKRETE, welt-spezifische Zufallslisten, die
der Erzähler aktiv per Tool zieht (NICHT die abstrakte Story-Dynamik).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Place(BaseModel):
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)


class Person(BaseModel):
    name: str
    role: str = ""
    description: str = ""
    relations: str = ""
    tags: list[str] = Field(default_factory=list)


class Item(BaseModel):
    """Gegenstand / Artefakt."""

    name: str
    description: str = ""
    properties: str = ""          # Wirkung / besondere Eigenschaften
    tags: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    """Begriffserklärung — sorgt für konsistente Welt-Terminologie."""

    term: str
    definition: str


class HistoryEvent(BaseModel):
    """Ein historisches Ereignis / Epoche der Welt."""

    when: str = ""                # Zeit/Epoche (frei)
    title: str
    description: str = ""


class Fragment(BaseModel):
    """Lore / Story-Hook / Ereignis-Baustein."""

    title: str
    text: str
    tags: list[str] = Field(default_factory=list)


class Beat(BaseModel):
    """Ein Punkt im Spannungsbogen."""

    name: str
    goal: str
    tension: int = Field(ge=0, le=10)  # 0=ruhig … 10=Höhepunkt


class Blueprint(BaseModel):
    """Bauplan: Beat-Folge + Eskalationslogik (Makro-Spannungsbogen)."""

    premise: str
    beats: list[Beat] = Field(default_factory=list)
    escalation_rule: str = (
        "Steigere Spannung pro Beat; greife Spieler-Ideen auf und webe sie ein, "
        "ohne den Spieler auf Schienen zu setzen."
    )


class RandomEntry(BaseModel):
    weight: int = 1
    text: str


class RandomTable(BaseModel):
    """Welt-spezifische, KONKRETE Zufallsliste (vom Erzähler aktiv gezogen)."""

    name: str
    description: str = ""
    entries: list[RandomEntry] = Field(default_factory=list)


class FXPreset(BaseModel):
    """Pro-Welt Stimm-Effekt (überschreibt [fx] aus config.toml)."""

    reverb_room_size: float | None = None
    reverb_damping: float | None = None
    reverb_wet_level: float | None = None
    reverb_dry_level: float | None = None
    distortion_drive_db: float | None = None


class World(BaseModel):
    # --- Kern / Beschreibung ---
    id: str
    name: str
    genre: str
    description: str                       # Spiel-/Weltbeschreibung
    player_role: str
    starting_situation: str = ""           # Beschreibung der Ausgangssituation
    narration_style: str = ""              # Erzählton (technisch)
    mood: str = ""                         # Grundstimmung
    ambience: str = ""                     # Ambiente / Sinneseindrücke
    magic_physics: str = ""                # Physik- bzw. Magiesystem (Regeln)

    # --- Strukturierter Weltinhalt ---
    places: list[Place] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    fragments: list[Fragment] = Field(default_factory=list)

    # --- Dramaturgie & Spielmechanik ---
    blueprint: Blueprint
    random_tables: list[RandomTable] = Field(default_factory=list)

    # --- Präsentation ---
    wait_sound: str = ""
    fx_preset: FXPreset = Field(default_factory=FXPreset)
