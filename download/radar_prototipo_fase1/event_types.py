"""
event_types.py — Eventos del pipeline event-driven (v2.0).

Cada evento es inmutable (frozen dataclass) y cumple el data_contract del spec v2.0:
    case_id: string
    patent: string
    jurisdiction: string
    score: number
    source: string
    evidence: string
    timestamp: iso8601

Flujo de eventos:
    SignalCollected → EntitiesExtracted → CaseScored → CaseDeduplicated → CasePublished

Reglas (v2.0):
    - no_llm_side_effects: el extractor sólo produce datos, no escribe afuera
    - no_direct_external_writes: el pipeline sólo escribe via sinks
    - requires_event_validation: todo evento pasa por EventValidator antes del dispatch
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from models import Signal, Case, now_iso


# ---------------------------------------------------------------------------
# Base común (no dataclass — sólo type hint)
# ---------------------------------------------------------------------------
class Event:
    """Marker base class. Cada evento es su propio frozen dataclass."""
    event_id: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any]


# ---------------------------------------------------------------------------
# Eventos concretos (frozen, sin herencia para evitar issues con defaults)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SignalCollected:
    event_id: str
    event_type: str = "signal_collected"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def signal(self) -> Signal:
        return Signal(**self.payload["signal"])


@dataclass(frozen=True)
class EntitiesExtracted:
    event_id: str
    event_type: str = "entities_extracted"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_partial(self) -> Case:
        return Case(**self.payload["case_partial"])


@dataclass(frozen=True)
class CaseScored:
    event_id: str
    event_type: str = "case_scored"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case(self) -> Case:
        return Case(**self.payload["case"])


@dataclass(frozen=True)
class CaseDeduplicated:
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


@dataclass(frozen=True)
class CasePublished:
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


@dataclass(frozen=True)
class EventRejected:
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


@dataclass(frozen=True)
class PolicyEvaluated:
    """Resultado de PolicyEngine.evaluate(case). Corrección C+D del spec."""
    event_id: str
    event_type: str = "policy_evaluated"
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


# Tipos válidos
EVENT_TYPES = {
    "signal_collected": SignalCollected,
    "entities_extracted": EntitiesExtracted,
    "case_scored": CaseScored,
    "case_deduplicated": CaseDeduplicated,
    "case_published": CasePublished,
    "event_rejected": EventRejected,
    "policy_evaluated": PolicyEvaluated,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_event_id(prefix: str, seed: str) -> str:
    """Genera ID estable para un evento."""
    import hashlib
    h = hashlib.sha256(f"{seed}|{now_iso()}".encode("utf-8")).hexdigest()[:12]
    return f"evt-{prefix}-{h}"


def event_to_dict(event) -> Dict[str, Any]:
    """Serializa evento a dict (para audit log)."""
    return asdict(event)


__all__ = [
    "Event", "SignalCollected", "EntitiesExtracted", "CaseScored",
    "CaseDeduplicated", "CasePublished", "EventRejected", "PolicyEvaluated",
    "EVENT_TYPES", "make_event_id", "event_to_dict",
]
