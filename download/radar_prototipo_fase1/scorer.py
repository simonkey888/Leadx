"""
scorer.py — Motor de scoring del Radar de Oportunidades.

Implementa el modelo de scoring 0-100 definido en el spec, con los 7 pesos:
  - explicit_intent: 30  → intención explícita de acción (vender, transferir, regularizar)
  - urgency: 15           → palabras o contexto de urgencia (URGENTE, hoy, antes de…)
  - jurisdiction_fit: 15  → jurisdicción está en TARGET_JURISDICTIONS
  - evidence_quality: 10  → tiene patente + monto + localidad + fuente confiable
  - commercial_potential: 10 → monto relevante o problema de alto valor comercial
  - channel_fit: 10       → fuente de alta prioridad (FB groups, marketplace, foros)
  - signal_repetition: 10 → señal repetida (mismo autor/perfil/contenido)

Cada dimensión se puntúa de 0 a 1, se multiplica por su peso, y la suma da el score final.
Umbrales (del spec):
  - critical: >= 80
  - high:     >= 60
  - medium:   >= 40
  - low:      < 40
"""
from __future__ import annotations
import re
from typing import Dict, Tuple, List
from dataclasses import dataclass

from models import Case
import config


# ---------------------------------------------------------------------------
# Heurísticas por dimensión
# ---------------------------------------------------------------------------
URGENCY_KEYWORDS = [
    "urgente", "hoy", "mañana", "antes de", "lo antes posible",
    "inmediato", "ya", "rápido", "rapido", "ahora",
    "mudanza", "traslado", "mudo", "viaje",
    "vencimiento", "vence",
]

EXPLICIT_INTENT_KEYWORDS = [
    # Venta/transferencia
    "vendo", "vender", "venta", "transferir", "transferencia", "traspaso",
    # Regularización
    "regularizar", "regularización", "regularizacion", "necesito arreglar",
    # Libre deuda
    "libre deuda", "necesito libre", "sacar libre",
    # Asesoramiento
    "consulto", "consulta", "asesoramiento", "necesito asesor", "abogado",
    # Defensa/reclamo
    "defender", "defensa", "reclamar", "reclamo", "denuncia", "apelar",
]

COMMERCIAL_PROBLEMS = {
    # Problemas con mayor potencial comercial (servicios que el negocio puede cobrar)
    "transferencia", "regularizacion", "libre_deuda",
}
LOW_COMMERCIAL_PROBLEMS = {
    # Problemas con menor potencial (consulta gratuita, defensa administrativa)
    "fotomulta",  # excepto si hay volumen / repetición
}

HIGH_PRIORITY_SOURCES = {
    "facebook_public_groups", "marketplace_public_posts", "public_forums"
}


