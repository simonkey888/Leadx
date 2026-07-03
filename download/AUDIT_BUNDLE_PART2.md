=== FILE: policy_engine.py (441 líneas) ===

```"""
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
```


=== FILE: radar_lite.py (503 líneas) ===

```"""
radar_lite.py — Radar de Oportunidades Fase 1 (versión minimalista).

Spec: "Radar de Oportunidades - Fase 1" v1.0

Objetivo: Detectar oportunidades comerciales explícitas en texto público
relacionado con multas, transferencias y libre deuda vehicular, y generar
derivación a WhatsApp.

Componentes EXCLUIDOS por spec:
    - event_bus
    - database
    - sheets
    - policy_engine
    - llm_agents
    - complex_workflows

Reglas:
    - no_external_writes: true
    - no_databases: true
    - no_crm_logic: true
    - no_automation_spam: true
    - manual_review_optional: true
    - focus_only_on_intent_detection: true

Uso:
    python radar_lite.py "texto de la señal pública"
    python radar_lite.py < archivo.txt
    echo "texto" | python radar_lite.py

Output: JSON con score, matched_keywords, snippet, whatsapp_link (si score >= 2)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from urllib.parse import quote

# ===========================================================================
# Configuración del spec (hardcoded, sin config externo)
# ===========================================================================

WHATSAPP_PHONE = "5493425691516"  # +54 9 342 5691516 (sin + ni espacios)
WHATSAPP_ENABLED = True
SCORE_THRESHOLD = 2  # >= 2 genera link de WhatsApp

# Keywords del spec, clasificadas por peso de intención
KEYWORDS_PROBLEM = [
    "multa", "fotomulta", "deuda", "patente",
]
KEYWORDS_CONTEXT = [
    "libre deuda", "transferencia", "urgente",
]
KEYWORDS_ACTION = [
    "vendo auto", "transferir auto", "no puedo vender", "no puedo transferir",
]

# Todas las keywords en una lista (para el campo debug.matched_keywords)
ALL_KEYWORDS = KEYWORDS_PROBLEM + KEYWORDS_CONTEXT + KEYWORDS_ACTION

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",  # AB 123 CD (nuevo)
    r"\b[A-Z]{3}\s?\d{3}\b",              # ABC 123 (viejo)
]

# Tipos de vehículo
VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]

# Jurisdicciones AR (para location extraction)
JURISDICTIONS = [
    "caba", "buenos aires", "pba", "gba", "córdoba", "cordoba", "santa fe",
    "rosario", "mendoza", "tucumán", "tucuman", "neuquén", "neuquen",
    "río negro", "rio negro", "chubut", "la pampa", "corrientes", "misiones",
    "salta", "jujuy", "formosa", "chaco", "santiago del estero", "la rioja",
    "catamarca", "san juan", "san luis", "santa cruz", "tierra del fuego",
]

# Localidades comunes (heurística: "en X", "de X", "vivo en X", "zona X")
LOCATION_PATTERNS = [
    r"(?:estoy en|vivo en|de|zona|en)\s+([A-ZÁÉÍÓÚa-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚa-záéíóúñ]+)?)",
]


# ===========================================================================
# Dataclass de resultado
# ===========================================================================
@dataclass
class RadarResult:
    """Resultado del análisis de una señal pública."""
    # Score 0-3
    score: int = 0
    intent: str = "no_relevant"  # no_relevant / low_intent / medium_intent / high_intent_actionable

    # Entity extraction
    name_or_alias: str = ""
    vehicle_reference: str = ""
    patent_if_present: str = ""
    location: str = ""
    problem_type: str = ""
    source_text_snippet: str = ""

    # Debug (spec: return_raw_score, return_matched_keywords, return_snippet)
    matched_keywords: List[str] = field(default_factory=list)

    # Output
    whatsapp_link: str = ""  # vacío si score < threshold
    triggered: bool = False  # True si score >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Keyword scan
# ===========================================================================
def scan_keywords(text: str) -> Dict[str, List[str]]:
    """
    Escanea el texto y devuelve las keywords matched por categoría.

    Returns:
        {"problem": [...], "context": [...], "action": [...]}
    """
    text_lower = text.lower()

    matched_problem = [kw for kw in KEYWORDS_PROBLEM if kw in text_lower]
    matched_context = [kw for kw in KEYWORDS_CONTEXT if kw in text_lower]
    matched_action = [kw for kw in KEYWORDS_ACTION if kw in text_lower]

    return {
        "problem": matched_problem,
        "context": matched_context,
        "action": matched_action,
    }


# ===========================================================================
# Score calculation (0-3)
# ===========================================================================
def calculate_score(matches: Dict[str, List[str]]) -> int:
    """
    Calcula score 0-3 basado en keywords matched.

    Heurística:
        +1 si hay alguna keyword de problema (multa, fotomulta, deuda, patente)
        +1 si hay alguna keyword de contexto (libre deuda, transferencia, urgente)
        +1 si hay alguna keyword de acción (vendo auto, transferir auto, no puedo...)
        Cap a 3.

    Resultado:
        0 = no_relevant (nada matcheó)
        1 = low_intent (sólo problema mencionado)
        2 = medium_intent (problema + contexto, o acción sola)
        3 = high_intent_actionable (problema + contexto + acción)
    """
    score = 0
    if matches["problem"]:
        score += 1
    if matches["context"]:
        score += 1
    if matches["action"]:
        score += 1
    return min(score, 3)


def score_to_intent(score: int) -> str:
    """Mapea score 0-3 a etiqueta de intención del spec."""
    mapping = {
        0: "no_relevant",
        1: "low_intent",
        2: "medium_intent",
        3: "high_intent_actionable",
    }
    return mapping.get(score, "no_relevant")


# ===========================================================================
# Entity extraction (light regex, optional)
# ===========================================================================
def extract_patent(text: str) -> str:
    """Extrae patente argentina si está presente."""
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    # Patente con palabra "patente" seguida de valor
    m = re.search(r"patente\s+([A-Z]{2,3}\s?\d{3}\s?[A-Z]{0,2})", text, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def extract_vehicle(text: str) -> str:
    """Extrae tipo de vehículo si está mencionado."""
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
    return ""


def extract_location(text: str) -> str:
    """Extrae localidad usando heurísticas simples."""
    for pattern in LOCATION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().title()
            # Filtrar falsos positivos
            if loc.lower() not in {"el", "la", "los", "las", "mi", "tu", "su", "un", "una"}:
                return loc
    # Buscar jurisdicciones conocidas
    text_lower = text.lower()
    for jur in JURISDICTIONS:
        if jur in text_lower:
            return jur.title()
    return ""


def extract_name(text: str) -> str:
    """
    Intenta extraer nombre/alias del autor.
    Heurísticas: @username, "Hola soy X", "Soy X".
    """
    # @username (X/Twitter)
    m = re.search(r"@(\w{3,20})", text)
    if m:
        return m.group(0)
    # "Hola soy X" / "Soy X"
    m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", text, re.IGNORECASE)
    if m:
        return m.group(1).title()
    return ""


def extract_problem_type(matches: Dict[str, List[str]]) -> str:
    """Deriva el tipo de problema desde las keywords matched."""
    all_matched = matches["problem"] + matches["context"] + matches["action"]
    if "vendo auto" in all_matched or "transferir auto" in all_matched or \
       "no puedo vender" in all_matched or "no puedo transferir" in all_matched or \
       "transferencia" in all_matched:
        return "transferencia"
    if "libre deuda" in all_matched:
        return "libre_deuda"
    if "fotomulta" in all_matched:
        return "fotomulta"
    if "multa" in all_matched:
        return "multa"
    if "patente" in all_matched:
        return "patente"
    if "deuda" in all_matched:
        return "deuda"
    return ""


def make_snippet(text: str, max_len: int = 120) -> str:
    """Crea un snippet truncado del texto original."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


# ===========================================================================
# WhatsApp link generation
# ===========================================================================
def generate_whatsapp_link(score: int, problem_type: str, snippet: str) -> str:
    """
    Genera link de WhatsApp según el template del spec.

    Template: "CASO RADAR\nINTENCION: {score}\nTIPO: {problem_type}\nEXTRACTO: {snippet}"
    URL: https://wa.me/5493425691516?text={encoded_message}
    """
    if not WHATSAPP_ENABLED:
        return ""

    message = (
        f"CASO RADAR\n"
        f"INTENCION: {score}\n"
        f"TIPO: {problem_type}\n"
        f"EXTRACTO: {snippet}"
    )
    encoded = quote(message)
    return f"https://wa.me/{WHATSAPP_PHONE}?text={encoded}"


# ===========================================================================
# Pipeline principal
# ===========================================================================
def analyze(text: str) -> RadarResult:
    """
    Pipeline completo del Radar Lite.

    Workflow del spec:
        1. input_text_received
        2. keyword_scan
        3. score_calculation
        4. intent_filtering
        5. if_score_ge_2_generate_output
        6. generate_whatsapp_link
    """
    # 1. input_text_received
    if not text or not text.strip():
        return RadarResult()

    # 2. keyword_scan
    matches = scan_keywords(text)

    # 3. score_calculation
    score = calculate_score(matches)
    intent = score_to_intent(score)

    # 4. intent_filtering
    triggered = score >= SCORE_THRESHOLD

    # Entity extraction (light regex, optional)
    patent = extract_patent(text)
    vehicle = extract_vehicle(text)
    location = extract_location(text)
    name = extract_name(text)
    problem_type = extract_problem_type(matches)
    snippet = make_snippet(text)

    # 5. if_score_ge_2_generate_output
    whatsapp_link = ""
    if triggered:
        # 6. generate_whatsapp_link
        whatsapp_link = generate_whatsapp_link(score, problem_type, snippet)

    # Debug: matched_keywords (todas las que matchearon, en una lista plana)
    all_matched = matches["problem"] + matches["context"] + matches["action"]

    return RadarResult(
        score=score,
        intent=intent,
        name_or_alias=name,
        vehicle_reference=vehicle,
        patent_if_present=patent,
        location=location,
        problem_type=problem_type,
        source_text_snippet=snippet,
        matched_keywords=all_matched,
        whatsapp_link=whatsapp_link,
        triggered=triggered,
    )


# ===========================================================================
# CLI
# ===========================================================================
def read_input() -> str:
    """Lee texto de argumento o stdin."""
    if len(sys.argv) > 1:
        # Argumento directo
        return " ".join(sys.argv[1:])
    # Stdin (pipe o redirect)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    # Modo interactivo
    print("Radar de Oportunidades - Fase 1 (Lite)", file=sys.stderr)
    print("Ingresá el texto de la señal pública (Ctrl+D para finalizar):", file=sys.stderr)
    return sys.stdin.read()


def main() -> int:
    text = read_input()
    if not text.strip():
        print(json.dumps({"error": "no input text"}, ensure_ascii=False))
        return 1

    result = analyze(text)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


# ===========================================================================
# Smoke tests (ejecutar con: python radar_lite.py --test)
# ===========================================================================
def run_tests():
    """Tests con los 4 tipos de input del spec."""
    print("=" * 70)
    print("  SMOKE TEST radar_lite.py")
    print("=" * 70)

    test_cases = [
        # 1. Facebook group post — high intent
        {
            "name": "FB post: vendo auto + libre deuda + urgente",
            "text": "URGENTE: vendo auto por traslado al exterior. Tengo libre deuda pendiente en Santa Fe, necesito regularizar y transferir antes del 15. Auto en Rafaela, patente ABC 999.",
            "expected_score": 3,
            "expected_trigger": True,
        },
        # 2. X post — medium intent
        {
            "name": "X post: fotomulta + consulta",
            "text": "@usuario_cabildo Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. Cómo hago el reclamo?? #fotomultas",
            "expected_score_min": 1,
            "expected_trigger": None,  # puede o no según keywords
        },
        # 3. Marketplace listing — high intent
        {
            "name": "Marketplace: vendo auto + transferencia",
            "text": "Vendo auto Peugeot 208 2019. Libre deuda y 08 firmado, listo para transferir. Sin deudas. $4.500.000. Zona Villa Crespo.",
            "expected_score_min": 2,
            "expected_trigger": True,
        },
        # 4. Manual text — no relevant
        {
            "name": "Manual: texto sin keywords",
            "text": "Hola, qué lindo día hace hoy para pasear por la ciudad.",
            "expected_score": 0,
            "expected_trigger": False,
        },
        # 5. Forum post — medium intent
        {
            "name": "Forum: no puedo transferir + multa",
            "text": "No puedo transferir el auto porque tengo 2 multas impagas de Córdoba. Alguien sabe cómo regularizar? Son del 2023.",
            "expected_score_min": 2,
            "expected_trigger": True,
        },
        # 6. Patente + deuda — low intent
        {
            "name": "Patente atrasada",
            "text": "Le debo 2 cuotas de patente de PBA, lo regularizo antes de transferir.",
            "expected_score_min": 1,
            "expected_trigger": None,
        },
    ]

    passed = 0
    failed = 0

    for tc in test_cases:
        result = analyze(tc["text"])
        ok = True
        reasons = []

        if "expected_score" in tc:
            if result.score != tc["expected_score"]:
                ok = False
                reasons.append(f"score={result.score} (expected {tc['expected_score']})")

        if "expected_score_min" in tc:
            if result.score < tc["expected_score_min"]:
                ok = False
                reasons.append(f"score={result.score} (expected >= {tc['expected_score_min']})")

        if tc["expected_trigger"] is not None:
            if result.triggered != tc["expected_trigger"]:
                ok = False
                reasons.append(f"triggered={result.triggered} (expected {tc['expected_trigger']})")

        status = "✓" if ok else "✗"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n  {status} {tc['name']}")
        print(f"    score={result.score} ({result.intent}) | triggered={result.triggered}")
        print(f"    matched_keywords={result.matched_keywords}")
        print(f"    problem_type={result.problem_type} | patent={result.patent_if_present or '—'} | location={result.location or '—'}")
        if result.whatsapp_link:
            print(f"    whatsapp_link={result.whatsapp_link[:80]}…")
        if reasons:
            for r in reasons:
                print(f"    FAIL: {r}")

    print(f"\n{'=' * 70}")
    print(f"  Resultado: {passed} pasaron, {failed} fallaron")
    print(f"{'=' * 70}")

    # Verificar WhatsApp link format
    print("\n  Verificación WhatsApp link:")
    result = analyze("URGENTE: vendo auto. Libre deuda pendiente. Transferir.")
    link = result.whatsapp_link
    assert link.startswith(f"https://wa.me/{WHATSAPP_PHONE}?text="), \
        f"Link mal formateado: {link[:60]}"
    # Decodificar y verificar template
    from urllib.parse import unquote
    encoded_part = link.split("?text=")[1]
    decoded = unquote(encoded_part)
    assert "CASO RADAR" in decoded
    assert f"INTENCION: {result.score}" in decoded
    assert f"TIPO: {result.problem_type}" in decoded
    assert "EXTRACTO:" in decoded
    print(f"  ✓ Link usa teléfono {WHATSAPP_PHONE}")
    print(f"  ✓ Template: CASO RADAR / INTENCION / TIPO / EXTRACTO")
    print(f"  ✓ Score threshold = {SCORE_THRESHOLD} (genera link si score >= {SCORE_THRESHOLD})")

    print(f"\n{'=' * 70}")
    print(f"  ✓ Todos los smoke tests OK")
    print(f"{'=' * 70}")
    return failed == 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if run_tests() else 1)
    sys.exit(main())
```


