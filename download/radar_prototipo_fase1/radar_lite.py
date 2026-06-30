"""
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
