"""Localization (de / en).

Design decision: the DE strings are kept VERBATIM identical to the original
German prompts (zero behaviour change for `de`). EN adds equivalents. Only
user-facing language is localized (voice-prompt audio, world content,
narration language, menu keywords, STT language). Internal behavioural
meta-instructions that the model simply obeys may remain German for `de`;
for `en` an explicit "Respond in English." is injected so output, planning
and world handling are fully English.
"""

from __future__ import annotations

DEFAULT_LOCALE = "de"
LOCALES = ("de", "en")


def norm(locale: str | None) -> str:
    loc = (locale or DEFAULT_LOCALE).lower()
    return loc if loc in LOCALES else DEFAULT_LOCALE


# --- Static voice-prompt texts (rendered to audio per locale) ---
VOICE_PROMPTS: dict[str, dict[str, str]] = {
    "de": {
        "welcome": "Hallo, ich bin dein Erzähler. Wenn du bereit bist, "
                    "weck mich mit Hey Jarvis.",
        "choose_world": "Welche Welt möchtest du spielen?",
        "world_sternenfahrt": "Sternenfahrt. Du bist Raumschiffkapitän.",
        "world_immerwald": "Das Immerwald-Reich. Du bist Waldläufer.",
        "menu_hint": "Du kannst sagen: neue Geschichte, Spielstand laden, "
                     "oder Geschichte speichern.",
        "not_understood": "Das habe ich nicht verstanden. Bitte wiederhole es.",
        "listening": "Ich höre.",
        "starting": "Die Geschichte beginnt.",
        "saved": "Die Geschichte wurde gespeichert.",
        "no_saves": "Es gibt keine gespeicherten Spielstände.",
        "goodbye": "Bis zum nächsten Mal.",
        "error_retry": "Es gab gerade eine Störung. Sag es bitte noch einmal.",
        # Differenzierte Fehler-Ansagen (siehe storyteller_core.health). Der
        # Pi-Loop wählt basierend auf EndpointError.kind die passende WAV
        # aus; error_retry bleibt der Fallback für unbekannte Fehler.
        "error_offline_cloud": "Ich kann gerade nicht ins Netz. Bitte sag "
                                 "einem Erwachsenen, dass das Internet weg "
                                 "ist.",
        "error_offline_local": "Mein Erzähler-Computer zuhause antwortet "
                                 "gerade nicht. Bitte sag einem Erwachsenen, "
                                 "dass er nachschauen soll.",
        "error_auth": "Mein Zugang passt nicht. Ein Erwachsener muss "
                       "das in den Einstellungen prüfen.",
        "error_busy": "Die Erzähler-Wolke ist gerade voll. Ich versuch's "
                       "gleich nochmal — frag mich in einer Minute.",
        "sys_menu": "Systemmenü. Sage: speichern, beenden, Spielzug zurück, "
                    "Welt zurücksetzen, Audio umschalten, Einführung, "
                    "Storymodus, oder Menü schließen.",
        "story_mode_ask": "Storymodus wählen: sage Auto, Plan, oder Frei.",
        "story_mode_set_auto": "Storymodus auf automatisch. Ich entscheide "
                                "nach deinem Spielverhalten.",
        "story_mode_set_planner": "Storymodus auf Plan. Ich folge immer "
                                    "einem Bogen.",
        "story_mode_set_free": "Storymodus auf frei. Du gestaltest, ich "
                                "reagiere.",
        "story_mode_unclear": "Das habe ich nicht verstanden. Sage Auto, "
                                "Plan, oder Frei.",
        "undone": "Der letzte Spielzug wurde zurückgenommen.",
        "confirm_reset": "Willst du diese Welt wirklich zurücksetzen? Der "
                         "ganze Spielstand geht verloren. Sage ja oder nein.",
        "confirm_undo": "Willst du den letzten Spielzug wirklich "
                        "zurücknehmen? Sage ja oder nein.",
        "cancelled": "Abgebrochen. Weiter geht's.",
        "world_reset": "Diese Welt wurde zurückgesetzt. Wir beginnen von vorn.",
        "closed": "Menü geschlossen. Weiter geht's.",
        "wake_hint": "Ich höre jetzt nicht mehr aktiv zu. Sag Hey Jarvis, "
                     "um mich wieder zu wecken.",
        "post_opening_hint": "Du kannst jetzt direkt antworten — ich höre. "
                              "Sonst sag Hey Jarvis, um mich zu wecken.",
        "wifi_setup": "Kein WLAN gefunden. Verbinde dein Handy mit dem "
                      "WLAN storyteller-wifi. Es öffnet sich automatisch "
                      "eine Seite, auf der du dein WLAN auswählen und das "
                      "Passwort eingeben kannst. Danach starte ich neu.",
        "audio_bt_on": "Audioausgabe auf Bluetooth umgestellt.",
        "audio_bt_off": "Audioausgabe zurück auf den Standard.",
        "greeting": "Hey, Du. Ich bin dein Geschichtenerzähler.",
        "intro": "Hi, ich bin Jarvis, dein Geschichtenerzähler. "
                 "Sag Hey Jarvis, wenn du eine Geschichte hören möchtest.",
        "intro_commands": "Während einer Geschichte kannst du jederzeit "
                           "sagen: Vermerken, gefolgt von einer Notiz — "
                           "etwa Vermerken, Otkar ist ein Bibliothekar — "
                           "dann nehme ich das in die Welt auf. "
                           "Wiederhole oder Sag das nochmal lässt mich "
                           "die letzte Erzählung wiederholen. "
                           "Menü oder System öffnet die Einstellungen. "
                           "Geschichte beenden speichert und führt zurück "
                           "zur Welt-Auswahl. "
                           "Beenden, Schluss oder Ausschalten fährt das "
                           "Gerät komplett herunter.",
        "nothing_to_repeat": "Da ist noch keine Erzählung, die ich "
                              "wiederholen könnte.",
        "start_question": "Möchtest du loslegen?",
        "start_question_repeat": "Ich habe das nicht verstanden — "
                                  "bitte sag Ja oder Nein.",
        "mode_question": "Möchtest du eine Welt spielen oder Welten "
                          "verwalten?",
        "mode_repeat": "Bitte sag: spielen oder verwalten.",
        # World-management sub-menu prompts (Pi voice).
        "manage_intro": "Du bist im Verwaltungs-Modus. Du kannst sagen: "
                         "Neue Welt, Welt kopieren, Welt umbenennen, "
                         "oder Welt löschen. Mit Abbrechen geht's "
                         "zurück.",
        "manage_choose_action": "Was möchtest du machen?",
        "manage_choose_world": "Welche Welt?",
        "manage_ask_new_name": "Wie soll die Welt heißen?",
        "manage_world_not_found": "Die Welt habe ich nicht gefunden. "
                                    "Ich versuche es nochmal.",
        "manage_name_in_use": "Eine Welt mit dem Namen gibt es schon. "
                                "Bitte sag einen anderen Namen.",
        "manage_action_unclear": "Das habe ich nicht verstanden. Sag "
                                   "Neue Welt, Kopieren, Umbenennen, "
                                   "Löschen oder Abbrechen.",
        "manage_cancelled": "Abgebrochen.",
        "manage_done": "Erledigt.",
        "design_intro": "Wir gestalten zusammen eine neue Welt. Ich "
                         "stelle dir ein paar Fragen — wenn dir die "
                         "Details reichen, sag einfach Generieren. Das "
                         "Erzeugen der Welt kann danach ein bis drei "
                         "Minuten dauern.",
        "design_reminder": "Du kannst jetzt Generieren sagen, wenn dir "
                            "die Details reichen.",
        "generating_wait": "Ich erzeuge die Welt — das dauert ein bis "
                            "drei Minuten. Im Hintergrund läuft ein "
                            "Wartesound.",
        "generated_fail": "Beim Erzeugen der Welt ist etwas "
                           "schiefgegangen. Lass uns zur Welt-Auswahl "
                           "zurückkehren.",
        "generated_confirm_ask": "Die Welt ist fertig. Direkt starten "
                                  "oder zurück zur Welt-Auswahl? Sag "
                                  "Starten oder Auswahl.",
        "design_cancelled": "Welt-Design abgebrochen. Sag Hey Jarvis, "
                             "wenn du wieder loslegen möchtest.",
        "design_resume": "Hier nochmal die Frage:",
        "story_ended": "Spielstand gespeichert. Bis später — sag "
                        "Hey Jarvis, wenn du weitermachen willst.",
        "intro_ask": "Möchtest du diese Einführung beim nächsten Start "
                     "wieder hören? Sage ja oder nein.",
        "commands_intro_ask": "Möchtest du die Befehls-Info beim "
                               "nächsten Start wieder hören? Sage ja "
                               "oder nein.",
        "commands_intro_on": "Befehls-Info wird künftig wieder "
                              "abgespielt.",
        "commands_intro_off": "Befehls-Info wird künftig übersprungen.",
        "intro_hint": "Du kannst das jederzeit im Systemmenü unter "
                      "Einführung wieder umstellen.",
        "intro_on": "Einführung wird künftig wieder abgespielt.",
        "intro_off": "Einführung wird künftig übersprungen.",
        "daily_cap_pause": "Das Tagesbudget für die Geschichte ist "
                            "erreicht. Ich speichere deinen Spielstand "
                            "und mache jetzt Pause. Bitte den Admin, "
                            "das Tageslimit zurückzusetzen — danach "
                            "können wir genau hier weitermachen.",
        "daily_cap_still": "Das Tagesbudget ist immer noch erreicht. "
                            "Sobald der Admin das Limit zurücksetzt, "
                            "können wir weitermachen. Bis dahin pausiere "
                            "ich.",
        "daily_cap_warning": "Hinweis: das Tagesbudget ist fast "
                              "aufgebraucht. Nur noch wenige Züge "
                              "möglich, bevor ich pausieren muss.",
    },
    "en": {
        "welcome": "Hello, I'm your storyteller. When you're ready, "
                    "wake me with Hey Jarvis.",
        "choose_world": "Which world would you like to play?",
        "world_sternenfahrt": "Starfaring. You are a starship captain.",
        "world_immerwald": "The Everwood Realm. You are a ranger.",
        "menu_hint": "You can say: new story, load save, or save story.",
        "not_understood": "I did not understand that. Please say it again.",
        "listening": "I'm listening.",
        "starting": "The story begins.",
        "saved": "The story has been saved.",
        "no_saves": "There are no saved games.",
        "goodbye": "Until next time.",
        "error_retry": "There was a glitch. Please say it again.",
        # Differentiated error announcements (see storyteller_core.health).
        # The Pi loop picks the matching WAV based on EndpointError.kind;
        # error_retry stays the fallback for unknown failures.
        "error_offline_cloud": "I can't reach the internet right now. "
                                 "Please tell a grown-up that the internet "
                                 "is down.",
        "error_offline_local": "My storyteller computer at home isn't "
                                 "answering. Please tell a grown-up to "
                                 "have a look.",
        "error_auth": "My access doesn't fit. A grown-up needs to check "
                       "the settings.",
        "error_busy": "The storyteller cloud is busy right now. I'll try "
                       "again — ask me in a minute.",
        "sys_menu": "System menu. Say: save, quit, undo turn, reset world, "
                    "switch audio, intro, story mode, or close menu.",
        "story_mode_ask": "Story mode: say auto, plan, or free.",
        "story_mode_set_auto": "Story mode set to automatic. I'll decide "
                                "based on how you play.",
        "story_mode_set_planner": "Story mode set to plan. I'll always "
                                    "follow an arc.",
        "story_mode_set_free": "Story mode set to free. You shape it, "
                                "I react.",
        "story_mode_unclear": "I didn't catch that. Say auto, plan, or "
                                "free.",
        "undone": "The last turn was undone.",
        "confirm_reset": "Do you really want to reset this world? The whole "
                         "saved game will be lost. Say yes or no.",
        "confirm_undo": "Do you really want to undo the last turn? Say yes "
                        "or no.",
        "cancelled": "Cancelled. Let's continue.",
        "world_reset": "This world has been reset. We start over.",
        "closed": "Menu closed. Let's continue.",
        "wake_hint": "I'm no longer actively listening. Say Hey Jarvis to "
                     "wake me again.",
        "post_opening_hint": "You can answer now — I'm listening. "
                              "Otherwise say Hey Jarvis to wake me.",
        "wifi_setup": "No Wi-Fi found. Connect your phone to the Wi-Fi "
                      "storyteller-wifi. A page opens automatically where "
                      "you can pick your Wi-Fi and enter the password. "
                      "Then I will restart.",
        "audio_bt_on": "Audio output switched to Bluetooth.",
        "audio_bt_off": "Audio output back to the default.",
        "greeting": "Hey there. I'm your storyteller.",
        "intro": "Hi, I'm Jarvis, your storyteller. "
                 "Say Hey Jarvis when you want to hear a story.",
        "intro_commands": "During a story you can say at any time: "
                           "Note, followed by a brief — e.g. Note, Otkar "
                           "is a librarian — and I'll add it to the "
                           "world. Repeat or Say that again lets me "
                           "replay the last narration. "
                           "Menu or System opens the settings. "
                           "End story saves and returns to the world "
                           "menu. Shut down or Goodbye powers the "
                           "device off.",
        "nothing_to_repeat": "There's no narration to repeat yet.",
        "start_question": "Would you like to get started?",
        "start_question_repeat": "I didn't catch that — please say "
                                  "yes or no.",
        "mode_question": "Would you like to play a world, or manage "
                          "worlds?",
        "mode_repeat": "Please say: play, or manage.",
        # World-management sub-menu prompts (Pi voice).
        "manage_intro": "You're in the management menu. You can say: "
                         "New world, copy world, rename world, or "
                         "delete world. Cancel to go back.",
        "manage_choose_action": "What would you like to do?",
        "manage_choose_world": "Which world?",
        "manage_ask_new_name": "What should it be called?",
        "manage_world_not_found": "I couldn't find that world. Let me "
                                    "ask again.",
        "manage_name_in_use": "A world with that name already exists. "
                                "Please say a different name.",
        "manage_action_unclear": "I didn't catch that. Say new, copy, "
                                   "rename, delete, or cancel.",
        "manage_cancelled": "Cancelled.",
        "manage_done": "Done.",
        "design_intro": "Let's design a new world together. I'll ask "
                         "you a few questions — when you have enough "
                         "details, just say Generate. Building the "
                         "world afterwards can take one to three "
                         "minutes.",
        "design_reminder": "You can say Generate now if you have enough "
                            "details.",
        "generating_wait": "I'm building the world — this takes one to "
                            "three minutes. You'll hear an ambient "
                            "wait-sound.",
        "generated_fail": "Something went wrong while building the "
                           "world. Let's go back to the world menu.",
        "generated_confirm_ask": "The world is ready. Start the story "
                                  "now, or back to the world menu? "
                                  "Say Start or Menu.",
        "design_cancelled": "World design cancelled. Say Hey Jarvis "
                             "when you want to start over.",
        "design_resume": "Here's the question again:",
        "story_ended": "Game saved. See you later — say Hey Jarvis to "
                        "pick up where we left off.",
        "intro_ask": "Would you like to hear this intro again next time? "
                     "Say yes or no.",
        "commands_intro_ask": "Would you like to hear the commands info "
                               "again next time? Say yes or no.",
        "commands_intro_on": "Commands info will be played again from "
                              "now on.",
        "commands_intro_off": "Commands info will be skipped from now on.",
        "intro_hint": "You can change this any time in the system menu "
                      "under Intro.",
        "intro_on": "The intro will be played again from now on.",
        "intro_off": "The intro will be skipped from now on.",
        "daily_cap_pause": "The daily budget for the story is reached. "
                            "I'm saving your progress and pausing now. "
                            "Ask the admin to reset the daily limit — "
                            "we can pick up right where we left off.",
        "daily_cap_still": "The daily budget is still reached. As soon "
                            "as the admin resets the limit, we can "
                            "continue. Until then I'll stay paused.",
        "daily_cap_warning": "Heads-up: the daily budget is nearly "
                              "spent. Only a few more turns before I "
                              "have to pause.",
    },
}

