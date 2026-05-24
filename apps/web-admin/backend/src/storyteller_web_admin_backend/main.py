"""storyteller-web-admin backend — FastAPI JSON API.

A clean JSON surface that the SvelteKit admin frontend consumes.

Endpoints (Phase 4b scope):
  GET    /api/health
  GET    /api/worlds                              list world summaries
  GET    /api/worlds/{world_id}                   full world detail
  PUT    /api/worlds/{world_id}                   replace world (full)
  POST   /api/worlds                              create new blank world
  DELETE /api/worlds/{world_id}                   delete world file

  GET    /api/saves                               list saved games (threads)
  DELETE /api/saves/{thread_id}                    reset one saved game

  GET    /api/wait_sounds                         list .wav files available as world wait_sound

  GET    /api/settings/models                     model overrides
  PUT    /api/settings/models                     update model overrides
  GET    /api/settings/audio                      audio backend override
  PUT    /api/settings/audio                      update audio backend override
  GET    /api/settings/moderation                 moderation thresholds
  PUT    /api/settings/moderation                 update moderation thresholds

  POST   /api/worlds/generate                     async LLM world generation (job)
  POST   /api/worlds/{world_id}/reindex           async RAG reindex (job)
  POST   /api/worlds/{world_id}/suggest           one schema-shaped content piece
  GET    /api/jobs/{job_id}                       job status
  GET    /api/transcripts                          list transcripts
  GET    /api/transcripts/{name}                   parsed transcript events

Run: storyteller-web-admin  (binds 0.0.0.0:8080)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from storyteller_core.config import ROOT, load_config
from storyteller_core.worlds.registry import all_world_ids, load_world, save_world
from storyteller_core.worlds.schema import World

from .jobs import JobRegistry

log = logging.getLogger("storyteller.web_admin")

app = FastAPI(title="StoryTeller Admin")
app.add_middleware(
    CORSMiddleware,
    allow_origins=load_config().web.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _auth(request, call_next):
    """Admin password gate. Active only when an admin token is set
    (STORYTELLER_ADMIN_TOKEN, or STORYTELLER_WEB_TOKEN as fallback). Read
    live, so changing .env applies without restart. Protects /api/* (except
    /api/health); the static SPA loads freely and sends the token."""
    from fastapi.responses import JSONResponse

    token = load_config().web.admin_token
    p = request.url.path
    if token and p.startswith("/api/") and p != "/api/health":
        if request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


JOBS = JobRegistry()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _cfg():
    return load_config()


def _models_path() -> Path:
    return ROOT / "data" / "models.json"


def _audio_path() -> Path:
    return ROOT / "data" / "audio.json"


def _moderation_path() -> Path:
    return ROOT / "data" / "moderation.json"


def _read_json(p: Path, default: Any) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("unreadable JSON %s, using default: %r", p, exc)
        return default


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                 encoding="utf-8")


# --------------------------------------------------------------------------
# REST: meta
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    cfg = _cfg()
    return {
        "ok": True,
        "limits": {
            "max_prompt_chars": cfg.web.max_prompt_chars,
            "max_turn_chars": cfg.web.max_turn_chars,
        },
    }


# --------------------------------------------------------------------------
# REST: worlds
# --------------------------------------------------------------------------

class WorldSummary(BaseModel):
    id: str
    name: str
    genre: str
    player_role: str


@app.get("/api/worlds", response_model=list[WorldSummary])
def list_worlds() -> list[WorldSummary]:
    cfg = _cfg()
    return [
        WorldSummary(id=wid, name=w.name, genre=w.genre,
                     player_role=w.player_role)
        for wid in sorted(all_world_ids(cfg))
        for w in [load_world(cfg, wid)]
    ]


@app.get("/api/worlds/{world_id}")
def get_world(world_id: str) -> dict:
    cfg = _cfg()
    if world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    return load_world(cfg, world_id).model_dump()


@app.put("/api/worlds/{world_id}")
def replace_world(world_id: str, payload: dict) -> dict:
    cfg = _cfg()
    if payload.get("id") != world_id:
        raise HTTPException(400, "world_id mismatch")
    try:
        w = World(**payload)
    except Exception as exc:
        raise HTTPException(422, f"invalid world: {exc}") from exc
    save_world(cfg, w)
    return {"ok": True, "id": w.id}


class CreateWorld(BaseModel):
    id: str
    name: str
    genre: str = ""
    player_role: str = ""
    description: str = ""


@app.post("/api/worlds")
def create_world(payload: CreateWorld) -> dict:
    cfg = _cfg()
    if payload.id in all_world_ids(cfg):
        raise HTTPException(409, "world already exists")
    w = World(
        id=payload.id, name=payload.name, genre=payload.genre,
        player_role=payload.player_role, description=payload.description,
    )
    save_world(cfg, w)
    return {"ok": True, "id": w.id}


@app.delete("/api/worlds/{world_id}")
def delete_world(world_id: str) -> dict:
    cfg = _cfg()
    if world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    # Delete both locale variants if present.
    deleted: list[str] = []
    for fn in (f"{world_id}.json", f"{world_id}.de.json", f"{world_id}.en.json"):
        p = ROOT / "data" / "worlds" / fn
        if p.exists():
            p.unlink()
            deleted.append(fn)
    return {"ok": True, "deleted": deleted}


# --------------------------------------------------------------------------
# REST: saved games (checkpoint threads)
# --------------------------------------------------------------------------

@app.get("/api/saves")
def list_saves() -> list[dict]:
    """Saved sessions (checkpoint threads) with world name + progress, so the
    admin can see and reset them. thread_id encodes the source: pi-<world>,
    cli-<world>, web-<id>."""
    from storyteller_core.story.graph import list_threads

    cfg = _cfg()
    names: dict[str, str] = {}
    for wid in all_world_ids(cfg):
        try:
            names[wid] = load_world(cfg, wid).name
        except Exception:
            names[wid] = wid
    out: list[dict] = []
    for t in list_threads():
        tid = t["thread_id"]
        world_id, source = None, "other"
        if tid.startswith("pi-"):
            world_id, source = tid[3:], "pi"
        elif tid.startswith("cli-"):
            world_id, source = tid[4:], "cli"
        elif tid.startswith("web-"):
            source = "web"
        out.append({**t, "world_id": world_id, "source": source,
                    "world_name": names.get(world_id or "", world_id or tid)})
    return out


@app.get("/api/wait_sounds")
def list_wait_sounds() -> list[str]:
    """Sorted list of filenames available as `World.wait_sound` — anything
    audio-shaped (.wav/.flac/.ogg/.mp3) in `paths.wait_sounds_dir`. Drop a
    file there and it shows up in the world editor's dropdown."""
    cfg = _cfg()
    p = cfg.path(cfg.paths.wait_sounds_dir)
    if not p.is_dir():
        return []
    exts = {".wav", ".flac", ".ogg", ".mp3"}
    return sorted(
        f.name for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in exts and not f.name.startswith("."))


@app.delete("/api/saves/{thread_id}")
def reset_save(thread_id: str) -> dict:
    """Delete one thread's checkpoints — resets that saved game so it starts
    fresh next time."""
    from storyteller_core.story.graph import delete_thread

    res = delete_thread(thread_id)
    if res["checkpoints_deleted"] == 0 and res["writes_deleted"] == 0:
        raise HTTPException(404, "no such saved game")
    return {"ok": True, **res}


# --------------------------------------------------------------------------
# REST: settings
# --------------------------------------------------------------------------

@app.get("/api/settings/models")
def get_models() -> dict:
    """Effective model names (defaults + admin overrides from data/models.json)."""
    cfg = _cfg()
    overrides = _read_json(_models_path(), {})
    return {
        "defaults": cfg.models.model_dump(),
        "overrides": overrides,
    }


@app.put("/api/settings/models")
def put_models(payload: dict) -> dict:
    _write_json(_models_path(), payload)
    return {"ok": True}


@app.get("/api/settings/audio")
def get_audio() -> dict:
    cfg = _cfg()
    overrides = _read_json(_audio_path(), {})
    return {
        "default_backend": cfg.audio.backend,
        "overrides": overrides,
        "allowed_backends": ["auto", "alsa_softvol", "portable", "pipewire"],
    }


class AudioPut(BaseModel):
    backend: str
    pw_sink: str | None = None


@app.put("/api/settings/audio")
def put_audio(payload: AudioPut) -> dict:
    if payload.backend not in {"auto", "alsa_softvol", "portable", "pipewire"}:
        raise HTTPException(422, f"unknown backend: {payload.backend}")
    data: dict = {"backend": payload.backend}
    if payload.pw_sink:
        data["pw_sink"] = payload.pw_sink
    _write_json(_audio_path(), data)
    return {"ok": True}


@app.get("/api/settings/moderation")
def get_moderation() -> dict:
    cfg = _cfg()
    overrides = _read_json(_moderation_path(), {})
    return {
        "enabled_default": cfg.moderation.enabled,
        "default_threshold": cfg.moderation.default_threshold,
        "overrides": overrides,
    }


@app.put("/api/settings/moderation")
def put_moderation(payload: dict) -> dict:
    _write_json(_moderation_path(), payload)
    return {"ok": True}


# --------------------------------------------------------------------------
# Cost (daily cap, ledger, resets)
# --------------------------------------------------------------------------

def _cost_overlay_path() -> Path:
    """Admin-editable subset of [cost] (caps, prices). Loaded by
    `load_config` as part of the data overlay — same pattern as
    moderation.json and models.json."""
    return ROOT / "data" / "cost.json"


@app.get("/api/cost/summary")
def cost_summary(days: int = 7) -> dict:
    from storyteller_core.story.ledger import CostLedger
    cfg = _cfg()
    return CostLedger(cfg).summary(days=int(days))


@app.get("/api/cost/sessions")
def cost_sessions(date: str | None = None) -> dict:
    from storyteller_core.story.ledger import CostLedger
    cfg = _cfg()
    return {"date": date, "sessions": CostLedger(cfg).sessions_for(date)}


@app.post("/api/cost/reset/daily")
def cost_reset_daily(payload: dict | None = None) -> dict:
    from storyteller_core.story.ledger import CostLedger
    cfg = _cfg()
    date = (payload or {}).get("date") if isinstance(payload, dict) else None
    d = CostLedger(cfg).reset_daily(date)
    return {"ok": True, "date": d}


@app.post("/api/cost/reset/session/{thread_id}")
def cost_reset_session(thread_id: str) -> dict:
    from storyteller_core.story.ledger import CostLedger
    cfg = _cfg()
    CostLedger(cfg).reset_session(thread_id)
    return {"ok": True, "thread_id": thread_id}


@app.get("/api/cost/config")
def get_cost_config() -> dict:
    cfg = _cfg()
    return {
        "enforce": cfg.cost.enforce,
        "daily_cap_usd": cfg.cost.daily_cap_usd,
        "warn_threshold_pct": cfg.cost.warn_threshold_pct,
        "usd_per_1m_input": cfg.cost.usd_per_1m_input,
        "usd_per_1m_output": cfg.cost.usd_per_1m_output,
        "usd_per_1m_embedding": cfg.cost.usd_per_1m_embedding,
        "usd_per_1m_tts_chars": cfg.cost.usd_per_1m_tts_chars,
        "usd_per_minute_stt": cfg.cost.usd_per_minute_stt,
        "overrides": _read_json(_cost_overlay_path(), {}),
    }


@app.put("/api/cost/config")
def put_cost_config(payload: dict) -> dict:
    """Persist an overlay of [cost] values to `data/cost.json`. Only the
    keys present in `payload` are written; the rest stay at their
    config.toml defaults."""
    allowed = {
        "enforce", "daily_cap_usd", "warn_threshold_pct",
        "usd_per_1m_input", "usd_per_1m_output", "usd_per_1m_embedding",
        "usd_per_1m_tts_chars", "usd_per_minute_stt",
    }
    clean = {k: v for k, v in (payload or {}).items() if k in allowed}
    _write_json(_cost_overlay_path(), clean)
    return {"ok": True, "stored": clean}


# --------------------------------------------------------------------------
# User notes (player-introduced world facts) + KnownFacts promotion
# --------------------------------------------------------------------------

class PromotePayload(BaseModel):
    """Editable fields used when an admin promotes a user note to the
    canonical world."""
    kind: str | None = None
    name: str | None = None
    description: str | None = None
    tags: list[str] = []


def _promote_to_world(cfg, world_id: str, kind: str, name: str,
                       description: str, tags: list[str]) -> dict:
    """Insert a new entry into `world.<bucket>` matching `kind` and
    persist the world. Returns the new entry as dict."""
    from storyteller_core.worlds.registry import load_world as _load
    from storyteller_core.worlds.registry import save_world as _save
    from storyteller_core.worlds.schema import (
        Fragment,
        Item,
        Person,
        Place,
    )

    world = _load(cfg, world_id)
    if kind == "person":
        entry = Person(name=name, role="", description=description,
                       relations="", tags=tags)
        world.persons = [*world.persons, entry]
    elif kind == "place":
        entry = Place(name=name, description=description, tags=tags)
        world.places = [*world.places, entry]
    elif kind == "item":
        entry = Item(name=name, description=description,
                     properties="", tags=tags)
        world.items = [*world.items, entry]
    else:  # fact -> store as fragment, the most flexible authored slot
        kind = "fact"
        entry = Fragment(title=name, text=description, tags=tags)
        world.fragments = [*world.fragments, entry]
    _save(cfg, world)
    return entry.model_dump()


@app.get("/api/worlds/{world_id}/user_notes")
def list_user_notes(world_id: str, promoted: bool | None = None) -> dict:
    from storyteller_core.story.user_notes import UserNoteStore

    cfg = _cfg()
    store = UserNoteStore(cfg, world_id)
    return {"world_id": world_id,
            "notes": [n.model_dump() for n in store.list(promoted=promoted)]}


@app.post("/api/worlds/{world_id}/user_notes/{note_id}/promote")
def promote_user_note(world_id: str, note_id: str,
                       payload: PromotePayload) -> dict:
    from storyteller_core.story.rag import RAG
    from storyteller_core.story.user_notes import UserNoteStore

    cfg = _cfg()
    store = UserNoteStore(cfg, world_id)
    note = store.get(note_id)
    if note is None:
        raise HTTPException(404, "unknown note")
    kind = (payload.kind or note.kind or "fact").lower()
    name = (payload.name or note.name).strip()
    description = (payload.description or note.description).strip()
    tags = payload.tags or note.tags
    if not name:
        raise HTTPException(422, "name is required")
    # 1) write the entry into world.json
    entry = _promote_to_world(cfg, world_id, kind, name, description, tags)
    # 2) replace the user-note RAG row with a canonical one (same content
    #    pattern as index_world). Falls back gracefully if RAG isn't open.
    try:
        rag = RAG(cfg)
        rag.remove_facts_by_content(world_id, note.locale,
                                     note.rag_fact_type(),
                                     note.as_rag_text())
        if kind == "person":
            text = f"PERSON {name} (): {description} "
        elif kind == "place":
            text = f"ORT {name}: {description}"
        elif kind == "item":
            text = f"GEGENSTAND {name}: {description} "
        else:
            text = f"{name}: {description}"
        rag.index_single_fact(world_id, note.locale, kind, text)
    except Exception as exc:
        log.warning("user-note promote RAG update failed: %r", exc)
    # 3) flip the note's promoted flag (kept for audit trail)
    store.mark_promoted(note_id)
    return {"ok": True, "note_id": note_id, "kind": kind,
            "world_entry": entry}


@app.delete("/api/worlds/{world_id}/user_notes/{note_id}")
def delete_user_note(world_id: str, note_id: str) -> dict:
    from storyteller_core.story.rag import RAG
    from storyteller_core.story.user_notes import UserNoteStore

    cfg = _cfg()
    store = UserNoteStore(cfg, world_id)
    note = store.get(note_id)
    if note is None:
        raise HTTPException(404, "unknown note")
    # Pull the RAG row first so retrieval stops finding it immediately.
    try:
        RAG(cfg).remove_facts_by_content(
            world_id, note.locale, note.rag_fact_type(),
            note.as_rag_text())
    except Exception as exc:
        log.warning("user-note delete RAG remove failed: %r", exc)
    store.delete(note_id)
    return {"ok": True, "note_id": note_id}


@app.get("/api/saves/{thread_id}/promotable")
def saves_promotable(thread_id: str) -> dict:
    """Return per-thread `KnownFacts` (player-fact tool calls) so the
    admin can promote them to the world."""
    from storyteller_core.story.graph import get_compiled

    snap = get_compiled().get_state({"configurable": {"thread_id": thread_id}})
    values = dict(snap.values) if snap and snap.values else {}
    known = values.get("known_facts") or []
    char_state = values.get("char_state") or {}
    return {
        "thread_id": thread_id,
        "known_facts": known,
        "char_state": char_state,
    }


class PromoteKnownPayload(BaseModel):
    world_id: str
    kind: str             # person | place | item | fact
    name: str
    description: str = ""
    tags: list[str] = []


@app.post("/api/saves/{thread_id}/promote_known_fact")
def saves_promote_known_fact(thread_id: str,
                              payload: PromoteKnownPayload) -> dict:
    """Promote a (kind, name, description) tuple from a thread's known
    facts directly into the canonical world. RAG also picks up the new
    row so the next turn can retrieve it."""
    from storyteller_core.story.rag import RAG

    cfg = _cfg()
    kind = (payload.kind or "fact").lower()
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(422, "name is required")
    entry = _promote_to_world(cfg, payload.world_id, kind, name,
                              payload.description, payload.tags)
    try:
        from storyteller_core.i18n import norm
        locale = norm(cfg.general.locale)
        if kind == "person":
            text = f"PERSON {name} (): {payload.description} "
        elif kind == "place":
            text = f"ORT {name}: {payload.description}"
        elif kind == "item":
            text = f"GEGENSTAND {name}: {payload.description} "
        else:
            text = f"{name}: {payload.description}"
        RAG(cfg).index_single_fact(payload.world_id, locale, kind, text)
    except Exception as exc:
        log.warning("known-fact promote RAG update failed: %r", exc)
    return {"ok": True, "thread_id": thread_id, "world_entry": entry}


# --------------------------------------------------------------------------
# Jobs + async-only endpoints (stubs)
# --------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        raise HTTPException(404, "unknown job")
    return {
        "id": j.id, "kind": j.kind, "title": j.title, "status": j.status,
        "started": j.started, "finished": j.finished, "elapsed": j.elapsed,
        "result_url": j.result_url, "error": j.error, "detail": j.detail,
    }


class GeneratePayload(BaseModel):
    prompt: str


@app.post("/api/worlds/generate")
def generate_world(payload: GeneratePayload) -> dict:
    """Async LLM world generation. Returns a job id to poll via /api/jobs/{id}.

    On success the job's `result_url` is the new world id (so the frontend
    can navigate to /worlds/<id>).
    """
    from storyteller_core.i18n import norm
    from storyteller_core.worlds.generate import generate_world as _gen
    from storyteller_core.worlds.registry import save_world as _save

    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise HTTPException(422, "prompt is empty")
    max_prompt = load_config().web.max_prompt_chars
    if len(prompt) > max_prompt:
        raise HTTPException(413, f"prompt too long (max {max_prompt} chars)")

    cfg = _cfg()
    loc = norm(cfg.general.locale)

    def _work(job) -> str:
        w = _gen(cfg, prompt, progress=job.progress)
        job.progress("Welt wird gespeichert…")
        _save(cfg, w)
        try:
            from storyteller_core.story.rag import WorldRAG
            job.progress("RAG wird indexiert…")
            n = WorldRAG(cfg).index_world(w, force=True, locale=loc)
            job.progress(f"RAG fertig ({n} Fakten).")
        except Exception as exc:  # non-fatal: world is on disk
            job.progress(f"RAG-Index fehlgeschlagen (Welt gespeichert): {exc!r}")
        return w.id

    j = JOBS.submit("world-gen", f"Welt aus Prompt: {prompt[:40]}", _work)
    return {"job_id": j.id}


@app.post("/api/worlds/{world_id}/reindex")
def reindex_world(world_id: str) -> dict:
    from storyteller_core.i18n import norm

    cfg = _cfg()
    if world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    loc = norm(cfg.general.locale)

    def _work(job) -> str:
        from storyteller_core.story.rag import WorldRAG
        job.progress(f"RAG wird neu indexiert für {world_id}…")
        n = WorldRAG(cfg).index_world(load_world(cfg, world_id), force=True,
                                      locale=loc)
        job.progress(f"{n} Fakten neu indexiert.")
        return world_id

    j = JOBS.submit("world-reindex", f"Reindex {world_id}", _work)
    return {"job_id": j.id}


# keys the model must return for each content kind (mirrors schema.py)
_SUGGEST_SHAPES: dict[str, list[str]] = {
    "region": ["name", "description", "tags"],
    "place": ["name", "description", "region", "contains", "adjacent",
              "tags"],
    "faction": ["name", "description", "goals", "allies", "enemies",
                "relations", "tags"],
    "person": ["name", "role", "description", "relations", "faction",
               "faction_role", "tags"],
    "item": ["name", "description", "properties", "tags"],
    "creature": ["name", "description", "habitat", "threat_level", "tags"],
    "glossary": ["term", "definition"],
    "history": ["when", "title", "description"],
    "fragment": ["title", "text", "tags"],
}

# List-typed fields per kind — the suggest endpoint coerces these to
# list[str] so the editor always gets a real array, even if the LLM
# returned a single string or null.
_SUGGEST_LIST_FIELDS: dict[str, set[str]] = {
    "place": {"tags", "contains", "adjacent"},
    "faction": {"tags", "allies", "enemies"},
    "person": {"tags"},
    "item": {"tags"},
    "creature": {"tags"},
    "region": {"tags"},
    "fragment": {"tags"},
}


class SuggestPayload(BaseModel):
    kind: str
    prompt: str = ""


@app.post("/api/worlds/{world_id}/suggest")
def suggest_piece(world_id: str, payload: SuggestPayload) -> dict:
    """Synchronously ask the gen model for ONE content piece of `kind`,
    consistent with the world. Returns the parsed piece (schema-shaped).

    Runs in FastAPI's threadpool (sync def), so a slow gen model blocks one
    worker, not the event loop — fine for a single-user admin tool.
    """
    from storyteller_core.oai import chat_extras, get_chat_client

    cfg = _cfg()
    if world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    kind = payload.kind
    if kind not in _SUGGEST_SHAPES:
        raise HTTPException(422, f"unknown kind: {kind}")

    w = load_world(cfg, world_id)
    keys = _SUGGEST_SHAPES[kind]
    sysmsg = (
        f"Du baust die Welt '{w.name}' ({w.genre}) aus. {w.description} "
        f"Stimmung: {w.mood}. Erzeuge GENAU EINEN {kind}-Eintrag, konsistent "
        f"zur Welt. Antworte als JSON mit genau diesen Schlüsseln: "
        f"{', '.join(keys)}. 'tags' ist ein Array von Strings (sonst weglassen). "
        f"Nutze die Sprache der Welt."
    )
    try:
        r = get_chat_client(cfg, "gen").chat.completions.create(
            model=cfg.models.gen,
            messages=[{"role": "system", "content": sysmsg},
                      {"role": "user", "content": payload.prompt or
                       f"Schlage einen passenden {kind}-Eintrag vor."}],
            response_format={"type": "json_object"},
            **chat_extras(cfg, "gen", temperature=cfg.models.gen_temperature),
        )
        data = json.loads(r.choices[0].message.content or "{}")
    except Exception as exc:
        raise HTTPException(502, f"gen model error: {exc!r}") from exc

    # keep only known keys; coerce list fields to list[str], scalar fields
    # to str. list_fields covers the per-kind list extensions
    # (contains/adjacent/allies/enemies) plus the universal `tags`.
    list_fields = _SUGGEST_LIST_FIELDS.get(kind, set()) | {"tags"}
    piece: dict = {}
    for k in keys:
        if k not in data:
            continue
        v = data[k]
        if k in list_fields:
            if isinstance(v, str):
                v = [t.strip() for t in v.split(",") if t.strip()]
            elif not isinstance(v, list):
                v = []
            piece[k] = [str(t) for t in v]
        elif isinstance(v, str):
            piece[k] = v
        else:
            # model returned a dict/list for a string field — flatten to text
            piece[k] = json.dumps(v, ensure_ascii=False) if not isinstance(v, (int, float)) else str(v)
    return {"kind": kind, "piece": piece}


@app.get("/api/transcripts")
def list_transcripts() -> list[dict]:
    import time as _t

    d = ROOT / "data" / "transcripts"
    if not d.exists():
        return []
    files = sorted(d.glob("*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict] = []
    for p in files:
        try:
            n = sum(1 for _ in p.open(encoding="utf-8"))
        except Exception:
            n = 0
        out.append({
            "name": p.name,
            "stem": p.stem,
            "events": n,
            "mtime": p.stat().st_mtime,
            "modified": _t.strftime("%Y-%m-%d %H:%M",
                                    _t.localtime(p.stat().st_mtime)),
        })
    return out


@app.get("/api/transcripts/{name}")
def get_transcript(name: str) -> dict:
    safe = name.replace("/", "").replace("..", "")
    p = ROOT / "data" / "transcripts" / safe
    if not p.exists():
        raise HTTPException(404, "transcript not found")
    events: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return {"name": p.name, "stem": p.stem, "events": events}


# --------------------------------------------------------------------------
# static SPA frontend (built by `yarn build` in apps/web-admin/frontend)
# Registered LAST so /api/* routes win; serves real files, else index.html.
# --------------------------------------------------------------------------
_FRONTEND = ROOT / "apps" / "web-admin" / "frontend" / "build"
if _FRONTEND.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str):
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404)
        target = _FRONTEND / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_FRONTEND / "index.html")
else:
    log.warning("frontend build missing at %s — run `yarn build` in "
                "apps/web-admin/frontend", _FRONTEND)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("storyteller_web_admin_backend.main:app",
                host="0.0.0.0", port=8080, log_level="info", reload=False)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
