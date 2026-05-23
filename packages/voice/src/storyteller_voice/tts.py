"""TTS provider abstraction.

OpenAITTS (default, OpenAI-compatible HTTP — incl. self-hosted kokoro);
WyomingTTS (Wyoming/TCP, e.g. a Piper server — NOT HTTP);
XttsTTS    (daswer123/xtts-api-server style — HTTP but not OpenAI-shaped);
LocalTTS   = Phase 10 (Pi 5 + AI HAT). Note: Whisper is NOT TTS.
Selected via config.tts.provider, or auto-detected from the tts endpoint
scheme (tcp://|wyoming:// -> Wyoming, xtts:// -> XTTS).

Long narrations are chunked at sentence boundaries. The XTTS provider also
exposes `synthesize_streaming`: it fetches all chunks IN PARALLEL but
yields them in the original order as each becomes ready. The caller (the
audio player) can start speaking the first chunk while the rest are still
being synthesised — masking most of the TTS latency behind playback.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from urllib.parse import urlparse

import numpy as np
from storyteller_core.config import Config
from storyteller_core.oai import get_tts_client

log = logging.getLogger("storyteller.tts")

OPENAI_TTS_SR = 24000  # response_format="pcm" => 24 kHz, s16le, mono


class TTS(ABC):
    @abstractmethod
    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        """Liefert (float32 mono [-1,1], sample_rate)."""
        ...

    def synthesize_streaming(
        self, text: str, instructions: str = "",
    ) -> Iterator[tuple[np.ndarray, int]]:
        """Yield ordered (float32 mono, sample_rate) chunks as they become
        ready. Default = one-shot (yield the whole result). Providers that
        chunk internally (e.g. XttsTTS) override this to enable streaming
        playback — the player can start the first chunk while the rest are
        still being synthesised."""
        yield self.synthesize(text, instructions)


class OpenAITTS(TTS):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        client = get_tts_client(self.cfg)
        log.info("TTS: model=%s voice=%s endpoint=%s", self.cfg.models.tts,
                 self.cfg.models.tts_voice,
                 self.cfg.models.tts_endpoint.base_url or "OpenAI")
        voice = self.cfg.models.tts_voice
        buf = bytearray()
        # WAV is self-describing (carries the real sample rate + channels), so
        # it works across servers — OpenAI returns 24 kHz mono, but others
        # (e.g. kokoro) may use a different rate or stereo PCM. Decoding raw
        # "pcm" with a fixed 24 kHz mono assumption garbles those.
        kw = dict(
            model=self.cfg.models.tts,
            voice=voice,
            input=text,
            response_format="wav",
        )
        # `instructions` (style steering) is an OpenAI gpt-4o-mini-tts feature.
        # Self-hosted servers (Piper, kokoro, …) don't know it and may reject
        # unknown fields, so only send it on the default OpenAI endpoint.
        if instructions and not self.cfg.models.tts_endpoint.base_url:
            kw["instructions"] = instructions
        with client.audio.speech.with_streaming_response.create(**kw) as resp:
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
        import io

        import soundfile as sf

        data, sr = sf.read(io.BytesIO(bytes(buf)), dtype="float32",
                           always_2d=False)
        if getattr(data, "ndim", 1) > 1:        # downmix to mono
            data = data.mean(axis=1)
        return np.ascontiguousarray(data, dtype=np.float32), int(sr)


class WyomingTTS(TTS):
    """TTS over the Wyoming protocol (raw TCP, not HTTP/OpenAI).

    A Wyoming voice server (e.g. Piper) is configured via the tts endpoint as
    ``tcp://host:port`` (or ``wyoming://host:port``). ``models.tts_voice`` (or
    ``models.tts``) selects the voice, e.g. ``de_DE-thorsten-high``. Piper
    returns 16-bit mono PCM, sample rate announced in the AudioStart event.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        u = urlparse(cfg.models.tts_endpoint.base_url)
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 10200

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        import asyncio

        voice = self.cfg.models.tts_voice or self.cfg.models.tts
        log.info("TTS: wyoming voice=%s endpoint=tcp://%s:%d",
                 voice, self.host, self.port)
        pcm, rate = asyncio.run(self._synthesize(text, voice))
        if not pcm:
            return np.zeros(0, dtype=np.float32), rate
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        return np.ascontiguousarray(audio, dtype=np.float32), rate

    async def _synthesize(self, text: str, voice: str) -> tuple[bytes, int]:
        from wyoming.audio import AudioChunk, AudioStop
        from wyoming.client import AsyncTcpClient
        from wyoming.tts import Synthesize, SynthesizeVoice

        buf = bytearray()
        rate = 22050
        async with AsyncTcpClient(self.host, self.port) as client:
            syn = Synthesize(text=text)
            if voice:
                syn.voice = SynthesizeVoice(name=voice)
            await client.write_event(syn.event())
            while True:
                event = await client.read_event()
                if event is None:
                    break
                if AudioChunk.is_type(event.type):
                    chunk = AudioChunk.from_event(event)
                    rate = chunk.rate or rate
                    buf.extend(chunk.audio)
                elif AudioStop.is_type(event.type):
                    break
        return bytes(buf), rate


