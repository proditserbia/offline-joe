from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable
from datetime import datetime, timezone
import json

from .schema import SCHEMA_SQL

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@dataclass
class MemoryStore:
    db_path: str

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def init(self) -> None:
        with self._connect() as con:
            con.executescript(SCHEMA_SQL)

    # --- EVENTS ---
    def add_event(self, source: str, text: str, intent: str | None, success: bool = True, meta: dict[str, Any] | None = None) -> int:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO events(ts_utc, source, text, intent, success, meta_json) VALUES(?,?,?,?,?,?)",
                (utc_now_iso(), source, text, intent, 1 if success else 0, meta_json),
            )
            return int(cur.lastrowid)

    def list_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, ts_utc, source, text, intent, success, meta_json FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            out.append({**dict(r), "meta": json.loads(r["meta_json"] or "{}")})
        return out

    def clear_events(self) -> int:
        with self._connect() as con:
            cur = con.execute("DELETE FROM events")
            return cur.rowcount

    # --- FACTS ---
    def set_fact(self, subject: str, predicate: str, obj: str, source: str = "voice", confidence: float = 1.0) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO facts(ts_utc, subject, predicate, object, confidence, source)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(subject, predicate) DO UPDATE SET
                  ts_utc=excluded.ts_utc,
                  object=excluded.object,
                  confidence=excluded.confidence,
                  source=excluded.source
                """,
                (utc_now_iso(), subject, predicate, obj, confidence, source),
            )

    def get_fact(self, subject: str, predicate: str) -> str | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT object FROM facts WHERE subject=? AND predicate=?",
                (subject, predicate),
            ).fetchone()
        return None if row is None else str(row["object"])

    def list_facts(self, subject: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = "SELECT ts_utc, subject, predicate, object, confidence, source FROM facts"
        params: list[Any] = []
        if subject:
            q += " WHERE subject=?"
            params.append(subject)
        q += " ORDER BY ts_utc DESC LIMIT ?"
        params.append(limit)
        with self._connect() as con:
            rows = con.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def clear_facts(self) -> int:
        with self._connect() as con:
            cur = con.execute("DELETE FROM facts")
            return cur.rowcount

    def vacuum(self) -> None:
        with self._connect() as con:
            con.execute("VACUUM")
