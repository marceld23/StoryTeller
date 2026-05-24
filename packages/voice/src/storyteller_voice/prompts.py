"""Voice-prompt cache: render fixed announcements once via TTS, then play
them back without the API (saves tokens + latency). Kept per locale:
data/voice_prompts/<locale>/*.wav (+ manifest.json).
"""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf
from storyteller_core.config import Config
from storyteller_core.i18n import VOICE_PROMPTS, norm


class VoicePromptCache:
    def __init__(self, cfg: Config, locale: str | None = None):
        self.cfg = cfg
        self.locale = norm(locale or cfg.general.locale)
        self.prompts = VOICE_PROMPTS[self.locale]
        self.dir = cfg.path(cfg.paths.voice_prompts_dir) / self.locale
        self.dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self.dir / "manifest.json"
        # Optional LED ring — when set, `play()` switches the ring to the
        # "speak" colour while a cached prompt plays so the player can tell
        # the system is talking and not still listening. Set via
        # `cache.leds = ring` from the caller after constructing both.
        self.leds = None

    def _voice(self) -> str:
        return self.cfg.voice_prompts.voice or self.cfg.models.tts_voice

    def _wav(self, pid: str):
        return self.dir / f"{pid}.wav"

    def _stale(self) -> bool:
        if not self._manifest.exists():
            return True
        try:
            m = json.loads(self._manifest.read_text())
        except Exception:
            return True
        return (m.get("voice") != self._voice()
                or m.get("model") != self.cfg.models.tts
                or m.get("texts") != self.prompts)

    def build(self, force: bool = False) -> list[str]:
        """Renders missing announcements (or all on force/change) via TTS.

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

        rebuild = force or self._stale()
        tts = get_tts(self.cfg)
        target_sr = 16000
        lead_silence_s = 0.3
        built: list[str] = []
        for pid, text in self.prompts.items():
            wav = self._wav(pid)
            if wav.exists() and not rebuild:
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
            from .tts import get_tts

            audio, sr = get_tts(self.cfg).synthesize(self.prompts.get(pid, ""))
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
        backend.play_wav(str(wav))
