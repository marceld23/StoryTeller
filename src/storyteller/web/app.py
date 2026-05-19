"""Admin web frontend (backend website), localized de/en via i18n.WEB.

- Dashboard (worlds, saves, configuration)
- Create a new world (all fields) or generate one from a single prompt
- Edit a world: base data + places/persons/items/glossary/history/
  fragments/random tables (optionally LLM-written); per-world dramaturgy
  (complexity, story patterns, tone, audience)
- Transcripts viewer; moderation thresholds; per-world RAG reindex

Start:  uv sync --extra web && uv run storyteller admin
The UI language follows config.general.locale.
"""

from __future__ import annotations

import html
import json

from ..config import Config, load_config
from ..i18n import norm, web
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


def _esc(x) -> str:
    return html.escape(str(x))


def _kind_fields(T: dict) -> dict:
    """kind -> (label, [placeholders for f1..f4]) in the active locale."""
    tg = T["fl_tags"]
    return {
        "place": (T["kind_place"], [T["fl_name"], T["fl_desc"], "", tg]),
        "person": (T["kind_person"], [T["fl_name"], T["fl_desc"],
                                      T["fl_rolerel"], tg]),
        "item": (T["kind_item"], [T["fl_name"], T["fl_desc"],
                                  T["fl_props"], tg]),
        "fragment": (T["kind_fragment"], [T["fl_title"], T["fl_text"], "",
                                          tg]),
        "glossary": (T["kind_glossary"], [T["fl_term"], T["fl_def"], "",
                                          ""]),
        "history": (T["kind_history"], [T["fl_title"], T["fl_desc"],
                                        T["fl_when"], ""]),
        "rtable": (T["kind_rtable"], [T["fl_name"], T["fl_desc"], "", ""]),
        "rentry": (T["kind_rentry"], [T["fl_list"], T["fl_text"],
                                      T["fl_weight"], ""]),
    }


def _page(T: dict, title: str, body: str) -> str:
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_esc(title)}</title>"
        # apply saved theme before paint (no flash)
        "<script>try{var t=localStorage.getItem('st-theme');"
        "if(t)document.documentElement.dataset.theme=t;}catch(e){}</script>"
        "<style>"
        ":root{--bg:#fff;--fg:#111;--card:#fff;--bd:#ccc;--link:#06c;"
        "--navbg:#111;--navfg:#fff;--navlink:#9cf;--pre:#f4f4f4}"
        "@media(prefers-color-scheme:dark){:root:not([data-theme=light]){"
        "--bg:#15171a;--fg:#e7e7e7;--card:#1e2126;--bd:#3a3f47;--link:#6cf;"
        "--navbg:#000;--navfg:#fff;--navlink:#9cf;--pre:#101216}}"
        ":root[data-theme=dark]{--bg:#15171a;--fg:#e7e7e7;--card:#1e2126;"
        "--bd:#3a3f47;--link:#6cf;--navbg:#000;--navfg:#fff;"
        "--navlink:#9cf;--pre:#101216}"
        "body{font:15px system-ui;margin:2rem;max-width:64rem;"
        "background:var(--bg);color:var(--fg)}"
        "form{margin:.5rem 0;padding:.6rem;border:1px solid var(--bd);"
        "border-radius:6px}input,textarea,select{font:inherit;width:100%;"
        "margin:.2rem 0;padding:.3rem;background:var(--card);"
        "color:var(--fg);border:1px solid var(--bd);border-radius:4px}"
        "button{font:inherit;padding:.4rem .8rem;margin-top:.3rem;"
        "background:var(--navbg);color:var(--navfg);border:0;"
        "border-radius:6px;cursor:pointer}li{margin:.2rem 0}"
        "a{color:var(--link)}h2{margin-top:1.4rem}"
        "pre{background:var(--pre);padding:.5rem;overflow:auto;"
        "border-radius:4px}nav{background:var(--navbg);color:var(--navfg);"
        "padding:.5rem .8rem;border-radius:6px;margin:-1rem 0 1rem}"
        "nav a{color:var(--navlink);margin-right:1rem;cursor:pointer}"
        ".card{border:1px solid var(--bd);background:var(--card);"
        "border-radius:8px;padding:.8rem;margin:.6rem 0}"
        # theme-aware tints (work on light & dark)
        ".b-user{background:rgba(90,140,255,.14)}"
        ".b-ok{background:rgba(60,180,90,.16)}"
        ".b-bad{background:rgba(220,60,60,.16)}</style>"
        "<script>function stTheme(){var d=document.documentElement,"
        "c=d.dataset.theme==='dark'?'light':'dark';d.dataset.theme=c;"
        "try{localStorage.setItem('st-theme',c);}catch(e){}}</script>"
        f"<nav><a href='/'>{T['nav_dash']}</a>"
        f"<a href='/new'>{T['nav_new']}</a>"
        f"<a href='/generate'>{T['nav_gen']}</a>"
        f"<a href='/saves'>{T['nav_saves']}</a>"
        f"<a href='/transcripts'>{T['nav_tr']}</a>"
        f"<a href='/moderation'>{T['nav_mod']}</a>"
        f"<a href='/audio'>{T['nav_audio']}</a>"
        f"<a href='/docs'>{T['nav_api']}</a>"
        "<a onclick='stTheme()' title='Dark/Light'>🌓</a></nav>"
        f"<h1>{_esc(title)}</h1>{body}"
    )


