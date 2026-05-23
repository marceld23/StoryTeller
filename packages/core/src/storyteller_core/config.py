"""Configuration: reads config/config.toml + .env. All model names editable."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "packages").is_dir():
            return parent
    return here.parents[4]


ROOT = _find_repo_root()


class Endpoint(BaseModel):
    """An OpenAI-compatible API endpoint. Empty = OpenAI defaults
    (api.openai.com + OPENAI_API_KEY). Set base_url (incl. host:port and
    /v1, e.g. http://192.168.1.50:8000/v1) to use a self-hosted server
    (vLLM / llama.cpp / Ollama / LM Studio). api_key is sent as the bearer
    token (many local servers accept any value)."""
    base_url: str = ""
    api_key: str = ""


class ModelsCfg(BaseModel):
    story_llm: str = "gpt-5.4-mini"            # narrator (quality matters)
    planner_llm: str = ""                      # architect+summarizer; ""=story_llm
    # One-shot, high-stakes calls that build NEW content (world generation
    # from a prompt, world-piece suggestions in the admin UI). Defaults to
    # the big "gpt-5.4" — these calls are rare; structural quality pays
    # off for every subsequent session.
    gen_llm: str = "gpt-5.4"
    # Narration "gate" — a small/fast LLM that decides per turn what the
    # narrator is allowed to reveal (curate authored plot vs. let the
    # player improvise). Empty => same model as planner_llm. Keep this on
    # a CHEAPER/FASTER model than story_llm if at all possible; runs every
    # turn that the gate is active.
    gate_llm: str = ""
    stt: str = "gpt-4o-mini-transcribe"
    tts: str = "gpt-4o-mini-tts"
    tts_voice: str = "ballad"
    embedding: str = "text-embedding-3-small"
    embedding_dim: int = 512
    # Sampling temperature per role.
    llm_temperature: float = 0.9               # narrator (story)
    planner_temperature: float = 0.6           # architect + summariser
    gen_temperature: float = 0.8               # world / content generation
    gate_temperature: float = 0.3              # curator (deterministic-ish)
    # Anti-repetition for the narrator. 0 = off (safe default, no behaviour
    # change); a mild 0.2-0.4 noticeably reduces repeated openers/phrases.
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    # Per-purpose OpenAI-compatible endpoints (empty = OpenAI). Lets each
    # call type point at a self-hosted server independently. Moderation
    # always uses the default OpenAI endpoint.
    story_endpoint: Endpoint = Endpoint()
    planner_endpoint: Endpoint = Endpoint()
    gen_endpoint: Endpoint = Endpoint()
    gate_endpoint: Endpoint = Endpoint()
    stt_endpoint: Endpoint = Endpoint()
    tts_endpoint: Endpoint = Endpoint()
    embedding_endpoint: Endpoint = Endpoint()

    @property
    def planner(self) -> str:
        return self.planner_llm or self.story_llm

    @property
    def gen(self) -> str:
        return self.gen_llm or self.story_llm

    @property
    def gate(self) -> str:
        return self.gate_llm or self.planner_llm or self.story_llm


class STTCfg(BaseModel):
    provider: str = "openai"  # openai | local_whisper (Phase 10)
    language: str = "de"


class TTSCfg(BaseModel):
    provider: str = "openai"  # openai | local (Phase 10)
    format: str = "pcm"
    sample_rate: int = 24000


class CaptureCfg(BaseModel):
    # Speech capture stops on a trailing pause instead of a hard cutoff,
    # so the player can speak as long as they want (within max_seconds).
    max_seconds: float = 30.0      # hard cap (cost guard / runaway)
    silence_seconds: float = 1.2   # pause that ends the turn
    start_timeout_s: float = 6.0   # no speech at all -> give up, re-prompt
    min_seconds: float = 0.5       # never end before this (ignore 1st breath)


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
    # WaitLoop volume boost. The ambient WAVs that ship with the repo are
    # mastered around 5% peak so they don't drown out the narrator on a hot
    # ReSpeaker line-out — but at default `default_volume_pct = 15` they're
    # almost inaudible. The WaitLoop multiplies sample values by this gain
    # before sending to the backend, with saturating clip to the int16
    # range so loud peaks don't fold over.
    # 1.0 = original level. The repo's ambient WAVs sit at ~20 % peak so
    # they don't compete with the narrator; 2.5 lifts them to ~50 % peak
    # — clearly audible but in the background. Tune up/down in
    # `data/audio.json` if your speakers / room call for it.
    wait_sound_gain: float = 2.5


class WakeWordCfg(BaseModel):
    engine: str = "openwakeword"
    model: str = ""        # built-in name or path to a custom .onnx
    model_de: str = ""     # optional per-locale override (de)
    model_en: str = ""     # optional per-locale override (en)
    threshold: float = 0.5
    # After the narrator speaks, listen once WITHOUT the wake word so the
    # player can reply directly; only after silence is the wake word needed.
    follow_up: bool = True


class HardwareCfg(BaseModel):
    # GPIO push-buttons. Each button has its own `<role>_button_*` group
    # so more roles can be added later without overloading a single set
    # of fields. Both ship out of the box, both default disabled.

    # Interrupt button — short press: pause/resume the current narration
    # (SIGSTOP / SIGCONT on the live aplay); long press: open the spoken
    # system menu.
    interrupt_button_enabled: bool = False    # master switch — no GPIO claim if false
    interrupt_button_pin: int = 17            # BCM pin (default 17 = physical pin 11)
    interrupt_button_pull_up: bool = True     # internal pull-up: button wires pin -> GND
    interrupt_button_bounce_s: float = 0.08   # debounce time in seconds
    interrupt_button_long_press_s: float = 2.0  # hold this long for "long press" semantics

    # Shutdown button — short press: announce "Spielstand gespeichert"
    # (the game is auto-checkpointed every turn, so this is just feedback);
    # long press: say goodbye and shut the Pi down via
    # `sudo -n systemctl poweroff`. Requires the running user to have
    # passwordless sudo for that command (see docs/SETUP_PI.md).
    shutdown_button_enabled: bool = False
    shutdown_button_pin: int = 27             # BCM pin (default 27 = physical pin 13)
    shutdown_button_pull_up: bool = True
    shutdown_button_bounce_s: float = 0.08
    shutdown_button_long_press_s: float = 2.0


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
    # Long-term memory: fold turns that fall out of the short window into a
    # rolling synopsis injected into the system prompt (continuity over a
    # long session). Folds in batches to keep cost/latency low.
    long_term_memory: bool = True
    synopsis_max_chars: int = 900
    synopsis_batch: int = 8        # fold this many old messages at once
    # Gentle nudge: after this many narrator turns on the same sub-beat,
    # remind the model it MAY advance_beat/complete_substory (0 = off).
    beat_nudge_after: int = 3
    # Upper bound for KnownFacts entries (oldest noteless evicted first).
    known_facts_cap: int = 30
    # Narration "gate": runs a small LLM each turn to decide which authored
    # reveals (fragments / history / glossary items / substory resolution)
    # the narrator MAY use this turn — the rest stays hidden. Player-driven
    # improvisation and new spontaneous facts are NOT gated; only the
    # pre-authored material is curated. Disable to fall back to the
    # algorithmic-only spoiler guards (next-beat / resolution_hint already
    # hidden everywhere).
    narration_gate_enabled: bool = True
    # Each turn the gate picks at most this many authored reveals to allow.
    narration_gate_max_reveals: int = 3
    # Checkpoint retention: keep this many checkpoints per session thread
    # (0 = unlimited). `storyteller-cli prune` enforces it.
    checkpoint_keep_per_thread: int = 100
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
    # Optional token auth for the web backends. Empty = disabled (open LAN).
    # auth_token (env STORYTELLER_WEB_TOKEN) gates the player UI; admin_token
    # (env STORYTELLER_ADMIN_TOKEN) gates the admin UI, falling back to
    # auth_token when unset. Kept out of the repo (set in .env).
    auth_token: str = ""
    admin_token: str = ""
    # Cross-origin allow-list. The built SPA is served same-origin (needs no
    # CORS); these cover `yarn dev`. Tighten/extend as needed.
    allowed_origins: list[str] = [
        "http://localhost:5173", "http://localhost:5174",
    ]
    # Hard caps on player/admin free-text input (cost/abuse guard).
    max_turn_chars: int = 2000
    max_prompt_chars: int = 4000


class ModerationCfg(BaseModel):
    enabled: bool = True
    model: str = "omni-moderation-latest"
    default_threshold: float = 0.5  # block any category at/above this score
    # Per-category baseline. Storyteller is an *adventure-style* narrator;
    # raw "violence" at 0.5 catches mundane action language ("die Schilde
    # hoch", "Mox' Jäger angreifen") and blocks too aggressively. We
    # loosen mundane categories and tighten the genuinely dangerous ones.
    # The admin can override anything via `data/moderation.json`.
    category_thresholds: dict[str, float] = Field(default_factory=lambda: {
        # Adventure-narrative — loose, otherwise the game can't function.
        "violence":              0.90,
        "violence/graphic":      0.85,
        "harassment":            0.85,
        "harassment/threatening": 0.80,
        "hate":                  0.75,
        "hate/threatening":      0.60,
        "illicit":               0.80,
        "illicit/violent":       0.70,
        # Sexual content — neutral default, restricted-minors strict.
        "sexual":                0.60,
        "sexual/minors":         0.05,
        # Self-harm — keep strict, no narrative value gained by relaxing.
        "self-harm":             0.40,
        "self-harm/intent":      0.35,
        "self-harm/instructions": 0.25,
    })


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


class TranscriptsCfg(BaseModel):
    # Also record the exact prompt sent to the narrator LLM each call
    # (system prompt + follow-up messages incl. tool round-trips) into the
    # transcript, viewable (collapsed) in the admin. Off by default — it
    # makes data/transcripts/*.jsonl noticeably larger.
    capture_prompts: bool = False


class PathsCfg(BaseModel):
    worlds_dir: str = "data/worlds"
    saves_dir: str = "data/saves"
    rag_db: str = "data/rag.db"
    wait_sounds_dir: str = "data/wait_sounds"
    voice_prompts_dir: str = "data/voice_prompts"


class Config(BaseModel):
    general: GeneralCfg = GeneralCfg()
    runtime: RuntimeCfg = RuntimeCfg()
    capture: CaptureCfg = CaptureCfg()
    models: ModelsCfg = ModelsCfg()
    stt: STTCfg = STTCfg()
    tts: TTSCfg = TTSCfg()
    audio: AudioCfg = AudioCfg()
    wakeword: WakeWordCfg = WakeWordCfg()
    hardware: HardwareCfg = HardwareCfg()
    fx: FXCfg = FXCfg()
    story: StoryCfg = StoryCfg()
    cost: CostCfg = CostCfg()
    logging: LoggingCfg = LoggingCfg()
    web: WebCfg = WebCfg()
    moderation: ModerationCfg = ModerationCfg()
    netcheck: NetcheckCfg = NetcheckCfg()
    voice_prompts: VoicePromptsCfg = VoicePromptsCfg()
    transcripts: TranscriptsCfg = TranscriptsCfg()
    paths: PathsCfg = PathsCfg()

    openai_api_key: str = ""

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p

    @property
    def root(self) -> Path:
        return ROOT


# Files whose change should rebuild the config (so admin/.env edits apply
# without restarting the services). moderation.json / settings.json are read
# live elsewhere and don't need to be watched here.
def _watch_files(config_path: str | None) -> list[Path]:
    return [
        Path(config_path) if config_path else ROOT / "config" / "config.toml",
        ROOT / "data" / "models.json",
        ROOT / "data" / "audio.json",
        ROOT / "data" / "story.json",
        ROOT / ".env",
    ]


def _watch_sig(config_path: str | None) -> tuple:
    sig = []
    for p in _watch_files(config_path):
        try:
            sig.append((str(p), p.stat().st_mtime_ns))
        except OSError:
            sig.append((str(p), 0))
    return tuple(sig)


_CFG_CACHE: dict = {}


def _build_config(config_path: str | None) -> Config:
    load_dotenv(ROOT / ".env", override=True)
    cfg_file = Path(config_path) if config_path else ROOT / "config" / "config.toml"
    data: dict = {}
    if cfg_file.exists():
        data = tomllib.loads(cfg_file.read_text())
    cfg = Config(**data)
    cfg.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    cfg.web.auth_token = os.environ.get("STORYTELLER_WEB_TOKEN", cfg.web.auth_token)
    cfg.web.admin_token = (os.environ.get("STORYTELLER_ADMIN_TOKEN", "")
                           or cfg.web.admin_token or cfg.web.auth_token)
    _apply_model_overrides(cfg)
    _apply_story_overrides(cfg)
    return cfg


def load_config(config_path: str | None = None) -> Config:
    """Load configuration. Rebuilt automatically when config.toml, the
    data/*.json runtime overrides, or .env change — so admin edits and key
    changes apply WITHOUT restarting the services. Between changes it returns
    the same cached object (a few stat() calls per lookup)."""
    key = config_path or "__default__"
    sig = _watch_sig(config_path)
    cached = _CFG_CACHE.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1]
    cfg = _build_config(config_path)
    _CFG_CACHE[key] = (sig, cfg)
    return cfg


load_config.cache_clear = _CFG_CACHE.clear  # test compatibility


def _apply_model_overrides(cfg: Config) -> None:
    """Apply admin-editable model overrides (data/models.json) onto cfg.models.

    Lives in core (no hardware dependency); the admin writes the file and the
    Pi voice loop / web backends pick it up on next load. Unknown / bad keys
    are logged and skipped.
    """
    import json
    import logging

    log = logging.getLogger("storyteller.config")
    p = ROOT / "data" / "models.json"
    if not p.exists():
        return
    try:
        ov = json.loads(p.read_text())
    except Exception as exc:
        log.warning("data/models.json unreadable, ignored: %r", exc)
        return
    if not isinstance(ov, dict) or not ov:
        return
    # Merge onto the current models config and re-validate as a whole, so
    # nested endpoints (and types) are parsed properly. Unknown keys are
    # ignored by pydantic.
    try:
        merged = {**cfg.models.model_dump(), **ov}
        cfg.models = ModelsCfg.model_validate(merged)
    except Exception as exc:
        log.warning("model overrides invalid, ignored: %r", exc)


def _apply_story_overrides(cfg: Config) -> None:
    """Per-deployment overrides for [story] (e.g. shorter memory window on a
    Pi to keep narrator prompts smaller and the LLM faster). Same shape as
    `_apply_model_overrides`: drop a `data/story.json` file with just the
    keys you want to change, repo defaults live in `config/config.toml`.
    """
    import json
    import logging

    log = logging.getLogger("storyteller.config")
    p = ROOT / "data" / "story.json"
    if not p.exists():
        return
    try:
        ov = json.loads(p.read_text())
    except Exception as exc:
        log.warning("data/story.json unreadable, ignored: %r", exc)
        return
    if not isinstance(ov, dict) or not ov:
        return
    try:
        merged = {**cfg.story.model_dump(), **ov}
        cfg.story = StoryCfg.model_validate(merged)
    except Exception as exc:
        log.warning("story overrides invalid, ignored: %r", exc)