# --- Menu world-selection keywords ---
WORLD_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "de": {
        "sternenfahrt": ["sternenfahrt", "scifi", "science", "raumschiff",
                          "weltraum", "kapitän", "all"],
        "immerwald": ["immerwald", "fantasy", "wald", "waldläufer", "magie",
                      "epos"],
    },
    "en": {
        "sternenfahrt": ["starfaring", "sci-fi", "scifi", "science",
                         "starship", "space", "captain"],
        "immerwald": ["everwood", "fantasy", "forest", "ranger", "magic",
                      "epic"],
    },
}

# --- Narration style guidance (DE verbatim from config default) ---
NARRATION_GUIDANCE = {
    "de": ("Erzähle EINFACH und KLAR fürs Zuhören: höchstens 4–6 kurze Sätze. "
           "Pro Antwort nur EINE Situation und höchstens ein bis zwei neue "
           "Namen/Dinge. KEINE NUMMERIERTEN LISTEN (1., 2., 3.), keine "
           "Aufzählungspunkte (-, *, •), keine Optionen-Liste — alles als "
           "fließende Prosa. Keine Detailflut, kein Vorgriff auf mehrere "
           "Handlungsstränge. Schließe mit EINER konkreten, offenen Lage "
           "oder Frage, auf die der Spieler direkt reagieren kann. Ruhig "
           "und bildhaft, aber sparsam."),
    "en": ("Narrate SIMPLY and CLEARLY for listening: at most 4–6 short "
           "sentences. Only ONE situation per reply and at most one or two "
           "new names/things. NO NUMBERED LISTS (1., 2., 3.), no bullet "
           "points (-, *, •), no enumerated options — everything as "
           "flowing prose. No detail flood, no jumping "
           "ahead across multiple plot threads. End with ONE concrete, open "
           "situation or question the player can react to directly. Calm and "
           "vivid, but sparing."),
}

