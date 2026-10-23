import sqlite3
import pytest
from agentlens.schema import init_db


def test_tables_created(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "spans", "cache_entries", "test_results"} <= names


def test_span_tree_and_cascade(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    conn.execute("INSERT INTO runs(id,name,started_at) VALUES('r1','demo',0)")
    conn.execute("INSERT INTO spans(id,run_id,kind,name,started_at) VALUES('s1','r1','agent','a',0)")
    conn.execute("INSERT INTO spans(id,run_id,parent_id,kind,name,started_at) VALUES('s2','r1','s1','llm','m',0)")
    conn.execute("DELETE FROM runs WHERE id='r1'")
    assert conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0] == 0


def test_rejects_bad_kind(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    conn.execute("INSERT INTO runs(id,name,started_at) VALUES('r1','demo',0)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO spans(id,run_id,kind,name,started_at) VALUES('s','r1','bogus','x',0)")
