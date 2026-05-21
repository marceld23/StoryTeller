"""prune_checkpoints keeps the N newest checkpoints per thread."""

import sqlite3

from storyteller_core.story.graph import prune_checkpoints


def _make_db(path, threads, per_thread):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, "
                 "checkpoint_id TEXT, parent_checkpoint_id TEXT, type TEXT, "
                 "checkpoint BLOB, metadata BLOB)")
    conn.execute("CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, "
                 "checkpoint_id TEXT, task_id TEXT, idx INT, channel TEXT, "
                 "type TEXT, value BLOB)")
    for t in threads:
        for i in range(per_thread):
            cid = f"cp-{i:04d}"
            conn.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?)",
                         (t, "", cid, None, "", b"", b""))
            conn.execute("INSERT INTO writes VALUES (?,?,?,?,?,?,?,?)",
                         (t, "", cid, "task", 0, "ch", "", b""))
    conn.commit()
    conn.close()


def test_prune_keeps_newest_per_thread(tmp_path):
    db = tmp_path / "checkpoints.db"
    _make_db(db, threads=["pi-a", "pi-b"], per_thread=10)

    res = prune_checkpoints(db_path=db, keep_per_thread=4)
    assert res["checkpoints_deleted"] == 12      # (10-4) * 2 threads
    assert res["writes_deleted"] == 12

    conn = sqlite3.connect(str(db))
    for t in ("pi-a", "pi-b"):
        rows = [r[0] for r in conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id=? "
            "ORDER BY checkpoint_id", (t,))]
        assert rows == ["cp-0006", "cp-0007", "cp-0008", "cp-0009"]  # newest 4
    assert conn.execute("SELECT count(*) FROM writes").fetchone()[0] == 8
    conn.close()


def test_prune_disabled_is_noop(tmp_path):
    db = tmp_path / "checkpoints.db"
    _make_db(db, threads=["pi-a"], per_thread=5)
    res = prune_checkpoints(db_path=db, keep_per_thread=0)
    assert res["checkpoints_deleted"] == 0
