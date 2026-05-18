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
        "welcome": "Willkommen beim Geschichtenerzähler.",
        "choose_world": "Welche Welt möchtest du spielen? Sage Sternenfahrt "
                        "für Science-Fiction, oder Immerwald für Fantasy.",
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
        "sys_menu": "Systemmenü. Sage: speichern, beenden, Spielzug zurück, "
                    "Spielstand laden, Audio umschalten, oder Menü "
                    "schließen.",
        "undone": "Der letzte Spielzug wurde zurückgenommen.",
        "closed": "Menü geschlossen. Weiter geht's.",
        "wake_hint": "Ich höre jetzt nicht mehr aktiv zu. Sag Hey Jarvis, "
                     "um mich wieder zu wecken.",
        "wifi_setup": "Kein WLAN gefunden. Verbinde dein Handy mit dem "
                      "WLAN storyteller-wifi. Es öffnet sich automatisch "
                      "eine Seite, auf der du dein WLAN auswählen und das "
                      "Passwort eingeben kannst. Danach starte ich neu.",
        "audio_bt_on": "Audioausgabe auf Bluetooth umgestellt.",
        "audio_bt_off": "Audioausgabe zurück auf den Standard.",
    },
    "en": {
        "welcome": "Welcome to the storyteller.",
        "choose_world": "Which world would you like to play? Say Starfaring "
                        "for science fiction, or Everwood for fantasy.",
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
        "sys_menu": "System menu. Say: save, quit, undo turn, load game, "
                    "switch audio, or close menu.",
        "undone": "The last turn was undone.",
        "closed": "Menu closed. Let's continue.",
        "wake_hint": "I'm no longer actively listening. Say Hey Jarvis to "
                     "wake me again.",
        "wifi_setup": "No Wi-Fi found. Connect your phone to the Wi-Fi "
                      "storyteller-wifi. A page opens automatically where "
                      "you can pick your Wi-Fi and enter the password. "
                      "Then I will restart.",
        "audio_bt_on": "Audio output switched to Bluetooth.",
        "audio_bt_off": "Audio output back to the default.",
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
           "Namen/Dinge. Keine Aufzählungen, keine Detailflut, kein Vorgriff "
           "auf mehrere Handlungsstränge. Schließe mit EINER konkreten, "
           "offenen Lage oder Frage, auf die der Spieler direkt reagieren "
           "kann. Ruhig und bildhaft, aber sparsam."),
    "en": ("Narrate SIMPLY and CLEARLY for listening: at most 4–6 short "
           "sentences. Only ONE situation per reply and at most one or two "
           "new names/things. No enumerations, no detail flood, no jumping "
           "ahead across multiple plot threads. End with ONE concrete, open "
           "situation or question the player can react to directly. Calm and "
           "vivid, but sparing."),
}

# --- Language instruction injected into the narrator system prompt ---
LANG_INSTRUCTION = {
    "de": "Antworte auf Deutsch.",
    "en": "Respond in English.",
}

MODERATION_BLOCKED = {
    "de": "Diese Eingabe kann ich nicht verarbeiten. Bitte formuliere es "
          "anders und freundlicher.",
    "en": "I can't process that input. Please rephrase it differently and "
          "more kindly.",
}

# --- Engine/CLI directives ---
OPENING_DIRECTIVE = {
    "de": ("[Beginne EINFACH und kurz: 3–5 kurze Sätze zur Ausgangslage, "
           "höchstens ein, zwei konkrete Dinge nennen, keine Infoflut. Ende "
           "mit EINER klaren, offenen Lage oder Frage, auf die der Spieler "
           "direkt reagieren kann.]"),
    "en": ("[Begin SIMPLY and briefly: 3–5 short sentences on the starting "
           "situation, mention at most one or two concrete things, no info "
           "flood. End with ONE clear, open situation or question the player "
           "can react to directly.]"),
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

# --- Question heuristic prefixes (Rückfragen-Kurzmodus) ---
Q_PREFIXES = {
    "de": ("was ", "wer ", "wo ", "wie ", "warum", "wieso", "welche",
           "welcher", "welches", "wann", "wozu", "kann ich", "darf ich",
           "habe ich", "hab ich", "gibt es", "gibt's", "wisst ihr",
           "weißt du", "weisst du", "erinner"),
    "en": ("what", "who", "where", "how", "why", "which", "when", "can i",
           "may i", "do i", "is there", "are there", "remind", "remember"),
}


# --- In-loop voice command keywords ---
CMD_KEYWORDS = {
    "de": {
        "quit": ("beenden", "aufhören", "schluss", "tschüss", "tschüs"),
        "save": ("speicher",),
        "load": ("lade", "spielstand"),
        "menu": ("system", "systemmenü", "systemmenu", "menü", "menu"),
    },
    "en": {
        "quit": ("quit", "stop", "exit", "goodbye", "that's all"),
        "save": ("save",),
        "load": ("load", "resume"),
        "menu": ("system", "system menu", "menu"),
    },
}


# --- Admin web UI strings ---
WEB = {
    "de": {
        "nav_dash": "🏠 Dashboard", "nav_new": "➕ Neue Welt",
        "nav_gen": "🧙 Welt aus Prompt", "nav_saves": "💾 Spielstände",
        "nav_tr": "📜 Verläufe", "nav_mod": "🛡 Moderation",
        "nav_api": "⚙ API", "nav_audio": "🔊 Audio",
        "audio_title": "Audio-Ausgabe",
        "audio_desc": "Backend zur Laufzeit umschalten (auch per Sprache: "
                      "System, dann Audio). pipewire = Bluetooth (vorher "
                      "scripts/setup_bluetooth.sh + Gerät koppeln).",
        "audio_backend": "Backend", "audio_sink_ph": "PipeWire-Sink "
                         "(leer = Default; wpctl status zeigt Namen)",
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
        "audio_title": "Audio output",
        "audio_desc": "Switch the backend at runtime (also by voice: "
                      "System, then Audio). pipewire = Bluetooth (run "
                      "scripts/setup_bluetooth.sh + pair a device first).",
        "audio_backend": "Backend", "audio_sink_ph": "PipeWire sink "
                         "(empty = default; wpctl status shows names)",
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
