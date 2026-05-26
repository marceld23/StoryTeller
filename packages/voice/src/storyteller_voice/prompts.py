"""Voice-prompt cache: render fixed announcements once via TTS, then play
them back without the API (saves tokens + latency).

Layout (multi-slot, one subdirectory per (endpoint, model, voice) combo):

    data/voice_prompts/<locale>/<slot>/<pid>.wav
    data/voice_prompts/<locale>/<slot>/manifest.json

Each slot caches a single TTS-config's worth of WAVs. Switching the
TTS voice or model picks a different slot — old WAVs stay on disk
and are reused the next time the operator switches back, instead of
being clobbered by a full rebuild. Per-prompt text staleness still
works inside each slot: only the actually-changed announcements are
re-rendered.

Old single-slot layouts (``<locale>/manifest.json`` + WAVs directly
under ``<locale>/``) are migrated lazily on the first
``VoicePromptCache`` construction: the existing files are moved into
the matching slot based on the old manifest's recorded voice/model.
"""

from __future__ import annotations

import json
import logging
import re

import numpy as np
import soundfile as sf
from storyteller_core.config import Config
from storyteller_core.i18n import VOICE_PROMPTS, norm

log = logging.getLogger("storyteller.prompts")


def _safe(s: str) -> str:
    """Filesystem-safe slug: alnum + . _ -, everything else collapsed to '-'."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (s or "").strip()).strip("-")
    return s or "default"


def _endpoint_host(cfg: Config) -> str:
    """Stable host identifier for the TTS endpoint. Empty base_url
    means "default OpenAI" — we use the literal "openai" so the
    cached slot doesn't change when the operator clears the field
    explicitly vs. leaving it default."""
    ep = getattr(cfg.models, "tts_endpoint", None)
    base = (getattr(ep, "base_url", "") or "").strip()
    if not base:
        return "openai"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base if "://" in base else f"http://{base}")
        host = (parsed.hostname or "").strip()
        if not host:
            return _safe(base)
        port = parsed.port
        return _safe(f"{host}-{port}") if port else _safe(host)
    except Exception:
        return _safe(base)


class VoicePromptCache:
    def __init__(self, cfg: Config, locale: str | None = None):
        self.cfg = cfg
        self.locale = norm(locale or cfg.general.locale)
        self.prompts = VOICE_PROMPTS[self.locale]
        self._locale_dir = cfg.path(cfg.paths.voice_prompts_dir) / self.locale
        self._locale_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_layout()
        self.dir = self._slot_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self.dir / "manifest.json"
        # Optional LED ring — when set, `play()` switches the ring to the
        # "speak" colour while a cached prompt plays so the player can tell
        # the system is talking and not still listening. Set via
        # `cache.leds = ring` from the caller after constructing both.
        self.leds = None

    # ---------- slot identity ----------

    def _voice(self) -> str:
        return self.cfg.voice_prompts.voice or self.cfg.models.tts_voice

    def _slot_key(self, *, model: str | None = None,
                  voice: str | None = None,
                  host: str | None = None) -> str:
        """Stable, filesystem-safe identifier for one TTS config slot.
        Encodes (endpoint host, model, voice) so any of the three
        changing parks the old WAVs in their own subdirectory."""
        host = host if host is not None else _endpoint_host(self.cfg)
        model = (model if model is not None else self.cfg.models.tts) or "default"
        voice = (voice if voice is not None else self._voice()) or "default"
        return f"{_safe(host)}__{_safe(model)}__{_safe(voice)}"

    def _slot_dir(self):
        return self._locale_dir / self._slot_key()

    def _wav(self, pid: str):
        return self.dir / f"{pid}.wav"

    # ---------- migration from old single-slot layout ----------

    def _migrate_legacy_layout(self) -> None:
        """If the operator is upgrading from the pre-multi-slot layout
        (manifest.json + WAVs sitting directly under ``<locale>/``),
        move them once into the slot subdirectory that matches the
        recorded voice/model. Silent best-effort — a partial move is
        OK because the build will fill any gaps on next run."""
        legacy_manifest = self._locale_dir / "manifest.json"
        if not legacy_manifest.exists():
            return
        try:
            m = json.loads(legacy_manifest.read_text())
        except Exception:
            return
        # Compute the slot the old WAVs belong to from what the manifest
        # recorded (NOT the current cfg — the old WAVs may have been
        # rendered with a different voice than the current setting).
        slot_key = self._slot_key(
            model=m.get("model") or "default",
            voice=m.get("voice") or "default",
            host=_endpoint_host(self.cfg),
        )
        target = self._locale_dir / slot_key
        target.mkdir(parents=True, exist_ok=True)
        moved = 0
        for wav in list(self._locale_dir.glob("*.wav")):
            try:
                wav.replace(target / wav.name)
                moved += 1
            except OSError as exc:
                log.warning("voice-prompt migrate: %s -> %s failed: %r",
                            wav, target, exc)
        try:
            legacy_manifest.replace(target / "manifest.json")
        except OSError:
            pass
        if moved:
            log.info("voice-prompt cache migrated to multi-slot layout: "
                     "%d WAVs moved into %s/", moved, slot_key)

    # ---------- manifest ----------

    def _manifest_data(self) -> dict:
        """Full manifest dict (voice / model / texts), or {} on miss."""
        if not self._manifest.exists():
            return {}
        try:
            return json.loads(self._manifest.read_text()) or {}
        except Exception:
            return {}

    def _stale(self) -> bool:
        """Used by external callers (admin endpoint etc.) to ask "would a
        build() do work right now?". Inside `build()` itself we re-derive
        the answer from the manifest contents for per-prompt granularity."""
        if not self._manifest.exists():
            return True
        m = self._manifest_data()
        return (m.get("voice") != self._voice()
                or m.get("model") != self.cfg.models.tts
                or m.get("texts") != self.prompts)

    # ---------- build ----------

    def build(self, force: bool = False) -> list[str]:
        """Render missing announcements (or all on force/change) via TTS.

        Per-slot semantics: a fresh (voice, model, endpoint) combo gets
        its own subdirectory. Switching to a slot whose WAVs already
        exist reuses them — only texts that changed in `i18n.VOICE_PROMPTS`
        since the slot's manifest was written are re-rendered.

        Two playback-robustness tweaks on the synthesized audio:
        1) Pre-resample to 16 kHz (ReSpeaker native rate). Otherwise ALSA's
           samplerate_best sinc resampler kicks in for every fresh aplay
           invocation after the mic was just closed and silently eats the
           first few seconds of the cached prompt on the ReSpeaker USB
           Mic Array v2.0. Doing the resample once at build time and
           writing 16 kHz files bypasses the resampler entirely.
        2) Prepend 300 ms of silence so any remaining USB-endpoint
           warmup latency cannot truncate the actual speech.
        """
        from math import gcd

        from scipy.signal import resample_poly

        from .tts import get_tts

        manifest = self._manifest_data()
        cached_texts: dict = manifest.get("texts") or {}
        # Voice/model are part of the slot identity, so within ONE slot
        # they can't drift; we still defensively check, in case an
        # operator hand-edited manifest.json or the slug logic ever
        # changes. `force` always rebuilds the current slot's contents.
        full_rebuild = (force
                        or not self._manifest.exists()
                        or manifest.get("voice") != self._voice()
                        or manifest.get("model") != self.cfg.models.tts)
        tts = get_tts(self.cfg)
        target_sr = 16000
        lead_silence_s = 0.3
        built: list[str] = []
        for pid, text in self.prompts.items():
            wav = self._wav(pid)
            stale = (full_rebuild or not wav.exists()
                     or cached_texts.get(pid) != text)
            if not stale:
                continue
            audio, sr = tts.synthesize(text)
            audio = np.asarray(audio, dtype=np.float32)
            if sr != target_sr:
                g = gcd(int(sr), target_sr)
                audio = resample_poly(audio, target_sr // g,
                                      int(sr) // g).astype(np.float32)
                sr = target_sr
            pad = np.zeros(int(sr * lead_silence_s), dtype=np.float32)
            audio = np.concatenate([pad, audio])
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
            built.append(pid)
        # Reap WAVs that no longer correspond to a known prompt — keeps
        # the slot in sync when an announcement is removed from
        # VOICE_PROMPTS in i18n.py. `world_<id>.wav` files are managed
        # by play()'s live-fallback path (one per runtime-generated
        # world; not listed in VOICE_PROMPTS), so they get a pass.
        keep = set(self.prompts.keys())
        for wav in self.dir.glob("*.wav"):
            pid = wav.stem
            if pid in keep or pid.startswith("world_"):
                continue
            try:
                wav.unlink()
                log.info("voice-prompt reaper: removed orphan %s", wav.name)
            except OSError as exc:
                log.warning("voice-prompt reaper: %s failed: %r", wav, exc)
        self._manifest.write_text(json.dumps(
            {"locale": self.locale, "voice": self._voice(),
             "model": self.cfg.models.tts, "texts": self.prompts},
            ensure_ascii=False, indent=2))
        return built

    def play(self, pid: str, backend) -> None:
        wav = self._wav(pid)
        if not wav.exists():
            if not self.cfg.voice_prompts.allow_live_fallback:
                return
            # World-specific prompts (e.g. `world_<id>` for worlds created
            # at runtime) have no entry in self.prompts, so .get returns
            # "" — sending "" to OpenAI TTS errors with 400 empty_string
            # and crashes the loop. Skip silently instead: the caller
            # always plays a generic follow-up ("starting" etc.).
            text = self.prompts.get(pid, "")
            if not text.strip():
                log.info(
                    "voice_prompt %r has no text and no cached WAV — "
                    "skipping (caller should play a generic follow-up).",
                    pid)
                return
            from .tts import get_tts

            audio, sr = get_tts(self.cfg).synthesize(text)
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
        # Indicate "system is talking" on the LED ring (e.g. dodger blue)
        # so the player can tell the green "I'm listening" pulse has ended
        # — was confusing in the menus where the ring stayed solid green
        # the whole time. Best-effort: any LED error is swallowed.
        if self.leds is not None:
            try:
                self.leds.speak()
            except Exception:
                pass
        # Apply audio.tts_gain so menu/system prompts sit at the same
        # loudness as narrator TTS (which gets the gain via play_array).
        # Cached WAVs are int16 — boost with saturating clip, then play
        # from a temp file. Skipped on gain ≈ 1.0 to avoid the I/O.
        gain = float(getattr(self.cfg.audio, "tts_gain", 1.0) or 1.0)
        if abs(gain - 1.0) < 0.01:
            backend.play_wav(str(wav))
            return
        try:
            import tempfile
            data, sr = sf.read(str(wav), dtype="int16", always_2d=False)
            if getattr(data, "ndim", 1) > 1:
                data = data[:, 0]
            boosted = np.clip(data.astype(np.int32) * gain,
                              -32768, 32767).astype(np.int16)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                tmp = t.name
            sf.write(tmp, boosted, int(sr), subtype="PCM_16")
            backend.play_wav(tmp)
        except Exception:
            # Any I/O hiccup: fall back to ungained playback rather than
            # break a voice prompt the player needs to hear.
            backend.play_wav(str(wav))
