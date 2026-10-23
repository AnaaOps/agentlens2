"""SQLite schema for agentlens traces. Single source of truth for the DB layout."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    started_at       REAL NOT NULL,
    ended_at         REAL,
    status           TEXT NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'success', 'error', 'max_steps')),
    model            TEXT,
    total_tokens     INTEGER NOT NULL DEFAULT 0,
    total_latency_ms REAL NOT NULL DEFAULT 0,
    error            TEXT,
    failure_label    TEXT
);

CREATE TABLE IF NOT EXISTS spans (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    parent_id     TEXT REFERENCES spans(id),
    kind          TEXT NOT NULL CHECK (kind IN ('agent', 'llm', 'tool')),
    name          TEXT NOT NULL,
    input_json    TEXT,
    output_json   TEXT,
    started_at    REAL NOT NULL,
    latency_ms    REAL,
    tokens_in     INTEGER,
    tokens_out    INTEGER,
    error         TEXT,
    failure_label TEXT
);

CREATE TABLE IF NOT EXISTS cache_entries (
    request_hash  TEXT PRIMARY KEY,
    model         TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS test_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    suite          TEXT NOT NULL,
    case_id        TEXT NOT NULL,
    run_id         TEXT REFERENCES runs(id) ON DELETE SET NULL,
    passed         INTEGER NOT NULL CHECK (passed IN (0, 1)),
    checker_output TEXT,
    git_sha        TEXT,
    created_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_spans_run     ON spans(run_id);
CREATE INDEX IF NOT EXISTS idx_spans_parent  ON spans(parent_id);
CREATE INDEX IF NOT EXISTS idx_runs_status   ON runs(status);
CREATE INDEX IF NOT EXISTS idx_results_suite ON test_results(suite, case_id);
"""


def connect(path: str = "agentlens.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str = "agentlens.db") -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