# --- Language instruction injected into the narrator system prompt ---
# Session-continuity guardrail: prevents the "Gute Nacht"-loop bug where
# the narrator, having said farewell once on "Das war's für heute", keeps
# repeating the farewell on every subsequent player input because the LLM
# mimics the closing pattern in memory. Injected unconditionally into the
# narrator system prompt.
SESSION_CONTINUITY_RULE = {
    "de": ("SESSION-KONTINUITÄT: War deine letzte Antwort ein Abschluss-/"
           "Abschieds-Satz (z.B. 'Gute Nacht', 'Bis später', 'Mach's gut') "
           "und der Spieler spricht jetzt einfach weiter, nimm das als "
           "ausdrücklichen Wunsch, die Geschichte fortzusetzen — knüpfe an "
           "die letzte Erzähl-Szene an und führe sie weiter. NIEMALS zwei "
           "Abschluss-/Abschieds-Sätze hintereinander. Nur wenn der Spieler "
           "EXPLIZIT erneut beendet ('Schluss', 'Ende', 'Das war's wirklich') "
           "darfst du den Abschluss bestätigen."),
    "en": ("SESSION CONTINUITY: If your previous reply was a farewell line "
           "(e.g. 'Good night', 'See you later') and the player just keeps "
           "talking, treat that as an explicit wish to continue the story — "
           "pick up the last narrative scene and carry it forward. NEVER "
           "produce two farewell lines in a row. Only when the player "
           "EXPLICITLY ends again ('We're done', 'Really stop now') may you "
           "confirm the farewell."),
}

LANG_INSTRUCTION = {
    "de": ("SPRACH-REGEL (verbindlich): Antworte AUSSCHLIESSLICH auf Deutsch. "
           "KEINE chinesischen, englischen, russischen, arabischen oder "
           "anderen nicht-lateinischen Schriftzeichen oder Wörter im Output, "
           "auch nicht als Beispiel, Zitat oder Stilisierung. Eigennamen "
           "aus der Welt bleiben unverändert."),
    "en": ("LANGUAGE RULE (mandatory): Respond ONLY in English. NO Chinese, "
           "German, Russian, Arabic or any other non-English / non-Latin "
           "characters or words in the output, even as examples, quotes or "
           "stylisation. World proper nouns are kept as-is."),
}

# Repair system prompt used when the narrator drifts into another language
# (notably Chinese with qwen-based models). One extra LLM call translates the
# drifted text back into the target locale while preserving voice.
REPAIR_LANGUAGE_SYS = {
    "de": ("Du erhältst Erzähltext mit Sprach-Abweichungen (z.B. "
           "chinesische oder russische Wörter mittendrin). Übersetze ihn "
           "vollständig und natürlich ins Deutsche, behalte Stil und "
           "Bedeutung der Erzählung. Eigennamen bleiben unverändert. Gib "
           "AUSSCHLIESSLICH den überarbeiteten Erzähltext zurück — kein "
           "Kommentar, keine Anführungszeichen darum."),
    "en": ("You receive narrative text with language drift (e.g. Chinese "
           "or Russian words mixed in). Translate it fully and naturally "
           "to English, preserving the narrative style and meaning. Proper "
           "nouns remain unchanged. Return ONLY the cleaned narrative text "
           "— no commentary, no surrounding quotes."),
}

MODERATION_BLOCKED = {
    "de": "Das war etwas zu grob — formulier es bitte zurückhaltender oder "
          "andersrum, dann geht's weiter.",
    "en": "That was a bit too rough — please phrase it more gently or "
          "differently, and we'll continue.",
}