class XttsTTS(TTS):
    """TTS over the daswer123/xtts-api-server HTTP API.

    Routes are not OpenAI-shaped — they live at ``/tts_to_audio/`` (POST)
    with body ``{text, speaker_wav, language}`` and return ``audio/wav``.
    Configured via the tts endpoint as ``xtts://host:port`` (or
    ``xtts+http://host:port`` — the prefix triggers this provider; the
    actual request always goes over plain HTTP). ``models.tts_voice`` (or
    ``models.tts``) names the registered speaker, e.g. ``marcel``.
    Language follows ``cfg.general.locale`` (de/en).

    Long narrations are split at sentence boundaries and synthesised in
    chunks, then concatenated — XTTS v2 is autoregressive and produces
    garbled audio toward the end of long single-request generations.
    """

    # XTTS sentence limit hovers around 250 chars in practice; keep a margin.
    MAX_CHUNK_CHARS = 220
    # Speech tempo. XTTS speed is a SERVER-GLOBAL setting (the per-request
    # body doesn't accept speed), so we push it once via /set_tts_settings
    # at start-up. 1.0 = normal, 1.2 = slightly brisker, 1.5 starts feeling
    # rushed; lower than 1.0 = slow/deliberate. Tweak here to retune.
    DEFAULT_SPEED = 1.2
    _settings_applied: bool = False   # one-shot guard, per process
    # Trim heuristic: XTTS v2 frequently appends a verbatim repetition of
    # short inputs after a long pause ("stacking reverb" effect). Only
    # attempt the cut when the audio is much longer than the text would
    # justify — otherwise we'd chop natural multi-sentence narration at the
    # first inter-sentence pause.
    TRIM_BLOAT_RATIO = 1.6       # cut only if actual > expected * this
    TRIM_CHARS_PER_S = 12.0      # rough speaking rate for the expected length
    TRIM_SILENCE_S = 0.5         # min pause length to count as a cut point
    TRIM_WINDOW_S = 0.05         # energy analysis window
    TRIM_SILENCE_REL = 0.05      # silence = energy below 5% of peak

    def __init__(self, cfg: Config):
        self.cfg = cfg
        raw = cfg.models.tts_endpoint.base_url
        # Strip the marker scheme so urlparse gives host:port; the wire is
        # always plain HTTP regardless of the scheme used in config.
        for prefix in ("xtts+http://", "xtts+https://", "xtts://"):
            if raw.startswith(prefix):
                raw = "http://" + raw[len(prefix):]
                break
        u = urlparse(raw)
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 8002
        self.base = f"http://{self.host}:{self.port}"
        # One-shot per process: sync the server's global TTS settings to our
        # preferred values (mainly: speech speed). XttsTTS is reconstructed
        # every idle cycle, so a class-level flag prevents needless HTTP.
        if not XttsTTS._settings_applied:
            self._apply_server_settings()
            XttsTTS._settings_applied = True

    def _apply_server_settings(self) -> None:
        """Pin server-globals (esp. `speed`). GETs current settings first to
        preserve fields we don't care about, then POSTs the merged dict only
        if anything actually differs. Best-effort: a failure is logged and
        ignored — TTS still works with whatever the server had."""
        import httpx

        try:
            cur = httpx.get(f"{self.base}/get_tts_settings",
                            timeout=5.0).json()
            target = dict(cur)
            target["speed"] = self.DEFAULT_SPEED
            if any(target.get(k) != cur.get(k) for k in target):
                httpx.post(f"{self.base}/set_tts_settings", json=target,
                           timeout=5.0).raise_for_status()
                log.info("XTTS: server settings synced (speed=%.2f)",
                         self.DEFAULT_SPEED)
            else:
                log.debug("XTTS: server settings already at target")
        except Exception as exc:
            log.warning("XTTS settings sync failed: %r", exc)

    @classmethod
    def _trim_repetition(cls, audio: np.ndarray, sr: int,
                         text: str) -> np.ndarray:
        """Cut XTTS's "appended repetition" artefact.

        Two-stage filter:
          1) Bloat gate — only attempt the trim when the actual audio is
             much longer than the text could justify (`TRIM_BLOAT_RATIO`
             over `len(text) / TRIM_CHARS_PER_S`). Multi-sentence prose
             that simply has natural pauses passes straight through.
          2) Cut at the first silence of >= TRIM_SILENCE_S that is followed
             by MORE audio (i.e. not the natural trailing silence at the
             end of the recording).
        """
        if audio.size == 0:
            return audio
        expected_s = max(1.0, len(text or "") / cls.TRIM_CHARS_PER_S)
        actual_s = audio.size / max(1, sr)
        if actual_s < expected_s * cls.TRIM_BLOAT_RATIO:
            return audio                       # likely no repetition
        peak = float(np.abs(audio).max())
        if peak < 0.05:                        # too quiet to analyse
            return audio
        win = max(1, int(sr * cls.TRIM_WINDOW_S))
        n_win = audio.size // win
        if n_win < 4:
            return audio
        # Window-max envelope; cheap and robust.
        env = np.abs(audio[: n_win * win]).reshape(n_win, win).max(axis=1)
        speaking = env > peak * cls.TRIM_SILENCE_REL
        if not speaking.any():
            return audio
        start = int(np.argmax(speaking))       # first speaking window
        gap_windows = max(1, int(cls.TRIM_SILENCE_S / cls.TRIM_WINDOW_S))
        silence_start: int | None = None
        for i in range(start + 1, n_win):
            if not speaking[i]:
                if silence_start is None:
                    silence_start = i
                elif (i - silence_start) >= gap_windows:
                    # Long enough silence found. Cut only if AUDIO RESUMES
                    # later (otherwise it's natural trailing silence).
                    if (speaking[i:].any()):
                        return audio[: silence_start * win + win // 2]
                    return audio
            else:
                silence_start = None
        return audio

    @classmethod
    def _chunks(cls, text: str) -> list[str]:
        """Split text into <= MAX_CHUNK_CHARS pieces on sentence boundaries
        (`.`, `!`, `?`, `…`). A single overlong sentence is kept as one
        chunk; XTTS may still warble at its tail but splitting mid-sentence
        sounds worse."""
        import re

        text = (text or "").strip()
        if not text:
            return []
        # Split keeping punctuation with the preceding sentence.
        parts = re.split(r"(?<=[.!?…])\s+", text)
        chunks: list[str] = []
        cur = ""
        for s in (p.strip() for p in parts):
            if not s:
                continue
            if cur and len(cur) + 1 + len(s) > cls.MAX_CHUNK_CHARS:
                chunks.append(cur)
                cur = s
            else:
                cur = f"{cur} {s}" if cur else s
        if cur:
            chunks.append(cur)
        return chunks or [text]

    # --- internals -----------------------------------------------------
    def _synth_one(self, client, chunk: str, idx: int, total: int,
                   speaker: str, language: str) -> tuple[np.ndarray, int]:
        """Fetch + decode + trim one chunk. Used by both the eager and the
        streaming paths."""
        import io

        import soundfile as sf

        r = client.post(
            f"{self.base}/tts_to_audio/",
            json={"text": chunk, "speaker_wav": speaker, "language": language},
        )
        r.raise_for_status()
        data, sr = sf.read(io.BytesIO(r.content), dtype="float32",
                           always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        raw_samples = len(data)
        data = self._trim_repetition(
            np.asarray(data, dtype=np.float32), int(sr), chunk)
        if len(data) < raw_samples:
            log.info("  chunk %d/%d: %d chars -> %d samples @ %d Hz "
                     "(trimmed %d ms XTTS repetition)",
                     idx, total, len(chunk), len(data), int(sr),
                     int(1000 * (raw_samples - len(data)) / int(sr)))
        else:
            log.debug("  chunk %d/%d: %d chars -> %d samples @ %d Hz",
                      idx, total, len(chunk), len(data), int(sr))
        return np.ascontiguousarray(data, dtype=np.float32), int(sr)

    def _prepare(self, text: str) -> tuple[list[str], str, str]:
        from storyteller_core.i18n import norm

        speaker = self.cfg.models.tts_voice or self.cfg.models.tts
        language = norm(self.cfg.general.locale)
        chunks = self._chunks(text)
        log.info("TTS: xtts speaker=%s language=%s endpoint=%s chunks=%d "
                 "(total %d chars)",
                 speaker, language, self.base, len(chunks), len(text or ""))
        return chunks, speaker, language

    # --- public API ----------------------------------------------------
    # IMPORTANT: the daswer123/xtts-api-server is NOT thread-safe under
    # concurrent /tts_to_audio/ POSTs against the same speaker — parallel
    # requests can race on the single GPU model instance and the server
    # returns the SAME audio for every request, which manifests as
    # "the narrator says the same short fragment three times in a row".
    # We therefore submit chunks SERIALLY (max_workers=1). The latency
    # masking is preserved by the producer/consumer pattern: while
    # play_stream blocks on `play_array(chunk_n)`, the executor is free
    # to render chunk_n+1 — by the time playback of n ends, n+1 is
    # usually already in the queue.
    _XTTS_MAX_WORKERS = 1

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        """Fetch chunks serially (XTTS server is not thread-safe), concatenate."""
        import concurrent.futures as _cf

        import httpx

        chunks, speaker, language = self._prepare(text)
        if not chunks:
            return np.zeros(0, dtype=np.float32), 24000
        with httpx.Client(timeout=60.0) as client:
            with _cf.ThreadPoolExecutor(max_workers=self._XTTS_MAX_WORKERS) as ex:
                futs = [ex.submit(self._synth_one, client, c, i + 1,
                                  len(chunks), speaker, language)
                        for i, c in enumerate(chunks)]
                results = [f.result() for f in futs]
        pieces = [a for a, _sr in results]
        sr_out = int(results[-1][1])
        out = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        return np.ascontiguousarray(out, dtype=np.float32), sr_out

    def synthesize_streaming(
        self, text: str, instructions: str = "",
    ) -> Iterator[tuple[np.ndarray, int]]:
        """Yield chunks in order as soon as each is ready. Chunks render one
        at a time (XTTS server is not thread-safe), but the consumer plays
        chunk N while chunk N+1 renders — so the perceived first-audio
        latency is roughly one chunk render, not the sum."""
        import concurrent.futures as _cf

        import httpx

        chunks, speaker, language = self._prepare(text)
        if not chunks:
            return
        # Keep the http client + executor alive for the whole stream so the
        # caller can consume at its own pace.
        client = httpx.Client(timeout=60.0)
        ex = _cf.ThreadPoolExecutor(max_workers=self._XTTS_MAX_WORKERS)
        try:
            futs = [ex.submit(self._synth_one, client, c, i + 1,
                              len(chunks), speaker, language)
                    for i, c in enumerate(chunks)]
            for f in futs:
                yield f.result()
        finally:
            ex.shutdown(wait=True)
            client.close()


class LocalTTS(TTS):
    """Phase 10 (optional): lokales TTS — NUR Pi 5 + AI HAT."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        raise NotImplementedError("Phase 10: lokales TTS (Pi 5 + AI HAT).")


def get_tts(cfg: Config) -> TTS:
    # Auto-detect from the endpoint scheme so it's admin-configurable and
    # hot-reloaded; OpenAI stays the default for everything else.
    ep = cfg.models.tts_endpoint.base_url or ""
    if cfg.tts.provider == "wyoming" or ep.startswith(("tcp://", "wyoming://")):
        return WyomingTTS(cfg)
    if cfg.tts.provider == "xtts" or ep.startswith(
            ("xtts://", "xtts+http://", "xtts+https://")):
        return XttsTTS(cfg)
    return {"openai": OpenAITTS, "local": LocalTTS}.get(
        cfg.tts.provider, OpenAITTS)(cfg)
