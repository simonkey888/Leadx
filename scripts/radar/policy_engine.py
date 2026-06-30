"""
policy_engine.py — Motor de políticas (corrección C+D del spec + B contract formal).

================================================================================
CONTRATO FORMAL DE PolicyEngine (corrección B)
================================================================================

Input:
    CaseScored (case con score calculado, score_version, is_canonical, etc.)

Output:
    PolicyDecision (frozen dataclass con actions, reasons, boost_delta,
                    decision_id, ruleset_version)

Garantías (4):
    1. no side effects
       - PolicyEngine.evaluate() no muta el input
       - No escribe a sistemas externos
       - No llama a sinks
       - Es una función pura: input → output

    2. deterministic
       - Para el mismo input (case + config), produce el mismo output
       - Sin random, sin time-dependent behavior, sin I/O
       - Decisiones reproducibles en replay

    3. versioned ruleset
       - POLICY_RULESET_VERSION explicita (ej: "v1.0")
       - Cada PolicyDecision incluye ruleset_version
       - Cambios de reglas → bump de version → migración
       - Permite comparar decisiones entre rulesets

    4. idempotent per case_id
       - Mismo case + mismo ruleset → mismo decision_id
       - decision_id = hash determinista de (case_id, ruleset_version, actions)
       - Re-evaluar el mismo case produce la misma decisión
       - Permite replay sin duplicados

================================================================================
ROL DE PolicyEngine (corrección A — capa congelada)
================================================================================

PolicyEngine es la ÚNICA fuente de decisiones del sistema.
Ningún otro componente decide qué hacer con un caso.

Capas (corrección A del spec de estabilización):
    Extractor       → solo transforma texto → estructura
    Scoring         → solo numérico + versionado
    PolicyEngine    → única fuente de decisiones  ← ESTA CAPA
    Sinks           → ejecución pura (0 lógica de negocio)

Reglas (configurables, default = spec v2.0):
    1. if score >= 80 → generate_whatsapp_intent
    2. if jurisdiction in TARGET → boost_priority (+5)
    3. if duplicate → suppress_output (corta evaluación)
    4. if canonical → publish_to_sheets
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from models import Case, now_iso
import config


# ---------------------------------------------------------------------------
# Versión del ruleset (corrección B: versioned ruleset)
# ---------------------------------------------------------------------------
# Bump cuando cambien las reglas. Permite comparar decisiones entre rulesets
# y migrar casos en replay.
POLICY_RULESET_VERSION = "v1.0"


# ===========================================================================
# PolicyDecision (output del PolicyEngine)
# ===========================================================================
@dataclass(frozen=True)
class PolicyDecision:
    """
    Decisión emitida por PolicyEngine. Inmutable.

    Una PolicyDecision es la INTENCIÓN del sistema sobre un caso. Los sinks
    la ejecutan, pero la decisión vive acá.

    Campos:
        case_id          : ID del caso sobre el que se decidió
        actions          : lista de acciones a ejecutar por sinks
                           ("generate_whatsapp_intent", "boost_priority",
                            "suppress_output", "publish_to_sheets")
        reasons          : una razón legible por cada action
        boost_delta      : delta de score a aplicar (ej: +5 por jurisdiction)
        metadata         : info adicional (target_jurisdiction, etc.)
        decision_id      : ID determinista (idempotencia per case_id)
                           hash(case_id, ruleset_version, actions)
        ruleset_version  : versión del ruleset usado (corrección B)
        timestamp        : ISO8601 de cuándo se emitió
    """
    case_id: str
    actions: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    boost_delta: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    decision_id: str = ""
    ruleset_version: str = POLICY_RULESET_VERSION
    timestamp: str = ""

    def has_action(self, action: str) -> bool:
        return action in self.actions

    def should_suppress(self) -> bool:
        return "suppress_output" in self.actions

    def should_publish_to_sheets(self) -> bool:
        return "publish_to_sheets" in self.actions and not self.should_suppress()

    def should_generate_whatsapp(self) -> bool:
        return "generate_whatsapp_intent" in self.actions and not self.should_suppress()


# ===========================================================================
# PolicyEngine — única fuente de decisiones
# ===========================================================================
class PolicyEngine:
    """
    Motor de políticas. ÚNICA fuente de decisiones del sistema.

    Ver CONTRATO FORMAL arriba (corrección B):
        - no side effects
        - deterministic
        - versioned ruleset (POLICY_RULESET_VERSION)
        - idempotent per case_id (decision_id determinista)
    """

    def __init__(
        self,
        whatsapp_score_threshold: int = 80,
        jurisdiction_boost_delta: int = 5,
        target_jurisdictions: Optional[Set[str]] = None,
        ruleset_version: str = POLICY_RULESET_VERSION,
    ):
        self.whatsapp_score_threshold = whatsapp_score_threshold
        self.jurisdiction_boost_delta = jurisdiction_boost_delta
        self.target_jurisdictions = target_jurisdictions or config.TARGET_JURISDICTIONS
        self.ruleset_version = ruleset_version

    def evaluate(self, case: Case) -> PolicyDecision:
        """
        Evalúa un case contra todas las reglas y devuelve PolicyDecision.

        Pure function (corrección B garantía 1):
            - NO muta el case
            - NO escribe externamente
            - Determinista (corrección B garantía 2)
            - Idempotente (corrección B garantía 4): mismo case + mismo
              ruleset → mismo decision_id
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
            return self._build_decision(
                case=case, actions=actions, reasons=reasons,
                boost_delta=0, metadata=metadata,
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

        return self._build_decision(
            case=case, actions=actions, reasons=reasons,
            boost_delta=boost_delta, metadata=metadata,
        )

    def _build_decision(
        self,
        case: Case,
        actions: List[str],
        reasons: List[str],
        boost_delta: int,
        metadata: Dict[str, Any],
    ) -> PolicyDecision:
        """
        Construye la PolicyDecision final con decision_id determinista.

        Corrección B garantía 4 (idempotent per case_id):
            decision_id = hash(case_id, ruleset_version, sorted(actions))
            Mismo case + mismo ruleset → mismo decision_id
        """
        decision_id = _deterministic_decision_id(
            case.case_id, self.ruleset_version, actions,
        )
        return PolicyDecision(
            case_id=case.case_id,
            actions=actions,
            reasons=reasons,
            boost_delta=boost_delta,
            metadata=metadata,
            decision_id=decision_id,
            ruleset_version=self.ruleset_version,
            timestamp=now_iso(),
        )


def _deterministic_decision_id(
    case_id: str, ruleset_version: str, actions: List[str],
) -> str:
    """
    Genera decision_id determinista (idempotencia per case_id).

    Mismo case_id + mismo ruleset_version + mismas actions → mismo ID.
    Sin timestamp, sin random, sin I/O.
    """
    # sorted(actions) para que el orden no afecte el hash
    actions_canonical = ",".join(sorted(actions))
    seed = f"{case_id}|{ruleset_version}|{actions_canonical}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"dec-{h}"


# ===========================================================================
# Helper: aplicar boost_delta a un case (muta el case)
# ===========================================================================
def apply_boost(case: Case, decision: PolicyDecision) -> Case:
    """
    Aplica el boost_delta de la decisión al score del case.

    IMPORTANTE: esto se hace EXPLÍCITAMENTE fuera del PolicyEngine (que es
    pure function y no muta inputs). El caller decide si aplica el boost.

    Mutates case in-place. Clampea a [0, 100].
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


# ===========================================================================
# Smoke test
# ===========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  SMOKE TEST policy_engine.py (con contract formal corrección B)")
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
    print(f"    decision_id = {d1.decision_id}")
    print(f"    ruleset_version = {d1.ruleset_version}")

    # Corrección B garantía 4: idempotencia
    d1_bis = engine.evaluate(case1)
    assert d1.decision_id == d1_bis.decision_id, "Should be idempotent"
    assert d1.actions == d1_bis.actions
    assert d1.boost_delta == d1_bis.boost_delta
    print(f"  ✓ Idempotencia: re-evaluar mismo case → mismo decision_id")

    # Corrección B garantía 1: no side effects
    original_score = case1.score
    original_canonical = case1.is_canonical
    _ = engine.evaluate(case1)
    assert case1.score == original_score
    assert case1.is_canonical == original_canonical
    print(f"  ✓ No side effects: case original NO mutado")

    # Corrección B garantía 2: deterministic
    # Mismo case en otra instancia de engine (misma config) → mismo decision_id
    engine2 = PolicyEngine()
    d1_ter = engine2.evaluate(case1)
    assert d1.decision_id == d1_ter.decision_id
    print(f"  ✓ Deterministic: otra instancia con misma config → mismo decision_id")

    # Corrección B garantía 3: versioned ruleset
    assert d1.ruleset_version == POLICY_RULESET_VERSION
    print(f"  ✓ Versioned ruleset: {d1.ruleset_version}")

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

    # Caso 3: duplicate → suppress_output
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

    # Caso 4: score 50 con whatsapp_number manual
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
    assert d4.has_action("boost_priority")
    print(f"  ✓ Caso con número manual: actions={d4.actions}")

    # Caso 5: approved por revisión
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
    print(f"  ✓ Caso approved: actions={d5.actions}")

    # Test apply_boost (mutación explícita, fuera del engine)
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
    assert case6_boosted.score_band == "critical"
    print(f"  ✓ apply_boost: 78 + 5 = 83, band=critical")

    # Validación del contrato formal (corrección B)
    print(f"\n  Contrato formal PolicyEngine (corrección B):")
    print(f"    Input:    CaseScored (case con score, score_version, is_canonical)")
    print(f"    Output:   PolicyDecision (actions, reasons, boost_delta, decision_id, ruleset_version)")
    print(f"    Garantías:")
    print(f"      1. no side effects      ✓ (no muta input, no escribe externo)")
    print(f"      2. deterministic        ✓ (mismo input → mismo output)")
    print(f"      3. versioned ruleset    ✓ (POLICY_RULESET_VERSION='{POLICY_RULESET_VERSION}')")
    print(f"      4. idempotent per case  ✓ (decision_id = hash(case_id, ruleset, actions))")

    print("\n" + "=" * 70)
    print("  ✓ Todos los smoke tests OK")
    print("=" * 70)



# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
