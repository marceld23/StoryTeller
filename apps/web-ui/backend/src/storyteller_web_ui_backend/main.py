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
import json
import logging
import uuid

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
from storyteller_core.config import ROOT, load_config
from storyteller_core.i18n import CMD_KEYWORDS, norm
from storyteller_core.story.cost import DailyCapExceeded
from storyteller_core.story.engine import StoryEngine
from storyteller_core.story.user_notes import create_user_note
from storyteller_core.worlds.generate import generate_world
from storyteller_core.worlds.registry import (
    all_world_ids,
    load_world,
    save_world,
)

log = logging.getLogger("storyteller.web_ui")


# --------------------------------------------------------------------------
# app + shared handles
# --------------------------------------------------------------------------

app = FastAPI(title="StoryTeller Play")

_CFG = load_config()

# Same-origin in production (SPA served by this backend); allow-list covers
# `yarn dev`. Tighten via web.allowed_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CFG.web.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _auth(request, call_next):
    """Token gate for /api/* (except /api/health). Active only when
    STORYTELLER_WEB_TOKEN is set; read live so .env changes apply without a
    restart. WebSockets authenticate via ?token=."""
    from fastapi.responses import JSONResponse

    token = load_config().web.auth_token
    p = request.url.path
    if token and p.startswith("/api/") and p != "/api/health":
        if request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


def _ws_authorized(websocket) -> bool:
    """WS auth via ?token= query (browsers can't set WS headers)."""
    token = load_config().web.auth_token
    if not token:
        return True
    return websocket.query_params.get("token", "") == token


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
    """Liveness + a low-detail "is the storyteller actually usable right now"
    flag for the player UI. We only report whether the story / tts / stt
    roles look healthy — the player has no use for per-endpoint diagnostics
    (those live in the admin UI). The hint says "Erzähler ist gerade nicht
    verfügbar" without leaking provider names or HTTP codes.
    """
    cfg = _cfg()
    storyteller_available = True
    try:
        from storyteller_core.health import HealthRegistry
        snap = HealthRegistry.get(cfg).snapshot()
        for role in ("story", "tts", "stt"):
            rs = snap.get(role)
            if rs and not rs.get("ok", True) and rs.get(
                    "consecutive_failures", 0) >= 2:
                storyteller_available = False
                break
    except Exception:
        # Health subsystem unavailable — don't block the UI on it.
        pass
    return {
        "ok": True,
        "storyteller_available": storyteller_available,
        "limits": {
            "max_prompt_chars": cfg.web.max_prompt_chars,
            "max_turn_chars": cfg.web.max_turn_chars,
        },
    }


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


@app.get("/api/wait_sound", include_in_schema=False)
def wait_sound():
    """Serve the neutral wait sound to the browser voice page so the
    "thinking" window has audible feedback. The same generic_waiting.wav
    the Pi plays during world generation lives in data/wait_sounds/."""
    from fastapi.responses import FileResponse
    p = _CFG.path(f"data/wait_sounds/{_CFG.story.world_gen_wait_sound}")
    if not p.is_file():
        raise HTTPException(404, "wait sound not present")
    return FileResponse(str(p), media_type="audio/wav")


