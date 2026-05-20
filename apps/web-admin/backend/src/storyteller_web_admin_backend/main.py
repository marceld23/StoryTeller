"""storyteller-web-admin backend — FastAPI JSON API.

Replaces the legacy inline-HTML admin (`legacy_app.py`) with a clean JSON
surface that the SvelteKit admin frontend consumes.

Endpoints (Phase 4b scope):
  GET    /api/health
  GET    /api/worlds                              list world summaries
  GET    /api/worlds/{world_id}                   full world detail
  PUT    /api/worlds/{world_id}                   replace world (full)
  POST   /api/worlds                              create new blank world
  DELETE /api/worlds/{world_id}                   delete world file

  GET    /api/settings/models                     model overrides
  PUT    /api/settings/models                     update model overrides
  GET    /api/settings/audio                      audio backend override
  PUT    /api/settings/audio                      update audio backend override
  GET    /api/settings/moderation                 moderation thresholds
  PUT    /api/settings/moderation                 update moderation thresholds

  POST   /api/worlds/generate                     async LLM world generation (stub: 501)
  POST   /api/worlds/{world_id}/reindex           async RAG reindex (stub: 501)
  GET    /api/jobs/{job_id}                       job status
  GET    /api/transcripts                         list transcripts (stub: 501)

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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    except Exception:
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
    return {"ok": True}


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
        raise HTTPException(422, f"invalid world: {exc}")
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


@app.post("/api/worlds/generate")
def generate_world_stub(_payload: dict) -> dict:
    """Async LLM world generation. NOT IMPLEMENTED YET."""
    raise HTTPException(
        501,
        "world generation endpoint is being ported from legacy_app.py in a "
        "follow-up. See legacy_app.py for the previous implementation.",
    )


@app.post("/api/worlds/{world_id}/reindex")
def reindex_world_stub(world_id: str) -> dict:
    raise HTTPException(
        501,
        f"RAG reindex for '{world_id}' is being ported from legacy_app.py.",
    )


@app.get("/api/transcripts")
def list_transcripts_stub() -> dict:
    raise HTTPException(
        501,
        "transcripts endpoint is being ported from legacy_app.py.",
    )


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
