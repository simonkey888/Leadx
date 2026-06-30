"""
event_pipeline.py — Pipeline event-driven v2.0.

Orquesta:
    1. collect_signals() → para cada signal: publica SignalCollected
    2. handler_on_signal_collected → LLM extract → publica EntitiesExtracted
    3. handler_on_entities_extracted → score → publica CaseScored
    4. handler_on_case_scored → dedup → publica CaseDeduplicated
    5. handler_on_case_deduplicated → si canonical → SinkFanOut → publica CasePublished

Reglas v2.0 cumplidas:
    - no_llm_side_effects: extractor es pure function
    - no_direct_external_writes: sólo los sinks escriben afuera
    - requires_event_validation: bus valida cada evento antes de dispatch

Si RADAR_LLM_API_KEY no está seteada, falla con error explícito al primer extract.
Si RADAR_WEBHOOK_URL no está seteada, el sink de Sheets falla al flush (no fatal).
"""
from __future__ import annotations

import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from models import Case, Signal, now_iso, AR_TZ
import config
from mock_sources import collect_signals
from event_types import (
    SignalCollected, EntitiesExtracted, CaseScored, CaseDeduplicated,
    CasePublished, EventRejected, make_event_id, event_to_dict,
)
from event_bus import EventBus
from event_validator import validate_event
from storage import AuditTrail, save_cases_jsonl, save_signals_jsonl
from scorer import update_case_score
from dedup import merge_duplicates
from llm_extractor import LLMExtractor, MissingLLMApiKeyError
from sinks import (
    Sink, WhatsAppLinkSink, GoogleSheetsWebhookSink, SinkFanOut,
)


@dataclass
class EventPipelineResult:
    signals_collected: int = 0
    events_published: int = 0
    events_rejected: int = 0
    cases_extracted: int = 0
    cases_canonical: int = 0
    duplicates_found: int = 0
    sinks_results: List[Dict[str, Any]] = field(default_factory=list)
    audit_entries: int = 0
    audit_chain_ok: bool = True
    duration_seconds: float = 0.0
    cases: List[Case] = field(default_factory=list)
    extractor_used: str = ""
    sinks_used: List[str] = field(default_factory=list)


