"""SQLite access layer. Every other module talks to the database only through TraceStore."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Optional

from .schema import init_db


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def dumps(obj: Any) -> Optional[str]:
    """Serialize anything to JSON text; unknown types fall back to str()."""
    if obj is None:
        return None
    return json.dumps(obj, default=str, ensure_ascii=False)


class TraceStore:
    def __init__(self, path: str = "agentlens.db"):
        self.path = path
        self.conn = init_db(path)

    def close(self) -> None:
        self.conn.close()

    # ---- runs -----------------------------------------------------------
    def start_run(self, name: str, model: Optional[str] = None) -> str:
        run_id = new_id()
        self.conn.execute(
            "INSERT INTO runs(id, name, started_at, model) VALUES (?, ?, ?, ?)",
            (run_id, name, time.time(), model))
        self.conn.commit()
        return run_id

    def end_run(self, run_id: str, status: str, total_latency_ms: float,
                error: Optional[str] = None) -> None:
        tokens = self.conn.execute(
            "SELECT COALESCE(SUM(COALESCE(tokens_in,0) + COALESCE(tokens_out,0)), 0) "
            "FROM spans WHERE run_id = ? AND kind = 'llm'", (run_id,)).fetchone()[0]
        self.conn.execute(
            "UPDATE runs SET ended_at=?, status=?, total_tokens=?, total_latency_ms=?, error=? "
            "WHERE id=?", (time.time(), status, tokens, total_latency_ms, error, run_id))
        self.conn.commit()

    def set_failure_label(self, run_id: str, label: Optional[str]) -> None:
        self.conn.execute("UPDATE runs SET failure_label=? WHERE id=?", (label, run_id))
        self.conn.commit()

    def get_run(self, run_id: str) -> Optional[sqlite3.Row]:
        """Accepts a full id or a unique prefix (like git short hashes)."""
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE id LIKE ? || '%'", (run_id,)).fetchall()
        if len(rows) > 1:
            raise ValueError(f"Ambiguous run id prefix '{run_id}' ({len(rows)} matches)")
        return rows[0] if rows else None

    def list_runs(self, limit: int = 20, status: Optional[str] = None) -> list[sqlite3.Row]:
        sql, params = "SELECT * FROM runs", []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY started_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    # ---- spans ----------------------------------------------------------
    def start_span(self, run_id: str, parent_id: Optional[str], kind: str,
                   name: str, input_obj: Any = None) -> str:
        span_id = new_id()
        self.conn.execute(
            "INSERT INTO spans(id, run_id, parent_id, kind, name, input_json, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (span_id, run_id, parent_id, kind, name, dumps(input_obj), time.time()))
        self.conn.commit()
        return span_id

    def finish_span(self, span_id: str, output_obj: Any, latency_ms: float,
                    tokens_in: Optional[int], tokens_out: Optional[int],
                    error: Optional[str]) -> None:
        self.conn.execute(
            "UPDATE spans SET output_json=?, latency_ms=?, tokens_in=?, tokens_out=?, error=? "
            "WHERE id=?", (dumps(output_obj), latency_ms, tokens_in, tokens_out, error, span_id))
        self.conn.commit()

    def get_spans(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM spans WHERE run_id=? ORDER BY started_at, rowid", (run_id,)).fetchall()

    # ---- response cache (powers replay) ---------------------------------
    def cache_get(self, request_hash: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT response_json FROM cache_entries WHERE request_hash=?",
            (request_hash,)).fetchone()
        return row[0] if row else None

    def cache_put(self, request_hash: str, model: str, response_json: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cache_entries(request_hash, model, response_json, created_at) "
            "VALUES (?, ?, ?, ?)", (request_hash, model, response_json, time.time()))
        self.conn.commit()

    # ---- test results ---------------------------------------------------
    def add_test_result(self, suite: str, case_id: str, run_id: Optional[str],
                        passed: bool, checker_output: str, version: str) -> None:
        self.conn.execute(
            "INSERT INTO test_results(suite, case_id, run_id, passed, checker_output, git_sha, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (suite, case_id, run_id, int(passed), checker_output, version, time.time()))
        self.conn.commit()

    def results_for(self, suite: str, version: str) -> dict[str, sqlite3.Row]:
        """Latest result per case for one version label."""
        rows = self.conn.execute(
            "SELECT * FROM test_results WHERE suite=? AND git_sha=? ORDER BY id",
            (suite, version)).fetchall()
        return {r["case_id"]: r for r in rows}