# --- Narration "gate" (curator) — decides PER TURN which authored
# reveals the narrator MAY use. Player improvisation stays free; only
# pre-authored plot points (fragments / history / glossary specifics /
# substory resolution) are curated.
GATE_SYS = {
    "de": ("Du bist Story-Kurator. Du entscheidest, was der Erzähler in "
           "DIESEM EINEN Spielzug verraten DARF und was er noch zurückhalten "
           "muss. Ziel: keine vorzeitigen Reveals von vor-geschriebenen "
           "Plot-Punkten (Fragmente, Vergangenheit, Substory-Auflösung). "
           "WICHTIG: Du schränkst nur AUTHORED-Material ein. Spontane "
           "Spieler-Ideen, improvisierte neue Fakten und freie Erzähl-"
           "Wendungen bleiben weiter erlaubt — du listest sie nicht. "
           "Alle Strings deiner Antwort AUSSCHLIESSLICH AUF DEUTSCH. "
           "Antworte AUSSCHLIESSLICH als JSON mit Schlüsseln: "
           "scene_intent (1 Satz: was DIESER Zug erreichen soll), "
           "permitted_reveals (Liste — max. die genannte Anzahl — kurzer "
           "Verweise auf konkrete authored Welt-Fakten, die der Erzähler "
           "JETZT einbauen darf), "
           "forbidden_topics (Liste authored Themen/Personen/Geheimnisse, "
           "die heute NICHT angedeutet werden dürfen — typischerweise die "
           "Substory-Auflösung, künftige Beats, ungeöffnete Fragmente), "
           "tone_nudge (kurzer Stil-Hinweis oder leerer String). "
           "Halte die Listen knapp und konkret."),
    "en": ("You are the story curator. You decide what the narrator MAY "
           "reveal in THIS ONE turn and what must still be held back. Goal: "
           "no premature reveals of pre-authored plot points (fragments, "
           "history, substory resolution). IMPORTANT: you only constrain "
           "AUTHORED material — spontaneous player ideas, improvised new "
           "facts and free narrative twists stay free; you don't list "
           "those. All string values in your response MUST be in English. "
           "Answer ONLY as JSON with keys: "
           "scene_intent (one sentence: what this turn aims at), "
           "permitted_reveals (list — at most the stated count — of short "
           "references to concrete authored world facts the narrator may "
           "weave in NOW), "
           "forbidden_topics (list of authored topics/persons/secrets that "
           "must NOT be hinted at today — typically the substory resolution, "
           "future beats, unopened fragments), "
           "tone_nudge (short style hint or empty string). "
           "Keep the lists tight and concrete."),
}

# Text added to the narrator's system prompt when a gate decision exists.
GATE_NARRATOR_RULE = {
    "de": ("KURATOR-LEITLINIE FÜR DIESEN ZUG: Erzähle frei und reagiere auf "
           "den Spieler — Spieler-Initiativen und improvisierte Wendungen "
           "sind ausdrücklich erlaubt. ABER: aus dem vor-geschriebenen "
           "Welt-Material darfst du heute NUR die unten genannten Reveals "
           "konkret nutzen. Die forbidden_topics darfst du heute weder "
           "andeuten noch erklären — auch wenn der Erzähl-Strom darauf "
           "zusteuert, lass es offen und führe in eine andere Richtung. "
           "Erfundene neue, harmlose Details (z.B. Geräusche, kleine "
           "Gegenstände, Nebenfiguren-Momente) bleiben jederzeit ok."),
    "en": ("CURATOR GUIDELINE FOR THIS TURN: Narrate freely and react to "
           "the player — player initiatives and improvised twists are "
           "explicitly welcome. BUT: from the pre-authored world material "
           "you may ONLY use the named reveals below today. The forbidden_"
           "topics must not be hinted at or explained today — even if the "
           "narrative drifts toward them, leave them open and pivot. "
           "Newly invented, harmless details (sounds, small props, NPC "
           "moments) are fine any time."),
}

# --- Engine/CLI directives ---
OPENING_DIRECTIVE = {
    "de": ("[Dies ist eine NEUE Geschichte. Die Welt wurde dem Spieler "
           "GERADE in einer separaten Einführung vorgestellt — wiederhole "
           "NICHT Setting, Rolle oder zentrale Spannung. Steig direkt in "
           "die erste Szene ein: 2–4 kurze Sätze zur konkreten "
           "Ausgangslage der Spielfigur (Ort, Zeit, ein, zwei konkrete "
           "Dinge). Ende mit EINER klaren, offenen Lage oder Frage, auf "
           "die der Spieler direkt reagieren kann. Einfach fürs Zuhören "
           "— keine Aufzählungen, keine Infoflut.]"),
    "en": ("[This is a NEW story. The world has JUST been introduced to "
           "the player in a separate intro — do NOT repeat setting, role "
           "or central tension. Drop straight into the first scene: 2–4 "
           "short sentences on the protagonist's starting situation "
           "(place, time, one or two concrete things). End with ONE "
           "clear, open situation or question the player can react to "
           "directly. Simple, audio-friendly — no lists, no info flood.]"),
}

# World intro: read-only, spoken-aloud "welcome to this world" before the
# first scene. NOT a turn — does not advance the chat memory or invoke
# tools. Stays clearly separated from OPENING_DIRECTIVE so the player
# hears two distinct phases (settled overview -> first scene).
INTRO_SYS = {
    "de": ("Du bist der Erzähler einer interaktiven Audio-Geschichte. "
           "Stelle dem Spieler die Welt vor, die er gleich spielen wird. "
           "GENAU drei kurze Absätze, zusammen 4–6 Sätze:\n"
           "1. Setting / Stimmung (1–2 Sätze): wo und wann spielt das? "
           "Welche Atmosphäre?\n"
           "2. Spielerrolle (1–2 Sätze): wer ist die Spielfigur, was tut "
           "sie?\n"
           "3. Zentrale Spannung (1–2 Sätze): was ist gerade unklar, "
           "bedrohlich, oder im Wandel? Mache neugierig, ohne die "
           "Geschichte vorwegzunehmen.\n"
           "Sprich den Spieler direkt an, ruhig und bildhaft, einfaches "
           "Deutsch — der Spieler hört dich vorlesen. KEINE "
           "Aufzählungen, KEINE Frage am Ende (die kommt in der "
           "nächsten Phase), KEINE Tool-Aufrufe."),
    "en": ("You are the narrator of an interactive audio story. "
           "Introduce the world the player is about to enter. EXACTLY "
           "three short paragraphs, 4–6 sentences total:\n"
           "1. Setting / mood (1–2 sentences): where and when? What "
           "atmosphere?\n"
           "2. Player role (1–2 sentences): who is the protagonist, "
           "what do they do?\n"
           "3. Central tension (1–2 sentences): what is uncertain, "
           "threatening, or in flux right now? Make the player curious "
           "without spoiling.\n"
           "Address the player directly, calm and vivid, simple English "
           "— they will hear you read aloud. NO lists, NO question at "
           "the end (the next phase asks), NO tool calls."),
}
RESTORE_DIRECTIVE = {
    "de": ("[Setze die Geschichte fort: fasse in 1-2 Sätzen zusammen, wo wir "
           "stehen, und weiter.]"),
    "en": ("[Continue the story: summarize in 1-2 sentences where we are, "
           "then carry on.]"),
}
RESUME_DIRECTIVE = {
    "de": "[Kurz zusammenfassen wo wir stehen, dann weiter.]",
    "en": "[Briefly summarize where we are, then continue.]",
}

