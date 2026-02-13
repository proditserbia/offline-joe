SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  source TEXT NOT NULL,          -- voice|cli|api
  text TEXT NOT NULL,
  intent TEXT,
  success INTEGER NOT NULL DEFAULT 1,
  meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  subject TEXT NOT NULL,         -- e.g. user
  predicate TEXT NOT NULL,       -- e.g. name
  object TEXT NOT NULL,          -- e.g. Ben
  confidence REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL,          -- voice|cli|api
  UNIQUE(subject, predicate)
);

CREATE INDEX IF NOT EXISTS idx_facts_sp ON facts(subject, predicate);
"""
