"""
pipeline.py — Orquestador end-to-end del Radar de Oportunidades (Fase 1).

Flujo:
  collect → privacy_filter → extract → normalize → score → dedup
          → store_evidence → queue → sheet_sync → audit_trail (en cada paso)

Cada paso escribe en el audit trail. El pipeline es idempotente: si se ejecuta
de nuevo sobre las mismas señales, produce los mismos casos (excepto timestamps).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from models import Case, Signal, AuditEntry, now_iso
import config
from mock_sources import collect_signals
from extractor import signal_to_case, privacy_filter
from scorer import update_case_score
from dedup import merge_duplicates
from storage import (
    AuditTrail, EvidenceStore, ReviewQueue, SheetSync,
    save_cases_jsonl, save_signals_jsonl,
)


@dataclass
class PipelineResult:
    signals_collected: int = 0
    signals_rejected_privacy: int = 0
    signals_no_entity: int = 0
    cases_extracted: int = 0
    cases_canonical: int = 0
    duplicates_found: int = 0
    critical_cases: int = 0
    high_cases: int = 0
    medium_cases: int = 0
    low_cases: int = 0
    sheet_mode: str = ""
    sheet_rows: int = 0
    audit_entries: int = 0
    audit_chain_ok: bool = True
    duration_seconds: float = 0.0
    cases: List[Case] = field(default_factory=list)


class RadarPipeline:
    """Pipeline completo del Radar de Oportunidades."""

    def __init__(
        self,
        use_real_sources: bool = False,
        sheet_dry_run: bool = True,
        audit: Optional[AuditTrail] = None,
        evidence: Optional[EvidenceStore] = None,
        queue: Optional[ReviewQueue] = None,
        sheet: Optional[SheetSync] = None,
    ):
        self.use_real_sources = use_real_sources
        self.sheet_dry_run = sheet_dry_run
        self.audit = audit or AuditTrail()
        self.evidence = evidence or EvidenceStore()
        self.queue = queue or ReviewQueue()
        self.sheet = sheet or SheetSync()

    def run(self) -> PipelineResult:
        import time
        t0 = time.time()
        result = PipelineResult()

        # 1. Collect
        self.audit.append(
            actor="system", action="pipeline_start",
            entity_type="batch", entity_id="run",
            details={"use_real_sources": self.use_real_sources, "sheet_dry_run": self.sheet_dry_run},
        )
        signals = collect_signals(use_real=self.use_real_sources)
        result.signals_collected = len(signals)
        self.audit.append(
            actor="system", action="collect",
            entity_type="batch", entity_id="signals",
            details={"count": len(signals)},
        )
        save_signals_jsonl(signals)

        # 2-3. Extract + Privacy filter
        cases: List[Case] = []
        for sig in signals:
            case, status = signal_to_case(sig)
            if case is None:
                if status.startswith("rejected_privacy"):
                    result.signals_rejected_privacy += 1
                else:
                    result.signals_no_entity += 1
                self.audit.append(
                    actor="system", action="reject",
                    entity_type="signal", entity_id=sig.signal_id,
                    details={"reason": status, "source_id": sig.source_id},
                )
                continue
            # Log extract
            self.audit.append(
                actor="system", action="extract",
                entity_type="signal", entity_id=sig.signal_id,
                details={"case_id": case.case_id, "problem_type": case.problem_type,
                         "jurisdiction": case.jurisdiction, "patent": case.patent},
            )
            cases.append(case)

        result.cases_extracted = len(cases)

        # 4. Score
        for case in cases:
            update_case_score(case)
            self.audit.append(
                actor="system", action="score",
                entity_type="case", entity_id=case.case_id,
                details={"score": case.score, "band": case.score_band,
                         "breakdown": case.score_breakdown},
            )

        # 5. Dedup
        cases, ndup = merge_duplicates(cases)
        result.duplicates_found = ndup
        self.audit.append(
            actor="system", action="dedup",
            entity_type="batch", entity_id="all",
            details={"duplicates_found": ndup,
                     "canonical_count": sum(1 for c in cases if c.is_canonical)},
        )

        # 6. Store evidence (sólo canónicos)
        for case in cases:
            if case.is_canonical:
                path, sha = self.evidence.store(case)
                case.evidence_path = path
                case.evidence_sha256 = sha
                self.audit.append(
                    actor="system", action="store_evidence",
                    entity_type="case", entity_id=case.case_id,
                    details={"sha256": sha, "path": path},
                )

        # 7. Review queue
        canonical = [c for c in cases if c.is_canonical]
        self.queue.initialize(canonical)
        self.audit.append(
            actor="system", action="queue_init",
            entity_type="batch", entity_id="all",
            details={"total_canonical": len(canonical)},
        )

        # 8. Sheet sync
        sync_result = self.sheet.sync(canonical, dry_run=self.sheet_dry_run, audit=self.audit)
        result.sheet_mode = sync_result["mode"]
        result.sheet_rows = sync_result["rows_queued"]

        # 9. Stats por banda
        for c in canonical:
            if c.score_band == "critical":
                result.critical_cases += 1
            elif c.score_band == "high":
                result.high_cases += 1
            elif c.score_band == "medium":
                result.medium_cases += 1
            else:
                result.low_cases += 1

        result.cases_canonical = len(canonical)
        result.cases = cases
        result.audit_entries = len(self.audit.read_all())
        result.audit_chain_ok = self.audit.verify_chain()
        result.duration_seconds = round(time.time() - t0, 2)

        # Persistir casos
        save_cases_jsonl(cases)

        self.audit.append(
            actor="system", action="pipeline_end",
            entity_type="batch", entity_id="run",
            details={
                "duration_seconds": result.duration_seconds,
                "signals_collected": result.signals_collected,
                "cases_canonical": result.cases_canonical,
                "duplicates_found": result.duplicates_found,
                "critical": result.critical_cases,
                "high": result.high_cases,
                "medium": result.medium_cases,
                "low": result.low_cases,
            },
        )

        return result

    def print_summary(self, result: PipelineResult) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — Pipeline Fase 1")
        print("=" * 70)
        print(f"  Duración:          {result.duration_seconds}s")
        print(f"  Señales recogidas: {result.signals_collected}")
        print(f"  Rechazadas (PII):  {result.signals_rejected_privacy}")
        print(f"  Sin entidad:       {result.signals_no_entity}")
        print(f"  Casos extraídos:   {result.cases_extracted}")
        print(f"  Duplicados:        {result.duplicates_found}")
        print(f"  Casos canónicos:   {result.cases_canonical}")
        print("-" * 70)
        print(f"  CRÍTICOS (>=80):   {result.critical_cases}")
        print(f"  ALTOS     (>=60):  {result.high_cases}")
        print(f"  MEDIOS    (>=40):  {result.medium_cases}")
        print(f"  BAJOS     (<40):   {result.low_cases}")
        print("-" * 70)
        print(f"  Audit trail:       {result.audit_entries} entradas")
        print(f"  Cadena íntegra:    {'✓' if result.audit_chain_ok else '✗ ROTA'}")
        print(f"  Sheet sync:        {result.sheet_mode} | {result.sheet_rows} filas")
        print(f"  Sheet URL:         {config.GOOGLE_SHEET_URL}")
        print("=" * 70)

        # Top 5 críticos
        crit = sorted(
            [c for c in result.cases if c.is_canonical and c.score >= 60],
            key=lambda c: c.score, reverse=True,
        )[:5]
        if crit:
            print("\n  TOP 5 CASOS PRIORITARIOS:")
            for c in crit:
                print(f"    [{c.score_band:8s}] {c.score:3d} | {c.case_id} | "
                      f"{c.problem_type:15s} | {c.jurisdiction:12s} | "
                      f"{c.patent or '—':8s} | {c.source_id}")
            print()


if __name__ == "__main__":
    p = RadarPipeline(use_real_sources=False, sheet_dry_run=True)
    result = p.run()
    p.print_summary(result)
