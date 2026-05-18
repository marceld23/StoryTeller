"""Admin-Web-Frontend (Backend-Website).

- Dashboard (Welten, Spielstände, Konfiguration)
- Neue Welt anlegen (alle Felder)
- Welt bearbeiten: Basisdaten + Orte/Personen/Gegenstände/Glossar/Historie/
  Fragmente/Zufallslisten hinzufügen, optional vom LLM schreiben lassen
- RAG je Welt neu indexieren

Start:  uv sync --extra web && uv run storyteller admin
"""

from __future__ import annotations

import html
import json

from ..config import Config, load_config
from ..oai import get_client
from ..worlds.registry import all_world_ids, load_world, save_world
from ..worlds.schema import (
    Beat,
    Blueprint,
    Fragment,
    GlossaryEntry,
    HistoryEvent,
    Item,
    Person,
    Place,
    RandomEntry,
    RandomTable,
    World,
)

# kind -> (Label, [Feld-Platzhalter für f1..f4])
KIND_FIELDS = {
    "place": ("Ort", ["Name", "Beschreibung", "", "tags,komma"]),
    "person": ("Person", ["Name", "Beschreibung", "Rolle/Beziehungen",
                           "tags,komma"]),
    "item": ("Gegenstand", ["Name", "Beschreibung", "Eigenschaften/Wirkung",
                             "tags,komma"]),
    "fragment": ("Fragment", ["Titel", "Text", "", "tags,komma"]),
    "glossary": ("Glossar-Begriff", ["Begriff", "Definition", "", ""]),
    "history": ("Historie", ["Titel", "Beschreibung", "Zeit/Epoche", ""]),
    "rtable": ("Zufallsliste", ["Name", "Beschreibung", "", ""]),
    "rentry": ("Zufallslisten-Eintrag", ["Liste (Name)", "Text", "Gewicht(z.B. 2)",
                                          ""]),
}


def _esc(x) -> str:
    return html.escape(str(x))


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{_esc(title)}</title>"
        "<style>body{font:15px system-ui;margin:2rem;max-width:64rem}"
        "form{margin:.5rem 0;padding:.6rem;border:1px solid #ccc;border-radius:6px}"
        "input,textarea,select{font:inherit;width:100%;margin:.2rem 0;padding:.3rem}"
        "button{font:inherit;padding:.4rem .8rem;margin-top:.3rem}"
        "li{margin:.2rem 0}a{color:#06c}h2{margin-top:1.4rem}"
        "nav{background:#111;color:#fff;padding:.5rem .8rem;border-radius:6px;"
        "margin:-1rem 0 1rem}nav a{color:#9cf;margin-right:1rem}"
        ".card{border:1px solid #ddd;border-radius:8px;padding:.8rem;margin:.6rem 0}"
        "</style>"
        "<nav><a href='/'>🏠 Dashboard</a><a href='/new'>➕ Neue Welt</a>"
        "<a href='/saves'>💾 Spielstände</a>"
        "<a href='/transcripts'>📜 Verläufe</a>"
        "<a href='/moderation'>🛡 Moderation</a>"
        "<a href='/docs'>⚙ API</a></nav>"
        f"<h1>{_esc(title)}</h1>{body}"
    )


def _add_form(wid: str, kind: str) -> str:
    label, ph = KIND_FIELDS[kind]
    fields = "".join(
        f"<{'textarea' if i == 1 else 'input'} name='f{i+1}' "
        f"placeholder='{_esc(p)}'>{'</textarea>' if i == 1 else ''}"
        for i, p in enumerate(ph) if p or i < 2)
    return (f"<form method='post' action='/w/{wid}/add'>"
            f"<input type='hidden' name='kind' value='{kind}'>"
            f"<b>{_esc(label)} hinzufügen</b>{fields}"
            f"<button>Hinzufügen</button></form>")


