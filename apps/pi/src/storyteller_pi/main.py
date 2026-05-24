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
import threading
import time

from rich import print as rp
from storyteller_core.config import load_config
from storyteller_core.i18n import (
    CMD_KEYWORDS,
    DESIGN_PROMPTS,
    NO_KEYWORDS,
    NOTE_PROMPTS,
    RESTORE_DIRECTIVE,
    YES_KEYWORDS,
    classify_play_mode,
    matches_end_story,
    norm,
)
from storyteller_core.story.cost import DailyCapExceeded
from storyteller_core.story.engine import StoryEngine
from storyteller_core.story.ledger import CostLedger
from storyteller_core.story.user_notes import create_user_note
from storyteller_core.story.world_design import WorldDesignInterview
from storyteller_core.worlds.generate import generate_world
from storyteller_core.worlds.registry import load_world, save_world

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


def _say(cfg, world, backend, tts, fx, leds, gen, speak: bool = True,
         interrupt=None):
    """Generate (LLM) under the wait-sound loop, then speak the result.

    speak=False (text/silent): only generate, no audio.
    interrupt: optional threading.Event — playback aborts when it is set
    (button barge-in). The caller inspects the event afterwards.

    Wait-sound coverage: the ambient loop keeps playing across BOTH the
    LLM call AND the first TTS chunk render — otherwise the player hears
    a confusing silent gap (5–10 s) between "wait loop stops" and "first
    audio arrives". As soon as chunk 1 is ready we drop the wait loop,
    switch the LEDs to speak, and play chunk 1; the remaining chunks
    pipeline behind it via the streaming player (chunk N+1 renders while
    chunk N plays).
    """
    if not speak:
        return gen()
    from storyteller_hardware.audio.player import play_stream
    from storyteller_voice.waitloop import WaitLoop

    text = ""
    first_chunk: tuple | None = None
    chunks_iter = None
    with WaitLoop(cfg, backend, world.wait_sound, leds):
        text = gen()
        if text:
            chunks_iter = tts.synthesize_streaming(text, world.narration_style)
            try:
                first_chunk = next(chunks_iter)
            except StopIteration:
                first_chunk = None
    if not text:
        return text
    if leds:
        leds.speak()

    def _rest():
        if first_chunk is not None:
            yield first_chunk
        if chunks_iter is not None:
            yield from chunks_iter

    play_stream(backend, _rest(), fx=fx, stop=interrupt)
    return text


