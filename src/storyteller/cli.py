"""Command line.

  storyteller info | seed | hw-test
  storyteller rag build [--force] [--world ID]
  storyteller voice-prompts build [--force] [--all-locales] [--locale de|en]
  storyteller wait-sounds build [--force] [--world ID]
  storyteller demo --world ID [--text "…"] [--opening] [--no-rag] [--locale]
  storyteller run [--world ID] [--ptt] [--text] [--silent]
                  [--profile pi|pc] [--locale de|en] [--no-rag] [--load NAME]
  storyteller admin                # web admin (uv sync --extra web)
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


def _say(cfg, world, backend, tts, fx, leds, gen, speak: bool = True):
    """LLM 'denkt' + TTS-Synthese laufen UNTER dem welt-spezifischen
    Wartesound-Loop (LED 'think'); erst danach wird die Erzählung gesprochen.
    speak=False (Text-/Silent-Modus): nur generieren, keine Audioausgabe."""
    if not speak:
        return gen()
    from .audio.player import play_array
    from .voice.waitloop import WaitLoop

    out = None
    with WaitLoop(cfg, backend, world.wait_sound, leds):
        text = gen()
        if text:
            a, sr = tts.synthesize(text, world.narration_style)
            out = (fx.process(a, sr), sr)
    if out is not None:
        if leds:
            leds.speak()
        play_array(backend, out[0], out[1])
    return text


def _classify(cfg, said: str, options: list[tuple[str, str]]) -> str:
    """Map a spoken choice to one option id via the LLM, or 'unknown'."""
    try:
        import json

        from .oai import get_client

        ids = [o[0] for o in options]
        cat = "\n".join(f"- {i}: {d}" for i, d in options)
        sysmsg = (
            "Map the user's spoken choice to exactly one option id below, or "
            "'unknown' if unclear. Consider meaning, not exact words. Answer "
            f"JSON only: {{\"choice\": \"<one of: "
            f"{', '.join(ids + ['unknown'])}>\"}}\n\nOPTIONS:\n" + cat)
        r = get_client(cfg).chat.completions.create(
            model=cfg.models.story_llm,
            messages=[{"role": "system", "content": sysmsg},
                      {"role": "user", "content": said}],
            response_format={"type": "json_object"})
        c = json.loads(r.choices[0].message.content or "{}") \
            .get("choice", "unknown").strip()
        return c if c in ids else "unknown"
    except Exception:
        return "unknown"


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
    from .i18n import LOCALES
    from .story.rag import WorldRAG
    from .worlds.registry import all_world_ids, load_world

    rag = WorldRAG(cfg)
    ids = [args.world] if args.world else all_world_ids(cfg)
    saved = cfg.general.locale
    try:
        for loc in LOCALES:
            cfg.general.locale = loc
            for wid in ids:
                w = load_world(cfg, wid)
                n = rag.index_world(w, force=args.force, locale=loc)
                print(f"[{loc}] {wid}: "
                      f"{'indexiert' if n else 'vorhanden'} "
                      f"({rag.count(wid, loc)})")
    finally:
        cfg.general.locale = saved
    return 0


def cmd_voice_prompts(cfg, args) -> int:
    from .i18n import LOCALES
    from .voice.prompts import VoicePromptCache

    locs = LOCALES if getattr(args, "all_locales", False) else \
        [getattr(args, "locale", None) or cfg.general.locale]
    for loc in locs:
        built = VoicePromptCache(cfg, loc).build(force=args.force)
        print(f"[{loc}] gerendert:", built or "(aktuell)")
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

    from .i18n import norm

    loc = norm(cfg.general.locale)
    rag = None
    if use_rag:
        try:
            from .story.rag import WorldRAG

            rag = WorldRAG(cfg)
            rag.index_world(world, locale=loc)
        except Exception as e:
            print(f"[warn] RAG aus: {e!r}")
    return StoryEngine(cfg, world, rag), rag


def cmd_demo(cfg, args) -> int:
    from .audio.backend import get_backend
    from .hardware.leds import LedRing
    from .voice.fx import VoiceFX
    from .voice.tts import get_tts
    from .worlds.registry import load_world

    if getattr(args, "locale", None):
        cfg.general.locale = args.locale
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
    from .i18n import CMD_KEYWORDS, RESUME_DIRECTIVE, norm
    from .runtime import resolve_profile
    from .worlds.registry import load_world

    if args.profile:
        cfg.runtime.profile = args.profile
    if getattr(args, "locale", None):
        cfg.general.locale = args.locale
    _loc = norm(cfg.general.locale)
    _cmd_kw = CMD_KEYWORDS[_loc]
    _resume_dir = RESUME_DIRECTIVE[_loc]
    rp(f"[dim]Profil: {resolve_profile(cfg)} | Backend: "
       f"{get_backend(cfg).name} | Locale: {_loc}[/dim]")
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

    speak = not args.silent          # --silent: keine Audioausgabe
    text_mode = args.text            # --text: Tastatur statt Mikro (PC)
    from .audio.player import play_array
    from .voice.waitloop import WaitLoop

    def _init_engine_ww():
        eng, _ = _make_engine(cfg, world, not args.no_rag)
        fxx = VoiceFX(cfg, world.fx_preset)
        wwx = None
        if not args.ptt and not text_mode:
            from .voice.wakeword import WakeWord

            w = WakeWord(cfg, backend)
            if w.available:
                wwx = w
            else:
                rp("[yellow]Wake-Word nicht verfügbar -> Push-to-talk"
                   "[/yellow]")
        return eng, fxx, wwx

    def _open(eng):
        from .i18n import RESTORE_DIRECTIVE, norm

        if restore_state:
            eng.restore(restore_state)
            return eng.turn(RESTORE_DIRECTIVE[norm(cfg.general.locale)])
        return eng.opening()

    # Pause nach der Welt-Auswahl mit dem Wartesound überbrücken (nur bei Audio).
    if speak:
        out = None
        with WaitLoop(cfg, backend, world.wait_sound, leds):
            engine, fx, ww = _init_engine_ww()
            style = world.narration_style
            first = _open(engine)
            if first:
                a, sr = tts.synthesize(first, style)
                out = (fx.process(a, sr), sr)
        rp(f"[green][Erzähler][/green] {first}")
        if out is not None:
            leds.speak()
            play_array(backend, out[0], out[1])
    else:
        engine, fx, ww = _init_engine_ww()
        style = world.narration_style
        first = _open(engine)
        rp(f"[green][Erzähler][/green] {first}")

    def autosave():
        return sm.save(f"{world.id}-auto", engine.snapshot())

    def _sysmenu():
        """Spoken system menu; then replay the last narration. -> 'quit'|None."""
        if speak:
            prompts.play("sys_menu", backend)
        else:
            rp("[dim]System: save / quit / undo / load / close[/dim]")
        if text_mode:
            pick = input("System: ").strip()
        else:
            leds.listen()
            with tempfile.NamedTemporaryFile(suffix=".wav",
                                             delete=False) as t:
                w = t.name
            backend.record_wav(w, 5)
            pick = stt.transcribe(w).strip()
        rp(f"[cyan][Du][/cyan] {pick}")
        opts = [("save", "speichern / save the game"),
                ("quit", "beenden / quit the game"),
                ("undo", "Spielzug zurück / undo the last turn"),
                ("load", "Spielstand laden / load the latest save"),
                ("close", "Menü schließen / close menu and continue")]
        ch = _classify(cfg, pick, opts)
        if ch == "unknown":
            lw = pick.lower()
            if any(k in lw for k in ("speich", "save")):
                ch = "save"
            elif any(k in lw for k in ("beend", "quit", "exit", "schluss",
                                       "aufhör")):
                ch = "quit"
            elif any(k in lw for k in ("zurück", "zuruck", "undo",
                                       "rückgäng", "ruckgang")):
                ch = "undo"
            elif any(k in lw for k in ("lad", "load")):
                ch = "close" if "spielstand" not in lw and "save" in lw \
                    else "load"
            else:
                ch = "close"
        if ch == "quit":
            return "quit"
        if ch == "save":
            autosave()
            prompts.play("saved", backend) if speak \
                else rp("[dim](gespeichert)[/dim]")
        elif ch == "undo":
            engine.undo_last()
            prompts.play("undone", backend) if speak \
                else rp("[dim](Spielzug zurück)[/dim]")
        elif ch == "load":
            if sm.latest():
                engine.restore(sm.load(sm.latest()))
            elif speak:
                prompts.play("no_saves", backend)
            else:
                rp("[dim](keine Spielstände)[/dim]")
        else:  # close
            prompts.play("closed", backend) if speak \
                else rp("[dim](Menü geschlossen)[/dim]")
        last = engine.last_narration() or engine.turn(_resume_dir)
        _say(cfg, world, backend, tts, fx, leds, (lambda: last), speak=speak)
        rp(f"[green][Erzähler][/green] {last}")
        return None

    import logging

    log = logging.getLogger("storyteller")
    # follow-up: after the narrator speaks, listen once WITHOUT the wake word
    follow_enabled = bool(ww) and cfg.wakeword.follow_up
    pending_follow = follow_enabled  # also lets the player answer the opening
    try:
        while True:
            leds.idle()
            try:
                if text_mode:
                    said = input("Du: ").strip()
                else:
                    if ww and not pending_follow:
                        if speak:  # static reminder when it stops listening
                            prompts.play("wake_hint", backend)
                        rp("[dim]… warte auf Wake-Word …[/dim]")
                        ww.listen_blocking()
                    elif ww and pending_follow:
                        rp("[dim]… sprich direkt weiter (oder still bleiben "
                           "für Wake-Word) …[/dim]")
                    elif not ww:
                        input("[Enter zum Sprechen, Strg+C beendet] ")
                    pending_follow = False
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
                _toks = [t.strip(",.!?;:") for t in low.split()]
                if _toks and len(_toks) <= 3 and any(
                        t in _cmd_kw["menu"] for t in _toks):
                    if _sysmenu() == "quit":
                        break
                    pending_follow = follow_enabled
                    continue
                if any(k in low for k in _cmd_kw["quit"]):
                    break
                if any(k in low for k in _cmd_kw["save"]):
                    autosave()
                    if speak:
                        prompts.play("saved", backend)
                    else:
                        rp("[dim](gespeichert)[/dim]")
                    continue
                if any(k in low for k in _cmd_kw["load"]):
                    if sm.latest():
                        def _resume():
                            engine.restore(sm.load(sm.latest()))
                            return engine.turn(_resume_dir)
                        r = _say(cfg, world, backend, tts, fx, leds, _resume,
                                 speak=speak)
                        rp(f"[green][Erzähler][/green] {r}")
                        pending_follow = follow_enabled
                    elif speak:
                        prompts.play("no_saves", backend)
                    else:
                        rp("[dim](keine Spielstände)[/dim]")
                    continue
                reply = _say(cfg, world, backend, tts, fx, leds,
                             lambda: engine.turn(said), speak=speak)
                rp(f"[green][Erzähler][/green] {reply}  "
                   f"[dim]({engine.state().value}, "
                   f"${engine.cost.usd:.3f})[/dim]")
                pending_follow = follow_enabled
                if engine.cost.over_cap:
                    rp("[yellow]Kostendeckel erreicht — Abschluss.[/yellow]")
                    autosave()
                    if speak:
                        prompts.play("goodbye", backend)
                    break
            except Exception as exc:
                log.warning("Zug-Fehler (Loop läuft weiter): %r", exc)
                try:
                    leds.error()
                    if speak:
                        prompts.play("error_retry", backend)
                except Exception:
                    pass
                time.sleep(1.0)
                continue
    except KeyboardInterrupt:
        print()
        autosave()
        if speak:
            prompts.play("goodbye", backend)
    leds.off()
    return 0


def cmd_chat(cfg, args) -> int:
    """Pure text REPL for testing — no STT/TTS/audio/menu/wake word."""
    from rich import print as rp

    from .i18n import CMD_KEYWORDS, RESUME_DIRECTIVE, norm
    from .persistence.saves import SaveManager
    from .worlds.registry import load_world

    if getattr(args, "locale", None):
        cfg.general.locale = args.locale
    loc = norm(cfg.general.locale)
    kw = CMD_KEYWORDS[loc]
    sm = SaveManager(cfg)

    wid = args.world
    restore_state = None
    if args.load:
        restore_state = sm.load(args.load)
        wid = restore_state["world_id"]
    world = load_world(cfg, wid)
    rp(f"[dim]chat | world={world.name} | locale={loc} | "
       f"commands: save / load / quit[/dim]")

    engine, _ = _make_engine(cfg, world, not args.no_rag)
    if restore_state:
        engine.restore(restore_state)
        first = engine.turn(RESUME_DIRECTIVE[loc])
    else:
        first = engine.opening()
    rp(f"\n[green][Narrator][/green] {first}\n")

    while True:
        try:
            said = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not said:
            continue
        low = said.lower()
        if low in ("quit", "exit", ":q", "q") or any(k in low
                                                     for k in kw["quit"]):
            break
        if low in ("save", ":w") or any(k in low for k in kw["save"]):
            print(f"[saved: {sm.save(f'{world.id}-chat', engine.snapshot())}]")
            continue
        if low in ("load",) or any(k in low for k in kw["load"]):
            if sm.latest():
                engine.restore(sm.load(sm.latest()))
                rp(f"[green][Narrator][/green] "
                   f"{engine.turn(RESUME_DIRECTIVE[loc])}\n")
            else:
                print("[no saves]")
            continue
        reply = engine.turn(said)
        rp(f"\n[green][Narrator][/green] {reply}  "
           f"[dim]({engine.state().value}, ${engine.cost.usd:.3f})[/dim]\n")
        if engine.cost.over_cap:
            rp("[yellow]cost cap reached — wrapping up.[/yellow]")
            sm.save(f"{world.id}-chat", engine.snapshot())
            break
    return 0


def cmd_netcheck(cfg, args) -> int:
    from .net import onboarding

    if args.check:  # safe: never starts the AP
        ok = onboarding.have_connectivity(cfg)
        print("connectivity:",
              "OK — connected (no AP)" if ok else "NONE — would start AP")
        return 0
    onboarding.run_onboarding(cfg)
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
    pv.add_argument("--locale", default=None, help="de|en")
    pv.add_argument("--all-locales", action="store_true",
                    help="alle Locales rendern")
    pw2 = sub.add_parser("wait-sounds")
    pw2.add_argument("build", nargs="?", default="build")
    pw2.add_argument("--force", action="store_true")
    pw2.add_argument("--world", default=None)
    pd = sub.add_parser("demo")
    pd.add_argument("--world", required=True)
    pd.add_argument("--text", default="")
    pd.add_argument("--opening", action="store_true")
    pd.add_argument("--no-rag", action="store_true")
    pd.add_argument("--locale", default=None, help="de|en")
    prun = sub.add_parser("run")
    prun.add_argument("--world", default=None)
    prun.add_argument("--ptt", action="store_true",
                      help="Push-to-talk (Enter) statt Wake-Word")
    prun.add_argument("--text", action="store_true",
                      help="Tastatur-Eingabe statt Mikrofon (PC ohne Mikro)")
    prun.add_argument("--silent", action="store_true",
                      help="keine Audioausgabe (reiner Text-Modus)")
    prun.add_argument("--profile", default=None,
                      help="auto|pi|pc — überschreibt config.runtime.profile")
    prun.add_argument("--locale", default=None,
                      help="de|en — überschreibt config.general.locale")
    prun.add_argument("--no-rag", action="store_true")
    prun.add_argument("--load", default=None)
    pc = sub.add_parser("chat", help="text REPL (no STT/TTS/audio)")
    pc.add_argument("--world", default="sternenfahrt")
    pc.add_argument("--locale", default=None, help="de|en")
    pc.add_argument("--no-rag", action="store_true")
    pc.add_argument("--load", default=None)
    pnc = sub.add_parser("netcheck",
                         help="Wi-Fi onboarding (captive portal if no Wi-Fi)")
    pnc.add_argument("--check", action="store_true",
                     help="only report connectivity (never starts the AP)")

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
    if args.cmd == "chat":
        return cmd_chat(cfg, args)
    if args.cmd == "netcheck":
        return cmd_netcheck(cfg, args)
    p.error("unbekannt")
    return 2


if __name__ == "__main__":
    sys.exit(main())
