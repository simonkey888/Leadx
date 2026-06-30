"""
policy_engine.py — Motor de políticas (corrección C+D del spec).

Corrección C: mover "trigger logic" fuera de sinks
    Antes: WhatsAppLinkSink(trigger=score_threshold) → sink decide
    Ahora: PolicyEngine → emite PolicyDecision → sink ejecuta

Corrección D: componente mínimo faltante
    {
      "policy_engine": {
        "rules": [
          "if score >= 80 → generate_whatsapp_intent",
          "if jurisdiction == target → boost_priority",
          "if duplicate → suppress_output"
        ]
      }
    }

PolicyEngine es pure function: input = case + context, output = PolicyDecision
No escribe externamente, no muta el case (sólo lee).

PolicyDecision.actions es una lista de acciones que los sinks deben ejecutar:
    - "generate_whatsapp_intent"
    - "boost_priority"
    - "suppress_output"
    - "publish_to_sheets"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from models import Case, now_iso
import config


# ---------------------------------------------------------------------------
# PolicyDecision (output del PolicyEngine)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PolicyDecision:
    """Decisión emitida por PolicyEngine para un case."""
    case_id: str
    actions: List[str] = field(default_factory=list)  # generate_whatsapp_intent, boost_priority, suppress_output, publish_to_sheets
    reasons: List[str] = field(default_factory=list)  # una razón por cada action
    boost_delta: int = 0  # boost de score a aplicar (ej: +5 por jurisdiction target)
    metadata: Dict[str, Any] = field(default_factory=dict)
    decision_id: str = ""
    timestamp: str = ""

    def has_action(self, action: str) -> bool:
        return action in self.actions

    def should_suppress(self) -> bool:
        return "suppress_output" in self.actions

    def should_publish_to_sheets(self) -> bool:
        return "publish_to_sheets" in self.actions and not self.should_suppress()

    def should_generate_whatsapp(self) -> bool:
        return "generate_whatsapp_intent" in self.actions and not self.should_suppress()


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------
class PolicyEngine:
    """
    Motor de políticas que evalúa un case y emite PolicyDecision.

    Pure function: no muta el case, no escribe externamente.
    Reglas (configurables, default = spec v2.0):
        1. if score >= 80 → generate_whatsapp_intent
        2. if jurisdiction in TARGET_JURISDICTIONS → boost_priority (+5)
        3. if duplicate → suppress_output
        4. if canonical → publish_to_sheets
    """

    def __init__(
        self,
        whatsapp_score_threshold: int = 80,
        jurisdiction_boost_delta: int = 5,
        target_jurisdictions: Optional[Set[str]] = None,
    ):
        self.whatsapp_score_threshold = whatsapp_score_threshold
        self.jurisdiction_boost_delta = jurisdiction_boost_delta
        self.target_jurisdictions = target_jurisdictions or config.TARGET_JURISDICTIONS

    def evaluate(self, case: Case) -> PolicyDecision:
        """
        Evalúa un case contra todas las reglas y devuelve PolicyDecision.

        Pure function: NO muta el case.
        El boost_delta se devuelve en la decisión; el caller decide si aplicarlo.
        """
        actions: List[str] = []
        reasons: List[str] = []
        boost_delta = 0
        metadata: Dict[str, Any] = {}

        # Regla 3 (evaluar primero): duplicate → suppress_output
        if not case.is_canonical:
            actions.append("suppress_output")
            reasons.append(f"duplicate of {case.duplicate_of}")
            metadata["duplicate_of"] = case.duplicate_of
            # Si es duplicate, no se evalúan más reglas (supresión total)
            return PolicyDecision(
                case_id=case.case_id,
                actions=actions,
                reasons=reasons,
                boost_delta=0,
                metadata=metadata,
                decision_id=_decision_id(case.case_id, "dup"),
                timestamp=now_iso(),
            )

        # Regla 1: score >= 80 → generate_whatsapp_intent
        if case.score >= self.whatsapp_score_threshold:
            actions.append("generate_whatsapp_intent")
            reasons.append(
                f"score {case.score} >= {self.whatsapp_score_threshold}"
            )
            metadata["whatsapp_score_threshold"] = self.whatsapp_score_threshold

        # Regla 2: jurisdiction in target → boost_priority
        if case.jurisdiction in self.target_jurisdictions:
            actions.append("boost_priority")
            reasons.append(
                f"jurisdiction {case.jurisdiction} in target {sorted(self.target_jurisdictions)}"
            )
            boost_delta = self.jurisdiction_boost_delta
            metadata["boost_delta"] = boost_delta
            metadata["target_jurisdiction"] = case.jurisdiction

        # Regla 4: canonical → publish_to_sheets
        if case.is_canonical:
            actions.append("publish_to_sheets")
            reasons.append("case is canonical (not duplicate)")

        # Trigger manual: si el case ya tiene whatsapp_number seteado
        # (override desde CLI de revisión humana), generar whatsapp intent
        if case.whatsapp_number and "generate_whatsapp_intent" not in actions:
            actions.append("generate_whatsapp_intent")
            reasons.append("manual whatsapp_number present (review override)")
            metadata["manual_override"] = True

        # Trigger manual: si el case está approved
        if (case.status == "approved" or case.review_state == "approved") and \
           "generate_whatsapp_intent" not in actions:
            actions.append("generate_whatsapp_intent")
            reasons.append("case approved by human review")
            metadata["approved_review"] = True

        return PolicyDecision(
            case_id=case.case_id,
            actions=actions,
            reasons=reasons,
            boost_delta=boost_delta,
            metadata=metadata,
            decision_id=_decision_id(case.case_id, "pol"),
            timestamp=now_iso(),
        )


def _decision_id(case_id: str, prefix: str) -> str:
    import hashlib
    h = hashlib.sha256(f"{case_id}|{prefix}|{now_iso()}".encode("utf-8")).hexdigest()[:10]
    return f"dec-{prefix}-{h}"


# ---------------------------------------------------------------------------
# Nuevos tipos de eventos para integración con bus
# ---------------------------------------------------------------------------
# PolicyDecision se emite como evento PolicyEvaluated
# (definido en event_types.py para mantener consistencia)

# ---------------------------------------------------------------------------
# Helper: aplicar boost_delta a un case (muta el case)
# ---------------------------------------------------------------------------
def apply_boost(case: Case, decision: PolicyDecision) -> Case:
    """
    Aplica el boost_delta de la decisión al score del case.
    Mutates case in-place. Clampea a [0, 100].

    Esto se hace EXPLÍCITAMENTE (no dentro del PolicyEngine) porque el engine
    es pure function y no debe mutar inputs.
    """
    if decision.boost_delta == 0:
        return case
    new_score = max(0, min(100, case.score + decision.boost_delta))
    case.score = new_score
    # Recalcular band
    if new_score >= config.SCORING_THRESHOLDS["critical"]:
        case.score_band = "critical"
    elif new_score >= config.SCORING_THRESHOLDS["high"]:
        case.score_band = "high"
    elif new_score >= config.SCORING_THRESHOLDS["medium"]:
        case.score_band = "medium"
    else:
        case.score_band = "low"
    case.updated_at = now_iso()
    return case


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("  SMOKE TEST policy_engine.py")
    print("=" * 70)

    from models import Case, now_iso

    engine = PolicyEngine()

    # Caso 1: score 85, CABA (target), canonical → whatsapp + boost + sheets
    case1 = Case(
        case_id="case-1", signal_id="sig-1",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1", profile_url="",
        timestamp=now_iso(), name_or_alias="Test", evidence_text="Test",
        score=85, jurisdiction="CABA", is_canonical=True,
        whatsapp_number="541155551234",
    )
    d1 = engine.evaluate(case1)
    assert d1.has_action("generate_whatsapp_intent")
    assert d1.has_action("boost_priority")
    assert d1.has_action("publish_to_sheets")
    assert d1.boost_delta == 5
    assert not d1.should_suppress()
    print(f"  ✓ Caso crítico CABA: actions={d1.actions}, boost={d1.boost_delta}")

    # Caso 2: score 50, MENDOZA (no target), canonical → sólo sheets
    case2 = Case(
        case_id="case-2", signal_id="sig-2",
        source_id="x_search",
        source_url="https://example.com/p/2", profile_url="",
        timestamp=now_iso(), name_or_alias="Test2", evidence_text="Test2",
        score=50, jurisdiction="MENDOZA", is_canonical=True,
    )
    d2 = engine.evaluate(case2)
    assert not d2.has_action("generate_whatsapp_intent")
    assert not d2.has_action("boost_priority")
    assert d2.has_action("publish_to_sheets")
    assert d2.boost_delta == 0
    print(f"  ✓ Caso medio no-target: actions={d2.actions}, boost=0")

    # Caso 3: duplicate → suppress_output (no se evalúan más reglas)
    case3 = Case(
        case_id="case-3", signal_id="sig-3",
        source_id="x_search",
        source_url="https://example.com/p/3", profile_url="",
        timestamp=now_iso(), name_or_alias="Test3", evidence_text="Test3",
        score=85, jurisdiction="CABA", is_canonical=False,
        duplicate_of="case-1",
    )
    d3 = engine.evaluate(case3)
    assert d3.should_suppress()
    assert d3.actions == ["suppress_output"]
    assert not d3.should_publish_to_sheets()
    assert not d3.should_generate_whatsapp()
    print(f"  ✓ Duplicate: actions={d3.actions}, suppress=True")

    # Caso 4: score 50 pero con whatsapp_number manual → whatsapp intent
    case4 = Case(
        case_id="case-4", signal_id="sig-4",
        source_id="x_search",
        source_url="https://example.com/p/4", profile_url="",
        timestamp=now_iso(), name_or_alias="Test4", evidence_text="Test4",
        score=50, jurisdiction="PBA", is_canonical=True,
        whatsapp_number="541100000000",
    )
    d4 = engine.evaluate(case4)
    assert d4.has_action("generate_whatsapp_intent")
    assert d4.has_action("boost_priority")  # PBA es target
    assert "manual whatsapp_number present" in d4.reasons[-1]
    print(f"  ✓ Caso con número manual: actions={d4.actions}")

    # Caso 5: approved por revisión → whatsapp intent sin score >= 80
    case5 = Case(
        case_id="case-5", signal_id="sig-5",
        source_id="x_search",
        source_url="https://example.com/p/5", profile_url="",
        timestamp=now_iso(), name_or_alias="Test5", evidence_text="Test5",
        score=55, jurisdiction="CORDOBA", is_canonical=True,
        whatsapp_number="", status="approved",
    )
    d5 = engine.evaluate(case5)
    assert d5.has_action("generate_whatsapp_intent")
    assert "approved by human review" in d5.reasons[-1]
    print(f"  ✓ Caso approved: actions={d5.actions}")

    # Test apply_boost
    case6 = Case(
        case_id="case-6", signal_id="sig-6",
        source_id="x_search",
        source_url="https://example.com/p/6", profile_url="",
        timestamp=now_iso(), name_or_alias="Test6", evidence_text="Test6",
        score=78, jurisdiction="CABA", is_canonical=True,
    )
    d6 = engine.evaluate(case6)
    assert d6.boost_delta == 5
    case6_boosted = apply_boost(case6, d6)
    assert case6_boosted.score == 83
    assert case6_boosted.score_band == "critical"  # 78+5=83 >= 80
    print(f"  ✓ apply_boost: 78 + 5 = 83, band=critical")

    # Pure function: el case original NO se muta en evaluate()
    case7 = Case(
        case_id="case-7", signal_id="sig-7",
        source_id="x_search",
        source_url="https://example.com/p/7", profile_url="",
        timestamp=now_iso(), name_or_alias="Test7", evidence_text="Test7",
        score=50, jurisdiction="CABA", is_canonical=True,
    )
    original_score = case7.score
    _ = engine.evaluate(case7)
    assert case7.score == original_score  # no mutado
    print(f"  ✓ evaluate() es pure function: no muta el case")

    print("\n" + "=" * 70)
    print("  ✓ Todos los smoke tests OK")
    print("=" * 70)
    print("""
  Reglas implementadas (corrección D del spec):
    1. if score >= 80 → generate_whatsapp_intent
    2. if jurisdiction in TARGET_JURISDICTIONS → boost_priority (+5)
    3. if duplicate → suppress_output (no se evalúan más reglas)
    4. if canonical → publish_to_sheets

  Triggers manuales adicionales:
    - whatsapp_number presente → generate_whatsapp_intent (override)
    - status == 'approved' → generate_whatsapp_intent (review humana)

  Arquitectura (corrección C):
    PolicyEngine (pure) → PolicyDecision → Sinks ejecutan
    Los sinks ya NO consultan triggers, sólo ejecutan actions
""")