@app.get("/api/sessions/{thread_id}/replay")
def session_replay(thread_id: str, world_id: str = Query(...)):
    """Synthesize the last narration as WAV.

    Two callers:
      * text-mode "🔊 anhören" button on a narration line — opt-in
        TTS without leaving the text UI;
      * voice-mode "Sag das nochmal" replay control.

    Returns 404 if the session has no narration yet (fresh thread).
    Cost: one TTS call per click — text-mode replay is opt-in to keep
    silent reading free.
    """
    from fastapi.responses import Response
    cfg = _cfg()
    engine = _make_engine(world_id, thread_id)
    text = engine.last_narration()
    if not text or not text.strip():
        raise HTTPException(404, "no narration to replay")
    wav = _synthesize_wav(cfg, text)
    return Response(content=wav, media_type="audio/wav",
                    headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------
# REST: player-side world generation (text-input parallel to the Pi voice-
# mode interview). Synchronous: the request blocks 1–3 minutes while the
# generator runs; the SvelteKit page shows a spinner. The web-ui process
# is single-process per gunicorn worker, so a single long-running gen is
# fine; concurrent generation isn't supported.
# --------------------------------------------------------------------------

class GeneratePayload(BaseModel):
    prompt: str


@app.post("/api/worlds/generate")
async def generate_player_world(payload: GeneratePayload) -> dict:
    """Generate a new world from a free-form player prompt. Mirrors the
    admin endpoint but is player-facing (the player web-ui never had
    access to /api/worlds/generate on the admin backend)."""
    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise HTTPException(422, "prompt is empty")
    max_prompt = _CFG.web.max_prompt_chars
    if len(prompt) > max_prompt:
        raise HTTPException(
            413, f"prompt too long (max {max_prompt} chars)")
    try:
        world = await asyncio.to_thread(generate_world, _CFG, prompt)
        await asyncio.to_thread(save_world, _CFG, world)
        # Index immediately so the RAG retrieves on the first turn.
        try:
            from storyteller_core.story.rag import RAG
            RAG(_CFG).index_world(
                world, force=True,
                locale=norm(_CFG.general.locale))
        except Exception as exc:
            log.warning("post-gen RAG index failed: %r", exc)
    except DailyCapExceeded as exc:
        raise HTTPException(
            402, f"Tagesbudget erreicht ({exc.usd_today:.2f} / "
                 f"{exc.cap_usd:.2f} USD)") from exc
    return {"id": world.id, "name": world.name, "genre": world.genre}


class NotePayload(BaseModel):
    text: str


@app.post("/api/sessions/{thread_id}/note")
async def session_note(thread_id: str, payload: NotePayload,
                        world_id: str = Query(...)) -> dict:
    """Player-introduced world fact via REST (alternative to the WS
    `note` message — useful for HTTP clients / non-WS pages)."""
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(422, "text is empty")
    engine = _make_engine(world_id, thread_id)
    try:
        note = await asyncio.to_thread(
            create_user_note, _CFG, world_id,
            norm(_CFG.general.locale), text,
            thread_id=thread_id, rag=engine.ctx.rag)
    except DailyCapExceeded as exc:
        raise HTTPException(
            402, f"Tagesbudget erreicht ({exc.usd_today:.2f} / "
                 f"{exc.cap_usd:.2f} USD)") from exc
    return {"id": note.id, "name": note.name, "kind": note.kind,
            "description": note.description}


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
    if not _ws_authorized(websocket):
        await websocket.close(code=4401)
        return
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
                if len(user_text) > _CFG.web.max_turn_chars:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Eingabe zu lang "
                                   f"(max {_CFG.web.max_turn_chars} Zeichen)."})
                    continue
                await websocket.send_json({"type": "thinking"})
                try:
                    reply = await asyncio.to_thread(engine.turn, user_text)
                except DailyCapExceeded as exc:
                    await websocket.send_json({
                        "type": "daily_cap_exceeded",
                        "usd_today": exc.usd_today,
                        "cap_usd": exc.cap_usd,
                        "message": (
                            "Tagesbudget erreicht "
                            f"({exc.usd_today:.2f} / "
                            f"{exc.cap_usd:.2f} USD). "
                            "Spielstand ist automatisch gespeichert. "
                            "Bitte später wieder vorbeischauen oder "
                            "den Admin um einen Reset bitten.")})
                    continue
                except Exception as exc:
                    log.exception("engine.turn failed")
                    await websocket.send_json({
                        "type": "error", "message": f"{exc!r}"})
                    continue
                await websocket.send_json({"type": "narration", "text": reply})
            elif mtype == "undo":
                text = await asyncio.to_thread(engine.undo_last)
                await websocket.send_json({"type": "narration", "text": text})
            elif mtype == "note":
                # Player-introduced world fact. Mirror the Pi voice
                # command "Vermerken: …": extract via gen LLM, store in
                # the per-world JSONL + RAG. Cap-checked.
                note_text = (msg.get("text") or "").strip()
                if not note_text:
                    await websocket.send_json({
                        "type": "error",
                        "message": "leere Notiz"})
                    continue
                try:
                    note = await asyncio.to_thread(
                        create_user_note, _CFG, world_id,
                        norm(_CFG.general.locale), note_text,
                        thread_id=thread_id,
                        rag=engine.ctx.rag)
                    await websocket.send_json({
                        "type": "note_saved",
                        "name": note.name, "kind": note.kind,
                        "description": note.description})
                except DailyCapExceeded as exc:
                    await websocket.send_json({
                        "type": "daily_cap_exceeded",
                        "usd_today": exc.usd_today,
                        "cap_usd": exc.cap_usd,
                        "message": (
                            "Tagesbudget erreicht — Notiz konnte "
                            "nicht klassifiziert werden.")})
                except Exception as exc:
                    log.warning("note create failed: %r", exc)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Notiz fehlgeschlagen: {exc!r}"})
            elif mtype == "end_story":
                # Soft close: state is auto-checkpointed, client should
                # navigate back to the world picker.
                await websocket.send_json({"type": "story_ended"})
                break
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