# --- Resume recap (spoken when continuing a SAVED game) ---
# A read-only "Was bisher geschah" — does NOT advance the story.
RECAP_SYS = {
    "de": ("Du bist der Erzähler. Der Spieler setzt einen gespeicherten "
           "Spielstand fort. Gib eine KURZE Erinnerung in 2 bis 4 einfachen "
           "Sätzen: zuerst was bisher geschah, dann die aktuelle Situation. "
           "Ende mit der offenen Lage oder Frage, auf die der Spieler direkt "
           "reagieren kann. Erzähle NICHT weiter und erfinde nichts Neues — "
           "fasse nur den bisherigen Stand zusammen. Sprich den Spieler "
           "direkt an (zweite Person)."),
    "en": ("You are the narrator. The player is resuming a saved game. Give "
           "a SHORT recap in 2 to 4 simple sentences: first what happened so "
           "far, then the current situation. End with the open situation or "
           "question the player can react to directly. Do NOT continue the "
           "story or invent anything new — only summarize the state so far. "
           "Address the player directly (second person)."),
}
RECAP_INTRO = {  # spoken lead-in prefixed to the recap
    "de": "Willkommen zurück. ",
    "en": "Welcome back. ",
}

# --- Question heuristic prefixes (Rückfragen-Kurzmodus) ---
Q_PREFIXES = {
    "de": ("was ", "wer ", "wo ", "wie ", "warum", "wieso", "welche",
           "welcher", "welches", "wann", "wozu", "kann ich", "darf ich",
           "habe ich", "hab ich", "gibt es", "gibt's", "wisst ihr",
           "weißt du", "weisst du", "erinner"),
    "en": ("what", "who", "where", "how", "why", "which", "when", "can i",
           "may i", "do i", "is there", "are there", "remind", "remember"),
}

# --- Long-term memory: rolling synopsis ---
SUMMARIZER_SYS = {
    "de": ("Du verdichtest den Spielverlauf zu einem knappen, faktentreuen "
           "Gedächtnis. Schreibe NUR Fließtext: etablierte Ereignisse, "
           "Entscheidungen, Beziehungen und offene Fäden. Keine "
           "Ausschmückung, keine Wiederholung, keine Anrede, keine "
           "Überschriften.\n\n"
           "STRENG WICHTIG: Die NEUE Zusammenfassung MUSS jeden Inhalt "
           "der bisherigen behalten. Du darfst nur ergänzen, präziser "
           "formulieren oder Redundanzen zusammenführen — NIEMALS "
           "etablierte Fakten, Personen, Orte, Beziehungen oder offene "
           "Fäden aus der vorigen Zusammenfassung weglassen. Wenn die "
           "neue Zusammenfassung kürzer als die alte ist, hast du "
           "etwas Wichtiges verloren. Integriere das Neue zusätzlich, "
           "chronologisch eingeordnet."),
    "en": ("You compress the play so far into a terse, faithful memory. "
           "Write ONLY prose: established events, decisions, relationships "
           "and open threads. No embellishment, no repetition, no "
           "salutations, no headings.\n\n"
           "STRICTLY IMPORTANT: The NEW summary MUST retain every "
           "piece of the prior summary. You may only add, sharpen "
           "phrasing, or fold duplicates — NEVER drop established "
           "facts, people, places, relationships or open threads from "
           "the prior summary. If your new summary is shorter than the "
           "previous one, you have lost something important. Integrate "
           "the new part in addition, placed chronologically."),
}
SYNOPSIS_LABEL = {
    "de": ("BISHER GESCHEHEN (Langzeit-Gedächtnis — als Kontinuität nutzen, "
           "NICHT vorlesen):"),
    "en": ("STORY SO FAR (long-term memory — use for continuity, do NOT "
           "read aloud):"),
}
CHARSTATE_LABEL = {
    "de": "FIGUREN-STAND (Konsistenz wahren; track_character zum Aktualisieren):",
    "en": "CHARACTER STATE (keep consistent; use track_character to update):",
}
VOICE_SAMPLE_LABEL = {
    "de": ("STILPROBE (NUR Tonfall, Rhythmus und Wortwahl nachahmen — den "
           "Inhalt NICHT übernehmen):"),
    "en": ("STYLE SAMPLE (imitate ONLY tone, rhythm and word choice — do "
           "NOT reuse its content):"),
}
BEAT_NUDGE = {
    "de": ("\nHINWEIS: Dieser Sub-Beat läuft schon mehrere Züge. Wenn das "
           "Beat-Ziel erreicht scheint, jetzt advance_beat (oder bei "
           "Auflösung complete_substory) aufrufen — nicht künstlich dehnen."),
    "en": ("\nNOTE: this sub-beat has run for several turns. If its goal "
           "seems reached, call advance_beat now (or complete_substory if "
           "resolved) — do not stretch it artificially."),
}


# --- In-loop voice command keywords ---
CMD_KEYWORDS = {
    "de": {
        # Hard shutdown of the appliance (sudo poweroff). Matched as
        # short token at first position so it doesn't fire mid-sentence.
        "shutdown": ("beenden", "aufhören", "schluss", "tschüss",
                       "tschüs", "ausschalten", "ausmachen"),
        "save": ("speicher",),
        "load": ("lade", "spielstand"),
        "menu": ("system", "systemmenü", "systemmenu", "menü", "menu"),
        "note": ("vermerken", "vermerk", "notiz", "merke", "merken"),
        # Re-play the last narration as TTS (no LLM call). Matched as a
        # short standalone phrase so a mid-sentence "nochmal" inside a
        # player input does not accidentally trigger a replay.
        "repeat": ("wiederhole", "wiederhol", "wiederholen", "nochmal",
                     "nochmals"),
        # Verwaltungs-Modus: Worte für die Aktions-Auswahl im
        # "Welten verwalten"-Untermenü auf dem Pi.
        "manage": ("verwalten", "verwaltung", "managen", "manage"),
        "create_world": ("neue", "neue welt", "neu", "erstell",
                          "erstellen", "anlegen", "create", "new"),
        "copy": ("kopier", "kopieren", "kopie", "duplizier",
                   "duplizieren", "duplikat", "copy", "duplicate"),
        "rename": ("umbenenn", "umbenennen", "umname", "umtaufen",
                     "umtauf", "rename"),
        "delete": ("lösch", "löschen", "entfern", "entfernen", "weg",
                     "delete", "remove"),
        # First token in the world-design interview loop that signals
        # "stop asking, build the world now". Matched ONLY inside the
        # interview — outside it the words are ignored.
        "generate": ("generieren", "generier", "erstellen", "los",
                       "fertig", "starten"),
        # Short cancel command for sub-flows like the world-design
        # interview (NOT the running story — there "schluss / beenden"
        # is shutdown, see "shutdown" bucket). Matched as a short
        # ≤3-token utterance with the cancel word at the start.
        "cancel": ("abbrechen", "abbruch", "stopp", "stop", "halt",
                     "beenden", "schluss", "aufhören"),
        # Voice-controlled "Storymodus" — soft plot-pressure pin. Three
        # values: "auto" (heuristic decides), "plan/planer" (always full
        # plot), "frei" (no plot pressure). The Pi sysmenu has an
        # "Storymodus"-Eintrag, the bare phrase also works mid-story.
        "story_mode": ("storymodus", "story-modus", "story modus",
                         "spielmodus", "modus"),
        "story_mode_auto": ("auto", "automatisch", "automatik"),
        "story_mode_planner": ("plan", "planer", "planner", "geplant",
                                 "plot", "story", "geschichte"),
        "story_mode_free": ("frei", "free", "freier", "freies",
                              "free roam", "explorieren",
                              "exploration", "erkundung"),
    },
    "en": {
        "shutdown": ("shutdown", "shut", "power off", "poweroff",
                       "turn off", "goodbye"),
        "save": ("save",),
        "load": ("load", "resume"),
        "menu": ("system", "system menu", "menu"),
        "note": ("note", "take note", "remember as world"),
        # Re-play the last narration as TTS (no LLM call). Matched as a
        # short standalone phrase so a mid-sentence "again" inside a
        # player input does not accidentally trigger a replay.
        "repeat": ("repeat", "again", "once more"),
        # World management sub-menu (Pi voice).
        "manage": ("manage", "management", "administer", "admin"),
        "create_world": ("new", "new world", "create", "make", "build"),
        "copy": ("copy", "duplicate", "clone"),
        "rename": ("rename", "retitle"),
        "delete": ("delete", "remove", "destroy"),
        "generate": ("generate", "create", "build", "go", "ready",
                      "done"),
        "cancel": ("cancel", "stop", "abort", "quit", "end",
                     "nevermind"),
        "story_mode": ("story mode", "storymode", "play mode",
                         "narrative mode"),
        "story_mode_auto": ("auto", "automatic"),
        "story_mode_planner": ("plan", "planner", "plot", "story",
                                 "planned"),
        "story_mode_free": ("free", "free roam", "freeform",
                              "explore", "exploration"),
    },
}


