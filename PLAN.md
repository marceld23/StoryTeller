# Storyteller — Umsetzungsplan

Interaktiver, sprachgesteuerter Geschichtenerzähler auf Raspberry Pi 4 mit
ReSpeaker USB Mic Array v2.0, OpenAI-API und lokaler Wake-Word-Erkennung.

> Status dieses Dokuments: **lebender Plan**. Phasen werden iterativ umgesetzt.
> Entscheidungen sind unten in „Festgelegte Entscheidungen" dokumentiert.

---

## 1. Festgelegte Entscheidungen

| Thema | Entscheidung | Begründung |
|---|---|---|
| Audio-Architektur | Getrennte Pipeline **STT → LLM → TTS** (nicht Realtime-API) | Deterministisches RAG-Einspeisen + Reverb-Effekt auf die Stimme nur so sauber möglich |
| Audio-Ausgabe | **Austauschbares Backend**; jetzt: ALSA `softvol` (ReSpeaker Line-Out); später: PipeWire-Sink (Bluetooth) | Erfüllt „Lautstärke per ALSA-softvol" jetzt; Bluetooth später ohne Umbau |
| Wake-Word | **openWakeWord** (self-hosted, kein Account) | Vollständig lokal/unabhängig |
| STT | **Provider-Abstraktion**; Default `gpt-4o-mini-transcribe` (OpenAI); optional **lokales Whisper** später | Niedrige Latenz, gutes Deutsch; lokal nur auf Pi 5 + AI HAT sinnvoll |
| TTS | **Provider-Abstraktion**; Default `gpt-4o-mini-tts` PCM (OpenAI); optional **lokales TTS** später | Whisper kann **kein** TTS; PCM-Stream ideal für Reverb; lokal nur auf Pi 5 + AI HAT |
| Story-LLM (Default) | `gpt-5.4-mini` | Wunsch des Nutzers; konfigurierbar |
| Embeddings (Default) | `text-embedding-3-small` (dim 512) | Preis/Qualität, klein auf dem Pi |
| RAG-Store | **sqlite-vec** (eine DB-Datei, `world_id` als partition key) | Winzig, aarch64/py3.13-Wheels, saubere Welt-Isolation |
| Audio-Effekt | **Spotify `pedalboard`** (Reverb/Distortion) | Fertige aarch64/py3.13-Wheels, CPU-günstig, in-process |
| Paket-/Env-Mgmt | **uv** + Python 3.13 | Wunsch des Nutzers |
| Web-Admin | FastAPI + Jinja2/HTMX (leichtgewichtig) | Klein genug für den Pi |
| Sprachmenü-Audio | **Voice-Prompt-Cache**: statische Ansagen einmalig rendern & als Audio ablegen, ohne API abspielen | Token + Latenz sparen |
| Substory-System | Makro-Blueprint + dynamisch geplante **Substories** (Statusmaschine), Plan per Tool/Injection anpassbar | Spannungsbogen halten, Spieler einbinden, nicht aus dem Ruder laufen |
| Story-Dynamik | Abstrakte Zufallswendungen (Tool + Auto-Injection + Planung), bogentreu | Überraschung „ohne die Story zu kippen" |
| Alle Modellnamen | **konfigurierbar** in `config/config.toml` | Wunsch des Nutzers |

---

## 2. Hardware-Setup (ReSpeaker USB Mic Array v2.0)

USB-ID `2886:0018`, ALSA `card ArrayUAC10`. **Kein** Hardware-Lautstärkeregler →
ALSA `softvol`-Plugin (offiziell von Seeed für genau dieses Gerät empfohlen).

1. **udev-Regel** `/etc/udev/rules.d/60-respeaker.rules` (einmalig, Root, via
   `scripts/setup_system.sh`) — non-root-Zugriff für LED-Ring + DSP-Tuning.