def _has_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _count_keywords(text: str, keywords: List[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


# ---------------------------------------------------------------------------
# Dimensiones de scoring (cada una retorna un float 0..1)
# ---------------------------------------------------------------------------
def score_explicit_intent(case: Case, repetition_count: int = 0) -> float:
    """Intención explícita de acción comercial."""
    text = case.evidence_text
    if not text:
        return 0.0
    matches = _count_keywords(text, EXPLICIT_INTENT_KEYWORDS)
    # 0 matches = 0.0, 1 = 0.5, 2+ = 1.0
    if matches == 0:
        return 0.0
    if matches == 1:
        return 0.6
    return 1.0


def score_urgency(case: Case, repetition_count: int = 0) -> float:
    """Urgencia temporal declarada."""
    text = case.evidence_text
    if not text:
        return 0.0
    matches = _count_keywords(text, URGENCY_KEYWORDS)
    if matches == 0:
        return 0.0
    if matches == 1:
        return 0.5
    return 1.0


def score_jurisdiction_fit(case: Case, repetition_count: int = 0) -> float:
    """Jurisdicción objetivo comercial."""
    if not case.jurisdiction:
        return 0.0
    if case.jurisdiction in config.TARGET_JURISDICTIONS:
        return 1.0
    return 0.2  # jurisdicción no objetivo pero conocida


def score_evidence_quality(case: Case, repetition_count: int = 0) -> float:
    """Calidad de la evidencia: patente + monto + localidad + año."""
    score = 0.0
    if case.patent:
        score += 0.3
    if case.amount and case.amount > 0:
        score += 0.25
    if case.locality:
        score += 0.2
    if case.year:
        score += 0.15
    if case.vehicle_type:
        score += 0.1
    return min(score, 1.0)


def score_commercial_potential(case: Case, repetition_count: int = 0) -> float:
    """Potencial comercial del problema."""
    if case.problem_type in COMMERCIAL_PROBLEMS:
        # Transferencia / regularización / libre deuda = alto valor
        base = 0.8
        if case.amount and case.amount > 1000000:
            base = 1.0  # monto alto (auto)
        return base
    if case.problem_type in LOW_COMMERCIAL_PROBLEMS:
        # Fotomulta: bajo individualmente, pero si hay repetición sube
        if repetition_count >= 2:
            return 0.7
        return 0.3
    if case.problem_type:
        return 0.4  # otro problema tipificado
    return 0.0


def score_channel_fit(case: Case, repetition_count: int = 0) -> float:
    """Ajuste del canal: fuente de alta prioridad."""
    if case.source_id in HIGH_PRIORITY_SOURCES:
        return 1.0
    # medium priority sources
    return 0.4


def score_signal_repetition(case: Case, repetition_count: int = 0) -> float:
    """Repetición de señal del mismo autor/perfil."""
    if repetition_count == 0:
        return 0.0
    if repetition_count == 1:
        return 0.5
    if repetition_count == 2:
        return 0.8
    return 1.0  # 3+ repeticiones


# ---------------------------------------------------------------------------
# Scoring principal
# ---------------------------------------------------------------------------
SCORING_FNS = {
    "explicit_intent": score_explicit_intent,
    "urgency": score_urgency,
    "jurisdiction_fit": score_jurisdiction_fit,
    "evidence_quality": score_evidence_quality,
    "commercial_potential": score_commercial_potential,
    "channel_fit": score_channel_fit,
    "signal_repetition": score_signal_repetition,
}


def score_case(case: Case, repetition_count: int = 0) -> Tuple[int, str, Dict[str, int]]:
    """
    Puntúa un caso y devuelve (score, band, breakdown).

    Args:
        case: Caso a puntúar
        repetition_count: cantidad de señales previas del mismo perfil/source_url

    Returns:
        score: int 0-100
        band: 'critical' | 'high' | 'medium' | 'low'
        breakdown: dict con puntaje por dimensión (valor 0..weight)
    """
    breakdown: Dict[str, int] = {}
    total = 0
    for dim, weight in config.SCORING_WEIGHTS.items():
        fn = SCORING_FNS[dim]
        raw = fn(case, repetition_count=repetition_count)  # 0..1
        weighted = int(round(raw * weight))
        breakdown[dim] = weighted
        total += weighted

    # Clamp a rango
    lo, hi = config.SCORING_RANGE
    total = max(lo, min(hi, total))

    # Band
    if total >= config.SCORING_THRESHOLDS["critical"]:
        band = "critical"
    elif total >= config.SCORING_THRESHOLDS["high"]:
        band = "high"
    elif total >= config.SCORING_THRESHOLDS["medium"]:
        band = "medium"
    else:
        band = "low"

    return total, band, breakdown


def update_case_score(case: Case, repetition_count: int = 0) -> Case:
    """Aplica scoring al caso in-place y lo devuelve."""
    score, band, breakdown = score_case(case, repetition_count=repetition_count)
    case.score = score
    case.score_band = band
    case.score_breakdown = breakdown
    return case


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    from extractor import signal_to_case

    sigs = generate_mock_signals()
    print(f"Scoring sobre {len(sigs)} señales…\n")
    for s in sigs:
        case, status = signal_to_case(s)
        if not case:
            continue
        update_case_score(case, repetition_count=0)
        print(f"  [{case.score_band:8s}] {case.score:3d} | {case.case_id} | {case.problem_type:15s} | {case.jurisdiction:12s} | {case.patent or '—'}")
        if case.score >= 60:
            print(f"           breakdown: {case.score_breakdown}")
