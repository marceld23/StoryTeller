"""Augment the shipped seed worlds with the schema fields they were
written before — regions, factions, creatures, tech_magic,
place.region / contains / adjacent, person.faction /
faction_role, and 3 blueprint variants instead of the legacy
single blueprint.

Pipeline per seed world:
  1. Generate ~5-7 regions from the world's description + the
     existing places (so the regions feel like a fit, not random
     additions).
  2. Map every existing place to one of those regions via a single
     LLM call. `contains` / `adjacent` stay empty — the admin can
     fill those when curating the seeds.
  3. Generate ~4-6 factions, again with the existing persons as
     context so the goals/allies/enemies feel plausible for the
     setting.
  4. Map every existing person to a faction (+ faction_role) via
     a single LLM call. Persons stay unaffiliated if no plausible
     fit (empty faction field).
  5. Generate ~5-7 creatures, with the regions as habitat anchor.
  6. Generate tech_magic from the existing free-text
     world.magic_physics summary.
  7. Generate 3 blueprint variants (short / medium / long), each
     with its own structure + twist_kind — the legacy single
     blueprint moves into variants[0] so the active arc is still
     the world's original arc by default.

Output: one JSON per (world, locale) under
        packages/core/src/storyteller_core/worlds/seeds/
        <id>.<locale>.json
Each output is a full, schema-validated World ready to ship.

Costs: ~6-7 LLM calls per world × 4 worlds (DE + EN of sternenfahrt
+ immerwald) ≈ 28 calls. With gpt-5.4 + reasoning_effort=medium
that's roughly $0.30-$0.60 total.

Idempotent: re-runs overwrite the output JSON. Safe to dry-run with
--dry to print without writing.

Usage:
    bash scripts/bake_voice_prompts.sh        # not this script, just FYI
    .venv/bin/python scripts/augment_seed_worlds.py [--dry] [--world ID]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the script runnable from any cwd (uses the workspace .venv).
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "core" / "src"))

from storyteller_core.config import load_config  # noqa: E402
from storyteller_core.worlds.generate import (  # noqa: E402
    _generate_blueprints,
    _generate_list,
    _generate_tech_magic,
    _llm_json,
)
from storyteller_core.worlds.schema import World  # noqa: E402
from storyteller_core.worlds.seed import seed_worlds  # noqa: E402

SEEDS_DIR = ROOT / "packages" / "core" / "src" / "storyteller_core" / "worlds" / "seeds"


def _skeleton_from(world: World) -> dict:
    """Mimic the dict the generation pipeline normally derives from the
    skeleton-call output, so we can reuse _generate_list /
    _generate_tech_magic / _generate_blueprints as-is."""
    return {
        "id": world.id,
        "name": world.name,
        "genre": world.genre,
        "description": world.description,
        "mood": world.mood,
        "ambience": world.ambience,
        "magic_physics": world.magic_physics,
        "player_role": world.player_role,
        "starting_situation": world.starting_situation,
        "narration_style": world.narration_style,
    }


def _augment_prompt(world: World, locale: str) -> str:
    """Bundle the world description + existing places + existing
    persons into the synthetic `ORIGINAL PROMPT` slot that
    _world_context() feeds every generation call. Crucial for
    augmentation: the generated regions / factions / creatures /
    blueprints MUST feel like they belong to the existing content,
    not invent a parallel world.

    Headers are locale-aware — German labels in an English prompt
    pulled blueprint variant names back into German on the first
    augmentation pass."""
    if locale == "de":
        h_places = "BESTEHENDE ORTE (vom Erzähler bereits etabliert):"
        h_persons = "BESTEHENDE PERSONEN:"
        h_important = (
            "WICHTIG: alles was du jetzt generierst (Regionen, "
            "Fraktionen, Kreaturen, Tech/Magie, Story-Bögen) MUSS "
            "zu diesen etablierten Orten und Personen passen. "
            "Erfinde keine konkurrierende Realität. Antworte in "
            "deutscher Sprache.")
    else:
        h_places = "EXISTING PLACES (already established by the narrator):"
        h_persons = "EXISTING PERSONS:"
        h_important = (
            "IMPORTANT: everything you now generate (regions, "
            "factions, creatures, tech/magic, story arcs) MUST fit "
            "these established places and persons. Do not invent a "
            "competing reality. Respond in English.")
    parts = [world.description.strip()]
    if world.places:
        parts.append(h_places)
        parts.extend(f"- {p.name}: {p.description}" for p in world.places)
    if world.persons:
        parts.append(h_persons)
        parts.extend(
            f"- {p.name} ({p.role}): {p.description}"
            for p in world.persons)
    parts.append(h_important)
    return "\n".join(parts)


_MAP_PLACES_TO_REGIONS_SYS_DE = (
    "Du ordnest existierende ORTE einer Welt jeweils EINER REGION "
    "zu. Antworte JSON ONLY:\n"
    '{"mappings":[{"place":"<exakter Ortsname>","region":'
    '"<exakter Regionsname>"}]}\n'
    "Regeln:\n"
    "- Jeder Ort kriegt genau eine Region.\n"
    "- Wenn ein Ort offensichtlich zu KEINER der angebotenen "
    "Regionen passt, lass `region` leer (\"\").\n"
    "- Verwende die Namen verbatim, gleiche Schreibung."
)

_MAP_PLACES_TO_REGIONS_SYS_EN = (
    "Map every existing PLACE in a world to exactly ONE REGION. "
    "Answer JSON ONLY:\n"
    '{"mappings":[{"place":"<exact place name>","region":'
    '"<exact region name>"}]}\n'
    "Rules:\n"
    "- Each place gets one region.\n"
    "- If a place clearly fits NONE of the offered regions, "
    "leave `region` empty (\"\").\n"
    "- Use the names verbatim, same spelling."
)


def map_places_to_regions(cfg, world: World, regions: list[dict],
                          locale: str) -> dict[str, str]:
    """Returns place_name -> region_name (or '')."""
    if not world.places or not regions:
        return {p.name: "" for p in world.places}
    sys = (_MAP_PLACES_TO_REGIONS_SYS_DE if locale == "de"
           else _MAP_PLACES_TO_REGIONS_SYS_EN)
    user = (
        f"WORLD: {world.name} ({world.genre})\n\n"
        f"REGIONS:\n"
        + "\n".join(f"- {r.get('name','')}: {r.get('description','')}"
                    for r in regions if r.get("name"))
        + "\n\nPLACES:\n"
        + "\n".join(f"- {p.name}: {p.description}" for p in world.places)
        + "\n\nMappe jeden Place auf eine Region."
    )
    try:
        data = _llm_json(cfg, sys, user)
    except Exception as exc:
        print(f"  WARN: map_places failed: {exc!r}", file=sys.stderr)
        return {p.name: "" for p in world.places}
    out = {p.name: "" for p in world.places}
    valid_regions = {r.get("name", "") for r in regions}
    for m in data.get("mappings") or []:
        place = (m.get("place") or "").strip()
        region = (m.get("region") or "").strip()
        if place in out and (region in valid_regions or region == ""):
            out[place] = region
    return out


_MAP_PERSONS_TO_FACTIONS_SYS_DE = (
    "Du ordnest existierende PERSONEN einer Welt jeweils EINER "
    "FRAKTION zu (oder lässt sie unaffiliated). Antworte JSON "
    "ONLY:\n"
    '{"mappings":[{"person":"<exakter Personenname>","faction":'
    '"<exakter Fraktionsname oder \\"\\">","faction_role":'
    '"<Rolle in der Fraktion>"}]}\n'
    "Regeln:\n"
    "- `faction` leer (\"\") wenn die Person zu keiner Fraktion "
    "passt — z.B. Solo-Charaktere, Außenseiter.\n"
    "- `faction_role` leer wenn `faction` leer ist.\n"
    "- `faction_role`: 1-3 Wörter (Anführerin, Späher, Novizin, …).\n"
    "- Verwende die Namen verbatim."
)

_MAP_PERSONS_TO_FACTIONS_SYS_EN = (
    "Map existing PERSONS to ONE faction each (or leave them "
    "unaffiliated). Answer JSON ONLY:\n"
    '{"mappings":[{"person":"<exact name>","faction":'
    '"<exact faction name or \\"\\">","faction_role":'
    '"<role in faction>"}]}\n'
    "Rules:\n"
    "- `faction` empty (\"\") if the person fits no faction.\n"
    "- `faction_role` empty when faction is empty.\n"
    "- `faction_role`: 1-3 words (leader, scout, novice, …).\n"
    "- Use the names verbatim."
)


def map_persons_to_factions(cfg, world: World, factions: list[dict],
                            locale: str) -> dict[str, tuple[str, str]]:
    """Returns person_name -> (faction_name, faction_role)."""
    if not world.persons or not factions:
        return {p.name: ("", "") for p in world.persons}
    sysmsg = (_MAP_PERSONS_TO_FACTIONS_SYS_DE if locale == "de"
              else _MAP_PERSONS_TO_FACTIONS_SYS_EN)
    user = (
        f"WORLD: {world.name} ({world.genre})\n\n"
        f"FACTIONS:\n"
        + "\n".join(f"- {f.get('name','')} (Ziel: {f.get('goals','')}): "
                    f"{f.get('description','')}"
                    for f in factions if f.get("name"))
        + "\n\nPERSONS:\n"
        + "\n".join(f"- {p.name} ({p.role}): {p.description}"
                    for p in world.persons)
        + "\n\nMappe jede Person."
    )
    try:
        data = _llm_json(cfg, sysmsg, user)
    except Exception as exc:
        print(f"  WARN: map_persons failed: {exc!r}", file=sys.stderr)
        return {p.name: ("", "") for p in world.persons}
    out = {p.name: ("", "") for p in world.persons}
    valid_factions = {f.get("name", "") for f in factions}
    for m in data.get("mappings") or []:
        person = (m.get("person") or "").strip()
        fac = (m.get("faction") or "").strip()
        role = (m.get("faction_role") or "").strip()
        if person in out:
            if fac and fac not in valid_factions:
                fac = ""
            if not fac:
                role = ""
            out[person] = (fac, role)
    return out


def augment_world(cfg, world: World, locale: str) -> dict:
    """Build the full augmented World dict for one (world, locale).
    Returns a payload ready to pass to World.model_validate()."""
    print(f"  → augmenting {world.id}.{locale} ({world.name})")
    skeleton = _skeleton_from(world)
    prompt = _augment_prompt(world, locale)

    # The step indices in _generate_list go into the progress msg —
    # they don't influence behaviour, only logging.
    regions = _generate_list(cfg, "regions", skeleton, prompt, 1, 6, None)
    print(f"     regions: {len(regions)}")

    place_region = map_places_to_regions(cfg, world, regions, locale)
    print(f"     place→region mappings: "
          f"{sum(1 for v in place_region.values() if v)}/{len(place_region)}")

    factions = _generate_list(cfg, "factions", skeleton, prompt, 2, 6, None,
                              regions=regions)
    print(f"     factions: {len(factions)}")

    person_faction = map_persons_to_factions(cfg, world, factions, locale)
    print(f"     person→faction mappings: "
          f"{sum(1 for f, _ in person_faction.values() if f)}/{len(person_faction)}")

    creatures = _generate_list(cfg, "creatures", skeleton, prompt, 3, 6, None,
                                regions=regions)
    print(f"     creatures: {len(creatures)}")

    tech_magic = _generate_tech_magic(cfg, skeleton, prompt, 4, 6, None)
    print(f"     tech_magic: {tech_magic.get('kind') if tech_magic else '(none)'}")

    blueprints = _generate_blueprints(cfg, skeleton, prompt, None)
    print(f"     blueprints: {len(blueprints)} variants "
          f"({', '.join(b.get('name','') for b in blueprints)})")

    # Compose the new World payload. Start from the existing world (so
    # all hand-curated places / persons / fragments / random_tables
    # stay intact), then ADD the new fields and ENRICH places/persons
    # in-place with their mapping.
    payload = world.model_dump()
    payload["regions"] = regions
    payload["factions"] = factions
    payload["creatures"] = creatures
    if tech_magic is not None:
        payload["tech_magic"] = tech_magic
    payload["blueprints"] = blueprints
    # NOTE: keep legacy `blueprint` mirrored to variants[0]'s
    # blueprint so any straggler code that still reads it stays
    # consistent — the engine prefers `blueprints` when non-empty.
    payload["blueprint"] = blueprints[0]["blueprint"]

    # Enrich existing places (region from mapping, empty
    # contains/adjacent — admin curates later).
    for p_dict, p in zip(payload["places"], world.places, strict=False):
        p_dict["region"] = place_region.get(p.name, "")
        p_dict.setdefault("contains", [])
        p_dict.setdefault("adjacent", [])

    # Enrich existing persons.
    for p_dict, p in zip(payload["persons"], world.persons, strict=False):
        fac, role = person_faction.get(p.name, ("", ""))
        p_dict["faction"] = fac
        p_dict["faction_role"] = role

    # Validate before returning — catch schema regressions early.
    World.model_validate(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true",
                        help="Don't write JSON, just print a summary.")
    parser.add_argument("--world", default="",
                        help="Augment only this world id (default: all).")
    parser.add_argument("--locale", default="",
                        help="Only this locale (de|en, default: both).")
    args = parser.parse_args()

    cfg = load_config()
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    locales = ("de", "en") if not args.locale else (args.locale,)
    total = 0
    for locale in locales:
        worlds = seed_worlds(locale)
        if args.world:
            worlds = [w for w in worlds if w.id == args.world]
        print(f"=== locale: {locale} ({len(worlds)} world{'s' if len(worlds) != 1 else ''}) ===")
        for w in worlds:
            payload = augment_world(cfg, w, locale)
            if args.dry:
                print(f"     [dry] would write "
                      f"{SEEDS_DIR}/{w.id}.{locale}.json")
                continue
            out_path = SEEDS_DIR / f"{w.id}.{locale}.json"
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2))
            print(f"     wrote {out_path.relative_to(ROOT)} "
                  f"({out_path.stat().st_size // 1024} KB)")
            total += 1
    print(f"\nDone. {total} JSON file(s) written under "
          f"{SEEDS_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