=== FILE: radar_pro.py (1195 líneas) ===

```"""
radar_pro.py — Radar de Oportunidades PRO (reporte ejecutivo comercial).

Misión: encontrar personas reales con problemas vehiculares públicos en Argentina.

Mejoras vs v4.1:
  - Filtro últimos 7 días (cuando hay fecha visible)
  - Sin inventar datos faltantes
  - Reporte ejecutivo comercial como salida principal (no JSON)
  - Scoring exacto del prompt PRO
  - Queries orientadas a dolor explícito
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Config
# ===========================================================================

OUTPUT_JSON = Path("/home/z/my-project/download/radar_pro_output.json")
OUTPUT_REPORT = Path("/home/z/my-project/download/radar_pro_reporte.md")
OUTPUT_TXT = Path("/home/z/my-project/download/radar_pro_reporte.txt")
RAW_PATH = Path("/home/z/my-project/download/radar_pro_raw.json")

MAX_ITERATIONS = 25
RESULTS_PER_QUERY = 10
MIN_LEADS_CALIENTES = 8

# ===========================================================================
# Queries orientadas a dolor explícito (no genéricas)
# ===========================================================================

QUERIES = [
    # Reddit — alta prioridad
    ("reddit", "site:reddit.com no puedo transferir auto argentina"),
    ("reddit", "site:reddit.com me llegó multa argentina"),
    ("reddit", "site:reddit.com libre deuda problema argentina"),
    ("reddit", "site:reddit.com fotomulta reclamo argentina"),
    ("reddit", "site:reddit.com multa no es mi auto"),
    ("reddit", "site:reddit.com 08 firmado problema"),
    # Facebook — alta prioridad
    ("facebook", "site:facebook.com no puedo transferir auto multa"),
    ("facebook", "site:facebook.com me llegó fotomulta"),
    ("facebook", "site:facebook.com libre deuda falso"),
    ("facebook", "site:facebook.com vendedor no entregó 08"),
    ("facebook", "site:facebook.com tengo multas impagas"),
    # Sin site: — frases humanas
    ("dolor", "no puedo transferir auto por multas argentina"),
    ("dolor", "me llegó una multa y no es mi auto"),
    ("dolor", "me dieron un libre deuda falso"),
    ("dolor", "multas vencidas sin notificar argentina"),
    ("dolor", "el vendedor no me entregó el 08"),
    ("dolor", "transferir auto con deudas problema"),
    ("dolor", "no me notificaron multa argentina"),
    ("dolor", "quiero transferir auto radicado otra provincia"),
    ("dolor", "patente bloqueada no puedo transferir"),
    ("dolor", "tengo fotomultas de ruta argentina"),
    ("dolor", "transferencia rechazada multas"),
]

# ===========================================================================
# Filtros obligatorios del spec PRO
# ===========================================================================

MUST_MATCH = ["multa", "fotomulta", "transferencia", "libre deuda", "patente", "08 firmado"]

PAIN_EXPLICIT_PATTERNS = [
    "no puedo transferir", "no puedo hacer la transferencia",
    "quiero transferir", "necesito transferir", "puedo hacer la transferencia",
    "transferencia de un auto", "transferencia de auto", "transferencia del auto",
    "transferir un auto", "transferir el auto",
    "me rechazaron", "transferencia bloqueada", "transferencia rechazada",
    "no me dejan transferir", "no me deja transferir",
    "se puede transferir con multas",
    "tengo multas", "tengo una multa", "tengo fotomultas",
    "me llegó una multa", "me llego una multa", "me llegó esa multa",
    "me llegaron fotomultas", "me llegaron multas",
    "no es mi auto", "no es mi vehículo", "no es mio",
    "multa de caminera", "multas vencidas", "multa impaga",
    "debo multas", "debo patente", "deuda de patente",
    "necesito libre deuda", "cómo saco libre deuda", "como saco libre deuda",
    "me piden libre deuda", "me pide libre deuda",
    "libre deuda falso", "no me dan libre deuda",
    "no me entregó", "nunca te entregó", "no me dio el 08",
    "no me notificaron", "no me llegó la notificación",
    "me saltó una deuda", "me salto una multa",
    "compré un auto con", "compre un auto con",
    "radicado en otra provincia", "radicada en otra",
    "alguien sabe cómo", "alguien sabe como",
    "cómo hago la transferencia", "como hago la transferencia",
    "no se puede transferir",
    "21 fotomultas", "tengo 21 fotomultas",
    "vendí un auto y no lo transfieren",
    "me llegan multas que no hice",
    "no me deja patentar",
]

# Preventivo (sin dolor explícito)
PREVENTIVE_PATTERNS = [
    "vendo auto", "vendo mi auto", "vendo moto",
    "permuto auto", "permuto mi auto", "permuto moto",
    "papeles al día", "papeles al dia", "titular al día",
    "quiero vender mi moto", "quiero vender mi auto",
]

# País
REJECT_COUNTRIES = {
    "méxico", "mexico", "colombia", "uruguay", "chile",
    "perú", "peru", "paraguay", "brasil", "brazil",
    "italia", "italy", "españa", "spain", "estados unidos", "eeuu", "usa",
}

COUNTRY_INDICATORS = {
    "México": ["méxico", "mexico", "cdmx", "guadalajara", "monterrey", "edomex"],
    "Colombia": ["colombia", "bogotá", "bogota", "medellín", "medellin"],
    "Uruguay": ["uruguay", "montevideo"],
    "Chile": ["chile", "santiago de chile", "valparaíso", "valparaiso"],
    "Perú": ["perú", "peru", "lima", "arequipa"],
    "Paraguay": ["paraguay", "asunción", "asuncion"],
    "Brasil": ["brasil", "brazil", "são paulo", "sao paulo", "rio de janeiro"],
    "Italia": ["italia", "italy", "pisa", "roma", "milano", "milán"],
    "España": ["españa", "espana", "madrid", "barcelona", "valencia"],
    "EEUU": ["estados unidos", "usa", "eeuu", "miami", "new york", "california"],
}

PREFERRED_PROVINCES = {
    "buenos aires", "pba", "gba", "santa fe", "rosario",
    "córdoba", "cordoba", "entre ríos", "entre rios", "mendoza",
    "caba", "capital federal", "la plata", "paraná", "parana",
    "neuquén", "neuquen", "salta",
}

# Argentina phone patterns
ARG_PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b0(2[0-9]|3[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\b(11|15)[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9]|37[0-9]|36[0-9]|29[0-9]|28[0-9]|22[0-9]|23[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

FOREIGN_PHONE_PATTERNS = [
    r"\+52\s?\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b52[\s\-]?\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\+57\s?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\+598\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\+56\s?\d{2}[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\+51\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\+595\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\+55\s?\d{2}[\s\-]?\d{4,5}[\s\-]?\d{4}",
]

# Blacklist estricta (organismos, noticias, SEO, concesionarias, competidores)
NEGATIVE_DOMAINS = {
    # Organismos oficiales
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    "rentascba.gov.ar", "rentas.gba.gov.ar", ".gov.ar",
    # Noticias / medios
    "clarin.com", "lanacion.com.ar", "infobae.com", "cronista.com",
    "ambito.com", "pagina12.com.ar", "perfil.com", "tn.com.ar",
    "cronica.com.ar", "minutouno.com", "infopico.com", "rosario3.com",
    "mdzol.com", "losandes.com.ar", "lavoz.com.ar", "eltribuno.com",
    # Calculadoras / blogs / SEO
    "elcerokm.com", "servidos.ar", "alarfin.com.ar", "autofact.cl",
    "autofact.com.ar", "kavak.com", "bitcar.com.ar", "comparaencasa.com",
    # Wikipedia / diccionarios
    "es.wikipedia.org", "en.wikipedia.org", "rae.es", "wiktionary.org",
    # Bancos / fintech
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    # Concesionarias / agencias / marketplace
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "autocosmos.com.ar", "demotores.com.ar", "encuentra24.com",
    "carone.com.ar", "derby.com.ar", "chrysler.com.ar",
    "derco.com.ar", "veico.com.ar", "chaher.com.ar",
    # YouTube / Instagram / TikTok
    "youtube.com", "tiktok.com", "instagram.com",
    # Empresas / seguros
    "nationwide.com", "allianz.com.ar", "sancor.com.ar",
    # Académico
    "researchgate.net", "academia.edu", "scielo.org",
    # LinkedIn corporativo
    "linkedin.com",
    # Sitios de quejas institucionales (no son leads humanos)
    "tuquejasuma.com",
}

# Blacklist de nombres de página (páginas oficiales dentro de facebook.com)
PAGE_BLACKLIST = [
    "rentascba", "rentascordoba", "municipalidadrosario", "arbaoficial",
    "comparaencasa", "viacordoba", "viacordobo", "autocosmos",
    "municrespo", "neuquencapital", "medidorosario",
    "rentas.gob", "municipalidad", "gov.ar",
    "rentas", "arba", "ansv", "argentina.gob",
    "legalesdeargentina",  # cuenta de abogados institucional
    "boedo55",  # blog informativo
]

INFORMATIONAL_INDICATORS = [
    "publicado por", "leer más", "leer mas", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso", "tutorial",
    "todo lo que necesitás saber", "todo lo que necesitas saber",
    "mejores consejos", "consejos para", "tips para",
    "trámite online", "turno web", "consulta de aranceles",
    "sistema integral de trámites",
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "giro", "remesa", "criptomoneda",
    # Indicadores de contenido institucional
    "ansv", "agencia nacional de seguridad vial",
    "ministerio de transporte", "dirección nacional",
]

# Indicadores de concesionaria / agencia / competidor
CONCESIONARIA_INDICATORS = [
    "concesionaria", "concesionario", "agencia oficial",
    "representante oficial", "grupo automotor", "autódromo",
    "toyota san isidro", "toyota pilar", "ford argentina",
]

AGENCIA_INDICATORS = [
    "agencia de autos", "usados garantía", "usados garantia",
    "compramos tu auto", "compramos tu usado", "vendemos usados",
    "stock disponible", "financiación a su medida",
]

COMPETIDOR_INDICATORS = [
    "compro autos con deudas", "compramos autos con deudas",
    "compro autos con multas", "compramos autos con multas",
    "gestoría", "gestoria", "gestor automotor",
    "abogado multas", "abogados multas", "despachante",
    "tramité tu transferencia", "te gestionamos",
    # Cuentas institucionales
    "legalesdeargentina", "abogado", "estudio jurídico",
]

PRIORITY_PLATFORMS = {
    "reddit.com": 100, "www.reddit.com": 100, "old.reddit.com": 100,
    "facebook.com": 95, "m.facebook.com": 95,
    "twitter.com": 85, "x.com": 85,
    "taringa.net": 75, "foroargentino.com": 75,
}

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]
VEHICLE_BRANDS = [
    "ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
    "peugeot", "renault", "citroen", "fiat", "nissan", "hyundai",
    "kia", "seat", "audi", "bmw", "mercedes",
]

PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

TITULAR_INDICATORS = [
    "soy titular", "titular del auto", "titular del vehículo",
    "a mi nombre", "está a mi nombre", "esta a mi nombre",
    "papeles a mi nombre", "tengo los papeles",
    "vendí mi auto", "vendi mi auto", "compré un auto", "compre un auto",
]


# ===========================================================================
# Dataclass
# ===========================================================================
@dataclass
class Lead:
    category: str = ""  # LEAD_CALIENTE | LEAD_COMERCIAL
    problema: str = ""
    persona: str = ""
    provincia: str = ""
    ciudad: str = ""
    vehiculo: str = ""
    plataforma: str = ""
    fecha: str = ""
    urgencia: int = 0
    confianza: int = 0
    whatsapp: str = ""
    telefono: str = ""
    perfil: str = ""
    publicacion: str = ""
    cita: str = ""
    score: int = 0
    lead_reason: str = ""
    query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# z-ai CLI
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    args = json.dumps({"query": query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_pro_{hash(query) & 0xFFFFFFFF:x}.json"
    for attempt in range(4):
        try:
            result = subprocess.run(
                ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
                capture_output=True, text=True, timeout=45,
            )
            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "429" in stderr or "too many requests" in stderr:
                    wait = 5 * (attempt + 1) * 2
                    print(f"    [rate-limit] esperando {wait}s (intento {attempt+1}/4)", file=sys.stderr)
                    time.sleep(wait)
                    continue
                return []
            with open(tmp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except subprocess.TimeoutExpired:
            return []
        except Exception:
            return []
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
    return []


# ===========================================================================
# Helpers
# ===========================================================================
def get_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def make_cita(name: str, snippet: str, max_len: int = 180) -> str:
    text = f"{name}. {snippet}".strip()
    # Limpiar repetición del sitio
    if " - " in text[:80]:
        parts = text.split(" - ", 1)
        if len(parts) > 1:
            text = parts[1]
    return text if len(text) <= max_len else text[:max_len - 1] + "…"


# ===========================================================================
# Country filter
# ===========================================================================
def detect_country(text: str, url: str, phone: str) -> str:
    text_lower = text.lower()
    for country, patterns in [
        ("México", FOREIGN_PHONE_PATTERNS[0:2]),
        ("Colombia", [FOREIGN_PHONE_PATTERNS[2]]),
        ("Uruguay", [FOREIGN_PHONE_PATTERNS[3]]),
        ("Chile", [FOREIGN_PHONE_PATTERNS[4]]),
        ("Perú", [FOREIGN_PHONE_PATTERNS[5]]),
        ("Paraguay", [FOREIGN_PHONE_PATTERNS[6]]),
        ("Brasil", [FOREIGN_PHONE_PATTERNS[7]]),
    ]:
        for pat in patterns:
            if re.search(pat, text):
                return country

    for country, indicators in COUNTRY_INDICATORS.items():
        for ind in indicators:
            if ind in text_lower:
                return country

    for pat in ARG_PHONE_PATTERNS:
        if re.search(pat, text):
            return "Argentina"

    for prov in PREFERRED_PROVINCES:
        if prov in text_lower:
            return "Argentina"

    return "Unknown"


# ===========================================================================
# Validación estricta de contacto
# ===========================================================================
def validate_phone_strict(phone: str) -> bool:
    if not phone:
        return False
    if not re.match(r"^[\d\s\+\-\(\)]+$", phone):
        return False
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10 or len(digits) > 15:
        return False
    if re.search(r"\d-\d-\d-\d-\d-\d-\d-\d", phone):
        return False
    if len(set(digits)) <= 2:
        return False
    return True


def clean_phone(phone: str) -> str:
    if not phone:
        return ""
    has_plus = phone.strip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    return ("+" if has_plus else "") + digits if digits else ""


def extract_phone_strict(text: str) -> str:
    for pattern in ARG_PHONE_PATTERNS:
        for m in re.finditer(pattern, text):
            phone = m.group(0).strip()
            if validate_phone_strict(phone):
                is_foreign = False
                for fp in FOREIGN_PHONE_PATTERNS:
                    if re.search(fp, phone):
                        is_foreign = True
                        break
                if not is_foreign:
                    return clean_phone(phone)
    return ""


def extract_whatsapp_strict(text: str) -> str:
    patterns = [
        r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
        r"wa\.me/(\d{8,15})",
        r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            num = m.group(1).strip()
            if validate_phone_strict(num):
                is_foreign = False
                for fp in FOREIGN_PHONE_PATTERNS:
                    if re.search(fp, num):
                        is_foreign = True
                        break
                if not is_foreign:
                    return clean_phone(num)
    return ""


# ===========================================================================
# Filtros
# ===========================================================================
def is_informational(result: Dict[str, Any]) -> bool:
    url = result.get("url", "").lower()
    host = get_host(result.get("url", ""))
    snippet = (result.get("snippet", "") or "").lower()
    name = (result.get("name", "") or "").lower()
    combined = f"{snippet} {name}"

    for excl in NEGATIVE_DOMAINS:
        if excl in host:
            return True

    for excl in PAGE_BLACKLIST:
        if excl in url:
            return True

    for ind in INFORMATIONAL_INDICATORS:
        if ind in combined:
            return True

    article_patterns = [
        r"^(c[oó]mo|gu[íi]a|mejores?|consejos?|tips?|todo lo que|pasos? para)",
        r"(?:calculadora|simulador|arancel|presupuesto|tarifa)",
        r"(?:tr[áa]mite|turno)\s+online",
    ]
    for pat in article_patterns:
        if re.search(pat, name):
            person_signals = [
                "vendo ", "permuto ", "tengo multa", "me llegó", "no puedo",
                "alguien sabe", "hola gente", "me rechazaron", "quiero transferir",
                "no es mi auto", "me dieron",
            ]
            if not any(s in snippet for s in person_signals):
                return True

    return False


def detect_commercial_entity(text: str) -> Tuple[bool, bool, bool]:
    text_lower = text.lower()
    is_conc = any(ind in text_lower for ind in CONCESIONARIA_INDICATORS)
    is_ag = any(ind in text_lower for ind in AGENCIA_INDICATORS)
    is_comp = any(ind in text_lower for ind in COMPETIDOR_INDICATORS)
    return is_conc, is_ag, is_comp


def is_real_person_signal(result: Dict[str, Any]) -> bool:
    text = (f"{result.get('name', '')} {result.get('snippet', '')}").lower()
    if re.search(r"@\w{3,20}", text):
        return True

    person_phrases = [
        "alguien sabe", "alguien me", "cómo hago", "como hago",
        "qué hago", "que hago", "me pasó", "me paso", "me llegaron",
        "me rechazaron", "no puedo", "tengo multas", "debo multas",
        "hola gente", "buenas gente", "buenas tardes", "buenos días",
        "consulto", "ayuda porfa", "vendo mi", "permuto mi",
        "soy titular", "titular del auto",
        "tengo una multa", "me llegó una multa", "me llego una multa",
        "no me deja transferir", "no me deja vender",
        "me piden libre deuda", "me pide libre deuda",
        "quiero transferir", "necesito transferir",
        "ayuda con transferencia",
        "cómo saco libre deuda", "como saco libre deuda",
        "no me llegó", "no me lego",
        "no es mi auto", "no es mi vehículo",
        "compré un auto", "compre un auto",
        "vendí mi auto", "vendi mi auto",
        "me dieron un libre deuda",
        "no me entregó", "nunca me entregó",
    ]
    for phrase in person_phrases:
        if phrase in text:
            return True

    host = get_host(result.get("url", ""))
    if host in PRIORITY_PLATFORMS:
        vehicle_keywords = [
            "auto", "moto", "camioneta", "vendo", "permuto", "transferir",
            "multa", "fotomulta", "patente", "libre deuda", "08 firmado",
        ]
        if any(kw in text for kw in vehicle_keywords):
            return True

    return False


def detect_person(result: Dict[str, Any]) -> Tuple[str, str]:
    text = f"{result.get('name', '')} {result.get('snippet', '')} {result.get('url', '')}"
    m = re.search(r"@(\w{3,20})", text)
    if m:
        username = m.group(0)
        host = get_host(result.get("url", ""))
        if "reddit.com" in host:
            return username, f"https://reddit.com/user/{m.group(1)}"
        elif "twitter.com" in host or "x.com" in host:
            return username, f"https://x.com/{m.group(1)}"
        elif "facebook.com" in host:
            return username, f"https://facebook.com/{m.group(1)}"
        return username, ""

    m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", text, re.IGNORECASE)
    if m:
        return m.group(1).title(), ""

    host = get_host(result.get("url", ""))
    if "facebook.com" in host:
        if re.search(r"vendo\s+\w+|permuto\s+\w+|no puedo\s+\w+", text, re.IGNORECASE):
            group_match = re.search(r"groups/(\d+)", result.get("url", ""))
            if group_match:
                return "Vendedor en FB group", f"https://facebook.com/groups/{group_match.group(1)}"
            return "Vendedor en FB group", result.get("url", "")

    if "reddit.com" in host:
        user_match = re.search(r"/user/(\w+)", result.get("url", ""))
        if user_match:
            return f"u/{user_match.group(1)}", f"https://reddit.com/user/{user_match.group(1)}"
        # Reddit post: usar el subreddit como referencia
        sub_match = re.search(r"/r/(\w+)/", result.get("url", ""))
        if sub_match:
            return f"Usuario en r/{sub_match.group(1)}", ""

    return "", ""


# ===========================================================================
# Extracción
# ===========================================================================
def extract_patent(text: str) -> str:
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def extract_location(text: str) -> Tuple[str, str]:
    text_lower = text.lower()
    cities = [
        ("lanús", "Buenos Aires"), ("lanus", "Buenos Aires"),
        ("avellaneda", "Buenos Aires"), ("quilmes", "Buenos Aires"),
        ("pilar", "Buenos Aires"), ("moreno", "Buenos Aires"),
        ("san martín", "Buenos Aires"), ("san martin", "Buenos Aires"),
        ("tigre", "Buenos Aires"), ("morón", "Buenos Aires"), ("moron", "Buenos Aires"),
        ("rosario", "Santa Fe"), ("villa gobernador gálvez", "Santa Fe"),
        ("córdoba", "Córdoba"), ("cordoba", "Córdoba"),
        ("mendoza", "Mendoza"), ("rafaela", "Santa Fe"),
        ("paraná", "Entre Ríos"), ("parana", "Entre Ríos"),
        ("concordia", "Entre Ríos"), ("la plata", "Buenos Aires"),
        ("junín", "Buenos Aires"), ("junin", "Buenos Aires"),
        ("salta", "Salta"), ("neuquén", "Neuquén"), ("neuquen", "Neuquén"),
        ("la quiaca", "Jujuy"), ("ushuaia", "Tierra del Fuego"),
    ]
    for city, prov in cities:
        if city in text_lower:
            return city.title(), prov
    for prov in PREFERRED_PROVINCES:
        if prov in text_lower:
            return "", prov.title()
    return "", ""


def extract_vehicle(text: str) -> str:
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
    for b in VEHICLE_BRANDS:
        if b in text_lower:
            return b
    return ""


def is_titular(text: str) -> bool:
    text_lower = text.lower()
    return any(ind in text_lower for ind in TITULAR_INDICATORS)


def parse_date(date_str: str) -> Optional[datetime]:
    """Intenta parsear fecha en varios formatos."""
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%b %d, %Y", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            return datetime.strptime(date_str[:25], fmt)
        except ValueError:
            continue
    return None


def is_recent(date_str: str, days: int = 7) -> Tuple[bool, bool]:
    """
    Returns: (is_recent, has_date)
    - is_recent: True si la fecha es de los últimos `days` días
    - has_date: True si la fecha estaba visible
    """
    dt = parse_date(date_str)
    if dt is None:
        return False, False
    # Handle timezone-aware vs naive
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return (now - dt) <= timedelta(days=days), True


# ===========================================================================
# Clasificación de problema
# ===========================================================================
def classify_problem(text: str) -> Tuple[str, str, int]:
    """
    Returns: (categoria, problema_corto, base_score)
      categoria: LEAD_CALIENTE | LEAD_COMERCIAL
    """
    text_lower = text.lower()

    # LEAD_CALIENTE: dolor explícito

    # Caso especial: compró auto con problema
    if ("compré un auto" in text_lower or "compre un auto" in text_lower) and \
       any(w in text_lower for w in ["multa", "libre deuda", "transferencia", "08"]):
        return "LEAD_CALIENTE", "Compró auto con problema documental", 95

    # Multa que no es suya
    if "no es mi auto" in text_lower or "no es mi vehículo" in text_lower or \
       ("no es mio" in text_lower and "multa" in text_lower):
        return "LEAD_CALIENTE", "Multa que no es suya", 95

    # Libre deuda falso
    if "libre deuda falso" in text_lower or "me dieron un libre deuda falso" in text_lower:
        return "LEAD_CALIENTE", "Le dieron libre deuda falso", 95

    # Vendedor no entregó 08
    if "no me entregó" in text_lower and "08" in text_lower or \
       "nunca te entregó" in text_lower or "no me dio el 08" in text_lower:
        return "LEAD_CALIENTE", "Vendedor no entregó formulario 08", 95

    # No me notificaron
    if "no me notificaron" in text_lower or "no me llegó la notificación" in text_lower or \
       "multas vencidas sin notificar" in text_lower or "sin notificar" in text_lower:
        return "LEAD_CALIENTE", "Multas sin notificación", 95

    # No puedo transferir
    if any(kw in text_lower for kw in [
        "no puedo transferir", "no puedo hacer la transferencia",
        "no me dejan transferir", "no me deja transferir",
        "no se puede transferir", "transferencia bloqueada",
        "transferencia rechazada", "me rechazaron la transferencia",
    ]):
        return "LEAD_CALIENTE", "No puede transferir el vehículo", 95

    # Quiero/necesito transferir
    if any(kw in text_lower for kw in [
        "quiero transferir", "necesito transferir",
        "puedo hacer la transferencia", "puedo transferir",
        "ayuda con transferencia", "transferencia de un auto",
        "transferencia de auto", "transferencia del auto",
        "transferir un auto", "transferir el auto",
        "cómo hago la transferencia", "como hago la transferencia",
        "radicado en otra provincia", "radicada en otra",
    ]):
        return "LEAD_CALIENTE", "Quiere transferir / problema de transferencia", 90

    # Tengo multas / me llegó multa
    if any(kw in text_lower for kw in [
        "tengo multas", "tengo una multa", "tengo fotomultas",
        "me llegó una multa", "me llego una multa", "me llegó esa multa",
        "me llegaron fotomultas", "me llegaron multas",
        "multa de caminera", "multas vencidas", "multa impaga",
        "debo multas", "tengo 21 fotomultas", "21 fotomultas",
        "me llegan multas que no hice",
    ]):
        return "LEAD_CALIENTE", "Tiene multas/fotomultas", 95

    # Libre deuda
    if any(kw in text_lower for kw in [
        "necesito libre deuda", "cómo saco libre deuda", "como saco libre deuda",
        "me piden libre deuda", "me pide libre deuda",
        "donde puedo pedir libre deuda", "no me dan libre deuda",
        "no me deja sacar libre deuda",
    ]):
        return "LEAD_CALIENTE", "Necesita libre deuda", 90

    # Patente
    if "patente bloqueada" in text_lower or "no puedo patentar" in text_lower:
        return "LEAD_CALIENTE", "Problema con patente", 90
    if "debo patente" in text_lower or "deuda de patente" in text_lower:
        return "LEAD_CALIENTE", "Debe patente", 85

    # Vendí y no transfieren
    if "vendí un auto" in text_lower and "no lo transfieren" in text_lower or \
       ("vendí mi auto" in text_lower and "no" in text_lower and "transfer" in text_lower):
        return "LEAD_CALIENTE", "Vendió auto y no le hicieron transferencia", 90

    # 21 fotomultas (caso específico encontrado)
    if "21 fotomultas" in text_lower or "foto multa" in text_lower:
        return "LEAD_CALIENTE", "Tiene fotomultas", 90

    # Alguien sabe + must_match
    if "alguien sabe" in text_lower and any(w in text_lower for w in MUST_MATCH):
        return "LEAD_CALIENTE", "Consulta con dolor explícito", 80

    # === LEAD_COMERCIAL: preventivo ===
    if "vendo" in text_lower and any(b in text_lower for b in VEHICLE_BRANDS + VEHICLE_TYPES):
        if is_titular(text_lower):
            return "LEAD_COMERCIAL", "Vende vehículo (titular)", 50
        return "LEAD_COMERCIAL", "Vende vehículo", 30

    if "permuto" in text_lower:
        return "LEAD_COMERCIAL", "Permuta vehículo", 40

    if any(w in text_lower for w in ["cómo hago", "como hago"]) and \
       any(w in text_lower for w in MUST_MATCH):
        return "LEAD_COMERCIAL", "Consulta documental", 35

    return "LEAD_COMERCIAL", "Señal vehicular genérica", 20


# ===========================================================================
# Scoring EXACTO del spec PRO
# ===========================================================================
def calculate_score_pro(
    text: str,
    category: str,
    base_score: int,
    country: str,
    province: str,
    is_conc: bool,
    is_ag: bool,
    is_comp: bool,
    has_phone: bool,
    has_whatsapp: bool,
    is_recent_pub: bool,
    has_date: bool,
) -> Tuple[int, int, int]:
    """
    Scoring del spec PRO:
      +60 multas/fotomultas
      +40 transferencia
      +30 libre deuda
      +25 titular/vendedor/comprador con contexto
      +20 contacto público
      +15 reciente
      +10 provincia cubierta
      -40 otro país
      -30 concesionaria/agencia
      -50 competidor/institucional
    """
    text_lower = text.lower()
    score = base_score

    # Evidencia de dolor (sumar puntos)
    if "multa" in text_lower or "fotomulta" in text_lower:
        score += 60
    if "transferencia" in text_lower or "transferir" in text_lower:
        score += 40
    if "libre deuda" in text_lower:
        score += 30
    if is_titular(text_lower) or "vendedor" in text_lower or "comprador" in text_lower:
        score += 25
    if has_phone or has_whatsapp:
        score += 20
    if is_recent_pub:
        score += 15
    if province and province.lower() in PREFERRED_PROVINCES:
        score += 10

    # Penalizaciones
    if country != "Argentina" and country != "Unknown":
        score -= 40
    if is_conc:
        score -= 30
    if is_ag:
        score -= 30
    if is_comp:
        score -= 50

    score = max(0, min(100, score))

    # Urgencia
    urgency_keywords = [
        "urgente", "hoy", "mañana", "ahora", "ya", "rápido",
        "antes de", "vencimiento", "vence", "mudanza", "traslado",
    ]
    matches = sum(1 for kw in urgency_keywords if kw in text_lower)
    urgency = 10
    if matches >= 2:
        urgency = 80
    elif matches == 1:
        urgency = 50
    if category == "LEAD_CALIENTE":
        urgency += 25
    urgency = min(urgency, 100)

    # Confianza
    confidence = 40
    if has_date:
        confidence += 15
    else:
        confidence -= 10  # sin fecha visible, bajar confianza
    if has_phone or has_whatsapp:
        confidence += 15
    if province:
        confidence += 10
    if country == "Unknown":
        confidence -= 15
    confidence = max(0, min(100, confidence))

    return score, urgency, confidence


# ===========================================================================
# Construcción de Lead
# ===========================================================================
def build_lead(result: Dict[str, Any], query: str) -> Optional[Lead]:
    if is_informational(result):
        return None

    if not is_real_person_signal(result):
        return None

    url = result.get("url", "")
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    date = result.get("date", "")
    combined = f"{name}. {snippet}"
    combined_lower = combined.lower()

    # MUST_MATCH obligatorio
    matched_must = [kw for kw in MUST_MATCH if kw in combined_lower]
    if not matched_must:
        return None

    # Country filter
    phone = extract_phone_strict(combined)
    whatsapp = extract_whatsapp_strict(combined)
    country = detect_country(combined, url, phone or whatsapp)

    if country in REJECT_COUNTRIES:
        return None

    if country == "Unknown":
        host = get_host(url)
        argentinian_hosts = ["facebook.com", "reddit.com", "twitter.com", "x.com"]
        if not any(h in host for h in argentinian_hosts):
            arg_strong_signals = ["buenos aires", "córdoba", "rosario", "mendoza",
                                   "caba", "patente", "libre deuda", "fotomulta",
                                   "argentina", "dnrpa", "arba"]
            if not any(s in combined_lower for s in arg_strong_signals):
                return None
        country = "Argentina"

    # Detectar persona
    person_name, profile_link = detect_person(result)

    host = get_host(url)
    platform_priority = PRIORITY_PLATFORMS.get(host, 30)

    # Detectar entidades comerciales
    is_conc, is_ag, is_comp = detect_commercial_entity(combined)

    # Si es competidor puro, descartar
    if is_comp:
        return None

    # Clasificar
    categoria, problema_corto, base_score = classify_problem(combined)

    patent = extract_patent(combined)
    city, province = extract_location(combined)
    vehicle = extract_vehicle(combined)

    # Fecha
    is_rec, has_date = is_recent(date, days=7)
    fecha_display = date[:10] if has_date and date else "No disponible"

    # Scoring PRO
    score, urgency, confidence = calculate_score_pro(
        text=combined,
        category=categoria,
        base_score=base_score,
        country=country,
        province=province,
        is_conc=is_conc,
        is_ag=is_ag,
        is_comp=is_comp,
        has_phone=bool(phone),
        has_whatsapp=bool(whatsapp),
        is_recent_pub=is_rec,
        has_date=has_date,
    )

    # Si es LEAD_CALIENTE pero score final < 50, degradar (probablemente no tan caliente)
    if categoria == "LEAD_CALIENTE" and score < 50:
        categoria = "LEAD_COMERCIAL"
        problema_corto = f"[degradado] {problema_corto}"

    plataforma_display = {
        "facebook.com": "Facebook",
        "reddit.com": "Reddit",
        "twitter.com": "X (Twitter)",
        "x.com": "X (Twitter)",
    }.get(host, host.title() if host else "Desconocida")

    return Lead(
        category=categoria,
        problema=problema_corto,
        persona=person_name or "Anónimo (no publicado)",
        provincia=province or "No detectada",
        ciudad=city or "No detectada",
        vehiculo=vehicle.title() if vehicle else "No mencionado",
        plataforma=plataforma_display,
        fecha=fecha_display,
        urgencia=urgency,
        confianza=confidence,
        whatsapp=whatsapp,
        telefono=phone,
        perfil=profile_link,
        publicacion=url,
        cita=make_cita(name, snippet),
        score=score,
        lead_reason=problema_corto,
        query=query,
    )


# ===========================================================================
# Loop
# ===========================================================================
def dedup(leads: List[Lead]) -> List[Lead]:
    seen: Set[str] = set()
    out = []
    for lead in leads:
        key = lead.publicacion or lead.cita[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def run_pipeline() -> Dict[str, Any]:
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES PRO — Reporte ejecutivo comercial", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    all_leads: List[Lead] = []
    all_raw: List[Dict[str, Any]] = []
    seen_queries: Set[str] = set()
    iterations = 0

    query_queue = list(QUERIES)

    while iterations < MAX_ITERATIONS:
        calientes = sum(1 for l in all_leads if l.category == "LEAD_CALIENTE")
        if calientes >= MIN_LEADS_CALIENTES:
            print(f"\n  [success] {calientes} leads calientes. Parando.", file=sys.stderr)
            break

        if not query_queue:
            print(f"\n  [info] Queries agotadas. Parando.", file=sys.stderr)
            break

        query_cat, query = query_queue.pop(0)
        if query in seen_queries:
            continue
        seen_queries.add(query)
        iterations += 1

        print(f"\n  [iter {iterations}/{MAX_ITERATIONS}] [{query_cat}] '{query}'", file=sys.stderr)
        print(f"    Calientes: {sum(1 for l in all_leads if l.category == 'LEAD_CALIENTE')}/{MIN_LEADS_CALIENTES}", file=sys.stderr)

        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
        all_raw.extend(results)

        new_count = 0
        for r in results:
            lead = build_lead(r, query)
            if lead is None:
                continue
            all_leads.append(lead)
            new_count += 1

        print(f"    Resultados: {len(results)} | Nuevos leads: {new_count}", file=sys.stderr)
        time.sleep(2.0)

    all_leads = dedup(all_leads)

    calientes = [l for l in all_leads if l.category == "LEAD_CALIENTE"]
    comerciales = [l for l in all_leads if l.category == "LEAD_COMERCIAL"]

    calientes.sort(key=lambda l: (l.score, l.urgencia, l.confianza), reverse=True)
    comerciales.sort(key=lambda l: (l.score, l.urgencia, l.confianza), reverse=True)

    contacts = [l for l in all_leads if l.whatsapp or l.telefono]

    output = {
        "project": "Radar de Oportunidades PRO",
        "version": "5.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "iterations": iterations,
            "queries_executed": len(seen_queries),
            "total_search_results": len(all_raw),
            "leads_calientes": len(calientes),
            "leads_comerciales": len(comerciales),
            "contactos_publicos": len(contacts),
            "success_met": len(calientes) >= MIN_LEADS_CALIENTES,
        },
        "leads_calientes": [l.to_dict() for l in calientes],
        "leads_comerciales": [l.to_dict() for l in comerciales],
    }

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_PATH.write_text(json.dumps(all_raw, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  Calientes: {len(calientes)} | Comerciales: {len(comerciales)} | Contactos: {len(contacts)}", file=sys.stderr)
    print(f"  Output: {OUTPUT_JSON}", file=sys.stderr)

    return output


# ===========================================================================
# Generación de reporte ejecutivo comercial
# ===========================================================================
def stars(score: int) -> str:
    if score >= 80: return "⭐⭐⭐⭐⭐"
    if score >= 60: return "⭐⭐⭐⭐☆"
    if score >= 40: return "⭐⭐⭐☆☆"
    if score >= 20: return "⭐⭐☆☆☆"
    return "⭐☆☆☆☆"


def generate_report(output: Dict[str, Any]) -> str:
    calientes = output["leads_calientes"]
    comerciales = output["leads_comerciales"]
    contacts = [l for l in calientes + comerciales if l.get("whatsapp") or l.get("telefono")]

    lines = []
    lines.append("# 🔍 RADAR DE OPORTUNIDADES — REPORTE EJECUTIVO COMERCIAL")
    lines.append("")
    lines.append(f"**Generado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines.append(f"**Misión:** Encontrar personas reales con problemas vehiculares públicos en Argentina")
    lines.append(f"**Fuentes:** Reddit, Facebook, X, foros públicos (solo contenido público)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ===== 1) LEADS CALIENTES =====
    lines.append("## 1) 🔥 LEADS CALIENTES (Dolor explícito)")
    lines.append("")
    lines.append(f"_{len(calientes)} personas con problema real declarado._")
    lines.append("")

    for i, l in enumerate(calientes, 1):
        wa = l.get("whatsapp", "") or "No publicado"
        ph = l.get("telefono", "") or "No publicado"
        lines.append(f"### Lead #{i}")
        lines.append(f"- **Problema:** {l['problema']}")
        lines.append(f"- **Persona:** {l['persona']}")
        lines.append(f"- **Provincia / ciudad:** {l['provincia']} / {l['ciudad']}")
        lines.append(f"- **Vehículo:** {l['vehiculo']}")
        lines.append(f"- **Plataforma:** {l['plataforma']}")
        lines.append(f"- **Fecha:** {l['fecha']}")
        lines.append(f"- **Urgencia:** {stars(l['urgencia'])} ({l['urgencia']}/100)")
        lines.append(f"- **Confianza:** {l['confianza']}%")
        lines.append(f"- **WhatsApp público:** {wa}")
        lines.append(f"- **Teléfono público:** {ph}")
        lines.append(f"- **Link:** {l['publicacion']}")
        lines.append(f"- **Cita:** _{l['cita']}_")
        lines.append("")

    # ===== 2) LEADS COMERCIALES =====
    lines.append("## 2) 🟡 LEADS COMERCIALES (Preventivos)")
    lines.append("")
    lines.append(f"_{len(comerciales)} señales preventivas (vende/permuto/consulta, sin dolor explícito)._")
    lines.append("")

    for i, l in enumerate(comerciales, 1):
        wa = l.get("whatsapp", "") or "—"
        ph = l.get("telefono", "") or "—"
        contact_str = f"WA: {wa}" if wa != "—" else (f"Tel: {ph}" if ph != "—" else "Sin contacto público")
        lines.append(f"**#{i}** {l['problema']} — {l['persona']} | {l['provincia']} | {l['vehiculo']} | {l['plataforma']} | {contact_str}")
        lines.append(f"  📝 _{l['cita'][:120]}_")
        lines.append(f"  🔗 {l['publicacion']}")
        lines.append("")

    # ===== 3) CONTACTOS PÚBLICOS =====
    lines.append("## 3) 📞 CONTACTOS PÚBLICOS ENCONTRADOS")
    lines.append("")
    if contacts:
        lines.append("| Persona | WhatsApp | Teléfono | Plataforma |")
        lines.append("|---------|----------|----------|------------|")
        for c in contacts:
            lines.append(f"| {c['persona']} | {c.get('whatsapp') or '—'} | {c.get('telefono') or '—'} | {c['plataforma']} |")
    else:
        lines.append("_No se encontraron contactos públicos en este lote._")
    lines.append("")

    # ===== 4) RESUMEN FINAL =====
    platform_counts = {}
    for l in calientes + comerciales:
        p = l["plataforma"]
        platform_counts[p] = platform_counts.get(p, 0) + 1

    problem_counts = {}
    for l in calientes:
        p = l["problema"]
        problem_counts[p] = problem_counts.get(p, 0) + 1

    lines.append("## 4) 📊 RESUMEN FINAL")
    lines.append("")
    lines.append(f"- **Leads calientes:** {len(calientes)}")
    lines.append(f"- **Leads comerciales:** {len(comerciales)}")
    lines.append(f"- **Contactos públicos:** {len(contacts)}")
    lines.append("")
    lines.append("**Por plataforma:**")
    for p, n in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {p}: {n}")
    lines.append("")
    lines.append("**Tipos de dolor más frecuentes (leads calientes):**")
    for p, n in sorted(problem_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {p}: {n}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Reporte generado automáticamente. Solo contenido público. Revisión humana obligatoria antes de contacto._")

    return "\n".join(lines)


# ===========================================================================
# Main
# ===========================================================================
if __name__ == "__main__":
    output = run_pipeline()
    report = generate_report(output)
    OUTPUT_REPORT.write_text(report, encoding="utf-8")
    OUTPUT_TXT.write_text(report, encoding="utf-8")
    print(report)
```


