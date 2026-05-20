"""storyteller-cli — text-mode REPL against the LangGraph story engine.

Commands:
  chat   [--world ID] [--thread NAME] [--new] [--locale de|en]
  info
  seed
  worlds                          list available worlds
  history [--thread NAME]         show checkpoint history for a thread

Voice and admin live in other apps (storyteller-pi, storyteller-web-admin).
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from storyteller_core.config import load_config
from storyteller_core.story.engine import StoryEngine
from storyteller_core.worlds.registry import all_world_ids, load_world


console = Console()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _print_narration(text: str) -> None:
    if not text:
        return
    console.print(Panel(text, border_style="cyan", padding=(1, 2)))


def _pick_world(cfg, requested: str | None) -> str:
    ids = sorted(all_world_ids(cfg))
    if not ids:
        console.print("[red]Keine Welten gefunden. Erst `storyteller-cli seed`.[/red]")
        sys.exit(2)
    if requested:
        if requested not in ids:
            console.print(f"[red]Welt '{requested}' nicht gefunden. "
                          f"Verfügbar: {', '.join(ids)}[/red]")
            sys.exit(2)
        return requested
    if len(ids) == 1:
        return ids[0]
    console.print("[bold]Welten:[/bold]")
    for i, wid in enumerate(ids, 1):
        console.print(f"  {i}. {wid}")
    while True:
        choice = console.input("Wähle Nummer: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(ids):
            return ids[int(choice) - 1]


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_chat(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.locale:
        cfg.general.locale = args.locale

    world_id = _pick_world(cfg, args.world)
    world = load_world(cfg, world_id)

    thread = args.thread or f"cli-{world_id}"
    if args.new:
        # Force a fresh branch: use a new thread id derived from timestamp.
        import time
        thread = f"{thread}-{int(time.time())}"
        console.print(f"[dim]Neue Session: thread_id = {thread}[/dim]")

    # Optional RAG
    rag = None
    if not args.no_rag:
        try:
            from storyteller_core.story.rag import WorldRAG
            rag = WorldRAG(cfg)
        except Exception as exc:
            console.print(f"[yellow]RAG nicht verfügbar ({exc}), weiter ohne.[/yellow]")

    engine = StoryEngine(cfg, world, rag=rag, thread_id=thread)

    # If thread is empty (no prior memory), trigger the opening.
    snap = engine.state()
    if not snap.get("memory"):
        console.print("[dim]…Eröffnung wird vorbereitet…[/dim]")
        _print_narration(engine.opening())
    else:
        console.print("[dim]Vorherige Sitzung fortgesetzt. Letzte Erzählung:[/dim]")
        _print_narration(engine.last_narration())

    console.print("[dim]Befehle: /undo, /state, /quit[/dim]")
    while True:
        try:
            line = console.input("[bold green]Du[/bold green] › ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]bis bald.[/dim]")
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            return 0
        if line == "/undo":
            console.print("[dim]…rückgängig…[/dim]")
            _print_narration(engine.undo_last())
            continue
        if line == "/state":
            s = engine.state()
            console.print({
                "thread": thread,
                "memory_len": len(s.get("memory") or []),
                "substory": (s.get("substory") or {}).get("title"),
                "macro_index": s.get("macro_index"),
                "beat_turns": s.get("beat_turns"),
                "cost": s.get("cost"),
                "synopsis_chars": len(s.get("synopsis") or ""),
            })
            continue
        console.print("[dim]…denke nach…[/dim]")
        try:
            reply = engine.turn(line)
        except Exception as exc:
            console.print(f"[red]Fehler: {exc!r}[/red]")
            continue
        _print_narration(reply)


def cmd_info(_args: argparse.Namespace) -> int:
    cfg = load_config()
    console.print({
        "story_llm": cfg.models.story_llm,
        "planner_llm": cfg.models.planner,
        "gen_llm": cfg.models.gen,
        "stt": cfg.models.stt,
        "tts": cfg.models.tts,
        "tts_voice": cfg.models.tts_voice,
        "embedding": cfg.models.embedding,
        "locale": cfg.general.locale,
        "audio.backend": cfg.audio.backend,
        "cost_cap_usd_per_session": cfg.story.cost_cap_usd_per_session,
    })
    return 0


def cmd_worlds(_args: argparse.Namespace) -> int:
    cfg = load_config()
    for wid in sorted(all_world_ids(cfg)):
        w = load_world(cfg, wid)
        console.print(f"  {wid:20s}  {w.name}  ({w.genre})")
    return 0


def cmd_seed(_args: argparse.Namespace) -> int:
    """Write built-in seed worlds into data/worlds/ if not already present."""
    from pathlib import Path

    from storyteller_core.config import ROOT
    from storyteller_core.worlds.seed import SEED_WORLDS

    out = ROOT / "data" / "worlds"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for w in SEED_WORLDS:
        target = out / f"{w.id}.json"
        if target.exists():
            console.print(f"  [dim]exists  {target.name}[/dim]")
            continue
        target.write_text(w.model_dump_json(indent=2), encoding="utf-8")
        written.append(target.name)
        console.print(f"  [green]wrote   {target.name}[/green]")
    console.print(f"[bold]{len(written)} new world(s) seeded.[/bold]")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    cfg = load_config()
    world_id = _pick_world(cfg, args.world)
    world = load_world(cfg, world_id)
    thread = args.thread or f"cli-{world_id}"
    engine = StoryEngine(cfg, world, thread_id=thread)
    n = 0
    for snap in engine.history():
        n += 1
        cp_id = snap.config.get("configurable", {}).get("checkpoint_id", "?")
        mem = snap.values.get("memory") if snap.values else None
        last = ""
        if mem:
            for m in reversed(mem):
                if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                    last = m["content"][:60].replace("\n", " ")
                    break
        console.print(f"  [{cp_id[-12:]}]  {last}")
    console.print(f"[dim]{n} checkpoint(s)[/dim]")
    return 0


# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="storyteller-cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    pchat = sub.add_parser("chat", help="text REPL against the story engine")
    pchat.add_argument("--world", help="world id (e.g. sternenfahrt)")
    pchat.add_argument("--thread", help="session id (default: cli-<world>)")
    pchat.add_argument("--new", action="store_true",
                       help="start a fresh session (new thread id)")
    pchat.add_argument("--locale", choices=("de", "en"))
    pchat.add_argument("--no-rag", action="store_true",
                       help="disable RAG retrieval")
    pchat.set_defaults(func=cmd_chat)

    pinfo = sub.add_parser("info", help="show effective configuration")
    pinfo.set_defaults(func=cmd_info)

    pworlds = sub.add_parser("worlds", help="list known worlds")
    pworlds.set_defaults(func=cmd_worlds)

    pseed = sub.add_parser("seed", help="write built-in worlds to data/worlds/")
    pseed.set_defaults(func=cmd_seed)

    phist = sub.add_parser("history",
                            help="dump checkpoint history for a thread")
    phist.add_argument("--world", help="world id")
    phist.add_argument("--thread", help="session id")
    phist.set_defaults(func=cmd_history)

    return p


def main() -> int:
    args = _build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