2. **ALSA softvol** über `~/.asoundrc` (userland, kein Root):
   `plug:respeaker_softvol` als Playback mit `amixer`-Control `Master` auf
   `card ArrayUAC10`; Capture via `dsnoop` (16 kHz, mono).
3. **pixel_ring v2** Modul vendored (`src/storyteller/hardware/pixel_ring_v2.py`)
   — die offizielle Lib ist seit 2021 unmaintained, der v2-USB-Pfad aber
   simpel & Python-3.13-tauglich.
4. **tuning.py** vendored + Python-3.13-Patch (`.tostring()` → `.tobytes()`).
5. Default-Firmware (1-Kanal, beamformed Mono) ist optimal für STT → **kein
   Reflash** nötig.

Lautstärke-API: `amixer -c ArrayUAC10 sset Master <pct>%`.

---

## 3. Architektur

```
                    ┌─────────────── Voice-Loop (Spielmodus) ───────────────┐
                    │                                                       │
  Mic (ReSpeaker) ──┤ openWakeWord ──► STT (OpenAI) ──► Story-Engine ──┐    │
                    │     ▲                                  │         │    │
                    │     │                                  ▼         │    │
  LED-Ring ◄────────┤  LED-State-Machine            RAG (sqlite-vec)   │    │
                    │  (wake/listen/think/speak)    Blueprint/Spannung  │    │
  Wartesound-Loop ◄─┤                               Known-Facts-Tool   │    │
                    │                               Random-Events      │    │
  Speaker ◄─────────┤ Audio-Backend ◄─ Reverb (pedalboard) ◄─ TTS ◄────┘    │
   (Line-Out/BT)    │ (ALSA softvol / PipeWire)                             │
                    └───────────────────────────────────────────────────────┘

  Web-Admin (FastAPI)  ──►  Welten/Fakten/Personen/Orte/Blueprints/Random-Tabellen
                            (LLM-gestütztes Schreiben von Fakten)
```

### 3.1 Module (`src/storyteller/`)

