"""
pending_queries_kv.py — Cola persistente de queries que fallaron con 429.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional, List, Dict, Any, Tuple

log = logging.getLogger(__name__)

KV_KEY_PENDING = "pending_queries"
MAX_PENDING_STORED = 12
MAX_RETRIES_PER_Q = 3
MIN_RETRY_HOURS = 3.0
MAX_PENDING_PER_RUN = 2
SLEEP_BETWEEN_RSS = 12

WORKER_URL = "https://leadx.simondalmasso44.workers.dev"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_from_now(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class KVClient:
    """Wrapper mínimo para /api/kv del Worker (auth con INGEST_SECRET)."""

    def __init__(self, worker_url: str, secret: str):
        self.worker_url = worker_url.rstrip("/")
        self.secret = secret

    def _headers(self) -> dict:
        return {
            "X-Webhook-Secret": self.secret,
            "Content-Type": "application/json",
            "User-Agent": "LeadX-Pipeline/2.0",
        }

    def get(self, key: str) -> Optional[dict]:
        url = f"{self.worker_url}/api/kv?key={key}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return data.get("value")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log.warning(f"KV GET {key}: HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            log.warning(f"KV GET {key}: {e}", file=sys.stderr)
            return None

    def put(self, key: str, value: dict, ttl_seconds: int = 0) -> bool:
        url = f"{self.worker_url}/api/kv"
        body = json.dumps({"key": key, "value": value, "ttl": ttl_seconds}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            log.error(f"KV PUT {key}: {e}", file=sys.stderr)
            return False


class PendingQuery:
    def __init__(self, url: str, query_text: str, group_idx: int,
                 retry_count: int = 0, failed_at: Optional[str] = None,
                 next_retry_after: Optional[str] = None):
        self.url = url
        self.query_text = query_text
        self.group_idx = group_idx
        self.retry_count = retry_count
        self.failed_at = failed_at or _now_iso()
        self.next_retry_after = next_retry_after or _hours_from_now(MIN_RETRY_HOURS)

    def is_ready(self) -> bool:
        try:
            next_dt = datetime.fromisoformat(self.next_retry_after)
            if next_dt.tzinfo is None:
                next_dt = next_dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= next_dt
        except Exception:
            return True

    def is_exhausted(self) -> bool:
        return self.retry_count >= MAX_RETRIES_PER_Q

    def to_dict(self) -> dict:
        return {
            "url": self.url, "query_text": self.query_text,
            "group_idx": self.group_idx, "retry_count": self.retry_count,
            "failed_at": self.failed_at, "next_retry_after": self.next_retry_after,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingQuery":
        return cls(
            url=d["url"], query_text=d["query_text"],
            group_idx=d.get("group_idx", -1),
            retry_count=d.get("retry_count", 0),
            failed_at=d.get("failed_at"),
            next_retry_after=d.get("next_retry_after"),
        )


class PendingQueryManager:
    def __init__(self, worker_url: str, secret: str):
        self.kv = KVClient(worker_url, secret)
        self.pending: List[PendingQuery] = []
        self._loaded = False

    def load(self):
        raw = self.kv.get(KV_KEY_PENDING)
        if not raw or "queries" not in raw:
            print(f"[PQM] No hay queries pendientes en KV", file=sys.stderr)
            self.pending = []
        else:
            self.pending = [PendingQuery.from_dict(q) for q in raw["queries"]]
            ready = sum(1 for q in self.pending if q.is_ready() and not q.is_exhausted())
            print(f"[PQM] Cargadas {len(self.pending)} queries pendientes ({ready} listas)",
                  file=sys.stderr)
        self._loaded = True

    def add(self, url: str, query_text: str, group_idx: int):
        for pq in self.pending:
            if pq.url == url:
                pq.retry_count += 1
                pq.next_retry_after = _hours_from_now(MIN_RETRY_HOURS * pq.retry_count)
                print(f"[PQM] Retry #{pq.retry_count} para '{query_text[:40]}'",
                      file=sys.stderr)
                return
        pq = PendingQuery(url=url, query_text=query_text, group_idx=group_idx)
        self.pending.append(pq)
        print(f"[PQM] Nueva query pendiente: '{query_text[:40]}'", file=sys.stderr)
        if len(self.pending) > MAX_PENDING_STORED:
            self.pending.sort(key=lambda q: (not q.is_exhausted(), -q.retry_count))
            self.pending = self.pending[:MAX_PENDING_STORED]

    def retry_pending(self, search_fn: Callable[[str], Tuple[List[Dict], bool]]) -> List[Dict]:
        """search_fn(query) → (leads, got_429). Reintenta máx 2 ready queries."""
        if not self._loaded:
            self.load()

        ready = [q for q in self.pending if q.is_ready() and not q.is_exhausted()]
        expired = [q for q in self.pending if q.is_exhausted()]

        if expired:
            print(f"[PQM] Descartando {len(expired)} queries agotadas (max retries)",
                  file=sys.stderr)
            self.pending = [q for q in self.pending if not q.is_exhausted()]

        if not ready:
            print(f"[PQM] No hay queries listas para retry en este run", file=sys.stderr)
            return []

        to_retry = ready[:MAX_PENDING_PER_RUN]
        recovered = []

        for i, pq in enumerate(to_retry):
            print(f"[PQM] Reintentando ({i+1}/{len(to_retry)}): '{pq.query_text[:40]}' "
                  f"[retry #{pq.retry_count + 1}]", file=sys.stderr)
            leads, got_429 = search_fn(pq.query_text)
            if got_429:
                pq.retry_count += 1
                pq.next_retry_after = _hours_from_now(MIN_RETRY_HOURS * pq.retry_count)
                print(f"[PQM] Retry falló (429). Próximo: {pq.next_retry_after[:19]}",
                      file=sys.stderr)
            else:
                print(f"[PQM] OK recuperada '{pq.query_text[:40]}' → {len(leads)} leads",
                      file=sys.stderr)
                recovered.extend(leads)
                self.pending = [q for q in self.pending if q.url != pq.url]
            if i < len(to_retry) - 1:
                time.sleep(SLEEP_BETWEEN_RSS)
        return recovered

    def save(self):
        payload = {
            "queries": [q.to_dict() for q in self.pending],
            "updated_at": _now_iso(),
            "count": len(self.pending),
        }
        ok = self.kv.put(KV_KEY_PENDING, payload, ttl_seconds=7 * 24 * 3600)
        if ok:
            print(f"[PQM] Guardadas {len(self.pending)} queries pendientes en KV",
                  file=sys.stderr)
        else:
            print(f"[PQM] ERROR al guardar pending_queries en KV", file=sys.stderr)

    def status(self) -> dict:
        return {
            "total_pending": len(self.pending),
            "ready_for_retry": sum(1 for q in self.pending if q.is_ready()),
            "exhausted": sum(1 for q in self.pending if q.is_exhausted()),
        }
