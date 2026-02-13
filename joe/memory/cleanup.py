from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .store import MemoryStore


def cleanup_events(store: MemoryStore, *, ttl_days: int, max_events: int) -> dict[str, int]:
    """Delete old/overflow events to keep DB small."""
    removed_ttl = 0
    removed_overflow = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=int(ttl_days))
    cutoff_iso = cutoff.isoformat(timespec="seconds")

    con = store._connect()
    cur = con.execute("DELETE FROM events WHERE ts_utc < ?", (cutoff_iso,))
    removed_ttl = int(cur.rowcount)

    # enforce max rows: keep newest max_events
    row = con.execute("SELECT COUNT(*) AS c FROM events").fetchone()
    count = int(row["c"]) if row else 0
    if count > int(max_events):
        to_remove = count - int(max_events)
        cur2 = con.execute(
            "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id ASC LIMIT ?)",
            (to_remove,),
        )
        removed_overflow = int(cur2.rowcount)

    con.commit()
    return {"removed_ttl": removed_ttl, "removed_overflow": removed_overflow}
