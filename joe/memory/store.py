from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading

from .schema import SCHEMA_SQL


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _apply_pragmas(con: sqlite3.Connection) -> None:
    # Good defaults for a small embedded DB on Pi:
    # - WAL for concurrency (readers don't block writers)
    # - NORMAL synchronous to reduce wear but still safe enough for events/facts
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA foreign_keys=ON;")


@dataclass
class MemoryStore:
    """Small SQLite-backed store for events + facts.

    Notes:
    - Uses per-thread connections (sqlite3 connections are not threadsafe).
    - WAL mode improves concurrent reads from API + voice loop.
    """

    db_path: str

    def __post_init__(self) -> None:
        self._local = threading.local()

    def _connect(self) -> sqlite3.Connection:
        con: sqlite3.Connection | None = getattr(self._local, "con", None)
        if con is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            con.row_factory = sqlite3.Row
            _apply_pragmas(con)
            self._local.con = con
        return con

    def close(self) -> None:
        con: sqlite3.Connection | None = getattr(self._local, "con", None)
        if con is not None:
            con.close()
            self._local.con = None

    def init(self) -> None:
        con = self._connect()
        con.executescript(SCHEMA_SQL)
        con.commit()

    # --- EVENTS ---
    def add_event(
        self,
        source: str,
        text: str,
        intent: str | None,
        *,
        success: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> int:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        con = self._connect()
        cur = con.execute(
            "INSERT INTO events(ts_utc, source, text, intent, success, meta_json) VALUES(?,?,?,?,?,?)",
            (utc_now_iso(), source, text, intent, 1 if success else 0, meta_json),
        )
        con.commit()
        return int(cur.lastrowid)

    def list_events(self, *, limit: int = 20) -> list[dict[str, Any]]:
        con = self._connect()
        rows = con.execute(
            "SELECT id, ts_utc, source, text, intent, success, meta_json "
            "FROM events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({**dict(r), "meta": json.loads(r["meta_json"] or "{}")})
        return out

    def clear_events(self) -> int:
        con = self._connect()
        cur = con.execute("DELETE FROM events")
        con.commit()
        return int(cur.rowcount)

    # --- FACTS ---
    def set_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        source: str = "voice",
        confidence: float = 1.0,
    ) -> None:
        con = self._connect()
        con.execute(
            '''
            INSERT INTO facts(ts_utc, subject, predicate, object, confidence, source)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(subject, predicate) DO UPDATE SET
              ts_utc=excluded.ts_utc,
              object=excluded.object,
              confidence=excluded.confidence,
              source=excluded.source
            ''',
            (utc_now_iso(), subject, predicate, obj, float(confidence), source),
        )
        con.commit()

    def get_fact(self, subject: str, predicate: str) -> str | None:
        con = self._connect()
        row = con.execute(
            "SELECT object FROM facts WHERE subject=? AND predicate=?",
            (subject, predicate),
        ).fetchone()
        return None if row is None else str(row["object"])

    def list_facts(self, *, subject: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = "SELECT ts_utc, subject, predicate, object, confidence, source FROM facts"
        params: list[Any] = []
        if subject:
            q += " WHERE subject=?"
            params.append(subject)
        q += " ORDER BY ts_utc DESC LIMIT ?"
        params.append(int(limit))
        con = self._connect()
        rows = con.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def clear_facts(self) -> int:
        con = self._connect()
        cur = con.execute("DELETE FROM facts")
        con.commit()
        return int(cur.rowcount)

    def vacuum(self) -> None:
        con = self._connect()
        con.execute("VACUUM")
        con.commit()