class EventPipeline:
    """Pipeline event-driven v2.0."""

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        bus: Optional[EventBus] = None,
        extractor: Optional[LLMExtractor] = None,
        sinks: Optional[List[Sink]] = None,
        use_real_sources: bool = False,
    ):
        self.audit = audit or AuditTrail()
        self.bus = bus or EventBus(audit=self.audit)
        # LLM extractor: falla explícito si no hay API key
        self.extractor = extractor  # lazy: se inicializa en _ensure_extractor
        # Sinks: si no se pasan, default = WhatsAppLinkSink + GoogleSheetsWebhookSink
        if sinks is not None:
            self.sinks = sinks
        else:
            self.sinks = [
                WhatsAppLinkSink(audit=self.audit, score_threshold=80),
                GoogleSheetsWebhookSink(audit=self.audit, batch_size=50),
            ]
        self.fanout = SinkFanOut(self.sinks)
        self.use_real_sources = use_real_sources

        # Estado temporal: casos en proceso (para dedup batch al final)
        self._cases_buffer: List[Case] = []
        self._result = EventPipelineResult()

        # Suscribir handlers
        self._wire_handlers()

    def _ensure_extractor(self) -> LLMExtractor:
        if self.extractor is None:
            # Esto falla con MissingLLMApiKeyError si no hay env var
            self.extractor = LLMExtractor(audit=self.audit) if False else LLMExtractor()
        return self.extractor

    def _wire_handlers(self) -> None:
        """Suscribe los handlers del pipeline al bus."""
        self.bus.subscribe("signal_collected", self._on_signal_collected)
        self.bus.subscribe("entities_extracted", self._on_entities_extracted)
        self.bus.subscribe("case_scored", self._on_case_scored)
        # case_deduplicated se maneja al final (batch dedup), no por evento

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_signal_collected(self, event: SignalCollected) -> None:
        """Signal → LLM extract → EntitiesExtracted."""
        signal = event.signal

        # Aplicar privacy filter primero (igual que en v1)
        from extractor import privacy_filter
        pf = privacy_filter(signal)
        if not pf.passed:
            self.audit.append(
                actor="system:handler:signal_collected",
                action="reject_privacy",
                entity_type="signal",
                entity_id=signal.signal_id,
                details={"reason": pf.reason},
            )
            return

        try:
            extractor = self._ensure_extractor()
            case_partial = extractor.extract_to_case(signal)
        except MissingLLMApiKeyError as e:
            raise  # propaga el error explícito
        except Exception as e:
            self.audit.append(
                actor="system:handler:signal_collected",
                action="extract_error",
                entity_type="signal",
                entity_id=signal.signal_id,
                details={"error": str(e), "error_type": type(e).__name__},
            )
            return

        self._cases_buffer.append(case_partial)
        self._result.cases_extracted += 1

        # Publicar EntitiesExtracted
        evt = EntitiesExtracted(
            event_id=make_event_id("ent", case_partial.case_id),
            event_type="entities_extracted",
            timestamp=now_iso(),
            payload={"case_partial": case_partial.to_dict()},
        )
        self.bus.publish(evt)

    def _on_entities_extracted(self, event: EntitiesExtracted) -> None:
        """EntitiesExtracted → score → CaseScored."""
        case = event.case_partial
        update_case_score(case)
        self.audit.append(
            actor="system:handler:entities_extracted",
            action="score",
            entity_type="case",
            entity_id=case.case_id,
            details={"score": case.score, "band": case.score_band},
        )

        # Publicar CaseScored
        evt = CaseScored(
            event_id=make_event_id("score", case.case_id),
            event_type="case_scored",
            timestamp=now_iso(),
            payload={"case": case.to_dict()},
        )
        self.bus.publish(evt)

    def _on_case_scored(self, event: CaseScored) -> None:
        """CaseScored → buffer para dedup batch."""
        # El dedup se hace al final sobre todos los casos del buffer
        # (no podemos dedup evento-por-evento sin conocer el resto)
        pass

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> EventPipelineResult:
        """Ejecuta el pipeline event-driven end-to-end."""
        t0 = time.time()

        # Pre-flight: si el extractor es LLM y no hay API key, fallar acá
        # con error explícito ANTES de procesar cualquier señal
        if self.extractor is None:
            try:
                self._ensure_extractor()
            except MissingLLMApiKeyError as e:
                self.audit.append(
                    actor="system:event_pipeline",
                    action="pipeline_abort",
                    entity_type="batch",
                    entity_id="run",
                    details={"reason": "missing_llm_api_key", "error": str(e)},
                )
                raise

        self.audit.append(
            actor="system:event_pipeline",
            action="pipeline_start",
            entity_type="batch",
            entity_id="run",
            details={
                "version": "2.0",
                "mode": "event_driven",
                "use_real_sources": self.use_real_sources,
                "sinks": [s.sink_id for s in self.sinks],
            },
        )

        # 1. Collect signals
        signals = collect_signals(use_real=self.use_real_sources)
        self._result.signals_collected = len(signals)
        save_signals_jsonl(signals)

        self.audit.append(
            actor="system:event_pipeline",
            action="collect",
            entity_type="batch",
            entity_id="signals",
            details={"count": len(signals)},
        )

        # 2. Publicar SignalCollected por cada señal
        for sig in signals:
            evt = SignalCollected(
                event_id=make_event_id("sig", sig.signal_id),
                event_type="signal_collected",
                timestamp=now_iso(),
                payload={"signal": sig.to_dict()},
            )
            self.bus.publish(evt)

        # 3. Dedup batch sobre todos los casos extraídos
        if self._cases_buffer:
            self._cases_buffer, ndup = merge_duplicates(self._cases_buffer)
            self._result.duplicates_found = ndup
            self.audit.append(
                actor="system:event_pipeline",
                action="dedup_batch",
                entity_type="batch",
                entity_id="all",
                details={
                    "duplicates_found": ndup,
                    "canonical_count": sum(1 for c in self._cases_buffer if c.is_canonical),
                },
            )

            # 4. Para cada caso canónico: publicar CaseDeduplicated + ejecutar sinks
            for case in self._cases_buffer:
                if not case.is_canonical:
                    continue

                dedup_evt = CaseDeduplicated(
                    event_id=make_event_id("dedup", case.case_id),
                    event_type="case_deduplicated",
                    timestamp=now_iso(),
                    payload={
                        "case": case.to_dict(),
                        "is_canonical": True,
                    },
                )
                self.bus.publish(dedup_evt)

                # Ejecutar sinks (regla: no_direct_external_writes → sólo via sinks)
                sinks_result = self.fanout.write(case)
                self._result.sinks_results.append({
                    "case_id": case.case_id,
                    "sinks": sinks_result,
                })

                # Publicar CasePublished
                pub_evt = CasePublished(
                    event_id=make_event_id("pub", case.case_id),
                    event_type="case_published",
                    timestamp=now_iso(),
                    payload={
                        "case_id": case.case_id,
                        "sinks_result": sinks_result,
                    },
                )
                self.bus.publish(pub_evt)

        # 5. Flush sinks (enviar batch pendiente de Google Sheets)
        flush_results = self.fanout.flush_all()
        if flush_results:
            self.audit.append(
                actor="system:event_pipeline",
                action="sinks_flush",
                entity_type="batch",
                entity_id="all",
                details={"flush_results": flush_results},
            )

        # 6. Stats finales
        bus_stats = self.bus.stats()
        self._result.events_published = bus_stats["published"]
        self._result.events_rejected = bus_stats["rejected"]
        self._result.cases_canonical = sum(1 for c in self._cases_buffer if c.is_canonical)
        self._result.cases = list(self._cases_buffer)
        self._result.extractor_used = type(self._ensure_extractor()).__name__ if self._cases_buffer else "none"
        self._result.sinks_used = [s.sink_id for s in self.sinks]
        self._result.audit_entries = len(self.audit.read_all())
        self._result.audit_chain_ok = self.audit.verify_chain()
        self._result.duration_seconds = round(time.time() - t0, 2)

        # 7. Persistir casos
        save_cases_jsonl(self._cases_buffer)

        self.audit.append(
            actor="system:event_pipeline",
            action="pipeline_end",
            entity_type="batch",
            entity_id="run",
            details={
                "duration_seconds": self._result.duration_seconds,
                "signals_collected": self._result.signals_collected,
                "cases_extracted": self._result.cases_extracted,
                "duplicates_found": self._result.duplicates_found,
                "cases_canonical": self._result.cases_canonical,
                "events_published": self._result.events_published,
                "events_rejected": self._result.events_rejected,
                "audit_chain_ok": self._result.audit_chain_ok,
            },
        )

        return self._result

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    def print_summary(self, result: EventPipelineResult) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — Event Pipeline v2.0")
        print("=" * 70)
        print(f"  Modo:               event_driven_pipeline")
        print(f"  Extractor:          {result.extractor_used}")
        print(f"  Sinks:              {', '.join(result.sinks_used)}")
        print(f"  Duración:           {result.duration_seconds}s")
        print("-" * 70)
        print(f"  Señales recogidas:  {result.signals_collected}")
        print(f"  Casos extraídos:    {result.cases_extracted}")
        print(f"  Duplicados:         {result.duplicates_found}")
        print(f"  Casos canónicos:    {result.cases_canonical}")
        print("-" * 70)
        print(f"  Eventos publicados: {result.events_published}")
        print(f"  Eventos rechazados: {result.events_rejected}")
        print(f"  Audit trail:        {result.audit_entries} entradas")
        print(f"  Cadena íntegra:     {'✓' if result.audit_chain_ok else '✗ ROTA'}")
        print("-" * 70)
        print(f"  Sinks ejecutados:   {len(result.sinks_results)} casos")

        # Resumen sinks
        wa_links = 0
        wa_skipped = 0
        sheets_queued = 0
        for sr in result.sinks_results:
            wa = sr["sinks"].get("whatsapp", {})
            if wa.get("status") == "ok":
                wa_links += 1
            else:
                wa_skipped += 1
            gs = sr["sinks"].get("google_sheets", {})
            if gs.get("status") == "queued":
                sheets_queued += 1
        print(f"  WhatsApp links:     {wa_links} generados, {wa_skipped} skipped")
        print(f"  Sheets encolados:   {sheets_queued}")
        print("=" * 70)

        # Top 3 críticos
        crit = sorted(
            [c for c in result.cases if c.is_canonical and c.score >= 60],
            key=lambda c: c.score, reverse=True,
        )[:3]
        if crit:
            print("\n  TOP 3 CASOS PRIORITARIOS:")
            for c in crit:
                wa_link = " [+WA]" if c.whatsapp_link else ""
                print(f"    [{c.score_band:8s}] {c.score:3d} | {c.case_id} | "
                      f"{c.problem_type:15s} | {c.jurisdiction:12s}{wa_link}")
            print()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST event_pipeline.py")
    print("=" * 70)

    # Sin API key → falla al primer extract (pre-flight)
    os.environ.pop("RADAR_LLM_API_KEY", None)
    os.environ.pop("RADAR_WEBHOOK_URL", None)

    pipeline = EventPipeline(use_real_sources=False)
    try:
        result = pipeline.run()
        print(f"\n  ✗ FAIL: debería fallar sin API key")
        sys.exit(1)
    except MissingLLMApiKeyError as e:
        assert "Missing LLM API key" in str(e)
        print(f"  ✓ Sin API key → '{e}'")

    # Con API key dummy → el pipeline corre, los handlers fallan en HTTP
    # (esperado: no hay endpoint real)
    os.environ["RADAR_LLM_API_KEY"] = "dummy-key-for-wiring-test"
    try:
        pipeline2 = EventPipeline(use_real_sources=False)
        try:
            result = pipeline2.run()
            pipeline2.print_summary(result)
            # Verificaciones del wiring (no del éxito de extracción)
            assert result.signals_collected > 0, "Should have collected signals"
            assert result.events_published > 0, "Should have published events"
            assert "whatsapp" in result.sinks_used
            assert "google_sheets" in result.sinks_used
            assert result.audit_chain_ok, "Audit chain should be intact"
            print(f"\n  ✓ Wiring verificado:")
            print(f"    - Bus publicó {result.events_published} eventos")
            print(f"    - {result.events_rejected} rechazados por validación")
            print(f"    - Sinks registrados: {result.sinks_used}")
            print(f"    - Audit chain íntegra: {result.audit_chain_ok}")
            print(f"    - Casos extraídos: {result.cases_extracted} (0 esperado con API key dummy)")
        except Exception as e:
            # Si hay errores inesperados, mostrar
            print(f"  ⚠ Pipeline corrió con error inesperado: {e}")
            raise
    finally:
        os.environ.pop("RADAR_LLM_API_KEY", None)

    print(f"\n  Para correr el pipeline completo (máquina del operador):")
    print(f"    export RADAR_LLM_API_KEY=<tu-api-key>")
    print(f"    export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec")
    print(f"    python main.py --event-pipeline")
