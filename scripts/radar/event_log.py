"""
event_log.py — Append-only event log con persistencia (corrección A).

Storage options (en orden de preferencia):
    1. SQLite (default, recomendado) — atomic, queryable, zero-deps
    2. JSONL (fallback) — simple, human-readable, para Drive o FS simple

Schema (corrección A del spec):
    event_id:    string PK
    event_type:  string
    payload:     JSON string
    timestamp:   iso8601
    version:     string (default "1.0")

El event_log es la fuente de verdad para:
- replay (re-procesar eventos con nuevo código)
- debugging histórico
- auditoría externa (lectura read-only para auditor)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict

from models import now_iso
import config


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "1.0"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    version     TEXT NOT NULL DEFAULT '1.0'
);
CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_ts   ON event_log(timestamp);
"""


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------
class EventLogBackend:
    """Interface común para backends de event_log."""

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        raise NotImplementedError

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SQLite backend (default)
# ---------------------------------------------------------------------------
class SQLiteEventLog(EventLogBackend):
    """Backend SQLite. Recomendado: atomic, queryable, zero-deps."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_CREATE_TABLE_SQL)
        self._conn.commit()

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            "INSERT OR REPLACE INTO event_log (event_id, event_type, payload, timestamp, version) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_id, event_type, payload_str, timestamp, version),
        )
        self._conn.commit()

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT event_id, event_type, payload, timestamp, version FROM event_log"
        clauses = []
        params: List[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "payload": json.loads(r[2]),
                "timestamp": r[3],
                "version": r[4],
            }
            for r in rows
        ]

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM event_log")
        return cur.fetchone()[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# JSONL backend (fallback)
# ---------------------------------------------------------------------------
class JSONLEventLog(EventLogBackend):
    """Backend JSONL. Simple, human-readable. Para Drive o FS simple."""

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Crear archivo si no existe
        if not self.file_path.exists():
            self.file_path.touch()

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        entry = {
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "timestamp": timestamp,
            "version": version,
        }
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        out = []
        with self.file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and entry.get("event_type") != event_type:
                    continue
                if since and entry.get("timestamp", "") < since:
                    continue
                out.append(entry)
                if limit and len(out) >= limit:
                    break
        return out

    def count(self) -> int:
        if not self.file_path.exists():
            return 0
        n = 0
        with self.file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def create_event_log(
    backend: str = "sqlite",
    path: Optional[Union[str, Path]] = None,
) -> EventLogBackend:
    """
    Factory para crear backend de event_log.

    Args:
        backend: "sqlite" (default) | "jsonl"
        path: path al archivo. Si None, usa default en SAMPLE_DATA_DIR.
    """
    if path is None:
        if backend == "sqlite":
            path = config.SAMPLE_DATA_DIR / "event_log.db"
        elif backend == "jsonl":
            path = config.SAMPLE_DATA_DIR / "event_log.jsonl"
        else:
            raise ValueError(f"Unknown backend: {backend}")

    if backend == "sqlite":
        return SQLiteEventLog(path)
    elif backend == "jsonl":
        return JSONLEventLog(path)
    else:
        raise ValueError(f"Unknown backend: {backend}")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile
    import os

    print("=" * 70)
    print("  SMOKE TEST event_log.py")
    print("=" * 70)

    # Test SQLite
    tmpdir = tempfile.mkdtemp()
    sqlite_path = os.path.join(tmpdir, "test_event_log.db")
    jsonl_path = os.path.join(tmpdir, "test_event_log.jsonl")

    print("\n  [SQLite backend]")
    log = SQLiteEventLog(sqlite_path)
    log.append("evt-1", "signal_collected", {"signal_id": "sig-1"}, "2026-06-30T10:00:00-03:00")
    log.append("evt-2", "case_scored", {"case_id": "case-1", "score": 82}, "2026-06-30T10:01:00-03:00")
    log.append("evt-3", "case_scored", {"case_id": "case-2", "score": 45}, "2026-06-30T10:02:00-03:00")
    assert log.count() == 3
    print(f"    ✓ Append 3 eventos, count={log.count()}")

    all_events = log.query()
    assert len(all_events) == 3
    assert all_events[0]["event_id"] == "evt-1"
    print(f"    ✓ Query all: {len(all_events)} eventos en orden temporal")

    scored = log.query(event_type="case_scored")
    assert len(scored) == 2
    assert scored[0]["payload"]["case_id"] == "case-1"
    print(f"    ✓ Query case_scored: {len(scored)} eventos")

    recent = log.query(since="2026-06-30T10:01:30-03:00")
    assert len(recent) == 1
    assert recent[0]["event_id"] == "evt-3"
    print(f"    ✓ Query since: {len(recent)} eventos (after filter)")

    limited = log.query(limit=2)
    assert len(limited) == 2
    print(f"    ✓ Query limit=2: {len(limited)} eventos")

    log.close()

    # Idempotencia: re-abrir el mismo DB mantiene datos
    log2 = SQLiteEventLog(sqlite_path)
    assert log2.count() == 3
    print(f"    ✓ Re-abrir DB mantiene datos: count={log2.count()}")
    log2.close()

    # Test JSONL
    print("\n  [JSONL backend]")
    jlog = JSONLEventLog(jsonl_path)
    jlog.append("evt-1", "signal_collected", {"signal_id": "sig-1"}, "2026-06-30T10:00:00-03:00")
    jlog.append("evt-2", "case_scored", {"case_id": "case-1", "score": 82}, "2026-06-30T10:01:00-03:00")
    assert jlog.count() == 2
    print(f"    ✓ Append 2 eventos, count={jlog.count()}")

    jall = jlog.query()
    assert len(jall) == 2
    assert jall[1]["payload"]["case_id"] == "case-1"
    print(f"    ✓ Query all: {len(jall)} eventos")

    jscored = jlog.query(event_type="case_scored")
    assert len(jscored) == 1
    print(f"    ✓ Query case_scored: {len(jscored)} eventos")

    # Factory
    print("\n  [Factory]")
    f_log = create_event_log("sqlite", sqlite_path)
    assert f_log.count() == 3
    print(f"    ✓ create_event_log('sqlite', ...) → count={f_log.count()}")
    f_log.close()

    # Limpieza
    import shutil
    shutil.rmtree(tmpdir)

    print("\n" + "=" * 70)
    print("  ✓ Todos los smoke tests OK")
    print("=" * 70)
    print("""
  Schema persistido:
    event_id (PK) | event_type | payload (JSON) | timestamp | version

  Backends disponibles:
    - sqlite (default, recomendado) — atomic, queryable
    - jsonl (fallback) — simple, para Drive

  Uso típico:
    from event_log import create_event_log
    log = create_event_log("sqlite")
    log.append(event_id, event_type, payload, timestamp, version="1.0")
""")
