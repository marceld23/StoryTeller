"""Pluggable audio backend (Pi/ALSA, portable/sounddevice, PipeWire).

Lets Storyteller run both on the Raspberry Pi with the ReSpeaker (ALSA
softvol, line-out) and on a normal PC without special hardware (portable
sounddevice backend with software volume).

WaitLoop and WakeWord no longer call aplay/arecord directly; they use this
backend's `loop_play()` / `mic_frames()` -> platform-neutral.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator

from storyteller_core.config import Config

from ..runtime import resolve_backend_name


# ---------- ALSA-Helfer (Pi/Linux) ----------

def _alsa_loop(pcm_bytes: bytes, sr: int, out_pcm: str,
               stop: threading.Event) -> None:
    """Spielt einen rohen int16-Mono-Puffer gapless in Schleife (aplay-stdin)."""
    if not pcm_bytes:
        return
    proc = subprocess.Popen(
        ["aplay", "-q", "-D", out_pcm, "-f", "S16_LE", "-r", str(sr),
         "-c", "1", "-t", "raw", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    chunk = max(1, sr * 2 // 4)
    try:
        pos = 0
        while not stop.is_set():
            end = pos + chunk
            proc.stdin.write(pcm_bytes[pos:end])
            pos = end
            if pos >= len(pcm_bytes):
                pos = 0
    except (BrokenPipeError, ValueError):
        pass
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()


def _alsa_mic_frames(in_pcm: str, sr: int, frame_len: int,
                     stop: threading.Event) -> Iterator:
    import numpy as np

    proc = subprocess.Popen(
        ["arecord", "-q", "-D", in_pcm, "-f", "S16_LE", "-r", str(sr),
         "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        while not stop.is_set():
            raw = proc.stdout.read(frame_len * 2)
            if not raw:
                break
            yield np.frombuffer(raw, dtype=np.int16)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=1.5)
        except Exception:
            proc.kill()


class AudioBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def set_volume(self, pct: int) -> None: ...

    @abstractmethod
    def get_volume(self) -> int | None: ...

    @abstractmethod
    def play_wav(self, wav_path: str) -> None: ...

    @abstractmethod
    def record_wav(self, wav_path: str, seconds: float) -> None: ...

    @abstractmethod
    def loop_play(self, pcm_bytes: bytes, sr: int,
                   stop: threading.Event) -> None: ...

    @abstractmethod
    def mic_frames(self, sr: int, frame_len: int,
                   stop: threading.Event) -> Iterator: ...

    def record_until_silence(self, wav_path: str) -> None:
        """Record a player turn that ends on a trailing pause.

        Keeps listening WHILE the player speaks (energy-based VAD over
        `mic_frames`), so nothing is cut off mid-sentence; stops after
        `capture.silence_seconds` of quiet, after `capture.max_seconds`
        at the latest, and gives up if nobody speaks within
        `capture.start_timeout_s`. Shared by every backend; writes a
        16-bit mono WAV (stdlib `wave`, no extra deps).
        """
        import wave

        import numpy as np

        c = self.cfg.capture
        sr = int(self.cfg.audio.input_sample_rate)
        frame_len = max(160, sr // 50)          # ~20 ms frames
        fdur = frame_len / sr
        cal_n = max(1, int(0.3 / fdur))         # ~0.3 s ambient calibration
        preroll_max = max(1, int(0.3 / fdur))   # keep speech onset
        stop = threading.Event()

        cal: list[float] = []
        noise: float | None = None
        preroll: list = []
        collected: list = []
        speaking = False
        spoken = 0.0
        quiet = 0.0
        elapsed = 0.0
        hot = 0  # consecutive voiced frames before we trust speech onset
        try:
            for frame in self.mic_frames(sr, frame_len, stop):
                f = np.asarray(frame, dtype=np.float32)
                rms = float(np.sqrt(np.mean(f * f))) if f.size else 0.0
                elapsed += fdur
                if noise is None:
                    cal.append(rms)
                    preroll.append(frame)
                    if len(preroll) > preroll_max:
                        preroll.pop(0)
                    if len(cal) >= cal_n:
                        noise = sorted(cal)[len(cal) // 2]  # median floor
                    continue
                thr = max(noise * 3.0, 300.0)
                voiced = rms >= thr
                if not speaking:
                    preroll.append(frame)
                    if len(preroll) > preroll_max:
                        preroll.pop(0)
                    hot = hot + 1 if voiced else 0
                    if hot >= 2:                # ~40 ms of real speech
                        speaking = True
                        collected.extend(preroll)
                        spoken = quiet = 0.0
                    elif elapsed >= c.start_timeout_s:
                        break                   # nobody spoke
                else:
                    collected.append(frame)
                    spoken += fdur
                    quiet = 0.0 if voiced else quiet + fdur
                    if spoken >= c.min_seconds and \
                            quiet >= c.silence_seconds:
                        break
                    if spoken >= c.max_seconds:
                        break
        finally:
            stop.set()

        pcm = (np.concatenate(collected).astype("<i2").tobytes()
               if collected else b"")
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)


class AlsaSoftvolBackend(AudioBackend):
    """Pi: Lautstärke via `amixer` (softvol), I/O via aplay/arecord."""

    name = "alsa_softvol"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.out_pcm = cfg.audio.output_alsa_pcm
        self.in_pcm = cfg.audio.input_alsa_pcm
        self.card = cfg.audio.mixer_card
        self.control = cfg.audio.mixer_control

    def _have(self, *bins: str) -> None:
        for b in bins:
            if shutil.which(b) is None:
                raise RuntimeError(
                    f"benötigtes Programm fehlt: {b} (apt install alsa-utils)")

    def prime(self) -> None:
        """Öffnet die softvol-PCM kurz, damit das amixer-Control entsteht."""
        self._have("aplay")
        subprocess.run(
            ["aplay", "-D", self.out_pcm, "-f", "S16_LE", "-r", "48000",
             "-c", "2", "-d", "1", "/dev/zero"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    def set_volume(self, pct: int) -> None:
        self._have("amixer")
        pct = max(0, min(100, int(pct)))
        r = subprocess.run(
            ["amixer", "-c", self.card, "sset", self.control, f"{pct}%"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            self.prime()
            subprocess.run(
                ["amixer", "-c", self.card, "sset", self.control, f"{pct}%"],
                capture_output=True, text=True, check=False,
            )

    def get_volume(self) -> int | None:
        self._have("amixer")
        r = subprocess.run(
            ["amixer", "-c", self.card, "sget", self.control],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        for tok in r.stdout.split():
            if tok.startswith("[") and tok.endswith("%]"):
                try:
                    return int(tok.strip("[]%"))
                except ValueError:
                    pass
        return None

    def play_wav(self, wav_path: str) -> None:
        self._have("aplay")
        subprocess.run(["aplay", "-q", "-D", self.out_pcm, wav_path],
                        check=True)

    def record_wav(self, wav_path: str, seconds: float) -> None:
        self._have("arecord")
        subprocess.run(
            ["arecord", "-q", "-D", self.in_pcm, "-f", "S16_LE",
             "-r", str(self.cfg.audio.input_sample_rate), "-c", "1",
             "-d", str(int(seconds)), wav_path],
            check=True,
        )

    def loop_play(self, pcm_bytes, sr, stop):
        _alsa_loop(pcm_bytes, sr, self.out_pcm, stop)

    def mic_frames(self, sr, frame_len, stop):
        yield from _alsa_mic_frames(self.in_pcm, sr, frame_len, stop)


class PortableBackend(AudioBackend):
    """PC: cross-platform via `sounddevice` (PortAudio).

    Keine ALSA-PCM-Namen, kein amixer — Lautstärke ist ein Software-Gain,
    der auf alle Wiedergaben angewendet wird. Default-Mikro/-Ausgabe des OS.
    """

    name = "portable"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._gain = max(0, min(100, cfg.audio.default_volume_pct)) / 100.0
        dev = cfg.audio.sd_output_device.strip()
        self._device = dev or None  # None => OS-Default

    # --- intern ---
    def _sd(self):
        import sounddevice as sd

        if self._device:
            sd.default.device = (None, self._device)
        return sd

    # --- API ---
    def set_volume(self, pct: int) -> None:
        self._gain = max(0, min(100, int(pct))) / 100.0

    def get_volume(self) -> int | None:
        return int(round(self._gain * 100))

    def play_wav(self, wav_path: str) -> None:
        import numpy as np
        import soundfile as sf

        sd = self._sd()
        data, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        sd.play(np.clip(data * self._gain, -1.0, 1.0), sr)
        sd.wait()

    def record_wav(self, wav_path: str, seconds: float) -> None:
        import soundfile as sf

        sd = self._sd()
        sr = self.cfg.audio.input_sample_rate
        rec = sd.rec(int(seconds * sr), samplerate=sr, channels=1,
                     dtype="int16")
        sd.wait()
        sf.write(wav_path, rec, sr, subtype="PCM_16")

    def loop_play(self, pcm_bytes, sr, stop):
        if not pcm_bytes:
            return
        import numpy as np

        sd = self._sd()
        buf = (np.frombuffer(pcm_bytes, dtype="<i2").astype("float32")
               / 32768.0) * self._gain
        block = max(1, sr // 8)
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as st:
            pos = 0
            n = len(buf)
            while not stop.is_set():
                end = pos + block
                if end <= n:
                    st.write(buf[pos:end])
                    pos = end
                else:
                    st.write(np.concatenate([buf[pos:], buf[: end - n]]))
                    pos = end - n

    def mic_frames(self, sr, frame_len, stop):
        import numpy as np

        sd = self._sd()
        with sd.InputStream(samplerate=sr, channels=1, dtype="int16",
                            blocksize=frame_len) as st:
            while not stop.is_set():
                data, _ = st.read(frame_len)
                yield np.asarray(data, dtype=np.int16).reshape(-1)


class PipeWireBackend(AudioBackend):
    """Phase 8: PipeWire-Sink (z.B. Bluetooth). Aufnahme bleibt am ReSpeaker."""

    name = "pipewire"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.sink = cfg.audio.pw_sink or "@DEFAULT_AUDIO_SINK@"
        self.in_pcm = cfg.audio.input_alsa_pcm

    def _have(self, *bins: str) -> None:
        for b in bins:
            if shutil.which(b) is None:
                raise RuntimeError(
                    f"{b} fehlt — PipeWire/Bluetooth einrichten: "
                    "scripts/setup_bluetooth.sh")

    def set_volume(self, pct: int) -> None:
        self._have("wpctl")
        pct = max(0, min(100, int(pct)))
        subprocess.run(["wpctl", "set-volume", self.sink, f"{pct/100:.2f}"],
                        check=False)

    def get_volume(self) -> int | None:
        self._have("wpctl")
        r = subprocess.run(["wpctl", "get-volume", self.sink],
                           capture_output=True, text=True)
        for tok in r.stdout.split():
            try:
                return int(round(float(tok) * 100))
            except ValueError:
                continue
        return None

    def play_wav(self, wav_path: str) -> None:
        self._have("pw-play")
        tgt = [] if self.sink == "@DEFAULT_AUDIO_SINK@" else \
            ["--target", self.sink]
        subprocess.run(["pw-play", *tgt, wav_path], check=True)

    def record_wav(self, wav_path: str, seconds: float) -> None:
        self._have("arecord")
        subprocess.run(
            ["arecord", "-q", "-D", self.in_pcm, "-f", "S16_LE",
             "-r", str(self.cfg.audio.input_sample_rate), "-c", "1",
             "-d", str(int(seconds)), wav_path], check=True)

    def loop_play(self, pcm_bytes, sr, stop):
        # Einfacher Loop über pw-play einer temporären WAV (BT, Phase 8).
        if not pcm_bytes:
            return
        import tempfile

        import numpy as np
        import soundfile as sf

        self._have("pw-play")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            path = t.name
        sf.write(path, np.frombuffer(pcm_bytes, dtype="<i2"), sr,
                 subtype="PCM_16")
        tgt = [] if self.sink == "@DEFAULT_AUDIO_SINK@" else \
            ["--target", self.sink]
        while not stop.is_set():
            p = subprocess.Popen(["pw-play", *tgt, path],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
            while p.poll() is None:
                if stop.wait(0.2):
                    p.terminate()
                    break

    def mic_frames(self, sr, frame_len, stop):
        yield from _alsa_mic_frames(self.in_pcm, sr, frame_len, stop)


_BACKENDS = {
    "alsa_softvol": AlsaSoftvolBackend,
    "portable": PortableBackend,
    "pipewire": PipeWireBackend,
}


def get_backend(cfg: Config) -> AudioBackend:
    """Factory: runtime override + profile resolve the concrete backend.

    The persisted playback volume (data/audio.json, admin-editable) is
    re-applied here, so every start honours the last setting.
    """
    from ..runtime import effective_volume, load_audio_override

    ov = load_audio_override(cfg)
    if ov.get("pw_sink"):
        cfg.audio.pw_sink = ov["pw_sink"]
    name = resolve_backend_name(cfg)
    cls = _BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"unbekanntes Audio-Backend: {name!r}")
    be = cls(cfg)
    try:
        be.set_volume(effective_volume(cfg))
    except Exception:  # pragma: no cover - HW-/install-abhängig
        pass
    return be
