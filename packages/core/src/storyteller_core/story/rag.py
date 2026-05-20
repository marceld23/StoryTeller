"""Per-(world, locale) RAG with sqlite-vec + OpenAI embeddings.

One DB file, `world_id` partition key composed as "<id>:<locale>" (clean
world/locale isolation), filterable fact_type, original text as +content.
Install: --extra rag.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import Config
from ..oai import get_client


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
        client = get_client(self.cfg)
        r = client.embeddings.create(
            model=self.cfg.models.embedding,
            input=texts,
            dimensions=self.dim,
        )
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
        for p in world.places:
            items.append(("place", f"ORT {p.name}: {p.description}"))
        for pe in world.persons:
            items.append(("person",
                           f"PERSON {pe.name} ({pe.role}): {pe.description} "
                           f"{pe.relations}"))
        for it in getattr(world, "items", []):
            items.append(("item",
                           f"GEGENSTAND {it.name}: {it.description} "
                           f"{it.properties}"))
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
        if not items:
            return 0

        from sqlite_vec import serialize_float32

        embs = self._embed([t for _, t in items])
        for (ftype, text), emb in zip(items, embs):
            db.execute(
                "INSERT INTO world_facts(world_id, embedding, fact_type,"
                " content) VALUES (?,?,?,?)",
                (wid, serialize_float32(emb), ftype, text),
            )
        db.commit()
        return len(items)

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