| Paket | Inhalt |
|---|---|
| `config.py` | Laden/Validieren von `config.toml` + `.env`; alle Modellnamen, Pfade, Audio-Backend, Wake-Word, Effekt-Parameter |
| `audio/backend.py` | `AudioBackend` (ABC) + `AlsaSoftvolBackend` (jetzt) + `PipeWireBackend` (Bluetooth, später). Gerät & Lautstärke konfigurierbar, zur Laufzeit umschaltbar (Sprachmenü) |
| `audio/player.py` | PCM-Stream-Wiedergabe (sounddevice), mischt Wartesound-Loop & TTS |
| `audio/recorder.py` | Mic-Aufnahme (16 kHz mono) für Wake-Word + STT |
| `hardware/pixel_ring_v2.py` | Vendored LED-Treiber (USB) |
| `hardware/leds.py` | High-Level LED-Zustände: `idle/wake/listen/think/speak/error` |
| `hardware/tuning.py` | Vendored + py3.13-Patch; DSP-Parameter (DOA/AGC/NS) |
| `voice/wakeword.py` | openWakeWord-Wrapper (eigenes deutsches Wort) |
| `voice/stt.py` | **STT-Provider-Abstraktion**: `OpenAISTT` (Default), `LocalWhisperSTT` (optional, Pi 5 + AI HAT) |
| `voice/tts.py` | **TTS-Provider-Abstraktion**: `OpenAITTS` PCM (Default), `LocalTTS` (optional, Pi 5 + AI HAT) |
| `voice/fx.py` | pedalboard-Reverb/Distortion, **pro Welt** parametrierbar |
| `voice/waitloop.py` | Welt-spezifischer Wartesound **gapless** in Schleife (stdin-Stream) während LLM-Wartezeit |
| `audio/ambient.py` | Prozedurale, nahtlos loopbare Ambience pro Welt (Mood: space/forest), offline; `storyteller wait-sounds build` |
| `voice/prompts.py` | **Voice-Prompt-Cache**: feste Ansagen-Katalog → einmalig via TTS gerendert, ohne API abgespielt (Token-Ersparnis) |
| `story/engine.py` | Orchestrierung v2: Co-Creation-Prompt, Tool-Calls, **Substory-Statusmaschine**, Cost-Cap, snapshot/restore. **Spieler gestaltet aktiv mit** — freie Spracheingabe wird aufgegriffen, keine Multiple-Choice |
| `story/substory.py` | **SubstoryPlan + SubstoryPlanner + NarrativeState**: erkennt „in Substory" vs. „abgeschlossen", plant via RAG+Kontext eine neue Substory, per Tool/Prompt-Injection abfragbar/anpassbar |
| `story/dynamics.py` | **Abstrakte Story-Dynamik** (Antagonist/Unvorhergesehenes …): Tool `roll_story_dynamic` + dezente Auto-Injection + Einplanung — als Würze, ohne den Bogen zu kippen |
| `story/cost.py` | Token-/Kostenschätzung + Session-Deckel (sanfter Abschluss) |
| `util/log.py` | Logging (Datei + Konsole) |
| `story/rag.py` | sqlite-vec, per-Welt-Retrieval, Metadaten-Filter (place/person/fragment) |
| `story/blueprint.py` | „Baupläne" = Beat-Plan + Spannungsbogen; hält die Story in der Spur |
| `story/knowledge.py` | Tool: dem Spieler bekannte Orte/Personen verwalten & abfragen |
| `story/random_events.py` | Welt-spezifische Zufallstabellen, vom LLM als Tool aufrufbar |
| `worlds/schema.py` | Pydantic-Modelle: World/Place/Person/Fragment/Blueprint/RandomTable |
| `worlds/seed.py` | 2 Default-Welten (Sci-Fi / High-Fantasy) |
| `menu/voice_menu.py` | Sprachgesteuertes Systemmenü: Welt wählen, laden, speichern |
| `persistence/saves.py` | Spielstände speichern/laden (JSON + RAG-Snapshot-Ref) |
| `web/app.py` | Admin-Frontend: Welten/Fakten CRUD + LLM-gestütztes Fakten-Schreiben |
| `cli.py` | Entrypoints: `storyteller run` / `admin` / `hw-test` / `seed` |

### 3.2 Datenmodell (Welt)

```
World
 ├─ id, name, genre
 ├─ description            (Spiel-/Weltbeschreibung)
 ├─ player_role            (Spielerrolle)
 ├─ starting_situation     (Ausgangssituation)
 ├─ narration_style        (Erzählton, technisch)
 ├─ mood                   (Grundstimmung)
 ├─ ambience               (Sinneseindrücke / Atmosphäre)
 ├─ magic_physics          (Physik- bzw. Magiesystem, Regeln)
 ├─ places[]      (name, description, tags)
 ├─ persons[]     (name, role, description, relations, tags)
 ├─ items[]       (name, description, properties, tags)
 ├─ glossary[]    (term, definition)            ← Begriffserklärung
 ├─ history[]     (when, title, description)
 ├─ fragments[]   (title, text, tags)           ← Lore / Hooks
 ├─ blueprint     (premise, beats[name,goal,tension], escalation_rule)
 ├─ random_tables[] (name, description, entries[weight,text])  ← konkret, genutzt
 └─ wait_sound, fx_preset
places/persons/items/glossary/history/fragments + mood/ambience/magic
 → in sqlite-vec embeddet (RAG), gefiltert per world_id + fact_type
   (place|person|item|glossary|history|fragment|system).
Alle Felder im Backend anlegbar/editierbar (auch LLM-gestützt).
```

### 3.3 Story-Engine — „nicht auf der Schiene"