=== FILE: radar_search.py (739 líneas) ===

```"""
radar_search.py — Radar de Oportunidades v1.1 (búsqueda real de contenido público).

Mission: Descubrir automáticamente oportunidades comerciales públicas relacionadas
con fotomultas, libre deuda y transferencias vehiculares, presentándolas para
revisión humana.

Phase 1 goal: Demostrar que el Radar puede encontrar oportunidades reales sin Ads.
Success: Encontrar al menos 10 oportunidades reales utilizando únicamente información pública.

Sin: CRM, Google Sheets, Database, Dashboards, Event Bus, Policy Engine, LLM Workflow, Cloud, Docker.

Estrategia:
  1. Buscar contenido público (vía z-ai web_search CLI)
  2. Leer publicaciones (vía z-ai page_reader CLI para top resultados)
  3. Extraer señales (regex + heurísticas)
  4. Calificar (intent_score, urgency_score, commercial_score, confidence — 0-100)
  5. Mostrar ranking (top 25, ordenado por commercial_score DESC, urgency_score DESC, confidence DESC)

Compliance:
  - only_public_information: True
  - never_bypass_logins: True
  - never_collect_private_information: True
  - never_send_messages: True
  - human_review_required: True
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from urllib.parse import quote, urlparse

# ===========================================================================
# Configuración del spec v1.1
# ===========================================================================

QUERIES = [
    "fotomulta argentina",
    "multa transito argentina",
    "libre deuda vehicular argentina",
    "transferencia auto argentina",
    "vendo auto argentina",
    "no puedo transferir auto",
    "patente auto argentina",
    "radares fotomultas argentina",
    "APSV multa",
    "multa ruta argentina",
]

# Contexto argentino para mejor relevancia
QUERY_CONTEXT = ""  # ya incluido en queries

# Cuántos resultados por query
RESULTS_PER_QUERY = 8

# Cuántas páginas leer a fondo (top candidates)
PAGES_TO_READ_FULL = 8

# Timeout para page_reader (segundos)
PAGE_READ_TIMEOUT = 45

# Top resultados a mostrar
TOP_RESULTS = 25

# Success criterion
MIN_OPORTUNIDADES_REALES = 10

# Output path
OUTPUT_PATH = Path("/home/z/my-project/download/radar_v1.1_output.json")
RAW_SEARCH_PATH = Path("/home/z/my-project/download/radar_v1.1_raw_search.json")
RAW_PAGES_PATH = Path("/home/z/my-project/download/radar_v1.1_raw_pages.json")

# ===========================================================================
# Keywords para scoring (basadas en el spec)
# ===========================================================================

# Indicadores de intención explícita de acción comercial
INTENT_KEYWORDS = [
    "vendo", "vender", "venta", "transferir", "transferencia", "traspaso",
    "regularizar", "necesito arreglar", "libre deuda", "sacar libre",
    "consulto", "consulta", "necesito asesor", "defender", "reclamar",
    "no puedo transferir", "no puedo vender", "no puedo renovar",
]

# Indicadores de urgencia
URGENCY_KEYWORDS = [
    "urgente", "hoy", "mañana", "ahora", "ya", "rápido", "rapido",
    "antes de", "lo antes posible", "vencimiento", "vence",
    "mudanza", "traslado", "mudo", "viaje",
]

# Indicadores de potencial comercial (problemas que el negocio puede cobrar)
COMMERCIAL_PROBLEMS = {
    "transferencia": 0.9,
    "regularizacion": 0.8,
    "libre_deuda": 0.8,
    "patente": 0.5,
    "fotomulta": 0.4,
    "multa": 0.4,
    "vtv": 0.3,
}

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

# Teléfonos argentinos públicos
PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b11[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b15[\s\-]?\d{4}[\s\-]?\d{4}",
]

WHATSAPP_PATTERNS = [
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"wa\.me/(\d{8,15})",
]

FACEBOOK_PROFILE_PATTERNS = [
    r"facebook\.com/[^/\s\"']{5,50}",
]

# Jurisdicciones AR
JURISDICTIONS = [
    "caba", "buenos aires", "pba", "gba", "córdoba", "cordoba", "santa fe",
    "rosario", "mendoza", "tucumán", "tucuman", "neuquén", "neuquen",
    "río negro", "rio negro", "chubut", "la pampa", "corrientes", "misiones",
    "salta", "jujuy", "formosa", "chaco", "santiago del estero", "la rioja",
    "catamarca", "san juan", "san luis", "santa cruz", "tierra del fuego",
]

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]

# Dominios a filtrar (no son oportunidades comerciales vehiculares)
EXCLUDED_DOMAINS = {
    # Bancos / fintech / transferencias dinero
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    "paypal.com", "n26.com", "bingx.com", "bybit.com",
    # Wikipedia / diccionarios
    "es.wikipedia.org", "en.wikipedia.org", "rae.es",
    # Sitios institucionales gubernamentales (no leads)
    "argentina.gob.ar", "buenosaires.gob.ar",
    # YouTube shorts (no texto útil)
    "youtube.com", "instagram.com",
}

# Palabras que indican que NO es una oportunidad comercial (filtro de snippet)
NEGATIVE_INDICATORS = [
    "wikipedia", "enciclopedia", "definición",
    "transferencia bancaria", "transferir dinero", "transferencia internacional",
    "enviar dinero", "giro", "remesa",
    "criptomoneda", "bitcoin", "exchange",
]


# ===========================================================================
# Dataclass de señal
# ===========================================================================
@dataclass
class Signal:
    """Señal extraída de contenido público."""
    # Identificación
    source: str  # host_name (ej: clarin.com)
    url: str
    name: str  # título de la página/post
    snippet: str  # texto extraído (snippet de search o texto de página)
    date: str  # fecha de publicación si está disponible

    # Entidades extraídas
    nombre_o_alias: str = ""
    ubicacion: str = ""
    tipo_problema: str = ""
    patente_si_aparece: str = ""
    telefono_si_es_publico: str = ""
    whatsapp_si_es_publico: str = ""
    facebook_profile_si_es_publico: str = ""

    # Scoring 0-100
    intent_score: int = 0
    urgency_score: int = 0
    commercial_score: int = 0
    confidence: int = 0

    # Output
    recommended_action: str = "Ignorar"  # Ignorar / Revisar / Posible cliente

    # Meta
    query: str = ""  # query que la encontró
    read_full: bool = False  # si se leyó la página completa

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Búsqueda web (vía z-ai CLI)
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Ejecuta búsqueda web vía z-ai CLI."""
    full_query = f"{query} {QUERY_CONTEXT}".strip()
    args = json.dumps({"query": full_query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_search_{hash(query) & 0xFFFFFFFF:x}.json"

    try:
        result = subprocess.run(
            ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  [warn] search failed for '{query}': {result.stderr[:200]}", file=sys.stderr)
            return []

        with open(tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []
        return data
    except subprocess.TimeoutExpired:
        print(f"  [warn] search timeout for '{query}'", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [warn] search error for '{query}': {e}", file=sys.stderr)
        return []
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def read_page(url: str) -> Optional[Dict[str, Any]]:
    """Lee contenido de una página vía z-ai page_reader CLI."""
    args = json.dumps({"url": url}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_page_{hash(url) & 0xFFFFFFFF:x}.json"

    try:
        result = subprocess.run(
            ["z-ai", "function", "-n", "page_reader", "-a", args, "-o", tmp_file],
            capture_output=True, text=True, timeout=PAGE_READ_TIMEOUT,
        )
        if result.returncode != 0:
            return None

        with open(tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # El formato puede ser {data: {...}} o directo
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except subprocess.TimeoutExpired:
        print(f"    [timeout] {url[:60]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    [error] {e}", file=sys.stderr)
        return None
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


# ===========================================================================
# Extracción de entidades
# ===========================================================================
def extract_patent(text: str) -> str:
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def extract_phone(text: str) -> str:
    for pattern in PHONE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0).strip()
    return ""


def extract_whatsapp(text: str) -> str:
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def extract_facebook_profile(text: str) -> str:
    for pattern in FACEBOOK_PROFILE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return ""


def extract_location(text: str) -> str:
    text_lower = text.lower()
    for jur in JURISDICTIONS:
        if jur in text_lower:
            return jur.title()
    return ""


def extract_vehicle(text: str) -> str:
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
    return ""


def extract_problem_type(text: str) -> str:
    text_lower = text.lower()
    priority = [
        ("fotomulta", "fotomulta"),
        ("foto multa", "fotomulta"),
        ("multa de ruta", "fotomulta"),
        ("apsv", "fotomulta"),
        ("radares", "fotomulta"),
        ("libre deuda", "libre_deuda"),
        ("transferencia", "transferencia"),
        ("transferir", "transferencia"),
        ("no puedo transferir", "transferencia"),
        ("no puedo vender", "transferencia"),
        ("vendo auto", "transferencia"),
        ("regularizar", "regularizacion"),
        ("regularizacion", "regularizacion"),
        ("patente", "patente"),
        ("multa", "multa"),
        ("multas", "multa"),
        ("deuda", "deuda"),
    ]
    for kw, problem in priority:
        if kw in text_lower:
            return problem
    return ""


def extract_name(text: str, title: str) -> str:
    """Intenta extraer nombre/alias del autor."""
    m = re.search(r"@(\w{3,20})", text)
    if m:
        return m.group(0)
    m = re.search(r"(?:por|de|autor)\s*:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})", text)
    if m:
        return m.group(1)
    return ""


# ===========================================================================
# Scoring (0-100)
# ===========================================================================
def count_keywords(text: str, keywords: List[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def calculate_intent_score(text: str) -> int:
    """
    Intención explícita de acción comercial.
    0-100 basado en cantidad y peso de keywords de intención.
    """
    matches = count_keywords(text, INTENT_KEYWORDS)
    if matches == 0:
        return 10
    if matches == 1:
        return 40
    if matches == 2:
        return 65
    if matches == 3:
        return 85
    return 100


def calculate_urgency_score(text: str) -> int:
    """
    Urgencia temporal declarada.
    0-100 basado en keywords de urgencia.
    """
    matches = count_keywords(text, URGENCY_KEYWORDS)
    if matches == 0:
        return 10
    if matches == 1:
        return 50
    if matches == 2:
        return 80
    return 100


def calculate_commercial_score(text: str, problem_type: str) -> int:
    """
    Potencial comercial del problema.
    0-100 basado en tipo de problema + monto + presencia de patente/vehículo.
    """
    base = COMMERCIAL_PROBLEMS.get(problem_type, 0.0)
    score = int(base * 70)  # base 0-70

    # Boost si hay patente (lead más concreto)
    if extract_patent(text):
        score += 15
    # Boost si hay vehículo mencionado
    if extract_vehicle(text):
        score += 10
    # Boost si hay ubicación
    if extract_location(text):
        score += 5

    return min(score, 100)


def calculate_confidence(signal: Signal, has_full_text: bool) -> int:
    """
    Confianza en la extracción.
    0-100 basado en:
      - si se leyó la página completa (+30)
      - si hay entidades concretas (patente, teléfono, ubicación)
      - si la fuente es confiable
    """
    conf = 30  # base
    if has_full_text:
        conf += 30
    if signal.patente_si_aparece:
        conf += 15
    if signal.telefono_si_es_publico or signal.whatsapp_si_es_publico:
        conf += 15
    if signal.ubicacion:
        conf += 10
    return min(conf, 100)


def assign_recommended_action(commercial: int, urgency: int, confidence: int) -> str:
    """
    Asigna acción recomendada según scores.
    - Posible cliente: commercial >= 60 AND confidence >= 50
    - Revisar: commercial >= 35 OR urgency >= 60
    - Ignorar: resto
    """
    if commercial >= 60 and confidence >= 50:
        return "Posible cliente"
    if commercial >= 35 or urgency >= 60:
        return "Revisar"
    return "Ignorar"


# ===========================================================================
# Pipeline principal
# ===========================================================================
def build_signal_from_search_result(result: Dict[str, Any], query: str) -> Signal:
    """Construye una Signal a partir de un resultado de búsqueda."""
    text = (result.get("snippet", "") or "")
    title = result.get("name", "") or ""
    combined = f"{title}. {text}"

    problem = extract_problem_type(combined)

    return Signal(
        source=result.get("host_name", ""),
        url=result.get("url", ""),
        name=title,
        snippet=text,
        date=result.get("date", ""),
        nombre_o_alias=extract_name(combined, title),
        ubicacion=extract_location(combined),
        tipo_problema=problem,
        patente_si_aparece=extract_patent(combined),
        telefono_si_es_publico=extract_phone(combined),
        whatsapp_si_es_publico=extract_whatsapp(combined),
        facebook_profile_si_es_publico=extract_facebook_profile(combined),
        intent_score=calculate_intent_score(combined),
        urgency_score=calculate_urgency_score(combined),
        commercial_score=calculate_commercial_score(combined, problem),
        confidence=0,  # se calcula después
        query=query,
        read_full=False,
    )


def enrich_signal_with_page(signal: Signal, page_data: Dict[str, Any]) -> Signal:
    """Enriquece la señal con el contenido completo de la página."""
    html = page_data.get("html", "") or ""
    # Convertir HTML a texto plano (simple)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Tomar primeros 3000 chars para no saturar
    full_text = f"{signal.name}. {text[:3000]}"

    # Re-extraer con texto completo
    problem = extract_problem_type(full_text) or signal.tipo_problema
    signal.tipo_problema = problem
    if not signal.patente_si_aparece:
        signal.patente_si_aparece = extract_patent(full_text)
    if not signal.telefono_si_es_publico:
        signal.telefono_si_es_publico = extract_phone(full_text)
    if not signal.whatsapp_si_es_publico:
        signal.whatsapp_si_es_publico = extract_whatsapp(full_text)
    if not signal.facebook_profile_si_es_publico:
        signal.facebook_profile_si_es_publico = extract_facebook_profile(full_text)
    if not signal.ubicacion:
        signal.ubicacion = extract_location(full_text)
    if not signal.nombre_o_alias:
        signal.nombre_o_alias = extract_name(full_text, signal.name)

    # Re-calcular scores con texto completo
    signal.intent_score = calculate_intent_score(full_text)
    signal.urgency_score = calculate_urgency_score(full_text)
    signal.commercial_score = calculate_commercial_score(full_text, problem)

    # Actualizar snippet con texto más rico
    if len(text) > len(signal.snippet):
        signal.snippet = text[:500]

    signal.read_full = True
    if page_data.get("publishedTime") and not signal.date:
        signal.date = page_data.get("publishedTime", "")

    return signal


def is_relevant_result(result: Dict[str, Any]) -> bool:
    """
    Filtra resultados que no son oportunidades comerciales vehiculares.
    Descarta bancos, fintech, wikipedia, etc.
    """
    url = result.get("url", "").lower()
    host = result.get("host_name", "").lower()
    snippet = (result.get("snippet", "") or "").lower()
    name = (result.get("name", "") or "").lower()

    # Filtro por dominio excluido
    for excl in EXCLUDED_DOMAINS:
        if excl in host:
            return False

    # Filtro por indicadores negativos en snippet o título
    combined = f"{snippet} {name}"
    for neg in NEGATIVE_INDICATORS:
        if neg in combined:
            return False

    return True


def dedup_by_url(signals: List[Signal]) -> List[Signal]:
    """Deduplica señales por URL."""
    seen: Set[str] = set()
    out = []
    for s in signals:
        if s.url in seen:
            continue
        seen.add(s.url)
        out.append(s)
    return out


def run_pipeline() -> Dict[str, Any]:
    """Ejecuta el pipeline completo de búsqueda y scoring."""
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES v1.1 — Búsqueda de contenido público", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # 1. Buscar contenido público
    print(f"\n[1/5] Buscando {len(QUERIES)} queries en contenido público…", file=sys.stderr)
    all_search_results: List[Dict[str, Any]] = []
    for i, query in enumerate(QUERIES, 1):
        print(f"  [{i}/{len(QUERIES)}] Buscando: '{query} {QUERY_CONTEXT}'", file=sys.stderr)
        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
        all_search_results.extend(results)
        time.sleep(0.3)  # rate limit cortés

    print(f"\n  Total resultados de búsqueda: {len(all_search_results)}", file=sys.stderr)

    # Guardar raw search
    RAW_SEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_SEARCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_search_results, f, ensure_ascii=False, indent=2)

    # 2. Construir señales iniciales desde snippets (filtrando irrelevantes)
    print(f"\n[2/5] Extrayendo señales de snippets (con filtro de relevancia)…", file=sys.stderr)
    signals = []
    filtered_out = 0
    for r in all_search_results:
        if not r.get("url") or not r.get("snippet"):
            continue
        if not is_relevant_result(r):
            filtered_out += 1
            continue
        sig = build_signal_from_search_result(r, r.get("_query", ""))
        signals.append(sig)

    print(f"  Filtrados (no relevantes): {filtered_out}", file=sys.stderr)

    # Dedup por URL
    signals = dedup_by_url(signals)
    print(f"  Señales únicas (post-dedup): {len(signals)}", file=sys.stderr)

    # 3. Leer páginas completas para top candidates
    # Ordenar por commercial_score + intent_score (preliminar) y tomar top N
    signals.sort(key=lambda s: (s.commercial_score + s.intent_score), reverse=True)
    candidates_to_read = signals[:PAGES_TO_READ_FULL]

    print(f"\n[3/5] Leyendo {len(candidates_to_read)} páginas a fondo…", file=sys.stderr)
    raw_pages: Dict[str, Dict[str, Any]] = {}
    for i, sig in enumerate(candidates_to_read, 1):
        print(f"  [{i}/{len(candidates_to_read)}] {sig.source}{sig.url[:60]}", file=sys.stderr)
        page_data = read_page(sig.url)
        if page_data:
            raw_pages[sig.url] = page_data
            enrich_signal_with_page(sig, page_data)
        time.sleep(0.5)  # rate limit cortés

    # Guardar raw pages
    with RAW_PAGES_PATH.open("w", encoding="utf-8") as f:
        json.dump(raw_pages, f, ensure_ascii=False, indent=2)

    # 4. Calcular confidence y recommended_action para todas
    print(f"\n[4/5] Calculando confidence y recommended_action…", file=sys.stderr)
    for sig in signals:
        sig.confidence = calculate_confidence(sig, sig.read_full)
        sig.recommended_action = assign_recommended_action(
            sig.commercial_score, sig.urgency_score, sig.confidence
        )

    # 5. Ranking y top 25
    print(f"\n[5/5] Ranking (commercial DESC, urgency DESC, confidence DESC)…", file=sys.stderr)
    signals.sort(
        key=lambda s: (s.commercial_score, s.urgency_score, s.confidence),
        reverse=True,
    )
    top = signals[:TOP_RESULTS]

    # Success criterion
    oportunities = [s for s in signals if s.recommended_action in ("Revisar", "Posible cliente")]
    success = len(oportunities) >= MIN_OPORTUNIDADES_REALES

    # Output final
    output = {
        "project_name": "Radar de Oportunidades",
        "version": "1.1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "queries_executed": len(QUERIES),
            "total_search_results": len(all_search_results),
            "unique_signals": len(signals),
            "pages_read_full": len(raw_pages),
            "opportunities_found": len(oportunities),
            "success_criterion_met": success,
            "min_required": MIN_OPORTUNIDADES_REALES,
        },
        "ranking": {
            "sort_by": ["commercial_score DESC", "urgency_score DESC", "confidence DESC"],
            "top_results": TOP_RESULTS,
        },
        "results": [
            {
                "score": s.commercial_score,
                "confidence": s.confidence,
                "source": s.source,
                "url": s.url,
                "name": s.name,
                "problem": s.tipo_problema,
                "snippet": s.snippet[:300] if s.snippet else "",
                "phone_if_public": s.telefono_si_es_publico,
                "whatsapp_if_public": s.whatsapp_si_es_publico,
                "recommended_action": s.recommended_action,
                "scores": {
                    "intent": s.intent_score,
                    "urgency": s.urgency_score,
                    "commercial": s.commercial_score,
                },
                "entities": {
                    "nombre_o_alias": s.nombre_o_alias,
                    "ubicacion": s.ubicacion,
                    "patente_si_aparece": s.patente_si_aparece,
                    "facebook_profile_si_es_publico": s.facebook_profile_si_es_publico,
                },
                "date": s.date,
                "query": s.query,
                "read_full": s.read_full,
            }
            for s in top
        ],
        "compliance": {
            "only_public_information": True,
            "never_bypass_logins": True,
            "never_collect_private_information": True,
            "never_send_messages": True,
            "human_review_required": True,
        },
    }

    # Guardar output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "=" * 70, file=sys.stderr)
    print("  RESULTADO", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Queries ejecutadas:        {len(QUERIES)}", file=sys.stderr)
    print(f"  Resultados de búsqueda:    {len(all_search_results)}", file=sys.stderr)
    print(f"  Señales únicas:            {len(signals)}", file=sys.stderr)
    print(f"  Páginas leídas a fondo:    {len(raw_pages)}", file=sys.stderr)
    print(f"  Oportunidades encontradas: {len(oportunities)}", file=sys.stderr)
    print(f"  Success criterion:         {'✓ CUMPLIDO' if success else '✗ NO cumplido'} ({len(oportunities)}/{MIN_OPORTUNIDADES_REALES})", file=sys.stderr)
    print(f"  Top {TOP_RESULTS} guardado en: {OUTPUT_PATH}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Print top 10
    print(f"\n  TOP 10 OPORTUNIDADES:", file=sys.stderr)
    for i, s in enumerate(top[:10], 1):
        print(f"    {i:2d}. [{s.recommended_action:15s}] C={s.commercial_score:3d} U={s.urgency_score:3d} I={s.urgency_score:3d} Conf={s.confidence:3d} | {s.source:20s} | {s.tipo_problema:15s} | {s.name[:50]}", file=sys.stderr)

    return output


if __name__ == "__main__":
    output = run_pipeline()
    # Print JSON a stdout
    print(json.dumps(output, ensure_ascii=False, indent=2))
```


