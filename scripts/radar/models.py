"""
models.py — Dataclasses del Radar de Oportunidades.

Signal: señal cruda detectada en una fuente pública.
Case: caso normalizado, extraído, puntúa do y deduplicado.
AuditEntry: entrada append-only del audit trail.
ReviewAction: acción de revisión humana sobre un caso.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any


AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def now_iso() -> str:
    return datetime.now(AR_TZ).isoformat()


def short_id(prefix: str, seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{h}"


@dataclass
class Signal:
    """Señal cruda detectada en una fuente pública."""
    source_id: str             # ej: facebook_public_groups
    source_url: str            # URL pública del post/comentario
    raw_text: str              # texto original tal cual apareció
    author_alias: str          # alias/name público (no se recolecta si es privado)
    profile_url: str           # URL pública del perfil (vacío si no aplica)
    detected_at: str           # ISO timestamp de detección
    signal_keywords: List[str] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def signal_id(self) -> str:
        seed = f"{self.source_id}|{self.source_url}|{self.raw_text[:120]}"
        return short_id("sig", seed)


@dataclass
class Case:
    """Caso normalizado, extraído, puntúa do y deduplicado."""
    # Identidad
    case_id: str
    signal_id: str
    source_id: str
    source_url: str
    profile_url: str
    timestamp: str                  # ISO timestamp de la señal original

    # Entidades extraídas
    name_or_alias: str = ""
    vehicle_type: str = ""
    patent: str = ""
    jurisdiction: str = ""
    locality: str = ""
    problem_type: str = ""
    year: Optional[int] = None
    amount: Optional[float] = None
    evidence_text: str = ""

    # Scoring
    score: int = 0
    score_band: str = "low"          # critical/high/medium/low
    score_breakdown: Dict[str, int] = field(default_factory=dict)

    # Dedup
    normalized_text_hash: str = ""
    duplicate_of: Optional[str] = None   # case_id del caso padre si es dup
    duplicates: List[str] = field(default_factory=list)
    is_canonical: bool = True

    # Review queue
    status: str = "needs_review"      # needs_review/approved/rejected/duplicate/needs_more_data
    review_action: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: str = ""

    # Evidence
    evidence_path: Optional[str] = None
    evidence_sha256: Optional[str] = None

    # Uploader v1.0 — WhatsApp + sheet schema
    whatsapp_number: str = ""           # vacío si no se puede inferir
    whatsapp_link: str = ""             # https://wa.me/<num>?text=...
    priority_level: str = ""            # = score_band (critical/high/medium/low)
    review_state: str = "needs_review"  # espejo de status para la sheet

    # Audit
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_sheet_row(self) -> Dict[str, Any]:
        """Fila lista para Google Sheet (columnas planas)."""
        return {
            "case_id": self.case_id,
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "profile_url": self.profile_url,
            "name_or_alias": self.name_or_alias,
            "vehicle_type": self.vehicle_type,
            "patent": self.patent,
            "jurisdiction": self.jurisdiction,
            "locality": self.locality,
            "problem_type": self.problem_type,
            "year": self.year if self.year is not None else "",
            "amount": self.amount if self.amount is not None else "",
            "score": self.score,
            "score_band": self.score_band,
            "status": self.status,
            "review_action": self.review_action or "",
            "reviewed_by": self.reviewed_by or "",
            "reviewed_at": self.reviewed_at or "",
            "evidence_path": self.evidence_path or "",
            "evidence_sha256": self.evidence_sha256 or "",
            "evidence_text": (self.evidence_text[:500] + "…") if len(self.evidence_text) > 500 else self.evidence_text,
            "duplicate_of": self.duplicate_of or "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AuditEntry:
    """Entrada append-only del audit trail."""
    timestamp: str
    actor: str               # system / reviewer:<nombre>
    action: str              # collect / extract / normalize / score / dedup / store_evidence / review / export / alert
    entity_type: str         # signal / case / review / alert
    entity_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    hash_prev: str = ""      # hash de la entrada anterior (cadena inmutable)
    hash_self: str = ""      # hash de esta entrada

    def to_log_line(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "hash_prev": self.hash_prev,
        }
        # hash_self = sha256 del payload serializado
        self.hash_self = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        payload["hash_self"] = self.hash_self
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass
class ReviewAction:
    """Acción de revisión humana sobre un caso."""
    case_id: str
    action: str              # approve / reject / duplicate / needs_more_data
    reviewer: str
    notes: str = ""
    timestamp: str = field(default_factory=now_iso)
