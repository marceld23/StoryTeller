"""Austauschbares Audio-Ausgabe-Backend.

Erfüllt jetzt: ALSA `softvol` auf dem ReSpeaker Line-Out (Software-Lautstärke,
da das Gerät keinen Hardware-Regler hat).
Vorbereitet (Phase 8): PipeWire-Backend für Bluetooth-Lautsprecher.

Die App adressiert IMMER über dieses Interface — kein hartes `pcm.!default`.
Zur Laufzeit umschaltbar (später via Sprachmenü).
"""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod

from ..config import Config


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


class AlsaSoftvolBackend(AudioBackend):
    """Lautstärke via `amixer` (softvol-Control), I/O via aplay/arecord.

    Robust beim Hardware-Bring-up (keine PortAudio-Geräte­namens-Fallen).
    Die Streaming-Wiedergabe der TTS folgt in Phase 2 (sounddevice).
    """

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
                raise RuntimeError(f"benötigtes Programm fehlt: {b} (apt install alsa-utils)")

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
            # Control existiert evtl. noch nicht -> primen und erneut
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
        subprocess.run(["aplay", "-q", "-D", self.out_pcm, wav_path], check=True)

    def record_wav(self, wav_path: str, seconds: float) -> None:
        self._have("arecord")
        subprocess.run(
            ["arecord", "-q", "-D", self.in_pcm, "-f", "S16_LE",
             "-r", str(self.cfg.audio.input_sample_rate), "-c", "1",
             "-d", str(int(seconds)), wav_path],
            check=True,
        )


class PipeWireBackend(AudioBackend):
    """Phase 8: PipeWire-Sink (z.B. Bluetooth-Lautsprecher).

    Software-Lautstärke über `wpctl` (PipeWire mischt mixer-lose Geräte selbst),
    Wiedergabe/Aufnahme über `pw-play`/`pw-record`. Voraussetzung: laufendes
    PipeWire + gekoppeltes BT-Gerät (scripts/setup_bluetooth.sh). Auf reinem
    ALSA-System nicht nutzbar -> klare Fehlermeldung statt stillem Versagen.
    """

    name = "pipewire"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.sink = cfg.audio.pw_sink or "@DEFAULT_AUDIO_SINK@"

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
        # Ausgabe z.B. "Volume: 0.80"
        for tok in r.stdout.split():
            try:
                return int(round(float(tok) * 100))
            except ValueError:
                continue
        return None

    def play_wav(self, wav_path: str) -> None:
        self._have("pw-play")
        target = [] if self.sink == "@DEFAULT_AUDIO_SINK@" else ["--target", self.sink]
        subprocess.run(["pw-play", *target, wav_path], check=True)

    def record_wav(self, wav_path: str, seconds: float) -> None:
        # Aufnahme bleibt am ReSpeaker-Mikro (ALSA) — robust & unabhängig vom
        # BT-Ausgang; daher arecord auf die konfigurierte Capture-PCM.
        self._have("arecord")
        subprocess.run(
            ["arecord", "-q", "-D", self.cfg.audio.input_alsa_pcm,
             "-f", "S16_LE", "-r", str(self.cfg.audio.input_sample_rate),
             "-c", "1", "-d", str(int(seconds)), wav_path],
            check=True)


def get_backend(cfg: Config) -> AudioBackend:
    """Factory: liefert das in config.audio.backend gewählte Backend."""
    backends = {
        "alsa_softvol": AlsaSoftvolBackend,
        "pipewire": PipeWireBackend,
    }
    cls = backends.get(cfg.audio.backend)
    if cls is None:
        raise ValueError(f"unbekanntes Audio-Backend: {cfg.audio.backend!r}")
    return cls(cfg)