def _pcm_to_wav(pcm, sr: int) -> bytes:
    """float32 mono [-1,1] -> 16-bit PCM WAV bytes (browser-playable)."""
    import io
    import wave

    import numpy as np

    clipped = np.clip(pcm, -1.0, 1.0)
    i16 = (clipped * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(i16.tobytes())
    return buf.getvalue()


def _transcribe(cfg, audio: bytes, suffix: str = ".webm") -> str:
    """Write the browser blob to a temp file and run STT (Whisper detects
    the container from the file extension)."""
    import os
    import tempfile

    from storyteller_voice.stt import get_stt

    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return get_stt(cfg).transcribe(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _synthesize_wav(cfg, text: str) -> bytes:
    from storyteller_voice.tts import get_tts

    pcm, sr = get_tts(cfg).synthesize(text)
    return _pcm_to_wav(pcm, sr)


@app.websocket("/ws/voice/{thread_id}")
async def ws_voice(websocket: WebSocket, thread_id: str,
                   world_id: str = Query(...)):
    """Voice play loop (push-to-talk style).

    Wire protocol:
      client -> server  binary frame   = one recorded utterance (webm/opus blob)
      client -> server  {"type":"undo"}
      server -> client  {"type":"narration","text":str}   (text of the reply)
      server -> client  {"type":"stt","text":str}          (what we heard)
      server -> client  {"type":"thinking"}
      server -> client  binary frame   = WAV audio of the narration (16-bit PCM)
      server -> client  {"type":"audio_done"}
      server -> client  {"type":"error","message":str}

    On connect the server sends the opening (text + audio).
    """
    if not _ws_authorized(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    cfg = _cfg()
    try:
        engine = _make_engine(world_id, thread_id)

        async def _say(text: str) -> None:
            """Send narration text + synthesized WAV audio."""
            await websocket.send_json({"type": "narration", "text": text})
            if text:
                try:
                    wav = await asyncio.to_thread(_synthesize_wav, cfg, text)
                    await websocket.send_bytes(wav)
                except Exception as exc:
                    log.warning("TTS failed: %r", exc)
            await websocket.send_json({"type": "audio_done"})

        snap = engine.state()
        if snap.get("memory"):
            await _say(engine.last_narration())
        else:
            await websocket.send_json({"type": "thinking"})
            await _say(await asyncio.to_thread(engine.opening))

        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                audio = msg["bytes"]
                try:
                    text_in = await asyncio.to_thread(_transcribe, cfg, audio)
                except Exception as exc:
                    log.exception("STT failed")
                    await websocket.send_json({"type": "error",
                                               "message": f"STT: {exc!r}"})
                    continue
                await websocket.send_json({"type": "stt", "text": text_in})
                if not text_in.strip():
                    await websocket.send_json({"type": "audio_done"})
                    continue
                # Voice command: "Wiederhole" / "Repeat" — replay the
                # last narration without a story turn. Matched as a
                # SHORT phrase (≤3 tokens) so a mid-sentence "again"
                # in player input cannot trigger a fake repeat.
                _toks = [t.strip(",.!?;:") for t in text_in.lower().split()]
                _loc = norm(cfg.general.locale)
                _repeat_kw = CMD_KEYWORDS.get(_loc, {}).get("repeat", ())
                if (_toks and len(_toks) <= 3
                        and any(t in _repeat_kw for t in _toks)):
                    last = await asyncio.to_thread(engine.last_narration)
                    if last and last.strip():
                        await _say(last)
                    else:
                        # No prior narration -> short message, no LLM call.
                        msg = ("Da ist noch keine Erzählung, die ich "
                               "wiederholen könnte." if _loc == "de"
                               else "There's no narration to repeat yet.")
                        await _say(msg)
                    continue
                await websocket.send_json({"type": "thinking"})
                try:
                    reply = await asyncio.to_thread(engine.turn, text_in)
                except DailyCapExceeded as exc:
                    await websocket.send_json({
                        "type": "daily_cap_exceeded",
                        "usd_today": exc.usd_today,
                        "cap_usd": exc.cap_usd,
                        "message": (
                            "Tagesbudget erreicht "
                            f"({exc.usd_today:.2f} / "
                            f"{exc.cap_usd:.2f} USD). Spielstand "
                            "ist gespeichert. Bitte später wieder "
                            "vorbeischauen.")})
                    continue
                except Exception as exc:
                    log.exception("engine.turn failed")
                    await websocket.send_json({"type": "error",
                                               "message": f"{exc!r}"})
                    continue
                await _say(reply)

            elif "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                except Exception:
                    continue
                if data.get("type") == "undo":
                    text = await asyncio.to_thread(engine.undo_last)
                    await _say(text)
                elif data.get("type") == "interrupt":
                    # Barge-in is handled client-side (the browser stops the
                    # <audio>); the WAV was already sent, nothing to cancel
                    # server-side. Player simply records again next.
                    pass

    except WebSocketDisconnect:
        log.info("ws_voice disconnected: thread=%s", thread_id)
    except Exception as exc:
        log.exception("ws_voice error")
        try:
            await websocket.send_json({"type": "error", "message": f"{exc!r}"})
        except Exception:
            pass


# --------------------------------------------------------------------------
# static SPA frontend (built by `yarn build` in apps/web-ui/frontend)
# Registered LAST so /api/* + /ws/* win; serves real files, else index.html.
# --------------------------------------------------------------------------
_FRONTEND = ROOT / "apps" / "web-ui" / "frontend" / "build"
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
                "apps/web-ui/frontend", _FRONTEND)


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
