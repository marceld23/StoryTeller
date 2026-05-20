"""storyteller-web-ui backend — FastAPI + WebSocket play loop.

Endpoints:
  GET  /api/health                         liveness
  GET  /api/worlds                         list available worlds
  GET  /api/worlds/{world_id}              world detail
  POST /api/sessions                       create session {world_id} -> {thread_id, opening}
  GET  /api/sessions/{thread_id}/state     current state snapshot
  POST /api/sessions/{thread_id}/undo      undo last turn
  WS   /ws/play/{thread_id}?world_id=...   text-stream play loop
  WS   /ws/voice/{thread_id}?world_id=...  audio play loop (STT/TTS server-side)

Sessions are identified by `thread_id` (LangGraph checkpointer key). The
client passes `world_id` on every connection because the engine needs the
World object at construction time and we don't persist that mapping yet.

Run: storyteller-web-ui  (binds 0.0.0.0:8090)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from storyteller_core.config import load_config
from storyteller_core.story.engine import StoryEngine
from storyteller_core.worlds.registry import all_world_ids, load_world

log = logging.getLogger("storyteller.web_ui")


# --------------------------------------------------------------------------
# app + shared handles
# --------------------------------------------------------------------------

app = FastAPI(title="StoryTeller Play")

# Permissive CORS for local SvelteKit dev (yarn dev runs on :5173 by default).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cfg():
    return load_config()


def _make_engine(world_id: str, thread_id: str) -> StoryEngine:
    cfg = _cfg()
    world = load_world(cfg, world_id)
    rag = None
    try:
        from storyteller_core.story.rag import WorldRAG
        rag = WorldRAG(cfg)
    except Exception:
        rag = None
    return StoryEngine(cfg, world, rag=rag, thread_id=thread_id)


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------

class WorldSummary(BaseModel):
    id: str
    name: str
    genre: str
    player_role: str
    description: str


class CreateSession(BaseModel):
    world_id: str
    thread_id: str | None = None  # client may suggest, otherwise we generate


class CreatedSession(BaseModel):
    thread_id: str
    world_id: str
    opening: str


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/worlds", response_model=list[WorldSummary])
def list_worlds() -> list[WorldSummary]:
    cfg = _cfg()
    return [
        WorldSummary(
            id=wid, name=w.name, genre=w.genre,
            player_role=w.player_role, description=w.description,
        )
        for wid in sorted(all_world_ids(cfg))
        for w in [load_world(cfg, wid)]
    ]


@app.get("/api/worlds/{world_id}")
def world_detail(world_id: str) -> dict:
    cfg = _cfg()
    if world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    w = load_world(cfg, world_id)
    return w.model_dump()


@app.post("/api/sessions", response_model=CreatedSession)
def create_session(payload: CreateSession) -> CreatedSession:
    cfg = _cfg()
    if payload.world_id not in all_world_ids(cfg):
        raise HTTPException(404, "unknown world")
    thread_id = payload.thread_id or f"web-{uuid.uuid4().hex[:12]}"
    engine = _make_engine(payload.world_id, thread_id)
    # Trigger opening if thread is fresh
    state = engine.state()
    if state.get("memory"):
        opening = engine.last_narration()
    else:
        opening = engine.opening()
    return CreatedSession(thread_id=thread_id, world_id=payload.world_id,
                          opening=opening)


@app.get("/api/sessions/{thread_id}/state")
def session_state(thread_id: str, world_id: str = Query(...)) -> dict:
    engine = _make_engine(world_id, thread_id)
    s = engine.state()
    sub = s.get("substory") or {}
    return {
        "thread_id": thread_id,
        "world_id": world_id,
        "memory_len": len(s.get("memory") or []),
        "substory": {
            "title": sub.get("title"),
            "premise": sub.get("premise"),
            "cursor": sub.get("cursor"),
            "status": sub.get("status"),
        } if sub else None,
        "macro_index": s.get("macro_index"),
        "beat_turns": s.get("beat_turns"),
        "cost": s.get("cost"),
        "synopsis_chars": len(s.get("synopsis") or ""),
        "last_narration": engine.last_narration(),
    }


@app.post("/api/sessions/{thread_id}/undo")
def undo_turn(thread_id: str, world_id: str = Query(...)) -> dict:
    engine = _make_engine(world_id, thread_id)
    text = engine.undo_last()
    return {"narration": text}


# --------------------------------------------------------------------------
# WebSocket: text play
# --------------------------------------------------------------------------

@app.websocket("/ws/play/{thread_id}")
async def ws_play(websocket: WebSocket, thread_id: str,
                  world_id: str = Query(...)):
    """Text play loop.

    Wire protocol (JSON messages):
      client -> server  {"type": "turn", "text": str}
      client -> server  {"type": "undo"}
      server -> client  {"type": "thinking"}
      server -> client  {"type": "narration", "text": str}
      server -> client  {"type": "state", "data": {...}}
      server -> client  {"type": "error", "message": str}
    """
    await websocket.accept()
    try:
        engine = _make_engine(world_id, thread_id)
        # Send the current narration so the client picks up where it left off.
        snap = engine.state()
        opening_text = engine.last_narration() if snap.get("memory") else None
        if opening_text is None:
            await websocket.send_json({"type": "thinking"})
            opening_text = await asyncio.to_thread(engine.opening)
        await websocket.send_json({"type": "narration", "text": opening_text})

        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "turn":
                user_text = (msg.get("text") or "").strip()
                if not user_text:
                    continue
                await websocket.send_json({"type": "thinking"})
                try:
                    reply = await asyncio.to_thread(engine.turn, user_text)
                except Exception as exc:
                    log.exception("engine.turn failed")
                    await websocket.send_json({
                        "type": "error", "message": f"{exc!r}"})
                    continue
                await websocket.send_json({"type": "narration", "text": reply})
            elif mtype == "undo":
                text = await asyncio.to_thread(engine.undo_last)
                await websocket.send_json({"type": "narration", "text": text})
            else:
                await websocket.send_json({
                    "type": "error", "message": f"unknown type: {mtype}"})

    except WebSocketDisconnect:
        log.info("ws_play disconnected: thread=%s", thread_id)
    except Exception as exc:
        log.exception("ws_play error")
        try:
            await websocket.send_json({"type": "error", "message": f"{exc!r}"})
        except Exception:
            pass


# --------------------------------------------------------------------------
# WebSocket: voice play (server-side STT/TTS)
# --------------------------------------------------------------------------

@app.websocket("/ws/voice/{thread_id}")
async def ws_voice(websocket: WebSocket, thread_id: str,
                   world_id: str = Query(...)):
    """Voice play loop.

    NOT IMPLEMENTED YET. The wire protocol is reserved:
      client -> server  binary audio chunks (Opus or PCM16@16kHz)
      client -> server  {"type": "end_of_utterance"}
      server -> client  {"type": "stt", "text": str}
      server -> client  {"type": "narration", "text": str}
      server -> client  binary TTS audio chunks (PCM16@24kHz)

    Server-side: accumulate chunks until end_of_utterance -> STT -> engine.turn ->
    TTS -> stream back as binary frames.
    """
    await websocket.accept()
    await websocket.send_json({
        "type": "error",
        "message": "voice channel not implemented yet (Phase 4 follow-up)",
    })
    await websocket.close()


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("storyteller_web_ui_backend.main:app",
                host="0.0.0.0", port=8090, log_level="info", reload=False)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
