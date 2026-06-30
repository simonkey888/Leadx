"""
event_bus.py — Bus de eventos in-process síncrono (v2.0).

Características:
- Síncrono: handlers se ejecutan en orden dentro del mismo thread
- Validación obligatoria: todo evento pasa por EventValidator antes del dispatch
- Si un evento es inválido → se emite EventRejected y el original NO se dispatcha
- Audit log: cada publish queda registrado en AuditTrail
- Suscripción por event_type: un handler se suscribe a uno o varios tipos

Uso:
    bus = EventBus(audit=audit_trail)
    bus.subscribe("case_scored", my_handler)
    bus.publish(event)  # valida → dispatch → log
"""
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict

from event_types import (
    SignalCollected, EntitiesExtracted, CaseScored,
    CaseDeduplicated, CasePublished, EventRejected, DecisionIssued,
    make_event_id, event_to_dict,
)
from event_validator import validate_event
from storage import AuditTrail
from models import now_iso


# Tipo handler: recibe un Event y no devuelve nada (o devuelve algo que se ignora)
Handler = Callable[[Any], None]


class EventBus:
    """Bus de eventos in-process síncrono con validación obligatoria."""

    def __init__(self, audit: Optional[AuditTrail] = None):
        self._handlers: Dict[str, List[Handler]] = defaultdict(list)
        self._audit = audit
        self._published_count = 0
        self._rejected_count = 0
        self._dispatched_count = 0

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------
    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Suscribe un handler a un tipo de evento."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Desuscribe un handler."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------
    def publish(self, event) -> bool:
        """
        Publica un evento en el bus.

        Pasos:
        1. Validar evento contra data_contract
        2. Si inválido → emitir EventRejected, NO dispatchear, retornar False
        3. Si válido → dispatchear a todos los handlers suscritos al tipo
        4. Loguear en audit trail

        Returns:
            True si el evento fue válido y dispatcheado, False si fue rechazado
        """
        self._published_count += 1

        # 1. Validar
        result = validate_event(event)
        if not result.valid:
            self._rejected_count += 1
            # Emitir EventRejected
            reject = EventRejected(
                event_id=make_event_id("rej", event.event_id),
                event_type="event_rejected",
                timestamp=now_iso(),
                payload={
                    "reason": "; ".join(result.errors),
                    "original_event_type": getattr(event, "event_type", "unknown"),
                    "original_event_id": getattr(event, "event_id", ""),
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
            )
            self._log_audit(reject, valid=False, errors=result.errors)
            # Los EventRejected NO se dispatchean a handlers (evitar loop infinito)
            # pero sí quedan en audit
            return False

        # 2. Dispatch
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
                self._dispatched_count += 1
            except Exception as e:
                # Un handler que falla no rompe el bus, pero se loguea
                self._log_audit_error(event, e)

        # 3. Log
        self._log_audit(event, valid=True, errors=[])

        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        return {
            "published": self._published_count,
            "dispatched": self._dispatched_count,
            "rejected": self._rejected_count,
            "handlers_total": sum(len(hs) for hs in self._handlers.values()),
        }

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------
    def _log_audit(self, event, valid: bool, errors: List[str]) -> None:
        if self._audit is None:
            return
        self._audit.append(
            actor="system:event_bus",
            action=f"publish:{event.event_type}",
            entity_type="event",
            entity_id=event.event_id,
            details={
                "valid": valid,
                "errors": errors if not valid else [],
                "event_type": event.event_type,
            },
        )

    def _log_audit_error(self, event, exc: Exception) -> None:
        if self._audit is None:
            return
        self._audit.append(
            actor="system:event_bus",
            action=f"handler_error:{event.event_type}",
            entity_type="event",
            entity_id=event.event_id,
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Smoke test event_bus ===\n")

    audit = AuditTrail()
    bus = EventBus(audit=audit)

    # Handler que acumula eventos recibidos
    received = []
    def handler_scored(event):
        received.append(event.case.case_id)

    bus.subscribe("case_scored", handler_scored)

    # 1. Publicar evento válido
    from models import Case, now_iso
    case = Case(
        case_id="case-bus-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test",
        evidence_text="Test evidence",
        score=75,
    )
    evt = CaseScored(
        event_id=make_event_id("case", case.case_id),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": case.to_dict()},
    )
    ok = bus.publish(evt)
    assert ok, "Should publish successfully"
    assert received == ["case-bus-test"]
    print(f"  ✓ Evento válido publicado y dispatcheado a 1 handler")

    # 2. Publicar evento inválido (score fuera de rango)
    bad_case = case.to_dict()
    bad_case["score"] = 250
    evt_bad = CaseScored(
        event_id=make_event_id("case-bad", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case},
    )
    ok2 = bus.publish(evt_bad)
    assert not ok2, "Should reject"
    assert received == ["case-bus-test"], "Handler should NOT have been called for rejected event"
    print(f"  ✓ Evento inválido rechazado, handler no ejecutado")

    # 3. Stats
    s = bus.stats()
    assert s["published"] == 2
    assert s["dispatched"] == 1
    assert s["rejected"] == 1
    print(f"  ✓ Stats: {s}")

    # 4. Audit trail tiene ambas entradas (publish + reject)
    audit_entries = audit.read_all()
    publish_entries = [e for e in audit_entries if e["action"].startswith("publish:")]
    assert len(publish_entries) >= 2
    print(f"  ✓ Audit trail: {len(publish_entries)} publish entries logged")

    print("\n=== Todos los smoke tests OK ===")
