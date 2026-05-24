# User Guide — playing Storyteller

Storyteller is an interactive, voice-controlled narrator. You don't pick from
menus — you **speak (or type) freely** and the narrator weaves your actions
into the story, following a dramatic arc.

## Starting

- **Pi / voice:** `uv run --package storyteller-pi storyteller-pi run`
  (or it autostarts via systemd).
- **PC / text:** `uv run --package storyteller-cli storyteller-cli chat`.
- **Browser:** open the player UI at `http://<host>:8090` (play backend
  running); pick a world, then play by text or hold-to-talk.

## Boot sequence (Pi / voice)

1. After power-on you hear a short greeting: *"Hi, I'm Jarvis, your
   storyteller. Say Hey Jarvis when you want to hear a story."*
2. Then a one-time commands info lists what you can say during play
   (Note, Menu / System, End story, Shutdown). Both pieces can be
   toggled off independently in the system menu (*intro on/off* and
   *commands info on/off*).
3. The Pi **idles silently** with the LED ring green. Nothing happens
   until you say the wake word.
4. Say **"Hey Jarvis"**. The system answers: *"Would you like to get
   started?"* — answer *yes* to continue, *no* (or stay silent) to drop
   back into idle.
5. *"Would you like to play an existing world, or create a new one?"*
   * **Existing** → the world menu opens (*"Which world…?"*): answer
     naturally, e.g. *"something in space"* → Starfaring, *"dragons
     and magic"* → Everwood. (Recognition is LLM-based, so free
     phrasing works.) Each world resumes where you last left it.
   * **New** → the [voice-mode world design](#voice-mode-world-design)
     starts (see below).
   Pass `--new` to start a world over from scratch.

### Voice-mode world design

When you say *"new world"* at the mode question, Jarvis walks you
through a short interview to gather your idea, then generates the
world live. Step by step:

1. *"Let's design a new world together. I'll ask you a few questions —
   when you have enough details, just say Generate. Building the world
   afterwards can take one to three minutes."*
2. Jarvis asks a focused question — setting, your role as the player,
   tone, a central tension, the opening moment — one at a time. Answer
   freely; the next question builds on what you said.
3. After ~10 Q&A pairs Jarvis reminds you once that you can say
   *"Generate"* whenever you feel the picture is dense enough.
4. Say **"Generate"** (or *"Generieren"*) to end the interview.
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
  switches into passive mode and plays *"Ich höre jetzt nicht mehr
  aktiv zu, sag Hey Jarvis, um mich wieder zu wecken."* Say *"Hey
  Jarvis"* to resume; the last question is re-read first, then the
  mic re-opens.
* **Cancel the interview** by saying any of *"abbrechen"*, *"stopp"*,
  *"beenden"*, *"schluss"* (en: *"cancel"*, *"stop"*, *"abort"*,
  *"quit"*) as a short utterance (≤3 tokens). Jarvis confirms with
  *"Weltdesign abgebrochen. Sag Hey Jarvis, wenn du wieder loslegen
  möchtest."* and drops back to the wake-word idle. The same
  *"Geschichte beenden"* phrase from the story loop also works.

A JSONL transcript of every interview lands in
`data/transcripts/_world_design-<utc-ts>.jsonl` for audit.

## Voice commands during a story

After saying **"Hey Jarvis"** (or in the follow-up window after the
narrator just spoke) you can say any of:

| Say | Effect |
|-----|--------|
| anything else | The narrator weaves it into the story. |
| **Vermerken / Note** — followed by a brief | Adds the brief as a player-introduced fact to this world. Indexed into RAG immediately, so the narrator can pick it up from the very next turn. The admin can later promote it to the canonical world via the *Notizen* tab in the web admin. |
| **Menü / System / Menu** | Opens the spoken system menu (save, end story, shutdown, undo, reset world, audio output, intro toggle, commands info toggle, close menu). |
| **Geschichte beenden / End story** | Saves the current game (every turn is auto-checkpointed anyway), plays a short confirmation, and drops back to the wake-word idle. Saying *"Hey Jarvis"* afterwards reopens the world menu. |
| **Beenden / Schluss / Ausschalten / Shutdown** | Powers the device off (`systemctl poweroff` — needs NOPASSWD sudo, see *docs/SETUP_PI.md*). Same as a long-press on the shutdown GPIO button. |

## Talking to the narrator (voice loop)

1. Say the wake word **"Hey Jarvis"**. The LED ring shows *listen*.
2. Speak your action freely — recording ends automatically when you pause,
   e.g. *"I open the echo recorder and listen closely."*
3. The LED shows *think* and a per-world ambience plays while the system
   works; then the narrator answers (LED *speak*).
4. **Follow-up:** right after the narrator finishes you may answer
   **directly without the wake word**. If you stay silent it goes idle and
   briefly reminds you to say *"Hey Jarvis"* to wake it again.

Tips: ask short questions ("Who is Suri?") — you get a brief answer without
advancing the plot. The narrator keeps to a macro arc and dynamically
planned sub-stories, with occasional surprises that never derail the arc.

## System menu (during a story)

1. Be in listening mode (wake word, or the follow-up window).
2. Say just **"System"** (or "Menu") — short.
3. You hear: *save, quit, undo turn, **reset world**, audio (Bluetooth)
   on/off, intro on/off, close menu.*
4. Answer freely (destructive actions like undo / reset ask a yes/no safety
   question first). Then the last narrator message is replayed and play
   continues.

In **chat** mode there is no spoken menu — type `/undo` to roll back a turn,
`/state` to inspect, `/quit` (or Ctrl-D) to exit.

## Interrupting the narrator (barge-in)

Stop the narration whenever you want — the system then listens and figures
out what you said (system menu vs. a new story turn):

- **Pi** — press the optional GPIO push-button (off by default; see
  [SETUP_PI.md](SETUP_PI.md) for wiring + enabling in `config.toml`).
- **Web (`/voice`)** — the **Stopp** button under the microphone pauses
  the spoken playback.
- **CLI / chat** — press **Ctrl+C** while the narrator is generating to
  drop the in-progress turn and return to the prompt.

## Sessions & resuming

There is no manual save/load — every turn is **checkpointed automatically**
(LangGraph `SqliteSaver` in `data/checkpoints.db`). Each world has a stable
session, so simply starting that world again continues where you stopped —
with a short spoken recap of where the story left off. The system menu's
*reset world* (with a yes/no safety prompt) wipes that progress so the
world starts from the opening; the admin's **Spielstände** page does the
same with a button. "Undo" rolls back one turn. `--new` starts a fresh
branch without touching the saved one.

## Localization (German / English)

Set `config [general] locale = de | en`, or per run `--locale de|en`. This
changes narration language, the menu/wait audio, world content and speech
recognition. German prompts are kept verbatim.

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