def create_app(cfg: Config | None = None):
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, RedirectResponse

    cfg = cfg or load_config()
    loc = norm(cfg.general.locale)
    T = web(loc)
    KF = _kind_fields(T)
    app = FastAPI(title="Storyteller Admin")

    def _add_form(wid: str, kind: str) -> str:
        label, ph = KF[kind]
        fields = "".join(
            f"<{'textarea' if i == 1 else 'input'} name='f{i+1}' "
            f"placeholder='{_esc(p)}'>{'</textarea>' if i == 1 else ''}"
            for i, p in enumerate(ph) if p or i < 2)
        return (f"<form method='post' action='/w/{wid}/add'>"
                f"<input type='hidden' name='kind' value='{kind}'>"
                f"<b>{_esc(label)} {T['add_suffix']}</b>{fields}"
                f"<button>{T['add_btn']}</button></form>")

    @app.get("/", response_class=HTMLResponse)
    def index():
        worlds = "".join(f"<li><a href='/w/{w}'>{_esc(w)}</a></li>"
                         for w in all_world_ids(cfg))
        m = cfg.models
        sd = cfg.path(cfg.paths.saves_dir)
        n = len(list(sd.glob("*.json"))) if sd.exists() else 0
        return _page(T, T["backend"], (
            f"<div class='card'><b>{T['config']}</b><br>"
            f"Story-LLM: {_esc(m.story_llm)}<br>"
            f"Gen-LLM: {_esc(m.gen)} | Planner: {_esc(m.planner)}<br>"
            f"STT/TTS: {_esc(m.stt)} / {_esc(m.tts)} ({_esc(m.tts_voice)})"
            f"<br>Audio: {_esc(cfg.audio.backend)} | {T['cost_cap']} "
            f"${cfg.story.cost_cap_usd_per_session} | Locale: {loc}</div>"
            f"<div class='card'><b>{T['worlds']}</b><ul>{worlds}</ul>"
            f"<a href='/new'>{T['new_world']}</a></div>"
            f"<div class='card'><b>{T['saves']}:</b> {n} "
            f"(<a href='/saves'>{T['view']}</a>)</div>"))

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
                rows.append(
                    f"<li><b>{_esc(s.get('_name', p.stem))}</b> — "
                    f"{T['s_world']} {_esc(s.get('world_id', '?'))}, "
                    f"{len(s.get('memory', []))} {T['s_msgs']}, {ts}</li>")
            except Exception:
                rows.append(f"<li>{_esc(p.name)} ({T['s_unreadable']})</li>")
        return _page(T, T["saves"], ("<ul>" + "".join(rows) + "</ul>")
                     if rows else f"<p>{T['saves_none']}</p>")

    @app.get("/generate", response_class=HTMLResponse)
    def generate_form():
        return _page(T, T["gen_title"], (
            f"<p>{T['gen_desc']}</p>"
            "<form method='post' action='/generate'>"
            f"<textarea name='prompt' rows='6' placeholder="
            f"'{_esc(T['gen_ph'])}' required></textarea>"
            f"<button>{T['gen_btn']}</button></form>"))

    @app.post("/generate")
    def generate_do(prompt: str = Form(...)):
        from ..worlds.generate import generate_world

        try:
            w = generate_world(cfg, prompt)
            save_world(cfg, w)
        except Exception as exc:
            return _page(T, T["error"],
                         f"<p>{T['gen_failed']}: {_esc(exc)}</p>"
                         f"<p><a href='/generate'>{T['back']}</a></p>")
        try:
            from ..story.rag import WorldRAG

            WorldRAG(cfg).index_world(w, force=True, locale=loc)
        except Exception:
            pass
        return RedirectResponse(f"/w/{w.id}", status_code=303)

    @app.get("/new", response_class=HTMLResponse)
    def new_form():
        def f(n, ph_key, ta=False):
            ph = _esc(T[ph_key])
            return (f"<textarea name='{n}' placeholder='{ph}'></textarea>"
                    if ta else f"<input name='{n}' placeholder='{ph}'>")
        return _page(T, T["new_title"], (
            "<form method='post' action='/new'>"
            f"{f('id','ph_id')}{f('name','ph_name')}"
            f"{f('genre','ph_genre')}{f('description','ph_desc',1)}"
            f"{f('player_role','ph_role')}"
            f"{f('starting_situation','ph_start',1)}"
            f"{f('narration_style','ph_style',1)}"
            f"{f('mood','ph_mood',1)}{f('ambience','ph_amb',1)}"
            f"{f('magic_physics','ph_magic',1)}"
            f"{f('premise','ph_premise',1)}"
            f"<button>{T['new_btn']}</button></form>"
            f"<p>{T['new_hint']}</p>"))

    @app.post("/new")
    def new_create(id: str = Form(...), name: str = Form(...),
                    genre: str = Form(""), description: str = Form(""),
                    player_role: str = Form(""),
                    starting_situation: str = Form(""),
                    narration_style: str = Form(""), mood: str = Form(""),
                    ambience: str = Form(""), magic_physics: str = Form(""),
                    premise: str = Form("")):
        wid = "".join(c for c in id.lower()
                      if c.isalnum() or c in "-_") or "welt"
        bp = Blueprint(
            premise=premise or f"Eine Geschichte in {name}.",
            beats=[Beat(name="Aufhänger", goal="Lage & Hook etablieren",
                        tension=2),
                   Beat(name="Zuspitzung", goal="Eskalation", tension=7),
                   Beat(name="Auflösung", goal="Abschluss", tension=3)])
        w = World(id=wid, name=name, genre=genre, description=description,
                  player_role=player_role,
                  starting_situation=starting_situation,
                  narration_style=narration_style, mood=mood,
                  ambience=ambience, magic_physics=magic_physics,
                  blueprint=bp)
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.get("/w/{wid}", response_class=HTMLResponse)
    def world_view(wid: str, sug: str = ""):
        w = load_world(cfg, wid)

        def sec(title, rows):
            return (f"<div class='card'><b>{title}</b><ul>"
                    + "".join(f"<li>{r}</li>" for r in rows) + "</ul></div>")

        base = (
            f"<form method='post' action='/w/{wid}/base'>"
            f"<b>{T['basedata']}</b>"
            f"<textarea name='description'>{_esc(w.description)}</textarea>"
            f"<textarea name='starting_situation'>"
            f"{_esc(w.starting_situation)}</textarea>"
            f"<textarea name='narration_style'>{_esc(w.narration_style)}"
            f"</textarea><textarea name='mood'>{_esc(w.mood)}</textarea>"
            f"<textarea name='ambience'>{_esc(w.ambience)}</textarea>"
            f"<textarea name='magic_physics'>{_esc(w.magic_physics)}"
            f"</textarea>"
            f"<textarea name='premise'>{_esc(w.blueprint.premise)}"
            f"</textarea>"
            f"<label>{T['complexity']}</label><select name='complexity'>"
            + "".join(f"<option{' selected' if w.complexity==c else ''}>"
                      f"{c}</option>" for c in ("simple", "standard", "rich"))
            + "</select>"
            f"<input name='audience' value='{_esc(w.audience)}' "
            f"placeholder='{_esc(T['ph_audience'])}'>"
            f"<input name='story_patterns' "
            f"value='{_esc(','.join(w.story_patterns))}' "
            f"placeholder='{_esc(T['ph_patterns'])}'>"
            f"<label>{T['tone_lbl']}</label>"
            f"<input name='t_dark' value='{w.tone.darkness}'>"
            f"<input name='t_humor' value='{w.tone.humor}'>"
            f"<input name='t_rom' value='{w.tone.romance}'>"
            f"<input name='t_act' value='{w.tone.action}'>"
            f"<input name='t_hor' value='{w.tone.horror}'>"
            "<select name='t_pace'>"
            + "".join(f"<option{' selected' if w.tone.pacing==p else ''}>"
                      f"{p}</option>" for p in ("slow", "medium", "fast"))
            + "</select>"
            f"<input name='t_notes' value='{_esc(w.tone.notes)}' "
            f"placeholder='{_esc(T['ph_tnotes'])}'>"
            f"<button>{T['base_save']}</button></form>")

        secs = (
            sec(T["sec_places"],
                [f"<b>{_esc(p.name)}</b> — {_esc(p.description)}"
                 for p in w.places])
            + sec(T["sec_persons"],
                  [f"<b>{_esc(p.name)}</b> ({_esc(p.role)}) — "
                   f"{_esc(p.description)}" for p in w.persons])
            + sec(T["sec_items"],
                  [f"<b>{_esc(i.name)}</b> — {_esc(i.description)} "
                   f"[{_esc(i.properties)}]" for i in w.items])
            + sec(T["sec_glossary"],
                  [f"<b>{_esc(g.term)}</b>: {_esc(g.definition)}"
                   for g in w.glossary])
            + sec(T["sec_history"],
                  [f"<b>{_esc(h.title)}</b> ({_esc(h.when)}) — "
                   f"{_esc(h.description)}" for h in w.history])
            + sec(T["sec_fragments"],
                  [f"<b>{_esc(fr.title)}</b> — {_esc(fr.text)}"
                   for fr in w.fragments])
            + sec(T["sec_rtables"], [
                f"<b>{_esc(t.name)}</b>: "
                + "; ".join(f"{_esc(e.text)} (×{e.weight})"
                            for e in t.entries)
                for t in w.random_tables]))

        sug_block = ""
        if sug:
            try:
                s = json.loads(sug)
                sug_block = (
                    f"<form method='post' action='/w/{wid}/add'>"
                    f"<b>{T['sug_title']}</b>"
                    f"<input name='kind' value='{_esc(s.get('kind',''))}'>"
                    f"<input name='f1' value='{_esc(s.get('f1',''))}'>"
                    f"<textarea name='f2'>{_esc(s.get('f2',''))}</textarea>"
                    f"<input name='f3' value='{_esc(s.get('f3',''))}'>"
                    f"<input name='f4' value='{_esc(s.get('f4',''))}'>"
                    f"<button>{T['apply']}</button></form>")
            except Exception:
                sug_block = f"<p>{T['sug_bad']}</p>"

        adds = "".join(_add_form(wid, k) for k in
                       ("place", "person", "item", "glossary", "history",
                        "fragment", "rtable", "rentry"))
        llm = (f"<form method='post' action='/w/{wid}/suggest'>"
               f"<b>{T['llm_title']}</b><select name='kind'>"
               + "".join(f"<option value='{k}'>{_esc(KF[k][0])}</option>"
                         for k in ("fragment", "place", "person", "item",
                                   "glossary", "history"))
               + f"</select><textarea name='prompt' "
               f"placeholder='{_esc(T['llm_ph'])}'></textarea>"
               f"<button>{T['llm_btn']}</button></form>")
        reindex = (f"<form method='post' action='/w/{wid}/reindex'>"
                   f"<button>{T['reindex_btn']}</button></form>")
        return _page(T, w.name, (
            f"<p><a href='/'>&larr; {T['nav_dash']}</a> | {_esc(w.genre)} | "
            f"{T['player']}: {_esc(w.player_role)}</p>"
            f"{base}{secs}{sug_block}"
            f"<h2>{T['add_h']}</h2>{adds}{llm}{reindex}"))

    @app.post("/w/{wid}/base")
    def world_base(wid: str, description: str = Form(""),
                    starting_situation: str = Form(""),
                    narration_style: str = Form(""), mood: str = Form(""),
                    ambience: str = Form(""), magic_physics: str = Form(""),
                    premise: str = Form(""),
                    complexity: str = Form("standard"),
                    audience: str = Form("erwachsene"),
                    story_patterns: str = Form(""), t_dark: str = Form("2"),
                    t_humor: str = Form("1"), t_rom: str = Form("1"),
                    t_act: str = Form("3"), t_hor: str = Form("1"),
                    t_pace: str = Form("medium"), t_notes: str = Form("")):
        from ..story.patterns import PATTERNS, norm_complexity

        def _i(v, d):
            try:
                return max(0, min(5, int(float(v))))
            except Exception:
                return d

        w = load_world(cfg, wid)
        w.description = description
        w.starting_situation = starting_situation
        w.narration_style = narration_style
        w.mood = mood
        w.ambience = ambience
        w.magic_physics = magic_physics
        if premise:
            w.blueprint.premise = premise
        w.complexity = norm_complexity(complexity)
        w.audience = audience or "erwachsene"
        w.story_patterns = [p.strip() for p in story_patterns.split(",")
                            if p.strip() in PATTERNS]
        w.tone.darkness = _i(t_dark, 2)
        w.tone.humor = _i(t_humor, 1)
        w.tone.romance = _i(t_rom, 1)
        w.tone.action = _i(t_act, 3)
        w.tone.horror = _i(t_hor, 1)
        w.tone.pacing = t_pace if t_pace in ("slow", "medium", "fast") \
            else "medium"
        w.tone.notes = t_notes
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.post("/w/{wid}/add")
    def world_add(wid: str, kind: str = Form(...), f1: str = Form(""),
                   f2: str = Form(""), f3: str = Form(""),
                   f4: str = Form("")):
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
                        text=f2,
                        weight=int(f3) if f3.strip().isdigit() else 1))
                    break
        else:
            w.fragments.append(Fragment(title=f1, text=f2, tags=tg))
        save_world(cfg, w)
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.post("/w/{wid}/suggest")
    def world_suggest(wid: str, kind: str = Form(...),
                      prompt: str = Form(...)):
        w = load_world(cfg, wid)
        label = KF.get(kind, (T["kind_fragment"], []))[0]
        sysmsg = (
            f"Build out the world {w.name} ({w.genre}). {w.description}. "
            f"Mood: {w.mood}. Produce EXACTLY ONE {label} entry, consistent "
            "with the world. Reply as JSON: {\"kind\":\"" + kind +
            "\",\"f1\":\"name/title/term\",\"f2\":\"description/text/"
            "definition\",\"f3\":\"role/properties/time or empty\","
            "\"f4\":\"tags,comma or empty\"}. Use the world's language.")
        try:
            r = get_client(cfg).chat.completions.create(
                model=cfg.models.gen,
                messages=[{"role": "system", "content": sysmsg},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"})
            sug = r.choices[0].message.content or "{}"
        except Exception as exc:
            sug = json.dumps({"kind": kind, "f1": "",
                              "f2": f"({T['error']}: {exc})",
                              "f3": "", "f4": ""})
        return RedirectResponse(f"/w/{wid}?sug={html.escape(sug)}",
                                status_code=303)

    @app.post("/w/{wid}/reindex")
    def world_reindex(wid: str):
        try:
            from ..story.rag import WorldRAG

            n = WorldRAG(cfg).index_world(load_world(cfg, wid), force=True,
                                          locale=loc)
            msg = f"{n} {T['reindexed']}"
        except Exception as exc:
            msg = f"{T['error']}: {exc}"
        return _page(T, T["reindex_t"], f"<p>{_esc(msg)}</p>"
                     f"<p><a href='/w/{wid}'>{T['back']}</a></p>")

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
                        f"{_esc(p.stem)}</a> — {n} {T['tr_events']}, "
                        f"{ts}</li>")
        return _page(T, T["tr_title"],
                     ("<ul>" + "".join(rows) + "</ul>") if rows
                     else f"<p>{T['tr_none']}</p>")

    @app.get("/transcript/{name}", response_class=HTMLResponse)
    def transcript_view(name: str):
        safe = name.replace("/", "").replace("..", "")
        p = cfg.path("data/transcripts") / safe
        if not p.exists():
            return _page(T, T["tr_one"], f"<p>{T['tr_notfound']}</p>")
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            t = e.get("type")
            if t == "user":
                out.append("<div class='card b-user'>"
                           f"<b>🧑 {T['tr_player']}:</b> "
                           f"{_esc(e.get('text',''))}</div>")
            elif t == "assistant":
                out.append(
                    f"<div class='card'><b>📖 {T['tr_narr']}</b> <small>["
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
                cls = "b-ok" if ok else "b-bad"
                fl = e.get("flagged", [])
                out.append(
                    f"<div class='card {cls}'>🛡 "
                    f"{T['mod_title']}: "
                    f"{'OK' if ok else T['tr_blocked']}"
                    + (f" — {_esc(json.dumps(fl,ensure_ascii=False))}"
                       if fl else "") + "</div>")
            elif t == "note":
                out.append(f"<p><i>{_esc(e.get('text',''))}</i></p>")
        return _page(T, f"{T['tr_one']}: {_esc(p.stem)}",
                     f"<p><a href='/transcripts'>&larr; {T['tr_all']}</a></p>"
                     + "".join(out))

    @app.get("/moderation", response_class=HTMLResponse)
    def moderation_form():
        from ..story.moderation import load_overrides

        ov = load_overrides(cfg)
        en = ov.get("enabled", cfg.moderation.enabled)
        dflt = ov.get("default", cfg.moderation.default_threshold)
        cats = json.dumps(ov.get("categories", {}), ensure_ascii=False,
                          indent=2)
        return _page(T, T["mod_title"], (
            f"<p>{T['mod_desc'] % _esc(cfg.moderation.model)}</p>"
            "<form method='post' action='/moderation'>"
            f"<label><input type='checkbox' name='enabled' "
            f"{'checked' if en else ''}> {T['mod_active']}</label><br>"
            f"<label>{T['mod_default']}</label>"
            f"<input name='default' value='{_esc(dflt)}'>"
            f"<label>{T['mod_cats']}</label>"
            f"<textarea name='categories' rows='8'>{_esc(cats)}</textarea>"
            f"<button>{T['save']}</button></form>"))

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

    @app.get("/audio", response_class=HTMLResponse)
    def audio_form():
        from ..runtime import (
            effective_volume,
            load_audio_override,
            resolve_backend_name,
        )

        ov = load_audio_override(cfg)
        cur = str(ov.get("backend") or cfg.audio.backend or "auto")
        sink = ov.get("pw_sink", cfg.audio.pw_sink or "")
        vol = effective_volume(cfg)
        live = None
        try:
            from ..audio.backend import get_backend

            live = get_backend(cfg).get_volume()
        except Exception:
            live = None
        live_txt = (f" ({T['audio_volume_now']}: {live} %)"
                    if isinstance(live, int) else "")
        opts = "".join(
            f"<option{' selected' if cur == b else ''}>{b}</option>"
            for b in ("auto", "alsa_softvol", "portable", "pipewire"))
        return _page(T, T["audio_title"], (
            f"<p>{T['audio_desc']}</p>"
            f"<p><b>{T['audio_backend']} (effektiv):</b> "
            f"{_esc(resolve_backend_name(cfg))}</p>"
            "<form method='post' action='/audio'>"
            f"<label>{T['audio_backend']}</label>"
            f"<select name='backend'>{opts}</select>"
            f"<input name='pw_sink' value='{_esc(sink)}' "
            f"placeholder='{_esc(T['audio_sink_ph'])}'>"
            f"<label>{T['audio_volume']}{live_txt}</label>"
            f"<input type='number' name='volume' min='0' max='100' "
            f"value='{vol}'>"
            f"<small>{T['audio_volume_hint']}</small>"
            f"<button>{T['save']}</button></form>"))

    @app.post("/audio")
    def audio_save(backend: str = Form("auto"), pw_sink: str = Form(""),
                   volume: str = Form("")):
        from ..runtime import save_audio_override

        b = backend if backend in ("auto", "alsa_softvol", "portable",
                                   "pipewire") else "auto"
        try:
            vol = max(0, min(100, int(float(volume))))
        except (TypeError, ValueError):
            vol = None
        data = {"backend": b, "pw_sink": pw_sink.strip()}
        if vol is not None:
            data["volume"] = vol
        save_audio_override(cfg, data)
        if vol is not None:
            try:
                from ..audio.backend import get_backend

                get_backend(cfg).set_volume(vol)
            except Exception:
                pass
        return RedirectResponse("/audio", status_code=303)

    return app


try:
    app = create_app()
except Exception:  # pragma: no cover
    app = None