# --- Dynamic templates for the world-design flow (live TTS) -----------
# Cached prompts cover everything that's static; the few lines below
# include the just-generated world name, so they're rendered live.
DESIGN_PROMPTS = {
    "de": {
        "generated_ok": "Die Welt {name} ist fertig.",
        "starting_in_world": "Die Geschichte in {name} beginnt jetzt.",
        "interview_fallback_question": "Erzähl mir mehr.",
    },
    "en": {
        "generated_ok": "The world {name} is ready.",
        "starting_in_world": "The story in {name} begins now.",
        "interview_fallback_question": "Tell me more.",
    },
}


# Yes/no-ish phrase buckets reused by main.py's voice gates.
YES_KEYWORDS = (
    "ja", "jo", "jap", "klar", "mach", "gerne", "bestätig", "bestatig",
    "yes", "yeah", "yep", "sure", "okay", "ok",
)
NO_KEYWORDS = (
    "nein", "nö", "no", "nope", "later", "stop",
)


def classify_play_mode(text: str) -> str:
    """Classify the answer to "spielen oder verwalten?".

    Returns ``"play"`` / ``"manage"`` / ``"unclear"``. Used only by the
    Pi main loop; intentionally heuristic (no LLM call) so the question
    stays free regardless of cost cap status. Manage keywords win when
    both fire (a player who says "neue Welt erstellen" obviously wants
    the management branch even though "spielen" might also appear).
    """
    lw = (text or "").strip().lower()
    if not lw:
        return "unclear"
    manage_kw = ("verwalt", "managen", "manage", "admin",
                 "neue welt", "neu", "erstell", "anlegen", "generier",
                 "kopier", "kopie", "umbenenn", "umtauf", "rename",
                 "lösch", "löschen", "entfern", "delete", "remove",
                 "duplikat", "duplizier", "duplicate", "build",
                 "design", "new world", "new ", "create", "make",
                 "destroy", "clone")
    play_kw = ("spielen", "spiel", "bestehend", "vorhanden",
               "weitermachen", "fortsetzen", "play", "existing", "old",
               "saved", "load", "weiter")
    if any(k in lw for k in manage_kw):
        return "manage"
    if any(k in lw for k in play_kw):
        return "play"
    return "unclear"


def classify_manage_action(text: str) -> str:
    """Classify the answer to "Was möchtest du machen?" inside the
    Verwaltungs-Modus into one of the four world-mgmt sub-actions
    or a cancel intent.

    Returns ``"create_world"`` / ``"copy"`` / ``"rename"`` /
    ``"delete"`` / ``"cancel"`` / ``"unclear"``. Heuristic only.
    """
    lw = (text or "").strip().lower()
    if not lw:
        return "unclear"
    cancel_kw = ("abbrech", "abbruch", "zurück", "stop", "stopp",
                 "raus", "ende", "cancel", "abort", "back", "nevermind")
    create_kw = ("neue welt", "neu erstell", "neu anleg", "neue",
                 "neu", "erstell", "generier", "new", "create", "build",
                 "design")
    copy_kw = ("kopier", "kopie", "duplizier", "duplikat", "copy",
               "duplicate", "clone")
    rename_kw = ("umbenenn", "umtauf", "umname", "rename")
    delete_kw = ("lösch", "entfern", "weg damit", "delete", "remove",
                 "destroy")
    if any(k in lw for k in cancel_kw):
        return "cancel"
    # Order matters: copy/rename/delete win over the broad "neu" trigger
    # so "kopier die neue welt" doesn't get routed to create_world.
    if any(k in lw for k in copy_kw):
        return "copy"
    if any(k in lw for k in rename_kw):
        return "rename"
    if any(k in lw for k in delete_kw):
        return "delete"
    if any(k in lw for k in create_kw):
        return "create_world"
    return "unclear"


# Multi-word phrases that close the CURRENT story (save + back to the
# wake-word idle / world menu) WITHOUT powering the device off. Matched
# as utterance prefix in the main loop (not as a token bag).
END_STORY_PHRASES = {
    "de": (
        "geschichte beenden", "geschichte ende", "geschichte aus",
        "geschichte vorbei", "story beenden", "story ende",
    ),
    "en": (
        "end story", "end the story", "stop story", "stop the story",
        "story over", "finish story",
    ),
}


def matches_end_story(text: str, locale: str) -> bool:
    """True if `text` starts with one of the END_STORY_PHRASES for `locale`."""
    s = (text or "").strip().lower()
    if not s:
        return False
    phrases = END_STORY_PHRASES.get(norm(locale), ())
    return any(s.startswith(p) for p in phrases)


# Phrases / templates for runtime user-note creation. Rendered via live
# TTS (not cached) because the player's content is dynamic.
NOTE_PROMPTS = {
    "de": {
        "saved": "Vermerk gespeichert: {name} als {kind}.",
        "saved_short": "Vermerk gespeichert.",
        "empty": "Was soll ich vermerken? Bitte sag den Inhalt noch einmal.",
        "kind_label": {
            "person": "Person", "place": "Ort", "item": "Gegenstand",
            "fact": "Welt-Fakt",
        },
    },
    "en": {
        "saved": "Note saved: {name} as {kind}.",
        "saved_short": "Note saved.",
        "empty": "What should I note down? Please say the content again.",
        "kind_label": {
            "person": "person", "place": "place", "item": "item",
            "fact": "world fact",
        },
    },
}


