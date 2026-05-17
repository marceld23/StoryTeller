"""Kommandozeile.

  storyteller info | seed | hw-test
  storyteller rag build [--force] [--world ID]
  storyteller voice-prompts build [--force]
  storyteller demo --world ID [--text "…"] [--opening] [--no-rag]
  storyteller run [--world ID] [--ptt] [--no-rag] [--load NAME]
  storyteller admin                # Web-Admin (uv sync --extra web)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from .config import load_config


def _write_sine(path: str, sr: int = 48000, secs: float = 1.2,
                 freq: int = 440, ch: int = 2) -> None:
    t = np.linspace(0, secs, int(sr * secs), endpoint=False)
    mono = (0.05 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    data = np.column_stack([mono, mono]).ravel() if ch == 2 else mono
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def _speak(backend, tts, fx, leds, text: str, style: str = "") -> None:
    from .audio.player import play_array

    if not text:
        return
    if leds:
        leds.speak()
    audio, sr = tts.synthesize(text, style)
    audio = fx.process(audio, sr)
    play_array(backend, audio, sr)


def _say(cfg, world, backend, tts, fx, leds, gen):
    """LLM 'denkt' + TTS-Synthese laufen UNTER dem welt-spezifischen
    Wartesound-Loop (LED 'think'); erst danach wird die Erzählung gesprochen.
    Kein Stille-Loch mehr — gilt für Eröffnung wie jeden Zug."""
    from .audio.player import play_array
    from .voice.waitloop import WaitLoop

    out = None
    with WaitLoop(cfg, world.wait_sound, leds):
        text = gen()
        if text:
            a, sr = tts.synthesize(text, world.narration_style)
            out = (fx.process(a, sr), sr)
    if out is not None:
        if leds:
            leds.speak()
        play_array(backend, out[0], out[1])
    return text


# ---------- einfache Befehle ----------

def cmd_info(cfg) -> int:
    from rich import print as rp

    rp("[bold]Storyteller — Konfiguration[/bold]")
    rp(f"  story_llm : {cfg.models.story_llm}")
    rp(f"  stt / tts : {cfg.models.stt} / {cfg.models.tts} ({cfg.models.tts_voice})")
    rp(f"  embedding : {cfg.models.embedding} dim={cfg.models.embedding_dim}")
    rp(f"  audio     : {cfg.audio.backend}  out={cfg.audio.output_alsa_pcm}")
    rp(f"  wakeword  : {cfg.wakeword.engine} ({cfg.wakeword.model or 'default'})")
    rp(f"  cost cap  : ${cfg.story.cost_cap_usd_per_session} "
       f"(enforce={cfg.cost.enforce})")
    key = cfg.openai_api_key
    rp(f"  API key   : {'gesetzt' if key else 'FEHLT'}")
    return 0


def cmd_seed(cfg) -> int:
    from .worlds.seed import write_seed

    for p in write_seed(cfg.path(cfg.paths.worlds_dir)):
        print(f"geschrieben: {p}")
    return 0


def cmd_hw_test(cfg) -> int:
    from rich import print as rp

    from .audio.backend import get_backend
    from .hardware.leds import LedRing

    ok = True
    backend = get_backend(cfg)
    rp(f"[bold]Backend:[/bold] {backend.name}")
    try:
        if hasattr(backend, "prime"):
            backend.prime()
        for pct in (8, 15):
            backend.set_volume(pct)
            rp(f"  Lautstärke {pct}% -> {backend.get_volume()}%")
    except Exception as e:
        ok = False
        rp(f"  [red]Lautstärke:[/red] {e!r}")
    try:
        _write_sine("/tmp/st_tone.wav")
        backend.play_wav("/tmp/st_tone.wav")
        rp("  [green]Wiedergabe OK[/green]")
    except Exception as e:
        ok = False
        rp(f"  [red]Wiedergabe:[/red] {e!r}")
    try:
        backend.record_wav("/tmp/st_in.wav", 3)
        backend.play_wav("/tmp/st_in.wav")
        rp("  [green]Aufnahme OK[/green]")
    except Exception as e:
        ok = False
        rp(f"  [red]Aufnahme:[/red] {e!r}")
    try:
        ring = LedRing()
        if ring.available:
            for st in ("wake", "listen", "think", "speak"):
                getattr(ring, st)()
                time.sleep(0.8)
            ring.off()
            rp("  [green]LED OK[/green]")
        else:
            ok = False
            rp("  [yellow]LED nicht verfügbar[/yellow]")
    except Exception as e:
        ok = False
        rp(f"  [red]LED:[/red] {e!r}")
    rp(f"[bold]{'ALLES OK' if ok else 'TEILWEISE FEHLER'}[/bold]")
    return 0 if ok else 1


def cmd_rag(cfg, args) -> int:
    from .story.rag import WorldRAG
    from .worlds.registry import all_world_ids, load_world

    rag = WorldRAG(cfg)
    ids = [args.world] if args.world else all_world_ids(cfg)
    for wid in ids:
        n = rag.index_world(load_world(cfg, wid), force=args.force)
        print(f"{wid}: {'indexiert' if n else 'vorhanden'} ({rag.count(wid)})")
    return 0


def cmd_voice_prompts(cfg, args) -> int:
    from .voice.prompts import VoicePromptCache

    print("gerendert:", VoicePromptCache(cfg).build(force=args.force) or "(aktuell)")
    return 0


def cmd_wait_sounds(cfg, args) -> int:
    from .audio.ambient import mood_for, write_ambient
    from .worlds.registry import all_world_ids, load_world

    d = cfg.path(cfg.paths.wait_sounds_dir)
    ids = [args.world] if args.world else all_world_ids(cfg)
    for wid in ids:
        w = load_world(cfg, wid)
        name = w.wait_sound or f"{w.id}_ambient.wav"
        p = d / name
        if p.exists() and not args.force:
            print(f"{wid}: vorhanden ({p.name})")
            continue
        mood = mood_for(w)
        write_ambient(p, mood)
        print(f"{wid}: erzeugt {p.name} (mood={mood})")
    return 0


def _make_engine(cfg, world, use_rag: bool):
    from .story.engine import StoryEngine

    rag = None
    if use_rag:
        try:
            from .story.rag import WorldRAG

            rag = WorldRAG(cfg)
            rag.index_world(world)
        except Exception as e:
            print(f"[warn] RAG aus: {e!r}")
    return StoryEngine(cfg, world, rag), rag


def cmd_demo(cfg, args) -> int:
    from .audio.backend import get_backend
    from .hardware.leds import LedRing
    from .voice.fx import VoiceFX
    from .voice.tts import get_tts
    from .worlds.registry import load_world

    world = load_world(cfg, args.world)
    backend = get_backend(cfg)
    backend.set_volume(cfg.audio.default_volume_pct)
    leds = LedRing()
    engine, _ = _make_engine(cfg, world, not args.no_rag)
    fx = VoiceFX(cfg, world.fx_preset)
    tts = get_tts(cfg)
    text = engine.opening() if (args.opening or not args.text) \
        else engine.turn(args.text)
    print(f"\n[Erzähler] {text}\n")
    print(f"[Status] {engine.state().value} | Substory: "
          f"{engine.substory.title if engine.substory else '-'}")
    _speak(backend, tts, fx, leds, text, world.narration_style)
    leds.off()
    return 0


def cmd_run(cfg, args) -> int:
    from rich import print as rp

    from .audio.backend import get_backend
    from .hardware.leds import LedRing
    from .menu.voice_menu import VoiceMenu
    from .persistence.saves import SaveManager
    from .voice.fx import VoiceFX
    from .voice.prompts import VoicePromptCache
    from .voice.stt import get_stt
    from .voice.tts import get_tts
    from .voice.waitloop import WaitLoop
    from .worlds.registry import load_world

    backend = get_backend(cfg)
    backend.set_volume(cfg.audio.default_volume_pct)
    leds = LedRing()
    prompts = VoicePromptCache(cfg)
    stt = get_stt(cfg)
    tts = get_tts(cfg)
    sm = SaveManager(cfg)

    restore_state = None
    wid = args.world
    if args.load:
        restore_state = sm.load(args.load)
        wid = restore_state["world_id"]
    elif not wid:
        sel = VoiceMenu(cfg, backend, prompts, stt, leds).run()
        if sel.get("action") == "load" and sm.latest():
            restore_state = sm.load(sm.latest())
            wid = restore_state["world_id"]
        else:
            wid = sel.get("world_id") or "sternenfahrt"
    world = load_world(cfg, wid)
    rp(f"[bold]Welt:[/bold] {world.name}")

    # Pause nach der Welt-Auswahl mit dem Wartesound überbrücken: RAG,
    # Wake-Word-Modell-Ladung, Planung, Eröffnung UND TTS laufen alle unter
    # dem welt-spezifischen Loop — erst dann wird die Erzählung gesprochen.
    from .audio.player import play_array
    from .voice.waitloop import WaitLoop

    out = None
    with WaitLoop(cfg, world.wait_sound, leds):
        engine, _ = _make_engine(cfg, world, not args.no_rag)
        fx = VoiceFX(cfg, world.fx_preset)
        style = world.narration_style
        ww = None
        if not args.ptt:
            from .voice.wakeword import WakeWord

            ww = WakeWord(cfg)
            if not ww.available:
                rp("[yellow]Wake-Word aus -> Push-to-talk (Enter)[/yellow]")
                ww = None
        if restore_state:
            engine.restore(restore_state)
            first = engine.turn("[Setze die Geschichte fort: fasse in 1-2 "
                                "Sätzen zusammen, wo wir stehen, und weiter.]")
        else:
            first = engine.opening()
        if first:
            a, sr = tts.synthesize(first, style)
            out = (fx.process(a, sr), sr)
    rp(f"[green][Erzähler][/green] {first}")
    if out is not None:
        leds.speak()
        play_array(backend, out[0], out[1])

    def autosave():
        return sm.save(f"{world.id}-auto", engine.snapshot())

    import logging

    log = logging.getLogger("storyteller")
    try:
        while True:
            leds.idle()
            try:
                if ww:
                    rp("[dim]… warte auf Wake-Word …[/dim]")
                    ww.listen_blocking()
                else:
                    input("[Enter zum Sprechen, Strg+C beendet] ")
                leds.listen()
                with tempfile.NamedTemporaryFile(suffix=".wav",
                                                 delete=False) as t:
                    wav = t.name
                backend.record_wav(wav, 6)
                said = stt.transcribe(wav).strip()
                rp(f"[cyan][Du][/cyan] {said}")
                low = said.lower()
                if not said:
                    continue
                if any(k in low for k in ("beenden", "aufhören", "schluss",
                                          "tschüss", "tschüs")):
                    break
                if "speicher" in low:
                    autosave()
                    prompts.play("saved", backend)
                    continue
                if "lade" in low or "spielstand" in low:
                    if sm.latest():
                        def _resume():
                            engine.restore(sm.load(sm.latest()))
                            return engine.turn("[Kurz zusammenfassen wo wir "
                                               "stehen, dann weiter.]")
                        r = _say(cfg, world, backend, tts, fx, leds, _resume)
                        rp(f"[green][Erzähler][/green] {r}")
                    else:
                        prompts.play("no_saves", backend)
                    continue
                reply = _say(cfg, world, backend, tts, fx, leds,
                             lambda: engine.turn(said))
                rp(f"[green][Erzähler][/green] {reply}  "
                   f"[dim]({engine.state().value}, "
                   f"${engine.cost.usd:.3f})[/dim]")
                if engine.cost.over_cap:
                    rp("[yellow]Kostendeckel erreicht — Abschluss.[/yellow]")
                    autosave()
                    prompts.play("goodbye", backend)
                    break
            except Exception as exc:
                log.warning("Zug-Fehler (Loop läuft weiter): %r", exc)
                try:
                    leds.error()
                    prompts.play("error_retry", backend)
                except Exception:
                    pass
                time.sleep(1.0)
                continue
    except KeyboardInterrupt:
        print()
        autosave()
        prompts.play("goodbye", backend)
    leds.off()
    return 0


def cmd_admin(cfg) -> int:
    try:
        import uvicorn
    except Exception:
        print("Web-Admin braucht Extras:  uv sync --extra web")
        return 1
    print(f"Admin auf http://{cfg.web.host}:{cfg.web.port}  (Strg+C beendet)")
    uvicorn.run("storyteller.web.app:app", host=cfg.web.host,
                port=cfg.web.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="storyteller")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    for n in ("info", "seed", "hw-test", "admin"):
        sub.add_parser(n)
    pr = sub.add_parser("rag")
    pr.add_argument("build", nargs="?", default="build")
    pr.add_argument("--force", action="store_true")
    pr.add_argument("--world", default=None)
    pv = sub.add_parser("voice-prompts")
    pv.add_argument("build", nargs="?", default="build")
    pv.add_argument("--force", action="store_true")
    pw2 = sub.add_parser("wait-sounds")
    pw2.add_argument("build", nargs="?", default="build")
    pw2.add_argument("--force", action="store_true")
    pw2.add_argument("--world", default=None)
    pd = sub.add_parser("demo")
    pd.add_argument("--world", required=True)
    pd.add_argument("--text", default="")
    pd.add_argument("--opening", action="store_true")
    pd.add_argument("--no-rag", action="store_true")
    prun = sub.add_parser("run")
    prun.add_argument("--world", default=None)
    prun.add_argument("--ptt", action="store_true")
    prun.add_argument("--no-rag", action="store_true")
    prun.add_argument("--load", default=None)

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    try:
        from .util.log import setup_logging

        setup_logging(cfg)
    except Exception:
        pass

    if args.cmd == "info":
        return cmd_info(cfg)
    if args.cmd == "seed":
        return cmd_seed(cfg)
    if args.cmd == "hw-test":
        return cmd_hw_test(cfg)
    if args.cmd == "admin":
        return cmd_admin(cfg)
    if args.cmd == "rag":
        return cmd_rag(cfg, args)
    if args.cmd == "voice-prompts":
        return cmd_voice_prompts(cfg, args)
    if args.cmd == "wait-sounds":
        return cmd_wait_sounds(cfg, args)
    if args.cmd == "demo":
        return cmd_demo(cfg, args)
    if args.cmd == "run":
        return cmd_run(cfg, args)
    p.error("unbekannt")
    return 2


if __name__ == "__main__":
    sys.exit(main())
