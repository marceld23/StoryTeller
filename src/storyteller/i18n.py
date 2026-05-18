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
    },
    "en": {
        "quit": ("quit", "stop", "exit", "goodbye", "that's all"),
        "save": ("save",),
        "load": ("load", "resume"),
    },
}


def vp(locale: str) -> dict[str, str]:
    return VOICE_PROMPTS[norm(locale)]


def world_keywords(locale: str) -> dict[str, list[str]]:
    return WORLD_KEYWORDS[norm(locale)]