# --- Admin web UI strings ---
WEB = {
    "de": {
        "nav_dash": "🏠 Dashboard", "nav_new": "➕ Neue Welt",
        "nav_gen": "🧙 Welt aus Prompt", "nav_saves": "💾 Spielstände",
        "nav_tr": "📜 Verläufe", "nav_mod": "🛡 Moderation",
        "nav_api": "⚙ API", "nav_audio": "🔊 Audio",
        "job_running_h": "Läuft…",
        "job_kind": "Aufgabe",
        "job_elapsed": "Vergangen",
        "job_detail": "Status",
        "job_hint": ("Diese Seite aktualisiert sich automatisch alle 3 "
                     "Sekunden. Du kannst den Tab schließen — die Aufgabe "
                     "läuft im Admin weiter."),
        "job_refresh": "jetzt aktualisieren",
        "job_error_h": "Aufgabe fehlgeschlagen",
        "job_traceback": "Details (klick zum Aufklappen)",
        "job_not_found": "Aufgabe nicht gefunden (Admin neu gestartet?).",
        "job_title_gen": "Welt wird generiert",
        "job_title_suggest": "Vorschlag wird erzeugt",
        "job_title_reindex": "RAG wird neu indexiert",
        "btn_busy_gen": "Welt wird generiert… (kann 1–2 Minuten dauern)",
        "btn_busy_suggest": "Vorschlag läuft…",
        "btn_busy_reindex": "Reindex läuft…",
        "nav_models": "🧠 Modelle",
        "models_title": "Modelle",
        "models_desc": ("Modellnamen und Erzähl-Parameter. Änderungen "
                        "werden in data/models.json gespeichert und "
                        "überschreiben config.toml. Greifen sofort für "
                        "diese Admin-Sicht; für die laufende Erzähl-"
                        "Schleife erst nach Neustart von storyteller.service."),
        "models_story": "Erzähler-Modell (story_llm)",
        "models_planner": "Architekt + Zusammenfasser (planner_llm)",
        "models_planner_ph": "leer = wie story_llm",
        "models_gen": "Welt-/Inhalts-Generierung (gen_llm)",
        "models_gen_ph": "leer = wie story_llm",
        "models_temp": "Temperatur (Erzähler)",
        "models_freq": "frequency_penalty (Anti-Wiederholung)",
        "models_pres": "presence_penalty (Themen-Vielfalt)",
        "audio_title": "Audio-Ausgabe",
        "audio_desc": "Backend zur Laufzeit umschalten (auch per Sprache: "
                      "System, dann Audio). pipewire = Bluetooth (vorher "
                      "scripts/setup_bluetooth.sh + Gerät koppeln).",
        "audio_backend": "Backend", "audio_sink_ph": "PipeWire-Sink "
                         "(leer = Default; wpctl status zeigt Namen)",
        "audio_volume": "Lautstärke (0–100 %)",
        "audio_volume_hint": "Wirkt am Pi (ALSA) sofort — auch auf eine "
                             "laufende Erzählung; im PC-Modus erst beim "
                             "nächsten Start.",
        "audio_volume_now": "aktuell",
        "backend": "Storyteller — Backend", "config": "Konfiguration",
        "worlds": "Welten", "new_world": "➕ Neue Welt anlegen",
        "saves": "Spielstände", "view": "ansehen",
        "cost_cap": "Kostendeckel", "player": "Spieler",
        "saves_none": "Keine Spielstände.", "s_world": "Welt",
        "s_msgs": "Nachrichten", "s_unreadable": "nicht lesbar",
        "gen_title": "Welt aus Prompt generieren",
        "gen_desc": "Beschreibe deine Welt in ein paar Sätzen — das LLM "
                    "baut daraus eine komplette Welt (Beschreibung, Ort/"
                    "Person/Gegenstand/Glossar/Historie/Fragmente, "
                    "Blueprint, Zufallslisten, Ton, Komplexität, "
                    "Zielgruppe).",
        "gen_ph": "z.B. düstere Cyberpunk-Megacity; Spieler ist abtrünnige "
                  "Kopfgeldjägerin; Fokus Intrigen; Zielgruppe erwachsene",
        "gen_btn": "Welt generieren", "error": "Fehler",
        "gen_failed": "Generierung fehlgeschlagen", "back": "zurück",
        "new_title": "Neue Welt anlegen", "new_btn": "Welt anlegen",
        "new_hint": "Orte, Personen, Gegenstände, Glossar, Historie und "
                    "Zufallslisten danach auf der Welt-Seite ergänzen.",
        "ph_id": "id (kurz, z.B. mythos)", "ph_name": "Name",
        "ph_genre": "Genre", "ph_desc": "Weltbeschreibung",
        "ph_role": "Spielerrolle", "ph_start": "Ausgangssituation",
        "ph_style": "Erzählstil", "ph_mood": "Stimmung",
        "ph_amb": "Ambiente", "ph_magic": "Physik / Magie (Regeln)",
        "ph_premise": "Makro-Prämisse (Spannungsbogen)",
        "basedata": "Basisdaten", "complexity": "Komplexität",
        "ph_audience": "Zielgruppe / Alter, z.B. 12+",
        "ph_patterns": "Muster (leer=nach Komplexität): three_act,mystery,…",
        "tone_lbl": "Ton — düster/Humor/Romanze/Action/Horror (0–5), "
                    "Tempo, Notizen",
        "ph_tnotes": "Ton-/Genre-Notizen", "base_save": "Basisdaten speichern",
        "sec_places": "Orte", "sec_persons": "Personen",
        "sec_items": "Gegenstände", "sec_glossary": "Glossar",
        "sec_history": "Historie", "sec_fragments": "Fragmente",
        "sec_rtables": "Zufallslisten",
        "sug_title": "LLM-Vorschlag — prüfen &amp; übernehmen",
        "apply": "Übernehmen",
        "sug_bad": "(Vorschlag nicht lesbar)", "add_h": "Hinzufügen",
        "add_btn": "Hinzufügen", "add_suffix": "hinzufügen",
        "llm_title": "Vom LLM schreiben lassen", "llm_ph": "Worüber?",
        "llm_btn": "Vorschlag erzeugen", "reindex_btn": "RAG neu indexieren",
        "reindex_t": "Reindex", "reindexed": "Fakten neu indexiert",
        "tr_title": "Gespielte Verläufe", "tr_none": "Noch keine Verläufe.",
        "tr_events": "Ereignisse", "tr_one": "Verlauf",
        "tr_notfound": "nicht gefunden", "tr_all": "alle Verläufe",
        "tr_player": "Spieler", "tr_narr": "Erzähler",
        "tr_blocked": "BLOCKIERT",
        "mod_title": "Moderation",
        "mod_desc": "Spieler-Eingaben werden VOR der LLM-Antwort geprüft "
                    "(Modell %s). Schwelle = Score, ab dem blockiert wird "
                    "(0–1; niedriger = strenger).",
        "mod_active": "aktiv", "mod_default": "Default-Schwelle",
        "mod_cats": "Pro-Kategorie als JSON (OpenAI-Kategorien, z. B. "
                    "{harassment: 0.3, violence: 0.7})",
        "save": "Speichern",
        "kind_place": "Ort", "kind_person": "Person",
        "kind_item": "Gegenstand", "kind_fragment": "Fragment",
        "kind_glossary": "Glossar-Begriff", "kind_history": "Historie",
        "kind_rtable": "Zufallsliste", "kind_rentry": "Zufallslisten-Eintrag",
        "fl_name": "Name", "fl_desc": "Beschreibung",
        "fl_rolerel": "Rolle/Beziehungen", "fl_props": "Eigenschaften/Wirkung",
        "fl_title": "Titel", "fl_text": "Text", "fl_term": "Begriff",
        "fl_def": "Definition", "fl_when": "Zeit/Epoche",
        "fl_list": "Liste (Name)", "fl_weight": "Gewicht (z.B. 2)",
        "fl_tags": "tags,komma",
    },
    "en": {
        "nav_dash": "🏠 Dashboard", "nav_new": "➕ New world",
        "nav_gen": "🧙 World from prompt", "nav_saves": "💾 Saves",
        "nav_tr": "📜 Transcripts", "nav_mod": "🛡 Moderation",
        "nav_api": "⚙ API", "nav_audio": "🔊 Audio",
        "job_running_h": "Running…",
        "job_kind": "Task",
        "job_elapsed": "Elapsed",
        "job_detail": "Status",
        "job_hint": ("This page auto-refreshes every 3 seconds. You can "
                     "close the tab — the task keeps running in the admin."),
        "job_refresh": "refresh now",
        "job_error_h": "Task failed",
        "job_traceback": "Details (click to expand)",
        "job_not_found": "Task not found (admin restarted?).",
        "job_title_gen": "Generating world",
        "job_title_suggest": "Generating suggestion",
        "job_title_reindex": "Re-indexing RAG",
        "btn_busy_gen": "Generating world… (can take 1–2 minutes)",
        "btn_busy_suggest": "Suggestion running…",
        "btn_busy_reindex": "Reindex running…",
        "nav_models": "🧠 Models",
        "models_title": "Models",
        "models_desc": ("Model names and narration parameters. Changes are "
                        "saved to data/models.json and override config.toml. "
                        "They apply immediately to this admin view; the "
                        "running narrator loop picks them up only after "
                        "restarting storyteller.service."),
        "models_story": "Narrator model (story_llm)",
        "models_planner": "Architect + summariser (planner_llm)",
        "models_planner_ph": "empty = same as story_llm",
        "models_gen": "World / content generation (gen_llm)",
        "models_gen_ph": "empty = same as story_llm",
        "models_temp": "Temperature (narrator)",
        "models_freq": "frequency_penalty (anti-repetition)",
        "models_pres": "presence_penalty (topic variety)",
        "audio_title": "Audio output",
        "audio_desc": "Switch the backend at runtime (also by voice: "
                      "System, then Audio). pipewire = Bluetooth (run "
                      "scripts/setup_bluetooth.sh + pair a device first).",
        "audio_backend": "Backend", "audio_sink_ph": "PipeWire sink "
                         "(empty = default; wpctl status shows names)",
        "audio_volume": "Volume (0–100%)",
        "audio_volume_hint": "On the Pi (ALSA) this takes effect "
                             "immediately — even during a running story; "
                             "in PC mode only at the next start.",
        "audio_volume_now": "current",
        "backend": "Storyteller — Backend", "config": "Configuration",
        "worlds": "Worlds", "new_world": "➕ Create new world",
        "saves": "Saves", "view": "view", "cost_cap": "cost cap",
        "player": "Player", "saves_none": "No saves.", "s_world": "world",
        "s_msgs": "messages", "s_unreadable": "unreadable",
        "gen_title": "Generate world from prompt",
        "gen_desc": "Describe your world in a few sentences — the LLM builds "
                    "a complete world from it (description, places/persons/"
                    "items/glossary/history/fragments, blueprint, random "
                    "tables, tone, complexity, audience).",
        "gen_ph": "e.g. grim cyberpunk megacity; player is a rogue bounty "
                  "hunter; focus intrigue; audience adults",
        "gen_btn": "Generate world", "error": "Error",
        "gen_failed": "Generation failed", "back": "back",
        "new_title": "Create new world", "new_btn": "Create world",
        "new_hint": "Add places, persons, items, glossary, history and "
                    "random tables afterwards on the world page.",
        "ph_id": "id (short, e.g. mythos)", "ph_name": "Name",
        "ph_genre": "Genre", "ph_desc": "World description",
        "ph_role": "Player role", "ph_start": "Starting situation",
        "ph_style": "Narration style", "ph_mood": "Mood",
        "ph_amb": "Ambience", "ph_magic": "Physics / magic (rules)",
        "ph_premise": "Macro premise (story arc)",
        "basedata": "Base data", "complexity": "Complexity",
        "ph_audience": "Audience / age, e.g. 12+",
        "ph_patterns": "Patterns (empty=by complexity): three_act,mystery,…",
        "tone_lbl": "Tone — dark/humor/romance/action/horror (0–5), "
                    "pacing, notes",
        "ph_tnotes": "Tone/genre notes", "base_save": "Save base data",
        "sec_places": "Places", "sec_persons": "Persons",
        "sec_items": "Items", "sec_glossary": "Glossary",
        "sec_history": "History", "sec_fragments": "Fragments",
        "sec_rtables": "Random tables",
        "sug_title": "LLM suggestion — review &amp; apply",
        "apply": "Apply", "sug_bad": "(suggestion unreadable)",
        "add_h": "Add", "add_btn": "Add", "add_suffix": "add",
        "llm_title": "Let the LLM write", "llm_ph": "About what?",
        "llm_btn": "Generate suggestion", "reindex_btn": "Reindex RAG",
        "reindex_t": "Reindex", "reindexed": "facts reindexed",
        "tr_title": "Played transcripts", "tr_none": "No transcripts yet.",
        "tr_events": "events", "tr_one": "Transcript",
        "tr_notfound": "not found", "tr_all": "all transcripts",
        "tr_player": "Player", "tr_narr": "Narrator",
        "tr_blocked": "BLOCKED",
        "mod_title": "Moderation",
        "mod_desc": "Player input is checked BEFORE the LLM answers "
                    "(model %s). Threshold = score at/above which it is "
                    "blocked (0–1; lower = stricter).",
        "mod_active": "active", "mod_default": "Default threshold",
        "mod_cats": "Per-category as JSON (OpenAI categories, e.g. "
                    "{harassment: 0.3, violence: 0.7})",
        "save": "Save",
        "kind_place": "Place", "kind_person": "Person",
        "kind_item": "Item", "kind_fragment": "Fragment",
        "kind_glossary": "Glossary term", "kind_history": "History",
        "kind_rtable": "Random table", "kind_rentry": "Random-table entry",
        "fl_name": "Name", "fl_desc": "Description",
        "fl_rolerel": "Role/relations", "fl_props": "Properties/effect",
        "fl_title": "Title", "fl_text": "Text", "fl_term": "Term",
        "fl_def": "Definition", "fl_when": "Time/era",
        "fl_list": "List (name)", "fl_weight": "Weight (e.g. 2)",
        "fl_tags": "tags,comma",
    },
}


def web(locale: str) -> dict[str, str]:
    return WEB[norm(locale)]


def vp(locale: str) -> dict[str, str]:
    return VOICE_PROMPTS[norm(locale)]


def world_keywords(locale: str) -> dict[str, list[str]]:
    return WORLD_KEYWORDS[norm(locale)]
