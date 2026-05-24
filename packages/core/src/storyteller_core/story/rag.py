"""Per-(world, locale) RAG with sqlite-vec + OpenAI embeddings.

One DB file, `world_id` partition key composed as "<id>:<locale>" (clean
world/locale isolation), filterable fact_type, original text as +content.
Install: --extra rag.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import Config
from ..oai import get_embedding_client


class WorldRAG:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dim = cfg.models.embedding_dim
        self._db: sqlite3.Connection | None = None

    # --- intern ---
    def _conn(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db
        import sqlite_vec

        db_path = self.cfg.path(self.cfg.paths.rag_db)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(db_path), check_same_thread=False)
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        db.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS world_facts USING vec0(
                fact_id integer primary key,
                world_id text partition key,
                embedding float[{self.dim}] distance_metric=cosine,
                fact_type text,
                +content text
            )"""
        )
        self._db = db
        return db

    def _embed(self, texts: list[str]) -> list[list[float]]:
        client = get_embedding_client(self.cfg)
        r = client.embeddings.create(
            model=self.cfg.models.embedding,
            input=texts,
            dimensions=self.dim,
        )
        # Account for the embedding call in the cost ledger (skipped
        # automatically when embedding_endpoint points at a local server).
        try:
            from .cost import is_local_role
            from .ledger import CostLedger
            usage = getattr(r, "usage", None)
            if usage is not None and not is_local_role(self.cfg, "embedding"):
                tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                usd = tok / 1e6 * self.cfg.cost.usd_per_1m_embedding
                CostLedger(self.cfg).record(
                    kind="embed", usd=usd,
                    model=self.cfg.models.embedding, embed=tok)
        except Exception:
            pass
        return [d.embedding for d in r.data]

    # --- API ---
    @staticmethod
    def _key(world_id: str, locale: str) -> str:
        from ..i18n import norm

        return f"{world_id}:{norm(locale)}"

    def count(self, world_id: str, locale: str = "de") -> int:
        cur = self._conn().execute(
            "SELECT count(*) FROM world_facts WHERE world_id = ?",
            (self._key(world_id, locale),))
        return int(cur.fetchone()[0])

    def index_world(self, world, force: bool = False,
                    locale: str = "de") -> int:
        db = self._conn()
        wid = self._key(world.id, locale)
        if force:
            db.execute("DELETE FROM world_facts WHERE world_id = ?", (wid,))
            db.commit()
        elif self.count(world.id, locale) > 0:
            return 0

        items: list[tuple[str, str]] = []
        for r in getattr(world, "regions", []) or []:
            items.append(("region",
                           f"REGION {r.name}: {r.description}"))
        for p in world.places:
            # Enrich place facts with structural relations so a RAG hit
            # on the place name brings region / neighbours / sub-places
            # along in the same fact — saves the narrator from doing
            # multiple lookups to assemble geography.
            extras = []
            if getattr(p, "region", ""):
                extras.append(f"liegt in {p.region}")
            if getattr(p, "contains", []):
                extras.append(f"enthält {', '.join(p.contains)}")
            if getattr(p, "adjacent", []):
                extras.append(f"grenzt an {', '.join(p.adjacent)}")
            tail = f" ({'; '.join(extras)})" if extras else ""
            items.append(("place",
                           f"ORT {p.name}{tail}: {p.description}"))
        for f in getattr(world, "factions", []) or []:
            alliance = ""
            if getattr(f, "allies", []):
                alliance += f" Verbündete: {', '.join(f.allies)}."
            if getattr(f, "enemies", []):
                alliance += f" Gegner: {', '.join(f.enemies)}."
            items.append(("faction",
                           f"FRAKTION {f.name}: {f.description} "
                           f"Ziel: {f.goals}.{alliance} {f.relations}"))
        for pe in world.persons:
            # Person facts now carry faction membership inline so the
            # narrator can correctly stage allegiances without a second
            # RAG round-trip on the faction.
            fac = ""
            if getattr(pe, "faction", ""):
                role = getattr(pe, "faction_role", "")
                fac = (f" Mitglied der Fraktion {pe.faction}"
                       + (f" ({role})." if role else "."))
            items.append(("person",
                           f"PERSON {pe.name} ({pe.role}): {pe.description} "
                           f"{pe.relations}{fac}"))
        for it in getattr(world, "items", []):
            items.append(("item",
                           f"GEGENSTAND {it.name}: {it.description} "
                           f"{it.properties}"))
        for cr in getattr(world, "creatures", []) or []:
            habitat = f" Lebensraum: {cr.habitat}." if cr.habitat else ""
            threat = (f" Gefahrenstufe: {cr.threat_level}."
                      if getattr(cr, "threat_level", "") else "")
            items.append(("creature",
                           f"KREATUR {cr.name}: {cr.description}"
                           f"{habitat}{threat}"))
        for g in getattr(world, "glossary", []):
            items.append(("glossary", f"BEGRIFF {g.term}: {g.definition}"))
        for h in getattr(world, "history", []):
            items.append(("history",
                           f"HISTORIE ({h.when}) {h.title}: {h.description}"))
        for fr in world.fragments:
            items.append(("fragment", f"{fr.title}: {fr.text}"))
        for attr, label in (("magic_physics", "PHYSIK/MAGIE"),
                            ("ambience", "AMBIENTE"), ("mood", "STIMMUNG")):
            val = getattr(world, attr, "")
            if val:
                items.append(("system", f"{label}: {val}"))
        # Tech/magic structured rules: one fact per rule lets the RAG
        # surface only the relevant constraint instead of the whole
        # spec. The description is added once as an umbrella fact.
        tm = getattr(world, "tech_magic", None)
        if tm is not None:
            if tm.description:
                items.append(("tech_magic",
                               f"SYSTEM ({tm.kind}): {tm.description}"))
            for rule in (tm.rules or []):
                items.append(("tech_magic", f"REGEL: {rule}"))
            if tm.cost_or_risk:
                items.append(("tech_magic",
                               f"KOSTEN/RISIKO: {tm.cost_or_risk}"))
        if not items:
            return 0

        from sqlite_vec import serialize_float32

        embs = self._embed([t for _, t in items])
        for (ftype, text), emb in zip(items, embs, strict=False):
            db.execute(
                "INSERT INTO world_facts(world_id, embedding, fact_type,"
                " content) VALUES (?,?,?,?)",
                (wid, serialize_float32(emb), ftype, text),
            )
        db.commit()
        return len(items)

    def index_single_fact(self, world_id: str, locale: str,
                          fact_type: str, text: str) -> None:
        """Append ONE fact to the per-world RAG index. Used by the user-
        note system at runtime so player-introduced facts immediately show
        up in retrieval — both for the rest of the current session and for
        future sessions of the same world."""
        from sqlite_vec import serialize_float32

        wid = self._key(world_id, locale)
        emb = self._embed([text])[0]
        db = self._conn()
        db.execute(
            "INSERT INTO world_facts(world_id, embedding, fact_type,"
            " content) VALUES (?,?,?,?)",
            (wid, serialize_float32(emb), fact_type, text),
        )
        db.commit()

    def purge_world(self, world_id: str) -> int:
        """Delete ALL facts for this world across every locale partition.
        Called from worlds.registry.delete_world to keep the RAG DB
        consistent with the JSON file — otherwise the embeddings for
        the deleted world stay as orphan rows forever (and could even
        leak into RAG hits for a future world re-created under the
        same id). Returns the number of rows removed."""
        from ..i18n import LOCALES

        db = self._conn()
        total = 0
        for locale in LOCALES:
            cur = db.execute(
                "DELETE FROM world_facts WHERE world_id = ?",
                (self._key(world_id, locale),))
            total += cur.rowcount or 0
        db.commit()
        return total

    def move_world(self, old_id: str, new_id: str) -> int:
        """Repoint every fact's partition key from old_id to new_id
        across every locale partition. Called from
        worlds.registry.rename_world so the indexed embeddings move
        with the renamed world (instead of being re-indexed from
        scratch on first retrieval, which costs an OpenAI call for
        every fact). Returns the number of rows touched."""
        from ..i18n import LOCALES

        db = self._conn()
        total = 0
        for locale in LOCALES:
            cur = db.execute(
                "UPDATE world_facts SET world_id = ? WHERE world_id = ?",
                (self._key(new_id, locale), self._key(old_id, locale)))
            total += cur.rowcount or 0
        db.commit()
        return total

    def remove_facts_by_content(self, world_id: str, locale: str,
                                 fact_type: str, text: str) -> int:
        """Delete every fact with this exact content/type for this world.
        Used when an admin demotes a user-note or replaces it with a
        canonical world entry. Returns the number of rows removed."""
        wid = self._key(world_id, locale)
        cur = self._conn().execute(
            "DELETE FROM world_facts WHERE world_id = ? "
            "AND fact_type = ? AND content = ?",
            (wid, fact_type, text),
        )
        self._conn().commit()
        return cur.rowcount or 0

    def retrieve(self, world_id: str, query: str, k: int | None = None,
                 fact_type: str | None = None,
                 locale: str = "de") -> list[dict]:
        from sqlite_vec import serialize_float32

        k = k or self.cfg.story.rag_top_k
        q = self._embed([query])[0]
        sql = (
            "SELECT content, fact_type, distance FROM world_facts "
            "WHERE embedding MATCH ? AND world_id = ? AND k = ?"
        )
        params: list = [serialize_float32(q), self._key(world_id, locale), k]
        if fact_type:
            sql += " AND fact_type = ?"
            params.append(fact_type)
        sql += " ORDER BY distance"
        rows = self._conn().execute(sql, params).fetchall()
        return [{"content": c, "fact_type": t, "distance": d} for c, t, d in rows]