# --------------------------------------------------------------------------
# run — the voice loop
# --------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    from storyteller_hardware.audio.backend import get_backend
    from storyteller_hardware.leds import LedRing
    from storyteller_hardware.menu.voice_menu import VoiceMenu
    from storyteller_hardware.runtime import resolve_profile
    from storyteller_voice.fx import VoiceFX
    from storyteller_voice.prompts import VoicePromptCache
    from storyteller_voice.stt import get_stt
    from storyteller_voice.tts import get_tts

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
    # Give the cache the LED ring so cached prompt playback (menus, system
    # announcements) switches the ring to the "speak" colour — otherwise it
    # stays on the previous state (e.g. green / listening) and the player
    # can't tell the system is talking.
    prompts.leds = leds
    stt = get_stt(cfg)
    tts = get_tts(cfg)

    from storyteller_hardware.audio.playback_control import PLAYBACK
    from storyteller_hardware.button import GpioButton

    # Two optional GPIO push-buttons, both off by default. See
    # docs/SETUP_PI.md for wiring. Even if both are disabled (the repo
    # default) the rest of the loop runs unchanged.
    interrupt_btn = GpioButton(cfg, "interrupt")
    shutdown_btn = GpioButton(cfg, "shutdown")
    # Long-press on the interrupt button: abort the current narration and
    # ask the main loop to open the spoken system menu. The narration's
    # abort event is registered here so the button thread can set it.
    menu_requested = threading.Event()
    _current_interrupt: list[threading.Event | None] = [None]

    def _interrupt_short_press() -> None:
        # Short press = pause/resume of the currently playing aplay
        # subprocess (SIGSTOP / SIGCONT). No-op when nothing is playing.
        state = PLAYBACK.toggle()
        rp(f"[dim](Taster: {state})[/dim]")

    def _interrupt_long_press() -> None:
        # Long press = abort + open system menu.
        ev = _current_interrupt[0]
        if ev is not None:
            ev.set()
        menu_requested.set()
        rp("[dim](Taster lang: → Systemmenü)[/dim]")

    def _shutdown_short_press() -> None:
        # Short press = confirm "saved" (every turn is auto-checkpointed).
        if speak:
            try:
                prompts.play("saved", backend)
            except Exception:
                pass
        rp("[dim](Taster: Spielstand gespeichert)[/dim]")

    def _shutdown_long_press() -> None:
        # Long press = say goodbye and power off. Requires NOPASSWD sudo
        # for `systemctl poweroff` — see docs/SETUP_PI.md.
        log.info("shutdown button: powering off")
        if speak:
            try:
                prompts.play("goodbye", backend)
            except Exception:
                pass
        import subprocess
        try:
            subprocess.run(["sudo", "-n", "systemctl", "poweroff"],
                           check=False, timeout=5)
        except Exception as exc:
            log.warning("shutdown failed: %r", exc)

    interrupt_btn.set_callbacks(_interrupt_short_press, _interrupt_long_press)
    shutdown_btn.set_callbacks(_shutdown_short_press, _shutdown_long_press)

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

    # --- optional spoken intro at start ---
    # Two separately-toggleable parts (both default ON, persisted in
    # data/settings.json):
    #   intro_enabled         — short greeting ("Hi, ich bin Jarvis …")
    #   intro_commands_enabled — list of in-story voice commands
    # Both are cached, so this is offline-safe and tokens-free.
    if speak and not text_mode:
        from storyteller_hardware.runtime import load_settings

        _st = load_settings(cfg)
        if _st.get("intro_enabled", True):
            prompts.play("intro", backend)
        if _st.get("intro_commands_enabled", True):
            prompts.play("intro_commands", backend)

    # --- wake-word gate + yes/no start question ---
    # After the boot greeting the device idles silently until the wake
    # word fires. Only then we ask whether to start a story — answering
    # "yes" opens the world selection menu. Anything else (no / unclear
    # after one re-ask / no answer) drops back to the wake-word wait,
    # so the device stays unobtrusive when nobody wants to play.

    def _yesno(text: str) -> str:
        """Return "yes" / "no" / "unclear" from a free-form answer."""
        lw = (text or "").strip().lower()
        if not lw:
            return "unclear"
        toks = [t.strip(",.!?;:") for t in lw.split()]
        if any(k in toks or any(k in t for t in toks)
               for k in NO_KEYWORDS):
            return "no"
        if any(k in toks or any(k in t for t in toks)
               for k in YES_KEYWORDS):
            return "yes"
        return "unclear"

    def _record_answer() -> str:
        leds.listen()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            wav = t.name
        backend.record_until_silence(wav)
        return stt.transcribe(wav).strip()

    def _await_start_yes() -> bool:
        """Block on wake-word, then ask the start question. Returns True
        once the player confirms; loops on no / unclear / silence."""
        while True:
            leds.idle()
            if not ww.listen_blocking():
                # Wake-word listener exited (e.g. shutdown) — give up.
                return False
            if speak:
                prompts.play("start_question", backend)
            answer = _record_answer()
            rp(f"[cyan][Du][/cyan] {answer}")
            verdict = _yesno(answer)
            if verdict == "yes":
                return True
            if verdict == "no":
                # Sofort still — kein Bestätigungston, zurück in Idle.
                continue
            # unclear -> ein einziger Nachfrage-Versuch
            if speak:
                prompts.play("start_question_repeat", backend)
            answer = _record_answer()
            rp(f"[cyan][Du][/cyan] {answer}")
            if _yesno(answer) == "yes":
                return True
            # Bei zweitem Miss zurück in Idle (Wake-Word-Wait).

    def _ask_play_mode() -> str:
        """Ask "existing world or new world?". Returns "existing", "create"
        or "" (unclear after one retry — caller should drop back to idle)."""
        if speak:
            prompts.play("mode_question", backend)
        answer = _record_answer()
        rp(f"[cyan][Du][/cyan] {answer}")
        cls = classify_play_mode(answer)
        if cls != "unclear":
            return cls
        if speak:
            prompts.play("mode_repeat", backend)
        answer = _record_answer()
        rp(f"[cyan][Du][/cyan] {answer}")
        cls = classify_play_mode(answer)
        return cls if cls in ("existing", "create") else ""

    def _design_world_interactively():
        """Voice-mode world design + generation. Returns the freshly
        generated ``World`` instance (saved to disk + RAG-able) on success,
        ``None`` on abort (cap exceeded, generation failed, player said
        "Geschichte beenden", or user picked "back to menu" after
        generation). The caller treats ``None`` as "drop back to the world
        selection / wake-word idle"."""
        from types import SimpleNamespace

        from storyteller_core.worlds.schema import FXPreset
        from storyteller_voice.waitloop import WaitLoop

        loc = norm(cfg.general.locale)
        loc_cmds = CMD_KEYWORDS[loc]
        # Fake world-shaped object for the _say helper (which dereferences
        # world.wait_sound + world.narration_style) — we don't have a real
        # World yet because the player is just designing it.
        design_stub = SimpleNamespace(
            wait_sound=cfg.story.world_gen_wait_sound,
            narration_style="ruhig, freundlich, neutral",
            fx_preset=FXPreset(),
        )
        design_fx = VoiceFX(cfg, design_stub.fx_preset)
        interview = WorldDesignInterview(cfg, locale=loc)

        if speak:
            prompts.play("design_intro", backend)

        # Hand-crafted first question — saves one LLM call and keeps the
        # opener predictable.
        first_q = interview.opening_question()
        interview.add_question(first_q)
        _say(cfg, design_stub, backend, tts, design_fx, leds,
             (lambda q=first_q: q), speak=speak)

        reminder_played = False
        while True:
            leds.listen()
            with tempfile.NamedTemporaryFile(suffix=".wav",
                                              delete=False) as t:
                wav = t.name
            backend.record_until_silence(wav)
            answer = stt.transcribe(wav).strip()
            rp(f"[cyan][Du][/cyan] {answer}")
            if not answer:
                # silence: re-ask the previous question briefly
                _say(cfg, design_stub, backend, tts, design_fx, leds,
                     (lambda q=first_q: q), speak=speak)
                continue
            low = answer.lower()
            toks = [t.strip(",.!?;:") for t in low.split()]
            # Abort to wake-word idle
            if matches_end_story(low, loc):
                log.info("design interview aborted by player")
                return None
            # Generate trigger
            if toks and toks[0] in loc_cmds["generate"]:
                break
            # Otherwise: record + ask next question
            interview.add_user(answer)
            n_pairs = sum(1 for m in interview.history
                          if m["role"] == "user")
            try:
                q = interview.next_question()
            except DailyCapExceeded:
                if speak:
                    prompts.play("daily_cap_pause", backend)
                return None
            interview.add_question(q)
            # One-shot reminder once the player has answered enough
            # questions for the picture to be dense.
            if (n_pairs >= cfg.story.world_design_reminder_after
                    and not reminder_played):
                if speak:
                    prompts.play("design_reminder", backend)
                reminder_played = True
            _say(cfg, design_stub, backend, tts, design_fx, leds,
                 (lambda q=q: q), speak=speak)
            if n_pairs >= cfg.story.world_design_max_turns:
                log.info("design max turns reached — forcing generation")
                break
            first_q = q  # used as repeat target on next silent answer

        # Persist transcript first — survives a generation crash.
        try:
            tpath = interview.save_transcript()
            log.info("world-design transcript: %s", tpath)
        except Exception as exc:
            log.warning("transcript save failed: %r", exc)

        # GENERATION (1–3 minutes) under the neutral ambient.
        if speak:
            prompts.play("generating_wait", backend)
        try:
            with WaitLoop(cfg, backend, cfg.story.world_gen_wait_sound,
                          leds):
                world = generate_world(
                    cfg, interview.as_brief(),
                    progress=lambda m: log.info("gen: %s", m))
            save_world(cfg, world)
        except DailyCapExceeded:
            if speak:
                prompts.play("daily_cap_pause", backend)
            return None
        except Exception as exc:
            log.warning("world generation failed: %r", exc)
            if speak:
                prompts.play("generated_fail", backend)
            return None

        # Index the new world into the RAG store immediately so the
        # narrator can retrieve from it on the very first turn.
        try:
            from storyteller_core.story.rag import RAG
            RAG(cfg).index_world(world, force=True, locale=loc)
        except Exception as exc:
            log.warning("post-gen RAG indexing failed: %r", exc)

        # Confirmation + decision.
        display = world.display_name or world.name
        confirm = DESIGN_PROMPTS[loc]["generated_ok"].format(name=display)
        _say(cfg, design_stub, backend, tts, design_fx, leds,
             (lambda c=confirm: c), speak=speak)
        if speak:
            prompts.play("generated_confirm_ask", backend)
        ans = _record_answer()
        rp(f"[cyan][Du][/cyan] {ans}")
        lw = ans.lower()
        # "Starten" / "los" / "yes" → start the just-generated world.
        # Anything else (incl. "Auswahl" / "Menu") → caller falls back
        # to the world menu; the new world is on disk so it'll show up.
        if any(k in lw for k in ("start", "los", "begin", "go",
                                  "spielen", "play")) \
                or _yesno(ans) == "yes":
            return world
        return None

    def _play_one_story() -> str:
        """Run ONE story session.

        Returns ``"shutdown"`` (player asked to power the appliance
        off — outer loop says goodbye + poweroff) or ``"next_story"``
        (player asked to end the current story / pick a new one —
        outer loop reruns the world-selection flow). Plain fallthrough
        of the inner loop (shouldn't happen) also counts as
        ``"next_story"`` so the device stays usable."""
        # The inner loop hot-reloads cfg / stt / tts each idle tick so
        # admin changes pick up live; declare them nonlocal so the
        # references BEFORE that re-assignment (VoiceMenu, opening _say)
        # still see the outer cmd_run values instead of "referenced
        # before assignment".
        nonlocal cfg, stt, tts
        # Hot-reload now (before the design / menu phase) so admin /
        # .env edits made between stories pick up.
        cfg = load_config()
        stt = get_stt(cfg)
        tts = get_tts(cfg)
        # --- world selection ---
        world = None
        wid = args.world
        if wid:
            world = load_world(cfg, wid)
        elif text_mode or ww is None:
            world = load_world(cfg, "sternenfahrt")
        else:
            if not _await_start_yes():
                rp("[dim]Wake-Word-Listener beendet — Abbruch.[/dim]")
                return "shutdown"
            mode = _ask_play_mode()
            if mode == "create":
                # Voice-mode world generation. _design_world_interactively
                # runs the interview, calls generate_world under the
                # neutral wait-sound, and asks "start now or back to
                # menu". On None we fall through to the regular menu so
                # the just-saved world (if any) can be picked there.
                world = _design_world_interactively()
                if world is None:
                    return "next_story"
            elif mode == "existing":
                sel = VoiceMenu(cfg, backend, prompts, stt, leds, ww,
                                speak).run()
                wid = sel.get("world_id") or "sternenfahrt"
                world = load_world(cfg, wid)
            else:
                # unclear after retry → back to wake-word idle
                return "next_story"
        rp(f"[bold]Welt:[/bold] {world.name}")

        thread = args.thread or f"pi-{world.id}"
        if args.new:
            thread = f"{thread}-{int(time.time())}"
            rp(f"[dim]Neue Sitzung: thread_id = {thread}[/dim]")

        engine = _build_engine(cfg, world, use_rag=not args.no_rag,
                               thread_id=thread)
        fx = VoiceFX(cfg, world.fx_preset)

        def _arm() -> threading.Event:
            """Fresh interrupt event registered with the interrupt-button long-
            press handler so it can abort the upcoming narration."""
            ev = threading.Event()
            _current_interrupt[0] = ev
            return ev

        def _disarm() -> None:
            _current_interrupt[0] = None

        def _say_barge(gen) -> tuple[str, bool]:
            """Narrate with optional button long-press barge-in. Returns
            (text, interrupted). On long-press the playback aborts AND
            `menu_requested` is set so the caller opens the system menu;
            short-press toggles pause/resume of the active aplay and does
            NOT set `interrupted`."""
            ev = _arm()
            try:
                text = _say(cfg, world, backend, tts, fx, leds, gen,
                            speak=speak, interrupt=ev)
            finally:
                _disarm()
            interrupted = ev.is_set()
            if interrupted:
                rp("[yellow]… unterbrochen — ich höre …[/yellow]")
            return text, interrupted

        def _first_narration() -> str:
            snap = engine.state()
            if snap.get("memory"):
                # resume a SAVED game: short spoken recap (was bisher geschah +
                # aktuelle Lage). recap() is read-only and falls back to the last
                # narration if the LLM call fails.
                return engine.recap() or engine.last_narration() \
                    or engine.turn(RESTORE_DIRECTIVE[loc])
            return engine.opening()

        # Bridge the opening generation with the wait sound (audio mode only).
        # _say keeps the wait loop alive across BOTH the LLM call and the first
        # TTS chunk render, so the player hears continuous ambience until the
        # narrator actually starts speaking — no silent gap.
        opening_interrupted = False
        if speak:
            ev = _arm()
            try:
                first = _say(cfg, world, backend, tts, fx, leds,
                             _first_narration, speak=True, interrupt=ev)
            finally:
                _disarm()
            rp(f"[green][Erzähler][/green] {first}")
            opening_interrupted = ev.is_set()
            if opening_interrupted:
                rp("[yellow]… unterbrochen — ich höre …[/yellow]")
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
                    ("end_story", "Geschichte beenden, zurück zur "
                                   "Welt-Auswahl / end the story, back "
                                   "to the world menu"),
                    ("shutdown", "ausschalten, Pi herunterfahren / "
                                  "shut down the device"),
                    ("undo", "Spielzug zurück / undo the last turn"),
                    ("reset", "Welt zurücksetzen, Spielstand löschen, von vorn "
                              "beginnen / reset this world (delete progress)"),
                    ("audio", "Audio/Bluetooth umschalten / switch audio output"),
                    ("intro", "Einführung an oder aus / toggle the intro"),
                    ("commands", "Befehls-Info an oder aus / toggle the "
                                  "commands info"),
                    ("close", "Menü schließen / close menu and continue")]
            ch = _classify(cfg, pick, opts)
            if ch == "unknown":
                lw = pick.lower()
                if any(k in lw for k in ("zurücksetz", "zurucksetz", "reset",
                                         "von vorn", "von vorne", "neu beginn",
                                         "lösch", "loesch")):
                    ch = "reset"
                elif any(k in lw for k in ("geschichte beenden",
                                            "geschichte ende",
                                            "end story", "story over",
                                            "weltauswahl", "welt auswahl",
                                            "world menu")):
                    ch = "end_story"
                elif any(k in lw for k in ("ausschalten", "ausmachen",
                                            "herunterfahr", "shutdown",
                                            "shut down", "power off",
                                            "poweroff", "tschüss",
                                            "tschüs", "goodbye")):
                    ch = "shutdown"
                elif any(k in lw for k in ("beend", "schluss", "aufhör")):
                    # Bare "beenden / schluss" without "geschichte" → treat as
                    # shutdown for backwards compatibility with the old menu.
                    ch = "shutdown"
                elif any(k in lw for k in ("zurück", "zuruck", "undo",
                                           "rückgäng", "ruckgang")):
                    ch = "undo"
                elif any(k in lw for k in ("audio", "bluetooth", "blue tooth")):
                    ch = "audio"
                elif any(k in lw for k in ("befehl", "kommando", "command",
                                            "commands")):
                    ch = "commands"
                elif any(k in lw for k in ("einführ", "einfuehr", "intro",
                                           "einleitung", "tutorial")):
                    ch = "intro"
                elif any(k in lw for k in ("speich", "save")):
                    ch = "save"
                else:
                    ch = "close"

            def _confirm(prompt_id: str) -> bool:
                """Spoken yes/no safety check. Unclear answer counts as NO."""
                if speak:
                    prompts.play(prompt_id, backend)
                else:
                    rp(f"[dim]{prompt_id}: ja/nein?[/dim]")
                if text_mode:
                    ans = input("ja/nein: ").strip().lower()
                else:
                    leds.listen()
                    with tempfile.NamedTemporaryFile(suffix=".wav",
                                                     delete=False) as t:
                        w = t.name
                    backend.record_until_silence(w)
                    ans = stt.transcribe(w).strip().lower()
                rp(f"[cyan][Du][/cyan] {ans}")
                return any(k in ans for k in (
                    "ja", "jo", "jap", "klar", "mach", "bestätig", "bestatig",
                    "yes", "yeah", "yep", "sure", "okay", "ok"))

            if ch == "shutdown":
                return "shutdown"
            if ch == "end_story":
                return "end_story"
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
            elif ch == "commands":
                from storyteller_hardware.runtime import (
                    load_settings,
                    save_settings,
                )

                st = load_settings(cfg)
                new = not st.get("intro_commands_enabled", True)
                st["intro_commands_enabled"] = new
                save_settings(cfg, st)
                cmsg = "commands_intro_on" if new else "commands_intro_off"
                prompts.play(cmsg, backend) if speak \
                    else rp(f"[dim]({cmsg})[/dim]")
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
                if not _confirm("confirm_undo"):
                    prompts.play("cancelled", backend) if speak \
                        else rp("[dim](abgebrochen)[/dim]")
                    last = engine.last_narration()
                    if last:
                        _say(cfg, world, backend, tts, fx, leds, (lambda: last),
                             speak=speak)
                    return None
                last = engine.undo_last()
                prompts.play("undone", backend) if speak \
                    else rp("[dim](Spielzug zurück)[/dim]")
                if last:
                    _say(cfg, world, backend, tts, fx, leds, (lambda: last),
                         speak=speak)
                return None
            elif ch == "reset":
                if not _confirm("confirm_reset"):
                    prompts.play("cancelled", backend) if speak \
                        else rp("[dim](abgebrochen)[/dim]")
                    last = engine.last_narration()
                    if last:
                        _say(cfg, world, backend, tts, fx, leds, (lambda: last),
                             speak=speak)
                    return None
                # Wipe this world's saved progress, then start a fresh opening.
                # Mirror the menu's fresh-start cadence:
                #   1) world_reset prompt        ("Diese Welt wurde zurückgesetzt.")
                #   2) world_<wid> prompt        ("Sternenfahrt. Du bist ...")
                #   3) starting prompt           ("Die Geschichte beginnt.")
                #   4) generate + speak opening  (LLM call under the wait sound)
                # Without 2+3 the user just heard "reset" followed by a long
                # silence (LLM rendering) and then the in-medias-res story —
                # they couldn't tell the world had been re-introduced.
                res = engine.reset()
                log.info("world reset: %s", res)
                if speak:
                    prompts.play("world_reset", backend)
                    prompts.play(f"world_{world.id}", backend)
                    prompts.play("starting", backend)
                else:
                    rp("[dim](Welt zurückgesetzt)[/dim]")
                # _say handles the wait sound across both LLM and first TTS
                # chunk — no extra WaitLoop needed here.
                opening = _say(cfg, world, backend, tts, fx, leds,
                               engine.opening, speak=speak)
                if opening:
                    rp(f"[green][Erzähler][/green] {opening}")
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
        # A barge-in always leads straight to listening (even if follow-up is off).
        pending_follow = follow_enabled or opening_interrupted
        hinted = False                     # wake_hint announced ONCE per idle
        cap_pause_announced = False        # daily-cap pause prompt: once per idle
        try:
            while True:
                leds.idle()
                # Pick up admin/.env changes to STT/TTS (model + endpoint) without
                # a restart: rebuild from a fresh config each idle cycle. Cheap —
                # the underlying OpenAI clients are cached per (key, base_url).
                cfg = load_config()
                stt = get_stt(cfg)
                tts = get_tts(cfg)
                # Daily cost cap: refuse new turns when the day's spend is
                # exhausted. The previously saved state is untouched — when an
                # admin resets the cap we pick up exactly where we left off.
                ledger = CostLedger(cfg)
                if ledger.is_over_daily_cap():
                    if speak and not cap_pause_announced:
                        prompts.play("daily_cap_still", backend)
                        cap_pause_announced = True
                    time.sleep(5)
                    pending_follow = False
                    continue
                cap_pause_announced = False
                # If a long-press fired since the last iteration (typically:
                # during the previous narration; the button handler also armed
                # `menu_requested` so we get here even if the press happened at
                # idle) open the spoken system menu directly.
                if menu_requested.is_set():
                    menu_requested.clear()
                    rc = _sysmenu()
                    if rc == "shutdown":
                        return "shutdown"
                    if rc == "end_story":
                        return "next_story"
                    pending_follow = follow_enabled
                    continue
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
                    # ----- voice command: "Vermerken: …" -----
                    # If the player STARTS the utterance with a note keyword,
                    # we strip it and persist the rest as a UserNote (player-
                    # introduced world fact). The note also lands in RAG so
                    # the narrator can use it from the very next turn.
                    if toks and toks[0] in cmd_kw["note"]:
                        rest = said.split(None, 1)[1].lstrip(":,. ") \
                            if len(said.split(None, 1)) > 1 else ""
                        np = NOTE_PROMPTS[norm(cfg.general.locale)]
                        if not rest.strip():
                            empty_msg = np["empty"]
                            _say(cfg, world, backend, tts, fx, leds,
                                 (lambda m=empty_msg: m), speak=speak)
                        else:
                            try:
                                note = create_user_note(
                                    cfg, world.id, norm(cfg.general.locale),
                                    rest, thread_id=engine.thread_id,
                                    rag=engine.ctx.rag)
                                kind_label = np["kind_label"].get(
                                    note.kind, note.kind)
                                confirm = np["saved"].format(
                                    name=note.name, kind=kind_label)
                                log.info("user-note saved: %s (%s)",
                                         note.name, note.kind)
                                _say(cfg, world, backend, tts, fx, leds,
                                     (lambda c=confirm: c), speak=speak)
                            except DailyCapExceeded:
                                if speak:
                                    prompts.play("daily_cap_pause", backend)
                            except Exception as exc:
                                log.warning("user-note failed: %r", exc)
                                short_msg = np["saved_short"]
                                _say(cfg, world, backend, tts, fx, leds,
                                     (lambda m=short_msg: m),
                                     speak=speak)
                        pending_follow = follow_enabled
                        continue
                    if toks and len(toks) <= 3 and any(
                            t in cmd_kw["menu"] for t in toks):
                        rc = _sysmenu()
                        if rc == "shutdown":
                            return "shutdown"
                        if rc == "end_story":
                            return "next_story"
                        pending_follow = follow_enabled
                        continue
                    # "Geschichte beenden" / "end story" — save (auto-saved
                    # every turn anyway) + back to the wake-word idle / world
                    # menu. Does NOT power the device off.
                    if matches_end_story(low, norm(cfg.general.locale)):
                        if speak:
                            try:
                                prompts.play("story_ended", backend)
                            except Exception:
                                pass
                        log.info("end-story command: returning to world menu")
                        return "next_story"
                    # Shutdown keywords: "schluss" / "ausschalten" / "beenden"
                    # as a SHORT (1–3 token) utterance. Mid-sentence
                    # occurrences are ignored so a long player input that
                    # happens to contain "beenden" can't kill the device.
                    if toks and len(toks) <= 3 and any(
                            t in cmd_kw["shutdown"] for t in toks):
                        log.info("shutdown command received")
                        return "shutdown"
                    try:
                        reply, interrupted = _say_barge(
                            lambda s=said: engine.turn(s))
                    except DailyCapExceeded as exc:
                        log.warning("Daily cost cap reached — pausing story: %r",
                                    exc)
                        if speak:
                            prompts.play("daily_cap_pause", backend)
                        pending_follow = False
                        continue
                    rp(f"[green][Erzähler][/green] {reply}")
                    # One-shot approach warning when today's spend crosses the
                    # configured percentage of the daily cap.
                    if speak and ledger.is_approaching_daily_cap() \
                            and not ledger.warned_today():
                        prompts.play("daily_cap_warning", backend)
                        ledger.mark_warned_today()
                    # On barge-in: listen right away (no wake word) so the player
                    # can steer; the classify step below decides menu vs. story.
                    pending_follow = True if interrupted else follow_enabled
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
            return "shutdown"
        return "next_story"
    try:
        while True:
            rc = _play_one_story()
            if rc == "shutdown":
                if speak:
                    try:
                        prompts.play("goodbye", backend)
                    except Exception:
                        pass
                import subprocess
                try:
                    subprocess.run(
                        ["sudo", "-n", "systemctl", "poweroff"],
                        check=False, timeout=5)
                except Exception as exc:
                    log.warning("shutdown failed: %r", exc)
                break
            # rc == "next_story": outer loop iterates, wake-word gate
            # opens a fresh world-selection round.
    finally:
        interrupt_btn.close()
        shutdown_btn.close()
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
