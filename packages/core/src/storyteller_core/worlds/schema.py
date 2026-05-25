"""Data model of a game world.

All content parts (places, persons, items, fragments, history, glossary) are
embedded in sqlite-vec and injected at narration time via RAG (filtered by
world_id + type). The blueprint holds the macro arc. random_tables are
CONCRETE, world-specific random lists the narrator actively rolls via a tool
(NOT the abstract story dynamic).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Region(BaseModel):
    """A larger geography / area / domain. Places live inside regions —
    every Place.region SHOULD name an existing Region (the generator
    enforces this when both lists are produced together)."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class Place(BaseModel):
    name: str
    description: str
    region: str = ""                                  # Region name (or "")
    contains: list[str] = Field(default_factory=list)  # Sub-places by name
    adjacent: list[str] = Field(default_factory=list)  # Neighbouring places
    tags: list[str] = Field(default_factory=list)


class Faction(BaseModel):
    """A group / order / guild / power with goals and stance toward others."""

    name: str
    description: str = ""
    goals: str = ""
    allies: list[str] = Field(default_factory=list)
    enemies: list[str] = Field(default_factory=list)
    relations: str = ""                              # free-text nuance
    tags: list[str] = Field(default_factory=list)


class Person(BaseModel):
    name: str
    role: str = ""
    description: str = ""
    relations: str = ""                              # ties to other persons
    faction: str = ""                                # primary Faction (or "")
    faction_role: str = ""                           # role within that faction
    tags: list[str] = Field(default_factory=list)


class Creature(BaseModel):
    """A non-person being of the world (animal, monster, spirit, …).
    Habitat references a Region or place type."""

    name: str
    description: str = ""
    habitat: str = ""                                # Region name or place type
    threat_level: str = "medium"                     # low | medium | high
    tags: list[str] = Field(default_factory=list)


class TechMagic(BaseModel):
    """Structured description of the world's tech / magic system.
    Backs the free-text `World.magic_physics` summary; the narrator
    consults `rules` for what the world actually allows."""

    kind: str = "neither"                            # technology|magic|both|neither
    description: str = ""
    rules: list[str] = Field(default_factory=list)
    cost_or_risk: str = ""


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


class BlueprintVariant(BaseModel):
    """One self-contained story arc variant for a world. Multiple
    variants per world unlock replay value + tonal range — the
    substory planner picks the one that fits the player's current
    context. Fields beyond `blueprint` itself are signals the
    picker uses (length / structure / twist_kind / trigger_hints)."""

    name: str
    description: str = ""
    # Rough arc size — picker uses this to balance against player
    # appetite (someone three sessions deep tends toward longer arcs).
    length: str = "medium"               # short | medium | long | epic
    # Macro shape — gives the narrator a hint about pacing & callbacks.
    structure: str = "linear"            # linear | parallel | spiral
                                          #  | frame  | mosaic
    # Twist archetype the variant is built around. Empty = no
    # explicit twist baked in (a quieter slice-of-life arc).
    twist_kind: str = ""                 # betrayal | revelation |
                                          #  sacrifice | hidden_enemy |
                                          #  red_herring | role_reversal |
                                          #  circular | ""
    # Themes / setting cues that make this variant a natural fit.
    # Surfaced to the picker so it can match against player history.
    trigger_hints: list[str] = Field(default_factory=list)
    blueprint: Blueprint


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
    regions: list[Region] = Field(default_factory=list)
    places: list[Place] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    creatures: list[Creature] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    fragments: list[Fragment] = Field(default_factory=list)
    # Structured tech/magic system. `magic_physics` (above) stays as the
    # quick free-text summary used for prompt injection; `tech_magic`
    # holds the actionable rules the narrator can reference.
    tech_magic: TechMagic | None = None

    # --- Dramaturgy & game mechanics ---
    # `blueprint` is the legacy single-arc field. Existing worlds
    # (incl. all seed worlds today) live entirely on this one. The
    # newer `blueprints` list is what the substory-planner uses going
    # forward: 2-4 variants per world, each with its own length /
    # structure / twist signature. When `blueprints` is empty the
    # engine transparently treats `blueprint` as the sole variant —
    # so single-arc worlds keep working unchanged.
    blueprint: Blueprint
    blueprints: list[BlueprintVariant] = Field(default_factory=list)
    random_tables: list[RandomTable] = Field(default_factory=list)

    # --- Presentation ---
    wait_sound: str = ""
    fx_preset: FXPreset = Field(default_factory=FXPreset)

    def active_blueprint(self, choice: int = 0) -> Blueprint:
        """Resolve the Blueprint the engine should be tracking right
        now. With multi-variant worlds, `choice` indexes into
        `blueprints` (clamped to a valid range so a stale checkpoint
        can't crash the engine). With legacy single-variant worlds,
        the choice is ignored and the bare `blueprint` is returned —
        no migration needed for old worlds + old saves."""
        if not self.blueprints:
            return self.blueprint
        idx = max(0, min(choice, len(self.blueprints) - 1))
        return self.blueprints[idx].blueprint

    def variant_count(self) -> int:
        """1 for single-arc worlds, len(blueprints) for multi-variant."""
        return max(1, len(self.blueprints))
