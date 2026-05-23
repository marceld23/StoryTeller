"""Data model of a game world.

All content parts (places, persons, items, fragments, history, glossary) are
embedded in sqlite-vec and injected at narration time via RAG (filtered by
world_id + type). The blueprint holds the macro arc. random_tables are
CONCRETE, world-specific random lists the narrator actively rolls via a tool
(NOT the abstract story dynamic).
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
    """Object / artifact."""

    name: str
    description: str = ""
    properties: str = ""          # effect / special properties
    tags: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    """Term definition — ensures consistent world terminology."""

    term: str
    definition: str


class HistoryEvent(BaseModel):
    """A historical event / era of the world."""

    when: str = ""                # time/era (free text)
    title: str
    description: str = ""


class Fragment(BaseModel):
    """Lore / story hook / event building block."""

    title: str
    text: str
    tags: list[str] = Field(default_factory=list)


class Beat(BaseModel):
    """A point in the tension arc."""

    name: str
    goal: str
    tension: int = Field(ge=0, le=10)  # 0=calm … 10=climax


class Blueprint(BaseModel):
    """Blueprint: beat sequence + escalation logic (macro tension arc)."""

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
    """World-specific, CONCRETE random list (actively rolled by the narrator)."""

    name: str
    description: str = ""
    entries: list[RandomEntry] = Field(default_factory=list)


class FXPreset(BaseModel):
    """Per-world voice effect (overrides [fx] from config.toml)."""

    reverb_room_size: float | None = None
    reverb_damping: float | None = None
    reverb_wet_level: float | None = None
    reverb_dry_level: float | None = None
    distortion_drive_db: float | None = None


class Tone(BaseModel):
    """Per-world tonal / genre preferences (0 = none/light .. 5 = strong)."""

    darkness: int = 2          # light-hearted .. grim
    humor: int = 1
    romance: int = 1
    action: int = 3
    horror: int = 1
    pacing: str = "medium"     # slow | medium | fast
    notes: str = ""            # free-text genre/tone preferences


class World(BaseModel):
    # --- Core / description ---
    id: str
    name: str
    display_name: str = ""                 # short name for voice menu/TTS; "" => fall back to `name`
    genre: str
    description: str                       # game/world description
    player_role: str
    starting_situation: str = ""           # description of the starting situation
    narration_style: str = ""              # narrative tone (technical)
    voice_sample: str = ""                 # 1-2 example sentences in the world's style (style anchor)
    mood: str = ""                         # base mood
    ambience: str = ""                     # ambience / sensory impressions
    magic_physics: str = ""                # physics or magic system (rules)

    # --- Dramaturgy control (per world) ---
    complexity: str = "standard"           # simple | standard | rich
    story_patterns: list[str] = Field(default_factory=list)  # empty = by complexity
    audience: str = "erwachsene"           # target group / age, e.g. "12+"
    tone: Tone = Field(default_factory=Tone)

    # --- Structured world content ---
    places: list[Place] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    fragments: list[Fragment] = Field(default_factory=list)

    # --- Dramaturgy & game mechanics ---
    blueprint: Blueprint
    random_tables: list[RandomTable] = Field(default_factory=list)

    # --- Presentation ---
    wait_sound: str = ""
    fx_preset: FXPreset = Field(default_factory=FXPreset)
