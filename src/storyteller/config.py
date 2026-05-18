"""Configuration: reads config/config.toml + .env. All model names editable."""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]  # /home/pi/storyteller


class ModelsCfg(BaseModel):
    story_llm: str = "gpt-5.4-mini"
    stt: str = "gpt-4o-mini-transcribe"
    tts: str = "gpt-4o-mini-tts"
    tts_voice: str = "ballad"
    embedding: str = "text-embedding-3-small"
    embedding_dim: int = 512
    llm_temperature: float = 0.9


class STTCfg(BaseModel):
    provider: str = "openai"  # openai | local_whisper (Phase 10)
    language: str = "de"


class TTSCfg(BaseModel):
    provider: str = "openai"  # openai | local (Phase 10)
    format: str = "pcm"
    sample_rate: int = 24000


class GeneralCfg(BaseModel):
    locale: str = "de"  # de | en


class RuntimeCfg(BaseModel):
    profile: str = "auto"  # auto | pi | pc


class AudioCfg(BaseModel):
    backend: str = "auto"  # auto | alsa_softvol | portable | pipewire
    output_alsa_pcm: str = "plug:respeaker_softvol"
    input_alsa_pcm: str = "respeaker_capture"
    sd_output_device: str = ""
    mixer_card: str = "ArrayUAC10"
    mixer_control: str = "Master"
    default_volume_pct: int = 15
    input_sample_rate: int = 16000
    pw_sink: str = ""


class WakeWordCfg(BaseModel):
    engine: str = "openwakeword"
    model: str = ""
    threshold: float = 0.5
    # After the narrator speaks, listen once WITHOUT the wake word so the
    # player can reply directly; only after silence is the wake word needed.
    follow_up: bool = True


class FXCfg(BaseModel):
    enabled: bool = True
    reverb_room_size: float = 0.55
    reverb_damping: float = 0.55
    reverb_wet_level: float = 0.18
    reverb_dry_level: float = 0.85
    distortion_drive_db: float = 0.0


class StoryCfg(BaseModel):
    short_term_memory_turns: int = 12
    rag_top_k: int = 4
    cost_cap_usd_per_session: float = 2.0
    max_substory_beats: int = 5
    default_complexity: str = "standard"  # simple|standard|rich (world overrides)
    dynamic_event_prob: float = 0.15
    dynamics_in_planning: bool = True
    narration_guidance: str = (
        "Erzähle EINFACH und KLAR fürs Zuhören: höchstens 4–6 kurze Sätze. "
        "Pro Antwort nur EINE Situation und höchstens ein bis zwei neue "
        "Namen/Dinge. Keine Aufzählungen, keine Detailflut, kein Vorgriff auf "
        "mehrere Handlungsstränge. Schließe mit EINER konkreten, offenen Lage "
        "oder Frage, auf die der Spieler direkt reagieren kann. Ruhig und "
        "bildhaft, aber sparsam."
    )


class CostCfg(BaseModel):
    enforce: bool = True
    usd_per_1m_input: float = 0.30
    usd_per_1m_output: float = 1.20
    usd_per_1m_embedding: float = 0.02


class LoggingCfg(BaseModel):
    level: str = "INFO"
    file: str = "data/storyteller.log"


class WebCfg(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class ModerationCfg(BaseModel):
    enabled: bool = True
    model: str = "omni-moderation-latest"
    default_threshold: float = 0.5  # block a category at/above this score
    # Per-category overrides live in data/moderation.json (admin-editable).


class NetcheckCfg(BaseModel):
    enabled: bool = True
    iface: str = "wlan0"
    timeout_s: int = 45            # wait this long for Wi-Fi at boot
    ap_ssid: str = "storyteller-wifi"
    ap_password: str = "storyteller"   # WPA2, >= 8 chars; change me
    portal_host: str = "10.42.0.1"     # NM shared-mode gateway
    web_port: int = 80


class VoicePromptsCfg(BaseModel):
    enabled: bool = True
    allow_live_fallback: bool = True
    voice: str = ""  # empty => models.tts_voice


class PathsCfg(BaseModel):
    worlds_dir: str = "data/worlds"
    saves_dir: str = "data/saves"
    rag_db: str = "data/rag.db"
    wait_sounds_dir: str = "data/wait_sounds"
    voice_prompts_dir: str = "data/voice_prompts"


class Config(BaseModel):
    general: GeneralCfg = GeneralCfg()
    runtime: RuntimeCfg = RuntimeCfg()
    models: ModelsCfg = ModelsCfg()
    stt: STTCfg = STTCfg()
    tts: TTSCfg = TTSCfg()
    audio: AudioCfg = AudioCfg()
    wakeword: WakeWordCfg = WakeWordCfg()
    fx: FXCfg = FXCfg()
    story: StoryCfg = StoryCfg()
    cost: CostCfg = CostCfg()
    logging: LoggingCfg = LoggingCfg()
    web: WebCfg = WebCfg()
    moderation: ModerationCfg = ModerationCfg()
    netcheck: NetcheckCfg = NetcheckCfg()
    voice_prompts: VoicePromptsCfg = VoicePromptsCfg()
    paths: PathsCfg = PathsCfg()

    openai_api_key: str = ""

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p

    @property
    def root(self) -> Path:
        return ROOT


@lru_cache
def load_config(config_path: str | None = None) -> Config:
    """Load configuration (cached). config_path optionally overrides."""
    load_dotenv(ROOT / ".env")
    cfg_file = Path(config_path) if config_path else ROOT / "config" / "config.toml"
    data: dict = {}
    if cfg_file.exists():
        data = tomllib.loads(cfg_file.read_text())
    cfg = Config(**data)
    cfg.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    return cfg
