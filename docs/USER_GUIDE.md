# User Guide — playing Storyteller

Storyteller is an interactive, voice-controlled narrator. You don't pick from
menus — you **speak (or type) freely** and the narrator weaves your actions
into the story, following a dramatic arc.

## Starting

- **Pi / voice:** `uv run --package storyteller-pi storyteller-pi run`
  (or it autostarts via systemd).
- **PC / text:** `uv run --package storyteller-cli storyteller-cli chat`.
- **Browser:** open the player UI at `http://<host>:8090` (play backend
  running); pick a world, then play by text or tap-to-talk voice
  (click or spacebar to start/stop the recording).

## Boot sequence (Pi / voice)

1. After power-on you hear a single short greeting: *"Hello, I'm your
   storyteller. When you're ready, wake me with Hey Jarvis."*
   (Toggle: *intro on/off* in the system menu.)
2. The Pi **idles silently** with the LED ring green. Nothing happens
   until you say the wake word.
3. Say **"Hey Jarvis"**. The system answers: *"Would you like to get
   started?"* — answer *yes* to continue, *no* (or stay silent) to drop
   back into idle. **Shortcut:** if you also name a world in the yes
   answer (*"Yes, Starfaring please"* / DE: *"Ja, ich will die
   Scify-Welt spielen"*), the Pi skips the mode question and the
   world menu and jumps straight into that world.
4. *"Do you want to play a world or manage worlds?"* (DE: *"Möchtest
   du eine Welt spielen oder Welten verwalten?"*) — only asked when
   step 3's answer didn't already pick a world.
   * **Play** (DE: **Spielen**) → the world menu opens (*"Which
     world…?"*): answer naturally, e.g. *"something in space"* →
     Starfaring, *"dragons and magic"* → Everwood. (Recognition is
     LLM-based, so free phrasing works.) Each world resumes where
     you last left it.
   * **Manage** (DE: **Verwalten**) → the
     [world-management menu](#managing-worlds) opens: new world,
     copy, rename, or delete (see below).
   Pass `--new` to start a world over from scratch.
5. **Once a world is picked**, just before the first narration you
   hear the in-story commands briefing (Note / Repeat / Menu / End
   story / Shutdown — DE: Vermerken / Wiederhole / Menü / Geschichte
   beenden / Schluss — plus the wake-hint). Toggle off via the
   system menu (*commands info on/off*) if you don't want to hear
   it every session.

### Managing worlds

When you answer *"manage"* (DE: *"verwalten"*) at the mode question
— or use any management-flavoured word like *"new world"*, *"copy"*,
*"rename"*, *"delete"* (DE: *"neue Welt"*, *"kopieren"*,
*"umbenennen"*, *"löschen"*) — Jarvis opens the world management
sub-menu. Single-shot UX: one action per visit, then back to the
wake-word idle.

1. *"You're in management mode. You can say: New world, Copy world,
   Rename world, or Delete world. Say Cancel to go back."* (DE:
   *"Du bist im Verwaltungs-Modus. Du kannst sagen: Neue Welt, Welt
   kopieren, Welt umbenennen, oder Welt löschen. Mit Abbrechen
   geht's zurück."*)
2. *"What would you like to do?"* (DE: *"Was möchtest du machen?"*)
   — say one of:
   * **New world** (DE: **Neue Welt**) → drops into the
     [voice-mode world design](#voice-mode-world-design).
   * **Copy world** (DE: **Welt kopieren**) → asks which world,
     then for the new name. Confirms with yes/no. The copy gets
     the suffix " (Copy)" / " (Kopie)" by default unless you give
     it a different name; saves stay attached to the source (the
     copy is a fresh world definition).
   * **Rename world** (DE: **Welt umbenennen**) → asks which world,
     then for the new name. Confirms with yes/no. Saved games
     migrate to the new id automatically (`pi-<old>` → `pi-<new>`
     in `data/checkpoints.db`), and the RAG index is repointed in
     place (no costly re-embed).
   * **Delete world** (DE: **Welt löschen**) → asks which world,
     then a destructive confirmation (*"…world data and save will
     be lost. Yes or no?"* / DE: *"…Welt-Daten und Spielstand
     gehen verloren. Ja oder Nein?"*). Cleans up JSON + RAG
     embeddings + Pi saves.
   * **Cancel** (DE: **Abbrechen**) at any prompt → cancels and
     returns to wake-word idle.
3. After the action Jarvis says *"Done."* (DE: *"Erledigt."*) and
   goes back to the wake-word idle (the device says *"I'm no
   longer actively listening — say Hey Jarvis to wake me."* / DE:
   *"Ich höre jetzt nicht mehr aktiv zu — sag Hey Jarvis, um mich
   zu wecken."* once before going silent).

World selection inside the management menu uses the same free-form
LLM classifier as the play menu — say *"the Justus Sci-Fi one"* or
*"Starfaring"* / DE: *"die Justus-Scify"* or *"Sternenfahrt"* and
Jarvis picks the right world (STT artefacts like *"Scify / Sci-Fi /
Sai-Fai"* all match).

### Voice-mode world design

When you say *"new world"* (DE: *"neue Welt"*) in the management
menu, Jarvis walks you through a short interview to gather your
idea, then generates the world live. Step by step:

1. *"Let's design a new world together. I'll ask you a few questions —
   when you have enough details, just say Generate. Building the world
   afterwards can take one to three minutes."*
2. Jarvis asks a focused question — setting, your role as the player,
   tone, a central tension, the opening moment — one at a time. Answer
   freely; the next question builds on what you said.
3. After ~10 Q&A pairs Jarvis reminds you once that you can say
   *"Generate"* whenever you feel the picture is dense enough.
4. Say **"Generate"** (DE: **"Generieren"**) to end the interview.
5. *"I'm building the world — this takes one to three minutes. You'll
   hear an ambient wait-sound."* A neutral drone plays while the
   multi-step generation pipeline runs. **The generation itself
   can't be cancelled** — once you say *"Generate"* it runs through
   to completion.
6. When ready: *"The world `<name>` is ready. Start the story now, or
   back to the world menu? Say Start or Menu."* Saying **Start** drops
   you straight into the new world's opening; anything else lands you
   in the regular world menu (where the freshly saved world is now
   available alongside the seed worlds).

**During the interview** (before you say *"Generate"*) you can:

* **Stay silent** → after the next listening window times out, Jarvis
  switches into passive mode and plays *"I'm no longer actively
  listening — say Hey Jarvis to wake me again."* (DE: *"Ich höre
  jetzt nicht mehr aktiv zu, sag Hey Jarvis, um mich wieder zu
  wecken."*) Say *"Hey Jarvis"* to resume; the last question is
  re-read first, then the mic re-opens.
* **Cancel the interview** by saying any of *"cancel"*, *"stop"*,
  *"abort"*, *"quit"* (DE: *"abbrechen"*, *"stopp"*, *"beenden"*,
  *"schluss"*) as a short utterance (≤3 tokens). Jarvis confirms
  with *"World design cancelled. Say Hey Jarvis when you want to
  start again."* (DE: *"Weltdesign abgebrochen. Sag Hey Jarvis,
  wenn du wieder loslegen möchtest."*) and drops back to the
  wake-word idle. The same *"End story"* / *"Geschichte beenden"*
  phrase from the story loop also works.

A JSONL transcript of every interview lands in
`data/transcripts/_world_design-<utc-ts>.jsonl` for audit.

## Voice commands during a story

After saying **"Hey Jarvis"** (or in the follow-up window after the
narrator just spoke) you can say any of:

| Say | Effect |
|-----|--------|
| anything else | The narrator weaves it into the story. |
| **Note** (DE: **Vermerken**) — followed by a brief | Adds the brief as a player-introduced fact to this world. Indexed into RAG immediately, so the narrator can pick it up from the very next turn. The admin can later promote it to the canonical world via the *Notes* tab in the web admin. |
| **Repeat / Again** (DE: **Wiederhole / Sag das nochmal**) | Re-plays the last narration via TTS — no new story turn, no LLM call. Useful if you missed something. Matched as a SHORT phrase (≤3 tokens) so a mid-sentence "again" inside a real player input won't accidentally trigger it. |
| **Menu** (DE: **Menü / System**) | Opens the spoken system menu (save, end story, shutdown, undo, reset world, audio output, intro toggle, commands info toggle, close menu). |
| **End story** (DE: **Geschichte beenden**) | Saves the current game (every turn is auto-checkpointed anyway), plays a short confirmation, and drops back to the wake-word idle. Saying *"Hey Jarvis"* afterwards reopens the world menu. |
| **Shutdown / Power off** (DE: **Beenden / Schluss / Ausschalten**) | Powers the device off (`systemctl poweroff` — needs NOPASSWD sudo, see *docs/SETUP_PI.md*). Same as a long-press on the shutdown GPIO button. |

## Text REPL commands (CLI)

In `storyteller-cli chat` you can type these at any time:

| Command | Effect |
|---|---|
| `/undo` | Roll back the last turn. |
| `/state` | Print a JSON snapshot of session state (cost, beat, substory). |
| `/note <text>` | Add a player-introduced world fact (equivalent to the **Note** voice command, DE: **Vermerken**). Goes into the per-world JSONL + RAG, classified as person/place/item/fact via a small LLM call. |
| `/end` | Save (auto) and drop back to the world picker so you can pick another world or run `/create`. Process keeps running. |
| `/create <prompt>` | Generate a new world from your prompt synchronously (1–3 min). On success the new world is saved and immediately becomes the active session. |
| `/quit` (or `Ctrl-D`) | Exit the process entirely. |

If the daily cost cap is reached mid-turn, the CLI prints a clear "daily cap reached (X.XX / Y.YY USD)" line (DE: "Tagesbudget erreicht …") and returns to the prompt — the story state is already on disk and can be resumed after the admin resets the day.

## Web player UI

The browser-based player UI mirrors the same features as voice and CLI:

* **World picker** (text mode at `/`, voice mode at `/voice`). Worlds appear as **cards** (genre, your role, snippet) rather than a flat dropdown; the last world you played is highlighted with a ▶ *Resume* badge (DE: *Fortsetzen*) so resuming is one tap. A link to **"Create a new world"** (DE: *Neue Welt erstellen*) opens `/create`, where three vibe templates (Fantasy / Sci-Fi / Mystery — DE: *Fantasy / Sci-Fi / Krimi*) seed the prompt — pick one and adapt, or write from scratch. The page produces a new world (1–3 min synchronous request) and auto-selects it in the picker on success.
* **Session header** — once a story is running the header shows **the world name and genre** (not the internal `thread_id`). The 🌙 / ☀️ theme toggle and (voice mode) the 🔊 / 🔇 wait-sound toggle sit in the same header so they're out of the thumb zone.
* **In-game actions** (both text + voice pages):
  * **"+ Note"** (DE: *"+ Notiz"*) — opens a small textarea; the input is sent over WS as `{type: 'note', text}` and the backend wraps `create_user_note` (equivalent to the voice "Note" / "Vermerken" command).
  * **"End story"** (DE: *"Geschichte beenden"*) — asks for confirmation first (mis-click guard), then sends `{type: 'end_story'}`; the server closes the engine, the client drops back to the world picker. State is auto-saved as usual.
  * Errors are filtered to friendly one-liners (English: *"The storyteller is overloaded right now…"*, *"Lost connection to the storyteller…"* — DE: *"Der Erzähler ist gerade überlastet…"*, *"Verbindung zum Erzähler verloren…"*) instead of leaking Python exception reprs to the player.
* **Text mode** specifics:
  * The composer textarea stays **enabled while the narrator is generating** — you can pre-type the next move; only the **Send** button (DE: *Senden*) gates on `thinking=false`. Enter sends, Shift+Enter inserts a newline, and a live char-counter shows the configured `web.max_turn_chars` limit (input that overflows is highlighted red).
  * Each narrator line has an opt-in **🔊 button** (visible on hover / always on mobile) — clicking it fetches a one-shot TTS via `GET /api/sessions/<thread>/replay` and plays it without touching the chat state. Silent reading stays free; the click costs one TTS call.
  * Autoscroll only kicks in if the player is near the bottom; otherwise a **"new answer ↓" pill** (DE: *"neue Antwort ↓"*) appears so reading earlier text isn't interrupted.
* **Voice mode** specifics:
  * The push-to-talk button shows a **live mic-level meter** (five bars) plus the elapsed recording time `0:03`. A subtle hint under the button reminds the player of the **spacebar** shortcut (DE: *Leertaste*) and the **silence-stops-automatically** behaviour (DE: *stille-stoppt-automatisch*).
  * **VAD auto-stop** — after the player has spoken for ≥350 ms, ~1.5 s of silence ends the recording automatically (browser-side VAD; the existing tap-to-stop still works).
  * Saying *"Repeat"* / *"Again"* (DE: *"Wiederhole"* / *"Sag das nochmal"*) re-plays the last narration via TTS — no LLM call, no story turn. There's also a **🔁 Say it again** button (DE: *🔁 Sag das nochmal*) below the chat when no audio is playing, which calls the same `/replay` endpoint.
  * During narrator playback two distinct controls are exposed: **⏸ Pause** (purely local — resumes the same audio) and **✋ Interrupt** (DE: *Unterbrechen*) — local pause + sends `{type: 'interrupt'}` to the server.
  * Defensive WS handling: the binary frame is checked for `ArrayBuffer | Blob` instead of blindly wrapping `ev.data`, so a stray non-binary payload no longer crashes the audio path.
* **Daily cost cap pause** — when the server raises `DailyCapExceeded`, the WS sends `{type: 'daily_cap_exceeded', usd_today, cap_usd, message}`. Both pages show a red banner including the **current/cap USD** and a hint that the day resets at **midnight UTC** (or an admin can reset earlier). State on disk is untouched.
* **Wait-sound** — the voice page loops a soft ambient drone (same `generic_waiting.wav` the Pi uses) while the server is thinking. The 🔊 / 🔇 header toggle disables it and the preference persists in `localStorage` (`st-wait-sound`). The voice page also surfaces a red mic-warning banner when the browser refuses microphone access — typical reason: the page is loaded over plain `http://<lan-ip>:…` (no secure context). See [docs/SETUP_HTTPS.md](SETUP_HTTPS.md) for a one-shot HTTPS setup that unblocks voice from remote devices.

## Talking to the narrator (voice loop)

1. Say the wake word **"Hey Jarvis"**. The LED ring shows *listen*.
2. Speak your action freely — recording ends automatically when you pause,
   e.g. *"I open the echo recorder and listen closely."*
3. The LED shows *think* and a per-world ambience plays while the system
   works; then the narrator answers (LED *speak*).
4. **Follow-up:** right after the narrator finishes you may answer
   **directly without the wake word**. The mic stays open across several
   silent rounds (default ~18 s, configurable via
   `capture.silent_follow_patience`) so you have time to think between
   turns; only after the patience is exhausted does the system slip back
   to wake-word mode and briefly remind you to say *"Hey Jarvis"*.

Tips: ask short questions ("Who is Suri?") — you get a brief answer without
advancing the plot. The narrator keeps to a macro arc and dynamically
planned sub-stories, with occasional surprises that never derail the arc.

## System menu (during a story)

1. Be in listening mode (wake word, or the follow-up window).
2. Say just **"System"** (or "Menu") — short.
3. You hear: *save, quit, undo turn, **reset world**, audio (Bluetooth)
   on/off, intro on/off, commands info on/off, **Storymodus**, close menu.*
4. Answer freely (destructive actions like undo / reset ask a yes/no safety
   question first). Then the last narrator message is replayed and play
   continues.

## Storymodus (free vs. planned)

The narrator runs a **plot-pressure** dial that gradually fades the
planner / curator / beat-nudges in and out depending on how engaged
you are with the active arc. Three settings let you override it:

- **`Auto`** (default) — a heuristic per turn watches your inputs and
  decides how strongly to push toward the planned beats. You stay free
  to invent facts, ask world questions and improvise — that's still
  on-arc engagement. Only **consistent drift away from the active
  arc** (e.g. several turns of pure world-tourism, or explicit phrases
  like *"let's just…"* / DE: *"lass uns einfach…"*) gradually lowers
  the pressure.
- **`Plan`** (DE: same word, *Plan*) — pins full plot-pressure. The
  narrator always works on the planned arc and pushes for beat
  progress.
- **`Free`** (DE: **`Frei`**) — pins zero plot-pressure. The narrator
  becomes purely reactive: greets your ideas, lets the world breathe,
  no beat pressure, no anti-spoiler curator. The active arc (if any)
  is parked as `dormant_substory` — switching back to `Plan` or
  `Auto` resumes it where it was.

Set it via:
- **Pi voice (mid-story)** — say *"Story mode Free"* / *"Story mode
  Plan"* / *"Story mode Auto"* directly (DE: *"Storymodus frei"* /
  *"Storymodus Plan"* / *"Storymodus Auto"*), or open the system
  menu and pick "Story mode" / "Storymodus".
- **Admin UI** — Settings → Story mode → dropdown (DE: Einstellungen
  → Storymodus → dropdown).

The setting is global (per appliance), not per-world.

In **chat** mode there is no spoken menu — type `/undo` to roll back a turn,
`/state` to inspect, `/quit` (or Ctrl-D) to exit.

## Interrupting the narrator (barge-in)

Stop the narration whenever you want — the system then listens and figures
out what you said (system menu vs. a new story turn):

- **Pi** — press the optional GPIO push-button (off by default; see
  [SETUP_PI.md](SETUP_PI.md) for wiring + enabling in `config.toml`).
- **Web (`/voice`)** — the **Stop** button (DE: *Stopp*) under the
  microphone pauses the spoken playback.
- **CLI / chat** — press **Ctrl+C** while the narrator is generating to
  drop the in-progress turn and return to the prompt.

## Sessions & resuming

There is no manual save/load — every turn is **checkpointed automatically**
(LangGraph `SqliteSaver` in `data/checkpoints.db`). Each world has a stable
session, so simply starting that world again continues where you stopped —
with a short spoken recap of where the story left off. The system menu's
*reset world* (with a yes/no safety prompt) wipes that progress so the
world starts from the opening; the admin's **Saves** page (DE:
*Spielstände*) does the same with a button. "Undo" rolls back one turn.
`--new` starts a fresh branch without touching the saved one.

## Localization (German / English)

Repo default is **English** (`config [general] locale = en`). A
single deployment can be flipped to German via `STORYTELLER_LOCALE=de`
in `.env`, or per CLI run with `--locale de|en`. This changes
narration language, the menu/wait audio, world content and speech
recognition. The voice command examples in this guide annotate the
German equivalents in parentheses.

## Safety / moderation

Every player input is checked by the OpenAI moderation model **before** the
narrator answers. If it crosses a threshold the turn is refused politely.
Thresholds are configurable in the admin website (**Settings → Moderation**).

## Admin website

`http://<host>:8080` (Pi) or `http://localhost:8080` (PC) — create/edit
worlds, generate worlds from a prompt, view transcripts, and configure
models / endpoints / audio / moderation. Full walkthrough:
[ADMIN_GUIDE.md](ADMIN_GUIDE.md).

## Per-world dramaturgy (configurable in the admin)

Each world has its own story controls (Worlds → editor):

- **Complexity:** `simple` (short, calm patterns: vignette, three-act,
  kishōtenketsu, monster-of-week — few beats, low tension), `standard`
  (try/fail, mystery, seven-point, fichtean …), `rich` (hero's journey,
  Harmon story circle, Freytag, heist … — more beats, full tension).
- **Story patterns:** optional whitelist of specific patterns; empty = use
  the complexity's set. The planner picks one and instantiates its beat
  skeleton for each new substory.
- **Tone:** sliders 0–5 for darkness / humor / romance / action / horror,
  a pacing (slow/medium/fast) and free-text genre/tone notes — the narrator
  and the substory planner respect these.
- **Audience:** target group / age (e.g. "12+", "erwachsene") — steers
  content and vocabulary.
- **Voice sample:** 1–2 example sentences that anchor the narrative tone.

## Wi-Fi onboarding (Pi)

If the Pi finds no known Wi-Fi at boot it opens the AP **`storyteller-wifi`**
(WPA2, password from config). Connect a phone — a captive page pops up
automatically; pick your Wi-Fi, enter the key. The Pi saves it, reboots and
uses it from then on. (`storyteller-pi netcheck --check` reports connectivity
without ever starting the AP.)

## Quitting

Say "quit"/"beenden" (or via the system menu), or Ctrl-C. The session is
already checkpointed, so nothing is lost.
