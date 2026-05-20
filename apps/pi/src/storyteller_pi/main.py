"""Storyteller Pi entry point.

Voice loop with ReSpeaker LEDs + wake word + ALSA. Phase 3 fills this in
using `storyteller_core` (LangGraph engine), `storyteller_voice` (STT/TTS/FX),
and `storyteller_hardware` (audio backends, LED ring, voice menu).
"""

from __future__ import annotations


def main() -> int:
    raise SystemExit(
        "storyteller-pi is being rebuilt against the new LangGraph engine. "
        "See AGENTS.md."
    )