def create_app(cfg: Config | None = None):
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, RedirectResponse

    cfg = cfg or load_config()
    app = FastAPI(title="Storyteller Admin")

    @app.get("/", response_class=HTMLResponse)
    def index():
        worlds = "".join(f"<li><a href='/w/{w}'>{_esc(w)}</a></li>"
                         for w in all_world_ids(cfg))
        m = cfg.models
        sd = cfg.path(cfg.paths.saves_dir)
        n = len(list(sd.glob("*.json"))) if sd.exists() else 0
        return _page("Storyteller — Backend", (
            f"<div class='card'><b>Konfiguration</b><br>"
            f"Story-LLM: {_esc(m.story_llm)}<br>"
            f"STT/TTS: {_esc(m.stt)} / {_esc(m.tts)} ({_esc(m.tts_voice)})<br>"
            f"Audio: {_esc(cfg.audio.backend)} | Kostendeckel "
            f"${cfg.story.cost_cap_usd_per_session}</div>"
            f"<div class='card'><b>Welten</b><ul>{worlds}</ul>"
            f"<a href='/new'>➕ Neue Welt anlegen</a></div>"
            f"<div class='card'><b>Spielstände:</b> {n} "
            f"(<a href='/saves'>ansehen</a>)</div>"))

    @app.get("/saves", response_class=HTMLResponse)
    def saves_view():
        import time as _t

        d = cfg.path(cfg.paths.saves_dir)
        rows = []
        files = sorted(d.glob("*.json"), key=lambda q: q.stat().st_mtime,
                       reverse=True) if d.exists() else []
        for p in files:
            try:
                s = json.loads(p.read_text())
                ts = _t.strftime("%Y-%m-%d %H:%M",
                                 _t.localtime(s.get("_saved_at", 0)))
                rows.append(f"<li><b>{_esc(s.get('_name', p.stem))}</b> — Welt "
                            f"{_esc(s.get('world_id', '?'))}, "
                            f"{len(s.get('memory', []))} Nachrichten, {ts}</li>")
            except Exception:
                rows.append(f"<li>{_esc(p.name)} (nicht lesbar)</li>")
        return _page("Spielstände", ("<ul>" + "".join(rows) + "</ul>")
                     if rows else "<p>Keine Spielstände.</p>")

    @app.get("/new", response_class=HTMLResponse)
    def new_form():
        f = lambda n, p, ta=False: (  # noqa: E731
            f"<textarea name='{n}' placeholder='{_esc(p)}'></textarea>" if ta
            else f"<input name='{n}' placeholder='{_esc(p)}'>")
        return _page("Neue Welt anlegen", (
            "<form method='post' action='/new'>"
            f"{f('id','id (kurz, z.B. mythos)')}{f('name','Name')}"
            f"{f('genre','Genre')}{f('description','Weltbeschreibung',1)}"
            f"{f('player_role','Spielerrolle')}"
            f"{f('starting_situation','Ausgangssituation',1)}"
            f"{f('narration_style','Erzählstil',1)}"
            f"{f('mood','Stimmung',1)}{f('ambience','Ambiente',1)}"
            f"{f('magic_physics','Physik / Magie (Regeln)',1)}"
            f"{f('premise','Makro-Prämisse (Spannungsbogen)',1)}"
            "<button>Welt anlegen</button></form>"
            "<p>Orte, Personen, Gegenstände, Glossar, Historie und "
            "Zufallslisten danach auf der Welt-Seite ergänzen.</p>"))

    @app.post("/new")
    def new_create(id: str = Form(...), name: str = Form(...),
                    genre: str = Form(""), description: str = Form(""),
                    player_role: str = Form(""),
                    starting_situation: str = Form(""),
                    narration_style: str = Form(""), mood: str = Form(""),
                    ambience: str = Form(""), magic_physics: str = Form(""),
                    premise: str = Form("")):
        wid = "".join(c for c in id.lower() if c.isalnum() or c in "-_") or "welt"
        bp = Blueprint(premise=premise or f"Eine Geschichte in {name}.", beats=[
            Beat(name="Aufhänger", goal="Lage & Hook etablieren", tension=2),
            Beat(name="Zuspitzung", goal="Eskalation", tension=7),
            Beat(name="Auflösung", goal="Abschluss", tension=3)])
        w = World(id=wid, name=name, genre=genre, description=description,
                  player_role=player_role,
                  starting_situation=starting_situation,
                  narration_style=narration_style, mood=mood,
                  ambience=ambience, magic_physics=magic_physics, blueprint=bp)
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.get("/w/{wid}", response_class=HTMLResponse)
    def world_view(wid: str, sug: str = ""):
        w = load_world(cfg, wid)

        def sec(title, rows):
            return (f"<div class='card'><b>{title}</b><ul>"
                    + "".join(f"<li>{r}</li>" for r in rows) + "</ul></div>")

        base = (
            f"<form method='post' action='/w/{wid}/base'><b>Basisdaten</b>"
            f"<textarea name='description'>{_esc(w.description)}</textarea>"
            f"<textarea name='starting_situation'>"
            f"{_esc(w.starting_situation)}</textarea>"
            f"<textarea name='narration_style'>{_esc(w.narration_style)}"
            f"</textarea><textarea name='mood'>{_esc(w.mood)}</textarea>"
            f"<textarea name='ambience'>{_esc(w.ambience)}</textarea>"
            f"<textarea name='magic_physics'>{_esc(w.magic_physics)}</textarea>"
            f"<textarea name='premise'>{_esc(w.blueprint.premise)}</textarea>"
            "<button>Basisdaten speichern</button></form>")

        secs = (
            sec("Orte", [f"<b>{_esc(p.name)}</b> — {_esc(p.description)}"
                         for p in w.places])
            + sec("Personen", [f"<b>{_esc(p.name)}</b> ({_esc(p.role)}) — "
                               f"{_esc(p.description)}" for p in w.persons])
            + sec("Gegenstände", [f"<b>{_esc(i.name)}</b> — "
                                  f"{_esc(i.description)} [{_esc(i.properties)}]"
                                  for i in w.items])
            + sec("Glossar", [f"<b>{_esc(g.term)}</b>: {_esc(g.definition)}"
                              for g in w.glossary])
            + sec("Historie", [f"<b>{_esc(h.title)}</b> ({_esc(h.when)}) — "
                               f"{_esc(h.description)}" for h in w.history])
            + sec("Fragmente", [f"<b>{_esc(fr.title)}</b> — {_esc(fr.text)}"
                                for fr in w.fragments])
            + sec("Zufallslisten", [
                f"<b>{_esc(t.name)}</b>: "
                + "; ".join(f"{e.text} (×{e.weight})" for e in t.entries)
                for t in w.random_tables]))

        sug_block = ""
        if sug:
            try:
                s = json.loads(sug)
                sug_block = (
                    f"<form method='post' action='/w/{wid}/add'>"
                    "<b>LLM-Vorschlag — prüfen &amp; übernehmen</b>"
                    f"<input name='kind' value='{_esc(s.get('kind',''))}'>"
                    f"<input name='f1' value='{_esc(s.get('f1',''))}'>"
                    f"<textarea name='f2'>{_esc(s.get('f2',''))}</textarea>"
                    f"<input name='f3' value='{_esc(s.get('f3',''))}'>"
                    f"<input name='f4' value='{_esc(s.get('f4',''))}'>"
                    "<button>Übernehmen</button></form>")
            except Exception:
                sug_block = "<p>(Vorschlag nicht lesbar)</p>"

        adds = "".join(_add_form(wid, k) for k in
                       ("place", "person", "item", "glossary", "history",
                        "fragment", "rtable", "rentry"))
        llm = (f"<form method='post' action='/w/{wid}/suggest'>"
               "<b>Vom LLM schreiben lassen</b>"
               "<select name='kind'>"
               + "".join(f"<option value='{k}'>{_esc(KIND_FIELDS[k][0])}"
                         "</option>" for k in ("fragment", "place", "person",
                                                "item", "glossary", "history"))
               + "</select><textarea name='prompt' placeholder='Worüber?'>"
               "</textarea><button>Vorschlag erzeugen</button></form>")
        reindex = (f"<form method='post' action='/w/{wid}/reindex'>"
                   "<button>RAG neu indexieren</button></form>")
        return _page(f"Welt: {w.name}", (
            f"<p><a href='/'>&larr; Dashboard</a> | {_esc(w.genre)} | "
            f"Spieler: {_esc(w.player_role)}</p>{base}{secs}{sug_block}"
            f"<h2>Hinzufügen</h2>{adds}{llm}{reindex}"))

    @app.post("/w/{wid}/base")
    def world_base(wid: str, description: str = Form(""),
                    starting_situation: str = Form(""),
                    narration_style: str = Form(""), mood: str = Form(""),
                    ambience: str = Form(""), magic_physics: str = Form(""),
                    premise: str = Form("")):
        w = load_world(cfg, wid)
        w.description = description
        w.starting_situation = starting_situation
        w.narration_style = narration_style
        w.mood = mood
        w.ambience = ambience
        w.magic_physics = magic_physics
        if premise:
            w.blueprint.premise = premise
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.post("/w/{wid}/add")
    def world_add(wid: str, kind: str = Form(...), f1: str = Form(""),
                   f2: str = Form(""), f3: str = Form(""), f4: str = Form("")):
        w = load_world(cfg, wid)
        tg = [t.strip() for t in f4.split(",") if t.strip()]
        if kind == "place":
            w.places.append(Place(name=f1, description=f2, tags=tg))
        elif kind == "person":
            w.persons.append(Person(name=f1, description=f2, role=f3,
                                     relations=f3, tags=tg))
        elif kind == "item":
            w.items.append(Item(name=f1, description=f2, properties=f3,
                                 tags=tg))
        elif kind == "glossary":
            w.glossary.append(GlossaryEntry(term=f1, definition=f2))
        elif kind == "history":
            w.history.append(HistoryEvent(title=f1, description=f2, when=f3))
        elif kind == "rtable":
            w.random_tables.append(RandomTable(name=f1, description=f2))
        elif kind == "rentry":
            for t in w.random_tables:
                if t.name.lower() == f1.strip().lower():
                    t.entries.append(RandomEntry(
                        text=f2, weight=int(f3) if f3.strip().isdigit() else 1))
                    break
        else:
            w.fragments.append(Fragment(title=f1, text=f2, tags=tg))
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.post("/w/{wid}/suggest")
    def world_suggest(wid: str, kind: str = Form(...), prompt: str = Form(...)):
        w = load_world(cfg, wid)
        label = KIND_FIELDS.get(kind, ("Fragment", []))[0]
        sysmsg = (
            f"Du baust die Welt {w.name} ({w.genre}) aus. {w.description}. "
            f"Stimmung: {w.mood}. Erzeuge GENAU EINEN {label}-Eintrag, "
            "konsistent zur Welt. Antworte als JSON: {\"kind\":\"" + kind +
            "\",\"f1\":\"Name/Titel/Begriff\",\"f2\":\"Beschreibung/Text/"
            "Definition\",\"f3\":\"Rolle/Eigenschaften/Zeit oder leer\","
            "\"f4\":\"tags,komma oder leer\"}")
        try:
            r = get_client(cfg).chat.completions.create(
                model=cfg.models.story_llm,
                messages=[{"role": "system", "content": sysmsg},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            sug = r.choices[0].message.content or "{}"
        except Exception as exc:
            sug = json.dumps({"kind": kind, "f1": "", "f2": f"(Fehler: {exc})",
                              "f3": "", "f4": ""})
        return RedirectResponse(f"/w/{wid}?sug={html.escape(sug)}",
                                status_code=303)

    @app.post("/w/{wid}/reindex")
    def world_reindex(wid: str):
        try:
            from ..story.rag import WorldRAG

            n = WorldRAG(cfg).index_world(load_world(cfg, wid), force=True,
                                          locale=cfg.general.locale)
            msg = f"{n} Fakten neu indexiert"
        except Exception as exc:
            msg = f"Fehler: {exc}"
        return _page("Reindex", f"<p>{_esc(msg)}</p>"
                     f"<p><a href='/w/{wid}'>zurück</a></p>")

    # ---------- Transcripts ----------
    @app.get("/transcripts", response_class=HTMLResponse)
    def transcripts_list():
        import time as _t

        d = cfg.path("data/transcripts")
        files = sorted(d.glob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True) \
            if d.exists() else []
        rows = []
        for p in files:
            ts = _t.strftime("%Y-%m-%d %H:%M",
                             _t.localtime(p.stat().st_mtime))
            try:
                n = sum(1 for _ in p.open(encoding="utf-8"))
            except Exception:
                n = 0
            rows.append(f"<li><a href='/transcript/{_esc(p.name)}'>"
                        f"{_esc(p.stem)}</a> — {n} Ereignisse, {ts}</li>")
        return _page("Gespielte Verläufe",
                     ("<ul>" + "".join(rows) + "</ul>") if rows
                     else "<p>Noch keine Verläufe.</p>")

    @app.get("/transcript/{name}", response_class=HTMLResponse)
    def transcript_view(name: str):
        safe = name.replace("/", "").replace("..", "")
        p = cfg.path("data/transcripts") / safe
        if not p.exists():
            return _page("Verlauf", "<p>nicht gefunden</p>")
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            t = e.get("type")
            if t == "user":
                out.append("<div class='card' style='background:#eef'>"
                           f"<b>🧑 Spieler:</b> {_esc(e.get('text',''))}</div>")
            elif t == "assistant":
                out.append(
                    f"<div class='card'><b>📖 Erzähler</b> <small>["
                    f"{_esc(e.get('state',''))} ${e.get('cost',0)}]</small>"
                    f"<br>{_esc(e.get('text',''))}</div>")
            elif t == "tool":
                out.append(
                    "<details class='card'><summary>🔧 Tool: "
                    f"{_esc(e.get('name',''))}</summary><pre>args: "
                    f"{_esc(json.dumps(e.get('args',{}),ensure_ascii=False))}"
                    f"\nresult: {_esc(e.get('result',''))}</pre></details>")
            elif t == "moderation":
                ok = e.get("ok", True)
                col = "#e7f7e7" if ok else "#fde7e7"
                fl = e.get("flagged", [])
                out.append(
                    f"<div class='card' style='background:{col}'>🛡 "
                    f"Moderation: {'OK' if ok else 'BLOCKIERT'}"
                    + (f" — {_esc(json.dumps(fl,ensure_ascii=False))}"
                       if fl else "") + "</div>")
            elif t == "note":
                out.append(f"<p><i>{_esc(e.get('text',''))}</i></p>")
        return _page(f"Verlauf: {_esc(p.stem)}",
                     "<p><a href='/transcripts'>&larr; alle Verläufe</a></p>"
                     + "".join(out))

    # ---------- Moderation thresholds ----------
    @app.get("/moderation", response_class=HTMLResponse)
    def moderation_form():
        from ..story.moderation import load_overrides

        ov = load_overrides(cfg)
        en = ov.get("enabled", cfg.moderation.enabled)
        dflt = ov.get("default", cfg.moderation.default_threshold)
        cats = json.dumps(ov.get("categories", {}), ensure_ascii=False,
                          indent=2)
        return _page("Moderation", (
            "<p>Spieler-Eingaben werden VOR der LLM-Antwort geprüft "
            f"(Modell {_esc(cfg.moderation.model)}). Schwelle = Score, ab "
            "dem blockiert wird (0–1; niedriger = strenger).</p>"
            "<form method='post' action='/moderation'>"
            f"<label><input type='checkbox' name='enabled' "
            f"{'checked' if en else ''}> aktiv</label><br>"
            f"<label>Default-Schwelle</label>"
            f"<input name='default' value='{_esc(dflt)}'>"
            "<label>Pro-Kategorie als JSON (OpenAI-Kategorien, z. B. "
            "{\"harassment\": 0.3, \"violence\": 0.7})</label>"
            f"<textarea name='categories' rows='8'>{_esc(cats)}</textarea>"
            "<button>Speichern</button></form>"))

    @app.post("/moderation")
    def moderation_save(enabled: str = Form(None),
                        default: str = Form("0.5"),
                        categories: str = Form("{}")):
        from ..story.moderation import save_overrides

        try:
            cats = {str(k): float(v)
                    for k, v in json.loads(categories or "{}").items()}
        except Exception:
            cats = {}
        try:
            df = float(default)
        except Exception:
            df = cfg.moderation.default_threshold
        save_overrides(cfg, {"enabled": enabled is not None, "default": df,
                             "categories": cats})
        return RedirectResponse("/moderation", status_code=303)

    return app


try:
    app = create_app()
except Exception:  # pragma: no cover
    app = None
