"""storyteller-pi — Raspberry Pi voice loop against the LangGraph engine.

Subcommands:
  run        full voice loop (ReSpeaker + wake word + LEDs + ALSA).
             Flags: --world --thread --new --locale --profile
                    --text (keyboard) --silent (no TTS) --ptt (no wake word)
                    --no-rag
  netcheck   Wi-Fi onboarding: open AP + captive portal if offline at boot
             (--check only reports connectivity, never starts the AP)

Session state lives in the LangGraph checkpointer (data/checkpoints.db),
keyed by `thread_id`. The Pi uses a stable per-world thread ("pi-<world>")
so a story auto-resumes across restarts; `--new` forces a fresh branch.
There is no snapshot/restore and no SaveManager any more — "save" is
implicit (every turn is checkpointed).
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time

from rich import print as rp
from storyteller_core.config import load_config
from storyteller_core.i18n import CMD_KEYWORDS, RESTORE_DIRECTIVE, norm
from storyteller_core.story.engine import StoryEngine
from storyteller_core.worlds.registry import load_world

log = logging.getLogger("storyteller.pi")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _classify(cfg, said: str, options: list[tuple[str, str]]) -> str:
    """Map a spoken choice to one option id via the LLM, or 'unknown'."""
    try:
        import json

        from storyteller_core.oai import get_chat_client

        ids = [o[0] for o in options]
        cat = "\n".join(f"- {i}: {d}" for i, d in options)
        sysmsg = (
            "Map the user's spoken choice to exactly one option id below, or "
            "'unknown' if unclear. Consider meaning, not exact words. Answer "
            f"JSON only: {{\"choice\": \"<one of: "
            f"{', '.join(ids + ['unknown'])}>\"}}\n\nOPTIONS:\n" + cat)
        r = get_chat_client(cfg, "story").chat.completions.create(
            model=cfg.models.story_llm,
            messages=[{"role": "system", "content": sysmsg},
                      {"role": "user", "content": said}],
            response_format={"type": "json_object"})
        c = (json.loads(r.choices[0].message.content or "{}")
             .get("choice", "unknown").strip())
        return c if c in ids else "unknown"
    except Exception:
        return "unknown"


def _build_engine(cfg, world, *, use_rag: bool, thread_id: str) -> StoryEngine:
    """Construct a StoryEngine for the new (checkpointer-backed) API."""
    loc = norm(cfg.general.locale)
    rag = None
    if use_rag:
        try:
            from storyteller_core.story.rag import WorldRAG

            rag = WorldRAG(cfg)
            rag.index_world(world, locale=loc)
        except Exception as exc:
            rp(f"[yellow]RAG aus: {exc!r}[/yellow]")
    transcript = None
    try:
        from storyteller_core.story.transcript import Transcript

        sess = f"{world.id}-{time.strftime('%Y%m%d-%H%M%S')}"
        transcript = Transcript(cfg, sess)
    except Exception:
        pass
    return StoryEngine(cfg, world, rag=rag, transcript=transcript,
                       thread_id=thread_id)


def _say(cfg, world, backend, tts, fx, leds, gen, speak: bool = True):
    """Generate (LLM) under the wait-sound loop, then speak the result.

    speak=False (text/silent): only generate, no audio.
    """
    if not speak:
        return gen()
    from storyteller_hardware.audio.player import play_array
    from storyteller_voice.waitloop import WaitLoop

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


# --------------------------------------------------------------------------
# run — the voice loop
# --------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    from storyteller_hardware.audio.backend import get_backend
    from storyteller_hardware.audio.player import play_array
    from storyteller_hardware.leds import LedRing
    from storyteller_hardware.menu.voice_menu import VoiceMenu
    from storyteller_hardware.runtime import resolve_profile
    from storyteller_voice.fx import VoiceFX
    from storyteller_voice.prompts import VoicePromptCache
    from storyteller_voice.stt import get_stt
    from storyteller_voice.tts import get_tts
    from storyteller_voice.waitloop import WaitLoop

    cfg = load_config()
    if args.profile:
        cfg.runtime.profile = args.profile
    if args.locale:
        cfg.general.locale = args.locale
    loc = norm(cfg.general.locale)
    cmd_kw = CMD_KEYWORDS[loc]

    backend = get_backend(cfg)
    backend.set_volume(cfg.audio.default_volume_pct)
    rp(f"[dim]Profil: {resolve_profile(cfg)} | Backend: {backend.name} | "
       f"Locale: {loc}[/dim]")
    leds = LedRing()
    prompts = VoicePromptCache(cfg)
    stt = get_stt(cfg)
    tts = get_tts(cfg)

    speak = not args.silent      # --silent: no audio output
    text_mode = args.text        # --text: keyboard instead of mic
    ww = None
    if not args.ptt and not text_mode:
        from storyteller_voice.wakeword import WakeWord

        _w = WakeWord(cfg, backend)
        if _w.available:
            ww = _w
        else:
            rp("[yellow]Wake-Word nicht verfügbar -> Push-to-talk[/yellow]")

    # Guard: with neither a wake word nor a keyboard (no TTY, e.g. under
    # systemd) the loop has no way to get input and would busy-error on
    # input(). Fail fast with a clear message instead of an audible error
    # loop. Fix: bash scripts/install_wakeword.sh (uv sync prunes it).
    if ww is None and not text_mode and not sys.stdin.isatty():
        log.error("no wake word and no TTY — cannot read input as a service. "
                  "Run scripts/install_wakeword.sh (uv sync prunes the "
                  "wake-word packages), then restart storyteller.")
        return 1

    # --- optional spoken intro at start (toggle in the system menu -> Intro,
    # persisted in data/settings.json). Cached/offline-safe. ---
    if speak and not text_mode:
        from storyteller_hardware.runtime import load_settings

        if load_settings(cfg).get("intro_enabled", True):
            prompts.play("intro", backend)

    # --- world selection ---
    wid = args.world
    if not wid:
        if text_mode or ww is None:
            wid = "sternenfahrt"
        else:
            sel = VoiceMenu(cfg, backend, prompts, stt, leds, ww, speak).run()
            wid = sel.get("world_id") or "sternenfahrt"
    world = load_world(cfg, wid)
    rp(f"[bold]Welt:[/bold] {world.name}")

    thread = args.thread or f"pi-{world.id}"
    if args.new:
        thread = f"{thread}-{int(time.time())}"
        rp(f"[dim]Neue Sitzung: thread_id = {thread}[/dim]")

    engine = _build_engine(cfg, world, use_rag=not args.no_rag,
                           thread_id=thread)
    fx = VoiceFX(cfg, world.fx_preset)

    def _first_narration() -> str:
        snap = engine.state()
        if snap.get("memory"):
            # resume: replay the last narration (cheap, no LLM call)
            last = engine.last_narration()
            return last or engine.turn(RESTORE_DIRECTIVE[loc])
        return engine.opening()

    # Bridge the opening generation with the wait sound (audio mode only).
    if speak:
        out = None
        with WaitLoop(cfg, backend, world.wait_sound, leds):
            first = _first_narration()
            if first:
                a, sr = tts.synthesize(first, world.narration_style)
                out = (fx.process(a, sr), sr)
        rp(f"[green][Erzähler][/green] {first}")
        if out is not None:
            leds.speak()
            play_array(backend, out[0], out[1])
    else:
        first = _first_narration()
        rp(f"[green][Erzähler][/green] {first}")

    def _sysmenu() -> str | None:
        """Spoken system menu, then replay last narration. -> 'quit' | None."""
        nonlocal backend
        if speak:
            prompts.play("sys_menu", backend)
        else:
            rp("[dim]System: quit / undo / audio / intro / close[/dim]")
        if text_mode:
            pick = input("System: ").strip()
        else:
            leds.listen()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                w = t.name
            backend.record_until_silence(w)
            pick = stt.transcribe(w).strip()
        rp(f"[cyan][Du][/cyan] {pick}")
        opts = [("save", "speichern / save the game"),
                ("quit", "beenden / quit the game"),
                ("undo", "Spielzug zurück / undo the last turn"),
                ("audio", "Audio/Bluetooth umschalten / switch audio output"),
                ("intro", "Einführung an oder aus / toggle the intro"),
                ("close", "Menü schließen / close menu and continue")]
        ch = _classify(cfg, pick, opts)
        if ch == "unknown":
            lw = pick.lower()
            if any(k in lw for k in ("beend", "quit", "exit", "schluss",
                                     "aufhör")):
                ch = "quit"
            elif any(k in lw for k in ("zurück", "zuruck", "undo",
                                       "rückgäng", "ruckgang")):
                ch = "undo"
            elif any(k in lw for k in ("audio", "bluetooth", "blue tooth")):
                ch = "audio"
            elif any(k in lw for k in ("einführ", "einfuehr", "intro",
                                       "einleitung", "tutorial")):
                ch = "intro"
            elif any(k in lw for k in ("speich", "save")):
                ch = "save"
            else:
                ch = "close"

        if ch == "quit":
            return "quit"
        if ch == "audio":
            from storyteller_hardware.runtime import (
                load_audio_override,
                resolve_backend_name,
                save_audio_override,
            )

            ov = load_audio_override(cfg)
            if resolve_backend_name(cfg) == "pipewire":
                ov["backend"] = "auto"
                amsg = "audio_bt_off"
            else:
                ov["backend"] = "pipewire"
                amsg = "audio_bt_on"
            save_audio_override(cfg, ov)
            try:
                backend = get_backend(cfg)
                backend.set_volume(cfg.audio.default_volume_pct)
            except Exception as exc:
                log.warning("audio switch: %r", exc)
            prompts.play(amsg, backend) if speak else rp(f"[dim]({amsg})[/dim]")
        elif ch == "intro":
            from storyteller_hardware.runtime import (
                load_settings,
                save_settings,
            )

            st = load_settings(cfg)
            new = not st.get("intro_enabled", True)
            st["intro_enabled"] = new
            save_settings(cfg, st)
            imsg = "intro_on" if new else "intro_off"
            prompts.play(imsg, backend) if speak else rp(f"[dim]({imsg})[/dim]")
        elif ch == "save":
            # State is checkpointed every turn -> just confirm.
            prompts.play("saved", backend) if speak \
                else rp("[dim](gespeichert)[/dim]")
        elif ch == "undo":
            last = engine.undo_last()
            prompts.play("undone", backend) if speak \
                else rp("[dim](Spielzug zurück)[/dim]")
            if last:
                _say(cfg, world, backend, tts, fx, leds, (lambda: last),
                     speak=speak)
            return None
        else:  # close
            prompts.play("closed", backend) if speak \
                else rp("[dim](Menü geschlossen)[/dim]")

        last = engine.last_narration()
        if last:
            _say(cfg, world, backend, tts, fx, leds, (lambda: last),
                 speak=speak)
        return None

    # follow-up: after the narrator speaks, listen once WITHOUT the wake word
    follow_enabled = bool(ww) and cfg.wakeword.follow_up
    pending_follow = follow_enabled    # also lets the player answer the opening
    hinted = False                     # wake_hint announced ONCE per idle
    try:
        while True:
            leds.idle()
            # Pick up admin/.env changes to STT/TTS (model + endpoint) without
            # a restart: rebuild from a fresh config each idle cycle. Cheap —
            # the underlying OpenAI clients are cached per (key, base_url).
            cfg = load_config()
            stt = get_stt(cfg)
            tts = get_tts(cfg)
            try:
                if text_mode:
                    said = input("Du: ").strip()
                else:
                    if ww and not pending_follow:
                        if speak and not hinted:
                            prompts.play("wake_hint", backend)
                            hinted = True
                        rp("[dim]… warte auf Wake-Word …[/dim]")
                        if not ww.listen_blocking():
                            time.sleep(2)
                            continue
                        hinted = False
                    elif ww and pending_follow:
                        rp("[dim]… sprich direkt weiter …[/dim]")
                    elif not ww:
                        input("[Enter zum Sprechen, Strg+C beendet] ")
                    pending_follow = False
                    leds.listen()
                    with tempfile.NamedTemporaryFile(suffix=".wav",
                                                     delete=False) as t:
                        wav = t.name
                    backend.record_until_silence(wav)
                    said = stt.transcribe(wav).strip()
                rp(f"[cyan][Du][/cyan] {said}")
                low = said.lower()
                if not said:
                    continue
                toks = [t.strip(",.!?;:") for t in low.split()]
                if toks and len(toks) <= 3 and any(
                        t in cmd_kw["menu"] for t in toks):
                    if _sysmenu() == "quit":
                        break
                    pending_follow = follow_enabled
                    continue
                if any(k in low for k in cmd_kw["quit"]):
                    break
                reply = _say(cfg, world, backend, tts, fx, leds,
                             lambda s=said: engine.turn(s), speak=speak)
                rp(f"[green][Erzähler][/green] {reply}")
                pending_follow = follow_enabled
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
        if speak:
            prompts.play("goodbye", backend)
    leds.off()
    return 0


# --------------------------------------------------------------------------
# netcheck — Wi-Fi onboarding
# --------------------------------------------------------------------------

def cmd_netcheck(args: argparse.Namespace) -> int:
    from storyteller_hardware.net import onboarding

    cfg = load_config()
    if args.check:  # safe: never starts the AP
        ok = onboarding.have_connectivity(cfg)
        print("connectivity:",
              "OK — connected (no AP)" if ok else "NONE — would start AP")
        return 0
    onboarding.run_onboarding(cfg)
    return 0


# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="storyteller-pi")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="full Pi voice loop")
    pr.add_argument("--world",
                    help="world id (default: voice menu / sternenfahrt)")
    pr.add_argument("--thread", help="session id (default: pi-<world>)")
    pr.add_argument("--new", action="store_true",
                    help="start a fresh session (new thread id)")
    pr.add_argument("--locale", choices=("de", "en"))
    pr.add_argument("--profile", choices=("auto", "pi", "pc"))
    pr.add_argument("--text", action="store_true",
                    help="keyboard input instead of mic")
    pr.add_argument("--silent", action="store_true",
                    help="no TTS / audio output")
    pr.add_argument("--ptt", action="store_true",
                    help="push-to-talk (disable wake word)")
    pr.add_argument("--no-rag", action="store_true",
                    help="disable RAG retrieval")
    pr.set_defaults(func=cmd_run)

    pn = sub.add_parser("netcheck", help="Wi-Fi onboarding (captive portal)")
    pn.add_argument("--check", action="store_true",
                    help="only report connectivity; never start the AP")
    pn.set_defaults(func=cmd_netcheck)

    return p


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
