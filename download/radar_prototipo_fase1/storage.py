"""
storage.py — Persistencia: evidence store, audit trail, review queue, sheet sync.

Cuatro componentes:

1. EvidenceStore
   - Guarda evidencia de cada caso en disco (texto + metadata + hash SHA-256)
   - Estructura: <EVIDENCE_DIR>/<case_id>.json  +  <case_id>.txt
   - El hash garantiza integridad (re-verificable)

2. AuditTrail
   - Log append-only con hash chaining (cada entrada tiene hash_prev + hash_self)
   - Archivo: <SAMPLE_DATA_DIR>/audit_trail.log (una línea JSON por entrada)
   - Cualquier intento de mutar una línea anterior rompe la cadena

3. ReviewQueue
   - Cola de revisión humana: CSV + JSONL con estado, acción, SLA
   - Estados: needs_review / approved / rejected / duplicate / needs_more_data
   - SLA: 24h desde created_at hasta reviewed_at

4. SheetSync
   - Sincroniza casos a Google Sheet del spec (1jLeM6k...)
   - Modo real: requiere GOOGLE_SERVICE_ACCOUNT_FILE en env (gspread)
   - Modo dry-run (default Fase 1): imprime filas que se subirían, no toca la sheet
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from models import Case, AuditEntry, ReviewAction, AR_TZ, now_iso
import config


# ---------------------------------------------------------------------------
# EvidenceStore
# ---------------------------------------------------------------------------
class EvidenceStore:
    """Almacena evidencia por caso en disco con hash de integridad."""

    def __init__(self, base_dir: Path = config.EVIDENCE_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, case: Case) -> tuple[str, str]:
        """
        Guarda evidencia del caso.

        Returns:
            (path_rel, sha256) — path relativo al base_dir y hash de integridad.
        """
        case_dir = self.base_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        # Texto original
        text_path = case_dir / "evidence.txt"
        text_path.write_text(case.evidence_text, encoding="utf-8")

        # Metadata
        meta = {
            "case_id": case.case_id,
            "signal_id": case.signal_id,
            "source_id": case.source_id,
            "source_url": case.source_url,
            "timestamp": case.timestamp,
            "captured_at": now_iso(),
            "evidence_text": case.evidence_text,
            "extracted_entities": {
                "name_or_alias": case.name_or_alias,
                "vehicle_type": case.vehicle_type,
                "patent": case.patent,
                "jurisdiction": case.jurisdiction,
                "locality": case.locality,
                "problem_type": case.problem_type,
                "year": case.year,
                "amount": case.amount,
            },
            "score": case.score,
            "score_band": case.score_band,
            "score_breakdown": case.score_breakdown,
        }
        meta_path = case_dir / "evidence.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Hash SHA-256 del texto + metadata serializada
        h = hashlib.sha256()
        h.update(case.evidence_text.encode("utf-8"))
        h.update(json.dumps(meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        sha = h.hexdigest()
        (case_dir / "evidence.sha256").write_text(sha, encoding="utf-8")

        return str(case_dir.relative_to(self.base_dir.parent)), sha

    def verify(self, case: Case) -> bool:
        """Verifica que la evidencia almacenada siga siendo íntegra."""
        case_dir = self.base_dir / case.case_id
        sha_path = case_dir / "evidence.sha256"
        if not sha_path.exists():
            return False
        expected = sha_path.read_text(encoding="utf-8").strip()
        meta = json.loads((case_dir / "evidence.json").read_text(encoding="utf-8"))
        h = hashlib.sha256()
        h.update(case.evidence_text.encode("utf-8"))
        h.update(json.dumps(meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return h.hexdigest() == expected


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------
class AuditTrail:
    """Log append-only con hash chaining para trazabilidad inmutable."""

    def __init__(self, path: Path = config.AUDIT_TRAIL_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Hash de la última entrada existente (para chaining)
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return ""
        last_hash = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    last_hash = entry.get("hash_self", "")
                except json.JSONDecodeError:
                    continue
        return last_hash

    def append(self, actor: str, action: str, entity_type: str,
               entity_id: str, details: Optional[Dict[str, Any]] = None) -> AuditEntry:
        """Agrega una entrada al audit trail."""
        entry = AuditEntry(
            timestamp=now_iso(),
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            hash_prev=self._last_hash,
        )
        line = entry.to_log_line()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._last_hash = entry.hash_self
        return entry

    def verify_chain(self) -> bool:
        """Verifica que la cadena de hashes esté íntegra."""
        if not self.path.exists():
            return True
        prev_hash = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False
                if entry.get("hash_prev", "") != prev_hash:
                    return False
                prev_hash = entry.get("hash_self", "")
        return True

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out


# ---------------------------------------------------------------------------
# ReviewQueue
# ---------------------------------------------------------------------------
class ReviewQueue:
    """Cola de revisión humana: CSV + JSONL."""

    def __init__(
        self,
        csv_path: Path = config.REVIEW_QUEUE_PATH,
        jsonl_path: Path = config.SAMPLE_DATA_DIR / "review_queue.jsonl",
    ):
        self.csv_path = csv_path
        self.jsonl_path = jsonl_path

    def _csv_fields(self) -> List[str]:
        return [
            "case_id", "score", "score_band", "jurisdiction", "problem_type",
            "source_id", "source_url", "vehicle_type", "patent", "amount",
            "timestamp", "created_at", "status", "review_action",
            "reviewed_by", "reviewed_at", "review_notes",
            "duplicate_of", "evidence_path", "sla_hours_remaining",
        ]

    def initialize(self, cases: List[Case]) -> None:
        """Crea/reescribe la cola con todos los casos canónicos pendientes."""
        rows = [self._case_to_row(c) for c in cases if c.is_canonical]
        # CSV
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writeheader()
            writer.writerows(rows)
        # JSONL
        with self.jsonl_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _case_to_row(self, case: Case) -> Dict[str, Any]:
        sla_remaining = self._sla_remaining(case)
        return {
            "case_id": case.case_id,
            "score": case.score,
            "score_band": case.score_band,
            "jurisdiction": case.jurisdiction,
            "problem_type": case.problem_type,
            "source_id": case.source_id,
            "source_url": case.source_url,
            "vehicle_type": case.vehicle_type,
            "patent": case.patent,
            "amount": case.amount or "",
            "timestamp": case.timestamp,
            "created_at": case.created_at,
            "status": case.status,
            "review_action": case.review_action or "",
            "reviewed_by": case.reviewed_by or "",
            "reviewed_at": case.reviewed_at or "",
            "review_notes": case.review_notes,
            "duplicate_of": case.duplicate_of or "",
            "evidence_path": case.evidence_path or "",
            "sla_hours_remaining": sla_remaining,
        }

    def _sla_remaining(self, case: Case) -> float:
        """Calcula horas restantes de SLA (puede ser negativo si venció)."""
        try:
            created = datetime.fromisoformat(case.created_at)
            now = datetime.now(AR_TZ)
            elapsed_h = (now - created).total_seconds() / 3600.0
            return round(config.REVIEW_SLA_HOURS - elapsed_h, 1)
        except Exception:
            return config.REVIEW_SLA_HOURS

    def apply_review(self, case: Case, action: ReviewAction, audit: AuditTrail) -> None:
        """Aplica una acción de revisión a un caso y actualiza la cola."""
        if action.action not in config.REVIEW_ACTIONS:
            raise ValueError(f"Acción inválida: {action.action}")

        case.review_action = action.action
        case.reviewed_by = action.reviewer
        case.reviewed_at = action.timestamp
        case.review_notes = action.notes
        case.updated_at = now_iso()

        # Mapear acción a status
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "duplicate": "duplicate",
            "needs_more_data": "needs_more_data",
        }
        case.status = status_map[action.action]

        # Re-escribir la cola completa
        # (en Fase 2 esto será un UPDATE puntual en DB)
        all_rows = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["case_id"] == case.case_id:
                    row = self._case_to_row(case)
                all_rows.append(row)
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writeheader()
            writer.writerows(all_rows)

        # Audit
        audit.append(
            actor=f"reviewer:{action.reviewer}",
            action="review",
            entity_type="case",
            entity_id=case.case_id,
            details={"action": action.action, "notes": action.notes},
        )

    def pending(self) -> List[Dict[str, Any]]:
        """Devuelve los casos pendientes de revisión (status=needs_review)."""
        if not self.csv_path.exists():
            return []
        out = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"] == "needs_review":
                    out.append(row)
        return out

    def stats(self) -> Dict[str, int]:
        if not self.csv_path.exists():
            return {}
        stats: Dict[str, int] = {}
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats[row["status"]] = stats.get(row["status"], 0) + 1
        return stats


# ---------------------------------------------------------------------------
# SheetSync
# ---------------------------------------------------------------------------
class SheetSync:
    """
    Sincroniza casos a la Google Sheet del spec.

    Modo real (Fase 2/3): requiere service account.
    Modo dry-run (Fase 1, default): imprime filas y no toca la sheet.
    """

    def __init__(self, sheet_id: str = config.GOOGLE_SHEET_ID, tab: str = config.GOOGLE_SHEET_TAB):
        self.sheet_id = sheet_id
        self.tab = tab
        self.service_account_file = config.GOOGLE_SERVICE_ACCOUNT_FILE
        self._client = None
        self._sheet = None

    def _connect(self):
        """Conecta a Google Sheets via gspread. Requiere service account."""
        if not self.service_account_file:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_FILE no configurado. "
                "Setear env var RADAR_GOOGLE_SERVICE_ACCOUNT_FILE o usar dry_run=True."
            )
        try:
            import gspread
        except ImportError:
            raise RuntimeError(
                "gspread no instalado. Instalar con: pip install gspread"
            )
        self._client = gspread.service_account(filename=self.service_account_file)
        self._sheet = self._client.open_by_key(self.sheet_id).worksheet(self.tab)

    def sync(self, cases: List[Case], dry_run: bool = True, audit: Optional[AuditTrail] = None) -> Dict[str, Any]:
        """
        Sincroniza casos a la sheet.

        Args:
            cases: lista de casos a subir (sólo canónicos, normalmente)
            dry_run: si True (default Fase 1), no toca la sheet real
            audit: audit trail para registrar la acción

        Returns:
            Dict con: mode, rows_queued, rows_synced, sheet_url, sample_rows
        """
        rows = [c.to_sheet_row() for c in cases if c.is_canonical]

        if dry_run or not self.service_account_file:
            sample = rows[:3]
            if audit:
                audit.append(
                    actor="system",
                    action="sheet_sync",
                    entity_type="batch",
                    entity_id="dry_run",
                    details={
                        "mode": "dry_run",
                        "rows_queued": len(rows),
                        "sheet_url": config.GOOGLE_SHEET_URL,
                    },
                )
            return {
                "mode": "dry_run",
                "rows_queued": len(rows),
                "rows_synced": 0,
                "sheet_url": config.GOOGLE_SHEET_URL,
                "sample_rows": sample,
            }

        # Modo real
        self._connect()
        # Limpiar tab y escribir encabezados + filas
        headers = list(rows[0].keys()) if rows else []
        values = [headers] + [[r.get(h, "") for h in headers] for r in rows]
        self._sheet.update(values)
        if audit:
            audit.append(
                actor="system",
                action="sheet_sync",
                entity_type="batch",
                entity_id=f"sheet:{self.sheet_id}",
                details={
                    "mode": "real",
                    "rows_synced": len(rows),
                    "sheet_url": config.GOOGLE_SHEET_URL,
                },
            )
        return {
            "mode": "real",
            "rows_queued": len(rows),
            "rows_synced": len(rows),
            "sheet_url": config.GOOGLE_SHEET_URL,
        }


# ---------------------------------------------------------------------------
# Casos JSONL
# ---------------------------------------------------------------------------
def save_cases_jsonl(cases: List[Case], path: Path = config.CASES_PATH) -> None:
    """Persiste todos los casos (canónicos + duplicados) en JSONL."""
    with path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")


def load_cases_jsonl(path: Path = config.CASES_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Signals JSONL
# ---------------------------------------------------------------------------
def save_signals_jsonl(signals, path: Path = config.SIGNALS_MOCK_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    from extractor import signal_to_case
    from scorer import update_case_score
    from dedup import merge_duplicates

    audit = AuditTrail()
    print(f"Audit trail: {audit.path}")
    print(f"Cadena íntegra: {audit.verify_chain()}\n")

    sigs = generate_mock_signals()
    audit.append(actor="system", action="collect", entity_type="signal",
                 entity_id="batch", details={"count": len(sigs), "mode": "mock"})

    cases = []
    for s in sigs:
        case, status = signal_to_case(s)
        if case:
            audit.append(actor="system", action="extract", entity_type="signal",
                         entity_id=s.signal_id, details={"status": status, "case_id": case.case_id})
            update_case_score(case)
            audit.append(actor="system", action="score", entity_type="case",
                         entity_id=case.case_id, details={"score": case.score, "band": case.score_band})
            cases.append(case)
        else:
            audit.append(actor="system", action="reject", entity_type="signal",
                         entity_id=s.signal_id, details={"reason": status})

    cases, ndup = merge_duplicates(cases)
    audit.append(actor="system", action="dedup", entity_type="batch",
                 entity_id="all", details={"duplicates_found": ndup})

    ev = EvidenceStore()
    for c in cases:
        if c.is_canonical:
            path, sha = ev.store(c)
            c.evidence_path = path
            c.evidence_sha256 = sha
            audit.append(actor="system", action="store_evidence", entity_type="case",
                         entity_id=c.case_id, details={"sha256": sha[:16] + "…"})

    rq = ReviewQueue()
    rq.initialize(cases)
    audit.append(actor="system", action="queue_init", entity_type="batch",
                 entity_id="all", details={"total_canonical": sum(1 for c in cases if c.is_canonical)})

    save_cases_jsonl(cases)
    save_signals_jsonl(sigs)

    sheet = SheetSync()
    sync_result = sheet.sync(cases, dry_run=True, audit=audit)
    print(f"Sheet sync: {sync_result['mode']} | {sync_result['rows_queued']} filas")
    print(f"Sheet URL: {sync_result['sheet_url']}")
    print(f"\nCola de revisión: {rq.csv_path}")
    print(f"  Stats: {rq.stats()}")
    print(f"\nAudit trail: {len(audit.read_all())} entradas")
    print(f"Cadena íntegra: {audit.verify_chain()}")