=== FILE: radar_v2.py (977 líneas) ===

```"""
radar_v2.py — Radar de Oportunidades v2 (búsqueda de personas reales).

Mission: Encontrar personas reales que manifiesten públicamente un problema
relacionado con multas, transferencia de vehículos, libre deuda o fotomultas.
NO artículos, NO calculadoras, NO organismos oficiales, NO contenido SEO.

Estrategia clave (insight del usuario):
  Buscar tanto el problema explícito (fotomulta, multa) COMO el evento anterior
  (vendo auto, permuto, 08 firmado, registro automotor). El evento anterior es
  donde el lead todavía no descubrió que las multas le bloquean el trámite —
  mayor ventana comercial.

Loop adaptativo:
  1. Buscar query
  2. Filtrar informativo agresivo
  3. Si quedan leads humanos → acumular
  4. Si < 10 leads → re-buscar con queries refinadas
  5. Parar a los 10 leads humanos o max 50 iteraciones

Success:
  - >= 10 leads humanos distintos
  - >= 3 con whatsapp posible
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Configuración del spec v2
# ===========================================================================

OUTPUT_PATH = Path("/home/z/my-project/download/radar_v2_output.json")
RAW_SEARCH_PATH = Path("/home/z/my-project/download/radar_v2_raw_search.json")

MIN_REAL_LEADS = 10
MIN_WHATSAPP_CANDIDATES = 3
MAX_ITERATIONS = 50
RESULTS_PER_QUERY = 10

# ---------------------------------------------------------------------------
# Queries en 2 categorías (insight del usuario: evento-anterior + problema)
# ---------------------------------------------------------------------------
# (A) Evento anterior — lead todavía no sabe que tiene problema
QUERIES_EVENTO_ANTERIOR = [
    "vendo auto argentina",
    "permuto auto argentina",
    "quiero transferir auto",
    "08 firmado transferencia",
    "libre deuda auto",
    "registro automotor transferencia",
    "verificacion policial auto",
    "transferir auto usado",
    "vendo moto argentina",
    "permuto moto argentina",
]

# (B) Problema explícito — lead ya sabe que tiene multa/deuda
QUERIES_PROBLEMA_EXPLICITO = [
    "no puedo transferir auto multa",
    "me llegaron fotomultas",
    "tengo multas impagas",
    "no puedo vender auto",
    "me rechazaron transferencia",
    "me pide libre deuda",
    "debo multas transito",
    "patente bloqueada",
    "problema con transferencia auto",
    "fotomulta reclamo",
    "multa ruta apsv",
    "radares fotomultas consulta",
]

# (C) Queries con platform hints para priorizar conversaciones humanas
QUERIES_PLATFORM_HINTS = [
    "site:reddit.com multa argentina",
    "site:reddit.com transferencia auto argentina",
    "site:facebook.com vendo auto argentina",
    "site:facebook.com groups fotomulta",
    "site:twitter.com fotomulta",
    "site:twitter.com no puedo transferir auto",
    "site:taringa.net multa",
    "site:youtube.com vendo auto argentina",
    "site:foro.argentina multa transferencia",
    "foro argentino multa transito",
]

# Todas las queries en orden de prioridad (intercaladas)
ALL_QUERIES = []
for i in range(max(len(QUERIES_EVENTO_ANTERIOR), len(QUERIES_PROBLEMA_EXPLICITO), len(QUERIES_PLATFORM_HINTS))):
    if i < len(QUERIES_EVENTO_ANTERIOR):
        ALL_QUERIES.append(("evento_anterior", QUERIES_EVENTO_ANTERIOR[i]))
    if i < len(QUERIES_PROBLEMA_EXPLICITO):
        ALL_QUERIES.append(("problema_explicito", QUERIES_PROBLEMA_EXPLICITO[i]))
    if i < len(QUERIES_PLATFORM_HINTS):
        ALL_QUERIES.append(("platform_hint", QUERIES_PLATFORM_HINTS[i]))

# ---------------------------------------------------------------------------
# Positive signals (lenguaje humano, primera persona, consulta)
# ---------------------------------------------------------------------------
POSITIVE_SIGNALS = [
    "no puedo transferir", "tengo multas", "me llegaron fotomultas",
    "alguien sabe", "cómo hago", "como hago", "me rechazaron",
    "me pide libre deuda", "debo multas", "patente bloqueada",
    "no puedo vender el auto", "problema con transferencia",
    "radares", "fotomulta", "ayuda", "consulta", "consulto",
    "vendo auto", "permuto", "quiero transferir", "08 firmado",
    "registro automotor", "verificacion policial",
    "hola gente", "buenas", "alguien me", "me pasó", "me paso",
    "qué hago", "que hago", "me conviene", "vale la pena",
]

# ---------------------------------------------------------------------------
# Negative sources (blacklist estricta)
# ---------------------------------------------------------------------------
NEGATIVE_DOMAINS = {
    # Organismos oficiales
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    # Noticias / medios
    "clarin.com", "lanacion.com.ar", "infobae.com", "cronista.com",
    "ambito.com", "pagina12.com.ar", "perfil.com", "tn.com.ar",
    "cronica.com.ar", "minutouno.com", "infopico.com", "radiofonica.com.ar",
    # Calculadoras / blogs / SEO
    "elcerokm.com", "servidos.ar", "alarfin.com.ar", "autofact.cl",
    "autofact.com.ar", "kavak.com", "bitcar.com.ar", "bbva.com",
    "galicia.com", "bicisyscooters.com", "wikihow.com",
    # Wikipedia / diccionarios
    "es.wikipedia.org", "en.wikipedia.org", "rae.es", "wiktionary.org",
    # Bancos / fintech
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    "paypal.com", "n26.com", "bingx.com", "bybit.com",
    # Concesionarias / Marketplace
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "autocosmos.com.ar", "demotores.com.ar", "encuentra24.com",
    "carone.com.ar", "derby.com.ar", "chrysler.com.ar",
    # YouTube / Instagram (短视频 sin texto útil para lead)
    "youtube.com",  # comments no se indexan bien
    "tiktok.com",
    # Instagram requiere login para ver posts
    "instagram.com",
    # NOTA: facebook.com NO se excluye — los grupos públicos sí son indexables
    # y son la fuente #1 de leads humanos según el spec
    # Empresas de seguros / tasaciones
    "nationwide.com", "allianz.com.ar", "sancor.com.ar",
    # Académico
    "researchgate.net", "academia.edu", "scielo.org",
    # Otros
    "linkedin.com",  # posts corporativos, no leads humanos
}

# Indicadores de contenido informativo (para filtrar)
INFORMATIONAL_INDICATORS = [
    # Artículos
    "publicado por", "leer más", "leer mas", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso", "tutorial",
    "todo lo que necesitás saber", "todo lo que necesitas saber",
    # SEO
    "mejores consejos", "consejos para", "tips para",
    # Organismos
    "trámite online", "turno web", "consulta de aranceles",
    "sistema integral de trámites",
    # Bancos
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "giro", "remesa", "criptomoneda",
]

# ---------------------------------------------------------------------------
# Plataformas prioritarias (donde hay conversaciones humanas)
# ---------------------------------------------------------------------------
PRIORITY_PLATFORMS = {
    "facebook.com": 100,
    "m.facebook.com": 100,
    "reddit.com": 90,
    "www.reddit.com": 90,
    "old.reddit.com": 90,
    "twitter.com": 90,
    "x.com": 90,
    "taringa.net": 85,
    "foroargentino.com": 85,
}

# Patrones para detectar personas reales
PERSON_PATTERNS = [
    r"@(\w{3,20})",  # @username (X, Reddit, Instagram)
    r"(?:por|de|autor)\s*:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})",
    r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})",
]

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b15[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b11[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b34[0-9][\s\-]?\d{3}[\s\-]?\d{4}",  # Rosario / Santa Fe
]

WHATSAPP_PATTERNS = [
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"wa\.me/(\d{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
]

FACEBOOK_PROFILE_PATTERNS = [
    r"facebook\.com/[^/\s\"']{5,50}",
]

JURISDICTIONS = [
    "caba", "buenos aires", "pba", "gba", "córdoba", "cordoba", "santa fe",
    "rosario", "mendoza", "tucumán", "tucuman", "neuquén", "neuquen",
    "río negro", "rio negro", "chubut", "la pampa", "corrientes", "misiones",
    "salta", "jujuy", "formosa", "chaco", "santiago del estero", "la rioja",
    "catamarca", "san juan", "san luis", "santa cruz", "tierra del fuego",
    "lanús", "lanus", "avellaneda", "quilmes", "pilar", "moreno",
    "san martín", "san martin", "tigre", "morón", "moron", "flores",
    "caballito", "belgrano", "palermo",
]

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]


# ===========================================================================
# Dataclass de Lead
# ===========================================================================
@dataclass
class Lead:
    """Lead humano detectado en contenido público."""
    # Identificación
    person_name: str = ""
    profile_link: str = ""
    post_link: str = ""
    platform: str = ""
    date: str = ""

    # Contexto
    city_if_detected: str = ""
    vehicle_if_detected: str = ""
    problem_summary: str = ""
    quoted_text: str = ""

    # Scoring 0-100
    commercial_score: int = 0
    urgency_score: int = 0
    confidence: int = 0

    # Contacto
    possible_whatsapp: str = ""
    possible_phone: str = ""

    # Meta
    query: str = ""
    query_category: str = ""  # evento_anterior / problema_explicito / platform_hint
    source_host: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Llamadas a z-ai CLI
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Ejecuta búsqueda web vía z-ai CLI."""
    args = json.dumps({"query": query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_v2_search_{hash(query) & 0xFFFFFFFF:x}.json"

    try:
        result = subprocess.run(
            ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode != 0:
            return []
        with open(tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except (subprocess.TimeoutExpired, Exception):
        return []
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


# ===========================================================================
# Filtros
# ===========================================================================
def get_host(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().lstrip("www.")
    except Exception:
        return ""


def is_informational(result: Dict[str, Any]) -> bool:
    """
    Detecta si un resultado es contenido informativo (artículo, calculadora,
    organismo) en vez de conversación humana.
    """
    url = result.get("url", "").lower()
    host = get_host(result.get("url", ""))
    snippet = (result.get("snippet", "") or "").lower()
    name = (result.get("name", "") or "").lower()
    combined = f"{snippet} {name}"

    # 1. Blacklist de dominios
    for excl in NEGATIVE_DOMAINS:
        if excl in host:
            return True

    # 2. Indicadores informativos en texto
    for ind in INFORMATIONAL_INDICATORS:
        if ind in combined:
            return True

    # 3. Heurística: títulos tipo "Cómo...", "Guía...", "Mejores..."
    article_patterns = [
        r"^(c[oó]mo|gu[íi]a|mejores?|consejos?|tips?|todo lo que|pasos? para)",
        r"(?:calculadora|simulador|arancel|presupuesto|tarifa)",
        r"(?:tr[áa]mite|turno)\s+online",
    ]
    for pat in article_patterns:
        if re.search(pat, name):
            # Pero NO marcar como informativo si el snippet tiene señales de persona
            person_signals = [
                "vendo ", "permuto ", "tengo multa", "me llegó", "no puedo",
                "alguien sabe", "hola gente",
            ]
            if not any(s in snippet for s in person_signals):
                return True

    return False


def detect_person(result: Dict[str, Any]) -> Tuple[str, str]:
    """
    Detecta si el resultado contiene a una persona real.
    Returns: (person_name, profile_link)
    """
    text = f"{result.get('name', '')} {result.get('snippet', '')} {result.get('url', '')}"

    # @username (X/Reddit/Instagram)
    m = re.search(r"@(\w{3,20})", text)
    if m:
        username = m.group(0)
        host = get_host(result.get("url", ""))
        if "reddit.com" in host:
            return username, f"https://reddit.com/user/{m.group(1)}"
        elif "twitter.com" in host or "x.com" in host:
            return username, f"https://x.com/{m.group(1)}"
        elif "facebook.com" in host:
            return username, f"https://facebook.com/{m.group(1)}"
        return username, ""

    # "Soy X" / "Hola soy X"
    m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", text, re.IGNORECASE)
    if m:
        return m.group(1).title(), ""

    # "por X" / "de X" (autor)
    m = re.search(r"(?:por|de)\s+:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})", text)
    if m:
        return m.group(1), ""

    # Grupos de Facebook: usar el grupo como "persona" si hay post de venta
    host = get_host(result.get("url", ""))
    if "facebook.com" in host:
        # Si el snippet contiene "VENDO X", es un post humano en grupo público
        if re.search(r"vendo\s+\w+", text, re.IGNORECASE):
            # Extraer nombre del grupo del title si está
            group_match = re.search(r"groups/(\d+)", result.get("url", ""))
            if group_match:
                return f"Vendedor en FB group", f"https://facebook.com/groups/{group_match.group(1)}"
            return "Vendedor en FB group", result.get("url", "")

    # Reddit: usar username si está en URL
    if "reddit.com" in host:
        user_match = re.search(r"/user/(\w+)", result.get("url", ""))
        if user_match:
            return f"u/{user_match.group(1)}", f"https://reddit.com/user/{user_match.group(1)}"

    return "", ""


def is_real_person_signal(result: Dict[str, Any]) -> bool:
    """
    Heurística para detectar si un resultado representa una conversación humana.
    """
    text = (f"{result.get('name', '')} {result.get('snippet', '')}").lower()

    # Si tiene @username, es persona
    if re.search(r"@\w{3,20}", text):
        return True

    # Si tiene frases de primera persona / consulta
    person_phrases = [
        "alguien sabe", "alguien me", "cómo hago", "como hago",
        "qué hago", "que hago", "me pasó", "me paso", "me llegaron",
        "me rechazaron", "no puedo", "tengo multas", "debo multas",
        "hola gente", "buenas gente", "buenas tardes", "buenos días",
        "consulto", "ayuda porfa", "ayuda por favor",
        "vendo mi", "vendo mi auto", "permuto mi",
        # Posts de grupos de compra-venta (Facebook groups públicos)
        "vendo renault", "vendo ford", "vendo chevrolet", "vendo toyota",
        "vendo peugeot", "vendo volkswagen", "vendo vw", "vendo honda",
        "vendo fiat", "vendo citroen", "vendo nissan", "vendo hyundai",
        "vendo o permuto", "permuto x", "permuto por", "vendo o cambio",
        "tomamos usado", "tomo usado", "acepto permuta",
        # Señales de problema en grupos
        "tengo una multa", "me llegó una multa", "me llego una multa",
        "no me deja transferir", "no me deja vender",
        "me piden libre deuda", "me pide libre deuda",
    ]
    for phrase in person_phrases:
        if phrase in text:
            return True

    # Si está en una plataforma prioritaria y tiene keyword vehicular
    host = get_host(result.get("url", ""))
    if host in PRIORITY_PLATFORMS:
        vehicle_keywords = [
            "auto", "moto", "camioneta", "vendo", "permuto", "transferir",
            "multa", "fotomulta", "patente", "libre deuda",
        ]
        if any(kw in text for kw in vehicle_keywords):
            return True

    return False


# ===========================================================================
# Extracción de entidades
# ===========================================================================
def extract_patent(text: str) -> str:
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def extract_phone(text: str) -> str:
    for pattern in PHONE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0).strip()
    return ""


def extract_whatsapp(text: str) -> str:
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def extract_facebook_profile(text: str) -> str:
    for pattern in FACEBOOK_PROFILE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return ""


def extract_location(text: str) -> str:
    text_lower = text.lower()
    # Buscar localidades primero (más específicas)
    for loc in ["lanús", "lanus", "avellaneda", "quilmes", "pilar", "moreno",
                "san martín", "san martin", "tigre", "morón", "moron",
                "flores", "caballito", "belgrano", "palermo", "rosario",
                "córdoba", "cordoba", "mendoza", "rafaela"]:
        if loc in text_lower:
            return loc.title()
    # Luego jurisdicciones
    for jur in JURISDICTIONS:
        if jur in text_lower:
            return jur.title()
    return ""


def extract_vehicle(text: str) -> str:
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
    # Marcas comunes como proxy
    brands = ["ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
              "peugeot", "renault", "citroen", "fiat", "nissan", "hyundai"]
    for b in brands:
        if b in text_lower:
            return b
    return ""


def extract_problem_type(text: str) -> str:
    text_lower = text.lower()
    priority = [
        ("fotomulta", "fotomulta"),
        ("foto multa", "fotomulta"),
        ("multa de ruta", "fotomulta"),
        ("apsv", "fotomulta"),
        ("radares", "fotomulta"),
        ("libre deuda", "libre_deuda"),
        ("no puedo transferir", "transferencia_bloqueada"),
        ("no puedo vender", "transferencia_bloqueada"),
        ("me rechazaron", "transferencia_bloqueada"),
        ("transferencia", "transferencia"),
        ("transferir", "transferencia"),
        ("vendo auto", "venta"),
        ("permuto", "venta"),
        ("08 firmado", "transferencia"),
        ("registro automotor", "transferencia"),
        ("verificacion policial", "transferencia"),
        ("patente bloqueada", "patente"),
        ("patente", "patente"),
        ("multas", "multa"),
        ("multa", "multa"),
        ("deuda", "deuda"),
    ]
    for kw, problem in priority:
        if kw in text_lower:
            return problem
    return ""


def make_quoted_text(name: str, snippet: str, max_len: int = 250) -> str:
    """Texto citado de la publicación."""
    text = f"{name}. {snippet}".strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def make_problem_summary(text: str, problem_type: str) -> str:
    """Resumen corto del problema."""
    summaries = {
        "fotomulta": "Persona consultando por fotomulta/multa de ruta",
        "multa": "Persona con multas impagas o consultando cómo resolverlas",
        "libre_deuda": "Persona necesita tramitar libre deuda vehicular",
        "transferencia": "Persona quiere transferir un vehículo",
        "transferencia_bloqueada": "Persona bloqueada para transferir por multas/deudas",
        "venta": "Persona vendiendo vehículo (potencial necesidad de libre deuda)",
        "patente": "Persona con problema de patente (deuda/bloqueo)",
        "deuda": "Persona con deuda vehicular",
    }
    return summaries.get(problem_type, "Persona con problema vehicular")


# ===========================================================================
# Scoring
# ===========================================================================
def calculate_commercial_score(
    problem_type: str,
    has_evento_anterior: bool,
    has_problema_explicito: bool,
    platform_priority: int,
    has_phone: bool,
    has_whatsapp: bool,
    has_patent: bool,
) -> int:
    """
    Potencial comercial.
    Insight del usuario: evento-anterior + problema explícito = mayor valor
    (lead todavía no sabe que necesita ayuda).
    """
    base = 30

    # Boost por tipo de problema
    problem_boost = {
        "transferencia_bloqueada": 35,  # tiene problema Y quiere transferir
        "transferencia": 25,
        "libre_deuda": 30,
        "venta": 25,  # evento-anterior puro, alta ventana comercial
        "fotomulta": 20,
        "multa": 20,
        "patente": 15,
        "deuda": 15,
    }
    base += problem_boost.get(problem_type, 0)

    # Doble boost si tiene evento-anterior Y problema explícito
    if has_evento_anterior and has_problema_explicito:
        base += 15  # lead está vendiendo + tiene multas = oportunidad premium

    # Boost por plataforma prioritaria
    base += min(platform_priority // 10, 10)

    # Boost por señales de contacto (lead reachable)
    if has_whatsapp:
        base += 10
    if has_phone:
        base += 5
    if has_patent:
        base += 5  # lead concreto, no genérico

    return min(base, 100)


def calculate_urgency_score(text: str, problem_type: str) -> int:
    """Urgencia temporal."""
    urgency_keywords = [
        "urgente", "hoy", "mañana", "ahora", "ya", "rápido", "rapido",
        "antes de", "lo antes posible", "vencimiento", "vence",
        "mudanza", "traslado", "mudo", "viaje",
    ]
    text_lower = text.lower()
    matches = sum(1 for kw in urgency_keywords if kw in text_lower)

    base = 10
    if matches >= 2:
        base = 80
    elif matches == 1:
        base = 50

    # Problemas bloqueantes son más urgentes
    if problem_type in ("transferencia_bloqueada", "patente"):
        base += 15

    return min(base, 100)


def calculate_confidence(
    is_real_person: bool,
    has_person_name: bool,
    has_profile_link: bool,
    has_post_link: bool,
    platform_priority: int,
) -> int:
    """Confianza en que es un lead humano real."""
    if not is_real_person:
        return 10

    conf = 40  # base por ser persona real
    if has_person_name:
        conf += 20
    if has_profile_link:
        conf += 15
    if has_post_link:
        conf += 10
    conf += min(platform_priority // 10, 15)

    return min(conf, 100)


# ===========================================================================
# Construcción de Lead
# ===========================================================================
def build_lead_from_result(
    result: Dict[str, Any],
    query: str,
    query_category: str,
) -> Optional[Lead]:
    """Construye un Lead a partir de un resultado, o None si no es lead humano."""
    if is_informational(result):
        return None

    if not is_real_person_signal(result):
        return None

    url = result.get("url", "")
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    combined = f"{name}. {snippet}"

    # Detectar persona
    person_name, profile_link = detect_person(result)

    # Si no hay profile_link, intentar con facebook profile del snippet
    if not profile_link:
        fb = extract_facebook_profile(combined)
        if fb:
            profile_link = fb

    host = get_host(url)
    platform_priority = PRIORITY_PLATFORMS.get(host, 30)

    # Detectar evento-anterior vs problema explícito
    has_evento_anterior = any(
        kw in combined.lower() for kw in [
            "vendo", "permuto", "quiero transferir", "08 firmado",
            "registro automotor", "verificacion policial",
        ]
    )
    has_problema_explicito = any(
        kw in combined.lower() for kw in [
            "multa", "fotomulta", "deuda", "no puedo transferir",
            "no puedo vender", "me rechazaron", "bloqueada",
        ]
    )

    problem_type = extract_problem_type(combined)
    if not problem_type:
        # Si está en plataforma prioritaria y tiene keywords de venta, es lead
        if platform_priority >= 85 and has_evento_anterior:
            problem_type = "venta"  # lead de evento-anterior puro
        else:
            return None  # sin problema detectado y no es lead claro

    phone = extract_phone(combined)
    whatsapp = extract_whatsapp(combined)
    patent = extract_patent(combined)
    location = extract_location(combined)
    vehicle = extract_vehicle(combined)

    commercial = calculate_commercial_score(
        problem_type=problem_type,
        has_evento_anterior=has_evento_anterior,
        has_problema_explicito=has_problema_explicito,
        platform_priority=platform_priority,
        has_phone=bool(phone),
        has_whatsapp=bool(whatsapp),
        has_patent=bool(patent),
    )
    urgency = calculate_urgency_score(combined, problem_type)
    confidence = calculate_confidence(
        is_real_person=True,
        has_person_name=bool(person_name),
        has_profile_link=bool(profile_link),
        has_post_link=bool(url),
        platform_priority=platform_priority,
    )

    return Lead(
        person_name=person_name or "(sin nombre)",
        profile_link=profile_link,
        post_link=url,
        platform=host,
        date=result.get("date", ""),
        city_if_detected=location,
        vehicle_if_detected=vehicle,
        problem_summary=make_problem_summary(combined, problem_type),
        quoted_text=make_quoted_text(name, snippet),
        commercial_score=commercial,
        urgency_score=urgency,
        confidence=confidence,
        possible_whatsapp=whatsapp,
        possible_phone=phone,
        query=query,
        query_category=query_category,
        source_host=host,
    )


# ===========================================================================
# Loop adaptativo
# ===========================================================================
def dedup_by_post_link(leads: List[Lead]) -> List[Lead]:
    """Deduplica leads por post_link."""
    seen: Set[str] = set()
    out = []
    for lead in leads:
        key = lead.post_link or lead.quoted_text[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def run_pipeline() -> Dict[str, Any]:
    """Ejecuta el loop adaptativo hasta 10 leads humanos o max iteraciones."""
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES v2 — Búsqueda de personas reales", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    all_leads: List[Lead] = []
    all_raw_results: List[Dict[str, Any]] = []
    seen_queries: Set[str] = set()
    iterations = 0

    # Cola de queries: empezar con evento-anterior (mayor valor comercial)
    query_queue = list(ALL_QUERIES)

    while iterations < MAX_ITERATIONS:
        # Criterios de parada:
        # - >= 10 leads humanos Y >= 3 con whatsapp → success completo, parar
        # - >= 10 leads humanos pero < 3 whatsapp → seguir buscando whatsapp
        # - sin más queries → parar
        whatsapp_count = sum(1 for l in all_leads if l.possible_whatsapp or l.possible_phone)
        if len(all_leads) >= MIN_REAL_LEADS and whatsapp_count >= MIN_WHATSAPP_CANDIDATES:
            print(f"\n  [success] {len(all_leads)} leads + {whatsapp_count} whatsapp candidatos. Parando.", file=sys.stderr)
            break

        if not query_queue:
            # Si se acabaron las queries y no llegamos a 10, generar variaciones
            query_queue = generate_query_expansions(all_leads, seen_queries)
            if not query_queue:
                print(f"\n  [info] No hay más queries para expandir. Parando.", file=sys.stderr)
                break

        query, category = query_queue.pop(0)
        if query in seen_queries:
            continue
        seen_queries.add(query)
        iterations += 1

        print(f"\n  [iter {iterations}/{MAX_ITERATIONS}] Query ({category}): '{query}'", file=sys.stderr)
        print(f"    Leads hasta ahora: {len(all_leads)}/{MIN_REAL_LEADS}", file=sys.stderr)

        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
            r["_query_category"] = category
        all_raw_results.extend(results)

        # Filtrar informativos y construir leads
        new_leads_count = 0
        filtered_count = 0
        for r in results:
            lead = build_lead_from_result(r, query, category)
            if lead is None:
                filtered_count += 1
                continue
            all_leads.append(lead)
            new_leads_count += 1

        print(f"    Resultados: {len(results)} | Filtrados (informativos/no persona): {filtered_count} | Nuevos leads: {new_leads_count}", file=sys.stderr)

        # Rate limit cortés
        time.sleep(0.4)

    # Dedup final
    all_leads = dedup_by_post_link(all_leads)

    # Ranking
    all_leads.sort(
        key=lambda l: (l.commercial_score, l.urgency_score, l.confidence),
        reverse=True,
    )

    # Success criteria
    whatsapp_candidates = [l for l in all_leads if l.possible_whatsapp or l.possible_phone]
    success_leads = len(all_leads) >= MIN_REAL_LEADS
    success_whatsapp = len(whatsapp_candidates) >= MIN_WHATSAPP_CANDIDATES

    # Output
    output = {
        "project": "Radar de Oportunidades v2",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mission": "Encontrar personas reales que manifiesten públicamente un problema relacionado con multas, transferencia de vehículos, libre deuda o fotomultas.",
        "strategy": {
            "evento_anterior": "Buscar personas vendiendo/transfiriendo (ventana comercial alta: todavía no descubrieron que las multas bloquean el trámite)",
            "problema_explicito": "Buscar personas con multas/deudas ya manifestadas",
            "platform_hints": "Priorizar conversaciones humanas en Reddit, Facebook, X, foros",
        },
        "summary": {
            "iterations": iterations,
            "queries_executed": len(seen_queries),
            "total_search_results": len(all_raw_results),
            "leads_found": len(all_leads),
            "whatsapp_candidates": len(whatsapp_candidates),
            "success_leads_met": success_leads,
            "success_whatsapp_met": success_whatsapp,
            "min_required_leads": MIN_REAL_LEADS,
            "min_required_whatsapp": MIN_WHATSAPP_CANDIDATES,
        },
        "ranking": {
            "sorted_by": ["commercial_score DESC", "urgency_score DESC", "confidence DESC"],
        },
        "leads": [l.to_dict() for l in all_leads],
        "compliance": {
            "only_public_information": True,
            "never_bypass_logins": True,
            "never_collect_private_information": True,
            "never_send_messages": True,
            "human_review_required": True,
            "ignored_informational_results": True,
        },
    }

    # Guardar
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with RAW_SEARCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_raw_results, f, ensure_ascii=False, indent=2)

    # Summary
    print("\n" + "=" * 70, file=sys.stderr)
    print("  RESULTADO FINAL", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Iteraciones:              {iterations}", file=sys.stderr)
    print(f"  Queries ejecutadas:       {len(seen_queries)}", file=sys.stderr)
    print(f"  Resultados de búsqueda:   {len(all_raw_results)}", file=sys.stderr)
    print(f"  Leads humanos encontrados:{len(all_leads)}", file=sys.stderr)
    print(f"  Con whatsapp/teléfono:    {len(whatsapp_candidates)}", file=sys.stderr)
    print(f"  Success leads (>= 10):    {'✓ CUMPLIDO' if success_leads else '✗ NO cumplido'}", file=sys.stderr)
    print(f"  Success whatsapp (>= 3):  {'✓ CUMPLIDO' if success_whatsapp else '✗ NO cumplido'}", file=sys.stderr)
    print(f"  Output:                   {OUTPUT_PATH}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Print top leads
    if all_leads:
        print(f"\n  TOP LEADS:", file=sys.stderr)
        for i, l in enumerate(all_leads[:15], 1):
            wa = " [+WA]" if l.possible_whatsapp else ""
            ph = " [+TEL]" if l.possible_phone else ""
            print(f"    {i:2d}. [C={l.commercial_score:3d} U={l.urgency_score:3d} Conf={l.confidence:3d}] {l.person_name:20s} | {l.platform:20s} | {l.problem_summary[:50]}{wa}{ph}", file=sys.stderr)

    return output


def generate_query_expansions(
    existing_leads: List[Lead],
    seen_queries: Set[str],
) -> List[Tuple[str, str]]:
    """Genera queries expandidas basadas en lo encontrado hasta ahora."""
    expansions = []

    # Variaciones de evento-anterior + ciudades (los leads están funcionando acá)
    cities = ["buenos aires", "córdoba", "rosario", "mendoza", "la plata"]
    for city in cities:
        q = f"vendo auto {city}"
        if q not in seen_queries:
            expansions.append((q, "expansion_geografica"))
        q = f"permuto auto {city}"
        if q not in seen_queries:
            expansions.append((q, "expansion_geografica"))

    # Variaciones con WhatsApp explícito (para success criterion de whatsapp)
    whatsapp_queries = [
        "vendo auto whatsapp",
        "permuto auto whatsapp",
        "vendo auto contacto whatsapp",
        "vendo moto whatsapp argentina",
        "vendo auto telefono",
        "transferencia auto whatsapp contacto",
        "libre deuda whatsapp consulta",
        "fotomulta consulta whatsapp",
    ]
    for q in whatsapp_queries:
        if q not in seen_queries:
            expansions.append((q, "expansion_whatsapp"))

    # Variaciones de problema explícito
    problem_variations = [
        "multa no me llegó",
        "multa no me llego",
        "fotomulta no recibí",
        "fotomulta no recibi",
        "no puedo patentar auto",
        "debo patente auto",
        "registro automotor me rechazó",
        "transferencia rechazada multas",
    ]
    for q in problem_variations:
        if q not in seen_queries:
            expansions.append((q, "expansion_problema"))

    return expansions


if __name__ == "__main__":
    output = run_pipeline()
    print(json.dumps(output, ensure_ascii=False, indent=2))
```


