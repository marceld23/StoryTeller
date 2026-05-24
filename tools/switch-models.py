#!/usr/bin/env python3
"""Switch the active `data/models.json` between local and OpenAI variants.

Two pre-baked variants live alongside the active config:
    data/models_local.json    — qwen / faster-whisper / XTTS / bge-m3
    data/models_openai.json   — gpt-5.4 / gpt-4o-mini-tts / -transcribe / text-embedding-3-small

`models.json` is the file actually consumed by `load_config`; this script
just copies one of the variants over it. The running narrator picks the
change up on its next idle tick (load_config caches by file mtime), so
no service restart is necessary.

Usage:
    tools/switch-models.py            # show current state
    tools/switch-models.py status     # same
    tools/switch-models.py local      # activate local variant
    tools/switch-models.py openai     # activate OpenAI variant
    tools/switch-models.py <variant> --rebuild
                                      # also force-rebuild the voice prompt
                                      # cache right now (needs .venv python)

Use the bundled shell wrapper `tools/switch-models` if you want it to
auto-use the project's virtualenv (the --rebuild path needs it).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ACTIVE = DATA / "models.json"
VARIANTS: dict[str, Path] = {
    "local": DATA / "models_local.json",
    "openai": DATA / "models_openai.json",
}


def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def current_variant() -> str:
    active = _read_json(ACTIVE)
    if active is None:
        return "missing"
    for name, p in VARIANTS.items():
        v = _read_json(p)
        if v is not None and v == active:
            return name
    return "custom"


def _one_line(p: Path) -> str:
    d = _read_json(p) or {}
    ep = (d.get("story_endpoint") or {}).get("base_url") or "OpenAI default"
    return (f"story={d.get('story_llm', '?')}, "
            f"tts={d.get('tts', '?')}/{d.get('tts_voice', '?')}, "
            f"stt={d.get('stt', '?')}, "
            f"embed={d.get('embedding', '?')}  "
            f"[chat endpoint: {ep}]")


def cmd_status() -> int:
    cur = current_variant()
    print(f"active variant: {cur}")
    if ACTIVE.exists():
        print(f"  {ACTIVE.name}: {_one_line(ACTIVE)}")
    else:
        print(f"  {ACTIVE.name}: (missing — copy a variant to activate it)")
    print()
    for name, p in VARIANTS.items():
        mark = "*" if cur == name else " "
        if p.exists():
            print(f"  [{mark}] {name:<7} ({p.name}): {_one_line(p)}")
        else:
            print(f"  [ ] {name:<7} ({p.name}): (file missing)")
    return 0


def cmd_switch(target: str) -> int:
    src = VARIANTS[target]
    if not src.exists():
        print(f"error: {src} does not exist", file=sys.stderr)
        return 2
    if current_variant() == target:
        print(f"already on '{target}' — nothing to do")
        return 0
    shutil.copy(src, ACTIVE)
    print(f"switched: {ACTIVE.name} <- {src.name}")
    print(f"  {_one_line(ACTIVE)}")
    print()
    print("  the running narrator will pick this up on its next idle tick")
    print("  (no restart needed). voice prompts auto-rebuild on the next")
    print("  system message; pass --rebuild to render them now.")
    return 0


def cmd_rebuild_prompts() -> int:
    try:
        from storyteller_core.config import load_config
        from storyteller_voice.prompts import VoicePromptCache
    except ImportError as exc:
        print(f"error: cannot import project packages ({exc}).",
              file=sys.stderr)
        print("  re-run via the project venv, e.g. "
              ".venv/bin/python tools/switch-models.py "
              "<variant> --rebuild", file=sys.stderr)
        return 3
    load_config.cache_clear()
    cfg = load_config()
    print(f"  TTS now: {cfg.models.tts} voice={cfg.models.tts_voice} "
          f"endpoint={cfg.models.tts_endpoint.base_url or 'OpenAI'}")
    for loc in ("de", "en"):
        cache = VoicePromptCache(cfg, locale=loc)
        built = cache.build(force=True)
        print(f"  [{loc}] re-rendered {len(built)} prompts")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Switch active models.json between local / OpenAI")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "local", "openai"])
    p.add_argument("--rebuild", action="store_true",
                   help="also force-rebuild the voice prompt cache "
                        "(needs the project venv)")
    args = p.parse_args()

    if args.action == "status":
        return cmd_status()

    rc = cmd_switch(args.action)
    if rc != 0:
        return rc
    if args.rebuild:
        print("rebuilding voice prompts…")
        return cmd_rebuild_prompts()
    return 0


if __name__ == "__main__":
    sys.exit(main())