- Spieler spricht **frei** (kein Aktionsmenü). STT → Engine.
- Engine baut Prompt aus: Welt-Kontext (Beschreibung, Stimmung, Ambiente,
  Physik/Magie, Glossar-Auszug, Zufallslisten-Namen) + Makro-Blueprint +
  aktuelle Substory + RAG-Treffer + Kurzzeitgedächtnis + bekannte Fakten.
- LLM = Erzähler **mit Tools für gezielten Weltzugriff**:
  `get_world_overview`, `retrieve_world_fact(fact_type)`, `lookup_glossary`,
  `roll_random_event` (welt-eigene Listen), `roll_story_dynamic` (abstrakt),
  `remember_fact`, `advance_beat`, `complete_substory`,
  `get_/adjust_substory_plan`.
- Blueprint hält Spannungsbogen: Engine prüft Beat-Fortschritt, gibt dem LLM
  Leitplanken („wir sind in Beat 3/7, Eskalation steigt"), ohne den Spieler zu
  gängeln. Spieler-Ideen werden in `Fragments`/Kurzzeitgedächtnis aufgenommen
  und vom LLM weitergesponnen.

---

## 4. Phasenplan (iterativ)

- **Phase 0 — Setup & Gerüst** *(dieser Schritt)*: uv-Projekt, Config, Schema,
  2 Seed-Welten, Audio-Backend-Abstraktion, Hardware-Module vendored,
  `hw-test`-CLI, ALSA softvol, udev-Script.
- **Phase 1 — Hardware-Bring-up**: softvol/amixer, Mic-Aufnahme, LED-Ring,
  Tuning verifizieren (Akzeptanz: Ton raus + leiser/lauter, Aufnahme rein,
  LED-Muster, `tuning -p`).
- **Phase 2 — Audio-Pipeline**: Recorder → STT → (Echo) → TTS → Reverb →
  Backend. Wartesound-Loop + LED-States. Latenz messen.
- **Phase 3 — Wake-Word**: openWakeWord integrieren, eigenes DE-Wort trainieren,
  Mic-Gating.
- **Phase 4 — RAG & Welten**: sqlite-vec, Embeddings, Retrieval pro Welt,
  Seed-Import.
- **Phase 5 — Story-Engine**: Prompt-Bau, Tools, Blueprint/Spannungsbogen,
  Known-Facts, Random-Events.
- **Phase 6 — Sprachmenü & Persistenz**: Welt wählen/laden/speichern per Stimme. **Alle statischen Menü-Ansagen über den Voice-Prompt-Cache** (`voice/prompts.py`) — einmalig gerendert (`storyteller voice-prompts build`, braucht Phase-2-TTS), danach ohne API/Token abgespielt. Cache neu bauen, wenn TTS-Stimme/-Modell oder Texte sich ändern; Live-TTS-Fallback optional.
- **Phase 7 — Web-Admin**: CRUD + LLM-gestütztes Fakten-Schreiben.
- **Phase 8 — Bluetooth-Backend**: PipeWire-Sink-Implementierung hinter der
  bestehenden Abstraktion + Umschalten im Sprachmenü.
- **Phase 9 — Politur**: systemd-Service, Fehler-/Reconnect-Handling,
  Kostendeckel, Logging.
- **Phase 10 — Lokale Sprachmodelle (optional, Hardware-abhängig)**: lokales
  Whisper-STT + lokales TTS hinter der bestehenden Provider-Abstraktion
  (`voice/stt.py` / `voice/tts.py`). **Voraussetzung: Raspberry Pi 5 + AI HAT
  (NPU)** — auf dem aktuellen Pi 4 nicht latenz-tauglich. Vorteil: offline,
  keine API-Kosten, Datenschutz. Per Config umschaltbar (OpenAI ↔ lokal).
- **Phase 11 — WLAN-Onboarding (für später eingeplant)**: Ist beim Start kein
  bekanntes WLAN erreichbar, spannt der Pi einen eigenen **Access Point** auf
  (Fallback-Hotspot). Ein **Captive-Portal / Setup-Webseite** zeigt die
  verfügbaren Netze (Scan), nimmt SSID-Auswahl + WLAN-Schlüssel entgegen,
  speichert die Verbindung und der Pi verbindet sich damit und macht normal
  weiter (Reboot/Reconnect). Umsetzungsoptionen: NetworkManager (`nmcli
  device wifi`, AP-Profil) oder `hostapd`+`dnsmasq`; fertige Bausteine zur
  Orientierung: balena `wifi-connect`, `comitup`, `RaspiWiFi`. Eigene kleine
  FastAPI/Flask-Setup-Seite analog zum Backend; sauber vom Story-Web-Admin
  getrennt (eigener Port/Service, nur im AP-Modus aktiv). Sicherheitsnote:
  AP nur temporär, WPA2 auf dem Setup-AP, Schlüssel nie loggen.

### Umsetzungsstand

- ✅ **Phase 0–9 implementiert & getestet**: Setup/HW, Voice-Pipeline
  (STT→LLM→TTS→Reverb→Line-Out), Wake-Word (Default „hey jarvis", PTT-Fallback),
  RAG, **Story-Engine v2 mit Substory-Statusmaschine + abstrakter Story-Dynamik**,
  Sprachmenü, Spielstände (save/load, auch per Stimme), Web-Admin, Kostendeckel,
  Logging, systemd-Unit.
- 🟡 **Phase 8 (Bluetooth)**: `PipeWireBackend` + `scripts/setup_bluetooth.sh`
  vorhanden, aber **auf diesem Pi nicht testbar** (kein PipeWire installiert/aktiv).
  Aktivierung: Script ausführen, `[audio] backend = "pipewire"` setzen.
- ⏳ **Phase 10 (lokale Modelle)**: bewusst offen — braucht Pi 5 + AI HAT.

---

## 5. Risiken / offene Punkte

- openWakeWord: läuft jetzt mit **Default-Wort „hey jarvis"** (ONNX). Install
  reproduzierbar via `scripts/install_wakeword.sh` (= `--no-deps openwakeword`
  + `onnxruntime requests scipy scikit-learn` + Modell-Download; tflite-runtime
  wird umgangen, da keine py3.13-Wheels). Eigenes **deutsches** Wort später per
  Colab-Training (.onnx) + `config.wakeword.model`. Ohne openWakeWord:
  automatischer Push-to-talk-Fallback (Enter), Loop läuft trotzdem.
- OpenAI-Latenz: Wartesound-Loop + LED kaschieren; ggf. TTS-Streaming so früh
  wie möglich starten.
- Reverb pro Welt: dezente Defaults, übersteuerte Distortion vermeiden.
- Kosten: STT+LLM+TTS pro Zug — Kostendeckel/Logging in Phase 9.
- PipeWire vs. ALSA-softvol: App adressiert Geräte explizit über die
  Backend-Abstraktion (vermeidet Konflikt, wenn später PipeWire für Bluetooth
  dazukommt); `~/.asoundrc` setzt `!default` nur user-scoped als Komfort.
- Lokale Sprachmodelle (Phase 10) brauchen **Pi 5 + AI HAT**; auf dem
  jetzigen Pi 4 nur OpenAI-Provider praktikabel. Abstraktion ist von Anfang
  an vorhanden, damit kein Umbau nötig wird.

---

## 6. Default-Welten (Seed)

1. **„Sternenfahrt" (Sci-Fi)** — Menschen reisen mit Hyperraum-Technologie
   durchs All; viele Welten. Spieler = **Raumschiffkapitän**.
2. **„Das Immerwald-Reich" (High-Fantasy)** — epische High-Fantasy-Welt.
   Spieler = **Waldläufer**.

Details/Startfakten/Blueprints siehe `src/storyteller/worlds/seed.py`.
