"""
event_types.py — Eventos del pipeline event-driven v2.0.

Lectura del sistema: lead intelligence + rule-based triage system con auditoría completa.
No es agent system, no es event sourcing puro, no es CRM.

3 namespaces conceptuales separados (corrección C del spec de estabilización):

  ── Signal namespace ──
  Observaciones crudas del mundo exterior. No son decisiones del sistema.
    SignalCollected       : señal cruda detectada en una fuente pública

  ── Case namespace ──
  Estado agregado del sistema sobre una señal. No son decisiones.
    EntitiesExtracted     : caso parcial después de extracción LLM
    CaseScored            : caso con score calculado (estado agregado)
    CaseDeduplicated      : caso después de dedup (estado agregado)

  ── Decision namespace ──
  Intenciones políticas del sistema. Output de PolicyEngine.
    DecisionIssued        : PolicyDecision emitida por PolicyEngine (era PolicyEvaluated)
    CasePublished         : confirmación de ejecución de sinks (post-decision)

  ── Meta ──
    EventRejected         : evento inválido, no se procesa

Cada evento es inmutable (frozen dataclass) y cumple el data_contract del spec v2.0.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from models import Signal, Case, now_iso


# ===========================================================================
# Signal namespace — observaciones crudas del mundo exterior
# ===========================================================================
@dataclass(frozen=True)
class SignalCollected:
    """Señal cruda detectada en una fuente pública. Observación, no decisión."""
    event_id: str
    event_type: str = "signal_collected"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def signal(self) -> Signal:
        return Signal(**self.payload["signal"])


# ===========================================================================
# Case namespace — estado agregado del sistema sobre una señal
# ===========================================================================
@dataclass(frozen=True)
class EntitiesExtracted:
    """Caso parcial después de extracción LLM. Estado agregado."""
    event_id: str
    event_type: str = "entities_extracted"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_partial(self) -> Case:
        return Case(**self.payload["case_partial"])


@dataclass(frozen=True)
class CaseScored:
    """Caso con score calculado. Estado agregado, NO decisión."""
    event_id: str
    event_type: str = "case_scored"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case(self) -> Case:
        return Case(**self.payload["case"])


@dataclass(frozen=True)
class CaseDeduplicated:
    """Caso después de dedup. Estado agregado, NO decisión."""
    event_id: str
    event_type: str = "case_deduplicated"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case(self) -> Case:
        return Case(**self.payload["case"])

    @property
    def is_canonical(self) -> bool:
        return self.payload.get("is_canonical", True)


# ===========================================================================
# Decision namespace — intenciones políticas del sistema
# ===========================================================================
@dataclass(frozen=True)
class DecisionIssued:
    """
    Decisión emitida por PolicyEngine.

    Corrección C del spec de estabilización: renombrado desde PolicyEvaluated
    para que quede claro que esto es una DECISIÓN (intención política), no un
    evento de evaluación intermedia.

    Una DecisionIssued contiene:
      - case_id: caso sobre el que se decidió
      - decision: PolicyDecision serializada (actions, reasons, boost_delta,
                  decision_id, ruleset_version)
    """
    event_id: str
    event_type: str = "decision_issued"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.payload["case_id"]

    @property
    def decision(self) -> Dict[str, Any]:
        return self.payload.get("decision", {})

    @property
    def actions(self) -> List[str]:
        return self.decision.get("actions", [])

    @property
    def should_suppress(self) -> bool:
        return "suppress_output" in self.actions


@dataclass(frozen=True)
class CasePublished:
    """
    Confirmación de ejecución de sinks sobre un caso, post-decisión.

    Es un evento del namespace Decision porque registra la consecuencia de una
    DecisionIssued (los sinks ejecutaron lo que la policy mandó).
    """
    event_id: str
    event_type: str = "case_published"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.payload["case_id"]

    @property
    def sinks_result(self) -> Dict[str, Any]:
        return self.payload.get("sinks_result", {})


# ===========================================================================
# Meta — eventos de control
# ===========================================================================
@dataclass(frozen=True)
class EventRejected:
    """Evento inválido. No se dispatchea a handlers."""
    event_id: str
    event_type: str = "event_rejected"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        return self.payload.get("reason", "")

    @property
    def original_event_type(self) -> str:
        return self.payload.get("original_event_type", "")


# ===========================================================================
# Registro de tipos (para validación y dispatch)
# ===========================================================================
EVENT_TYPES = {
    # Signal namespace
    "signal_collected": SignalCollected,
    # Case namespace
    "entities_extracted": EntitiesExtracted,
    "case_scored": CaseScored,
    "case_deduplicated": CaseDeduplicated,
    # Decision namespace
    "decision_issued": DecisionIssued,
    "case_published": CasePublished,
    # Meta
    "event_rejected": EventRejected,
}

# Mapeo para backward-compat: PolicyEvaluated → DecisionIssued
DEPRECATED_EVENT_TYPES = {
    "policy_evaluated": "decision_issued",
}


# Namespace helper (para filtros y debugging)
SIGNAL_EVENTS = {"signal_collected"}
CASE_EVENTS = {"entities_extracted", "case_scored", "case_deduplicated"}
DECISION_EVENTS = {"decision_issued", "case_published"}
META_EVENTS = {"event_rejected"}


# ===========================================================================
# Helpers
# ===========================================================================
def make_event_id(prefix: str, seed: str) -> str:
    """Genera ID estable para un evento."""
    import hashlib
    h = hashlib.sha256(f"{seed}|{now_iso()}".encode("utf-8")).hexdigest()[:12]
    return f"evt-{prefix}-{h}"


def event_to_dict(event) -> Dict[str, Any]:
    """Serializa evento a dict (para audit log y event_log)."""
    return asdict(event)


__all__ = [
    # Signal namespace
    "SignalCollected",
    # Case namespace
    "EntitiesExtracted", "CaseScored", "CaseDeduplicated",
    # Decision namespace
    "DecisionIssued", "CasePublished",
    # Meta
    "EventRejected",
    # Registries
    "EVENT_TYPES", "DEPRECATED_EVENT_TYPES",
    "SIGNAL_EVENTS", "CASE_EVENTS", "DECISION_EVENTS", "META_EVENTS",
    # Helpers
    "make_event_id", "event_to_dict",
]
