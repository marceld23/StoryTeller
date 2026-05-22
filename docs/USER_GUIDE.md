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

On `run` without `--world` you first hear the **world menu**: *"Which
world…?"* — answer naturally, e.g. *"something in space"* → Starfaring,
*"dragons and magic"* → Everwood. (Recognition is LLM-based, so free phrasing
works.) Each world resumes where you last left it; pass `--new` to start it
over from scratch.

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
3. You hear: *quit, undo turn, audio (Bluetooth) on/off, intro on/off,
   close menu.*
4. Answer freely. Then the last narrator message is replayed and play
   continues.

In **chat** mode there is no spoken menu — type `/undo` to roll back a turn,
`/state` to inspect, `/quit` (or Ctrl-D) to exit.

## Sessions & resuming

There is no manual save/load — every turn is **checkpointed automatically**
(LangGraph `SqliteSaver` in `data/checkpoints.db`). Each world has a stable
session, so simply starting that world again continues where you stopped.
"Undo" rolls back one turn. To begin a world fresh, start with `--new`.

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
