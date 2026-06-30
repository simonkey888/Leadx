"""
extractor.py — Extracción de entidades, normalización y privacy filter.

Pipeline de extracción:
  raw_text → privacy_filter → regex_extractor → normalize → Case (parcial)

El extractor usa reglas (regex + keyword matching) en Fase 1. El LLM extractor
se documenta como stub para Fase 2 (ver LLMExtractor al final).

Privacy filter: rechaza señales que contengan PII explícita (DNI, CUIT/CUIL,
email, teléfono, dirección) o marcadas como privadas. Las señales rechazadas
se loguean en audit trail pero no generan caso.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from models import Signal, Case, AR_TZ, now_iso, short_id
import config


# ---------------------------------------------------------------------------
# Privacy filter
# ---------------------------------------------------------------------------
@dataclass
class PrivacyFilterResult:
    passed: bool
    reason: str = ""
    matched_patterns: List[str] = field(default_factory=list)
    masked_text: str = ""


def privacy_filter(signal: Signal) -> PrivacyFilterResult:
    """
    Aplica filtro de privacidad a una señal.

    Rechaza si:
    - Contiene DNI, CUIT/CUIL, email, teléfono o dirección explícita
    - La fuente es marcada como privada en raw_metadata
    """
    text = signal.raw_text
    matched: List[str] = []

    for pattern in config.PII_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append(pattern)

    # Verificar flag de privacidad en metadata
    if signal.raw_metadata.get("is_private", False):
        return PrivacyFilterResult(
            passed=False,
            reason="metadata marks signal as private",
            matched_patterns=matched,
        )

    if matched:
        return PrivacyFilterResult(
            passed=False,
            reason=f"PII detected: {len(matched)} pattern(s)",
            matched_patterns=matched,
        )

    # Masking opcional (no se aplica en Fase 1: rechazamos directo)
    return PrivacyFilterResult(passed=True, masked_text=text)


# ---------------------------------------------------------------------------
# Extracción regex
# ---------------------------------------------------------------------------
def _extract_patent(text: str) -> str:
    """Extrae patente argentina (formato nuevo AB123CD o viejo ABC123)."""
    for pattern in config.PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    # Patentes con palabra "patente" seguida de valor
    m = re.search(r"patente\s+([A-Z]{2,3}\s?\d{3}\s?[A-Z]{0,2})", text, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def _extract_amount(text: str) -> Optional[float]:
    """Extrae monto en pesos argentinos."""
    # $18.500 / $4.500.000 / 18500 pesos / $45.000
    patterns = [
        r"\$\s?(\d{1,3}(?:[.,]\d{3})+)",
        r"\$\s?(\d+(?:[.,]\d{3})*)",
        r"(\d{1,3}(?:[.,]\d{3})+)\s?pesos",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _extract_year(text: str) -> Optional[int]:
    """Extrae año entre 1990 y año actual+1."""
    import datetime
    current_year = datetime.datetime.now().year
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    for y in matches:
        year = int(y)
        if 1990 <= year <= current_year + 1:
            return year
    return None


def _map_value(text: str, mapping: Dict[str, str]) -> str:
    """Mapea texto a valor canónico usando un diccionario de alias."""
    text_lower = text.lower()
    for alias, canonical in mapping.items():
        if alias in text_lower:
            return canonical
    return ""


def _extract_jurisdiction(text: str, hint: str = "") -> str:
    """Extrae jurisdicción: usa hint de metadata si está, sino regex."""
    if hint:
        # Hint ya viene como código canónico
        return hint
    text_lower = text.lower()
    for alias, canonical in config.JURISDICTION_MAP.items():
        if alias in text_lower:
            return canonical
    return ""


def _extract_locality(text: str, hint: str = "") -> str:
    """Extrae localidad. En Fase 1 usa el hint de metadata o heuristicas simples."""
    if hint:
        return hint
    # Heurística: "estoy en X", "zona X", "vivo en X"
    patterns = [
        r"(?:estoy en|zona|vivo en|de)\s+([A-ZÁÉÍÓÚa-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚa-záéíóúñ]+)?)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            loc = m.group(1).strip().title()
            # Filtrar falsos positivos comunes
            if loc.lower() not in {"el", "la", "los", "las", "mi", "tu", "su"}:
                return loc
    return ""


def _extract_problem_type(text: str, hint: str = "") -> str:
    """Extrae tipo de problema."""
    if hint:
        return hint
    text_lower = text.lower()
    # Orden de prioridad: problemas específicos antes que genéricos
    priority_order = [
        "fotomulta", "foto multa", "multa de ruta", "apsv",
        "libre deuda", "transferencia", "transferir",
        "regularización vehicular", "regularizacion", "regularización",
        "patente", "vtv", "multas", "multa",
    ]
    for kw in priority_order:
        if kw in text_lower:
            return config.PROBLEM_TYPE_MAP.get(kw, kw)
    return ""


def _extract_vehicle_type(text: str) -> str:
    """Extrae tipo de vehículo."""
    return _map_value(text, config.VEHICLE_TYPE_MAP)


# ---------------------------------------------------------------------------
# Normalización de texto para dedup
# ---------------------------------------------------------------------------
def normalize_text_for_hash(text: str) -> str:
    """
    Normaliza texto para hashing en dedup:
    - lowercase
    - sin acentos
    - sin puntuación
    - sin whitespace múltiple
    - sin URLs/menciones/hashtags
    """
    import unicodedata
    # Quitar URLs, menciones, hashtags
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"@\w+", " ", t)
    t = re.sub(r"#\w+", " ", t)
    # Lowercase
    t = t.lower()
    # Sin acentos
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    # Sin puntuación
    t = re.sub(r"[^\w\s]", " ", t)
    # Sin whitespace múltiple
    t = re.sub(r"\s+", " ", t).strip()
    return t


def text_hash(text: str) -> str:
    """SHA-256 del texto normalizado (para dedup)."""
    return hashlib.sha256(normalize_text_for_hash(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LLM extractor (stub para Fase 2)
# ---------------------------------------------------------------------------
class LLMExtractor:
    """
    Stub de extractor LLM para Fase 2.

    En Fase 1 usamos extractor regex (más simple, determinista, sin costo API).
    En Fase 2 se puede reemplazar por una llamada a un LLM (GLM-4, GPT-4, etc.)
    que tome el raw_text y devuelva JSON con los campos de ENTITY_FIELDS.

    Ventajas del LLM:
    - Mejor extracción de contexto implícito
    - Mejor manejo de ambigüedad
    - Mejor normalización de jerga local

    Desventajas:
    - Costo por llamada
    - Latencia
    - No determinista (usar temperature=0 + cache)
    - Riesgo de alucinación (siempre validar con regex post-extracción)

    Firma esperada (Fase 2):
        def extract(self, signal: Signal) -> Dict[str, Any]:
            prompt = f"Extraer entidades del texto: {signal.raw_text}"
            response = llm.chat(prompt, schema=ENTITY_FIELDS)
            return response
    """

    def extract(self, signal: Signal) -> Dict[str, Any]:
        raise NotImplementedError(
            "LLMExtractor requiere API key. Usar extract_with_regex() en Fase 1."
        )


# ---------------------------------------------------------------------------
# Extractor principal (Fase 1: regex)
# ---------------------------------------------------------------------------
def extract_with_regex(signal: Signal) -> Dict[str, Any]:
    """
    Extrae entidades de una señal usando regex + keyword matching.

    Returns:
        Dict con campos de ENTITY_FIELDS normalizados.
    """
    text = signal.raw_text
    meta = signal.raw_metadata

    extracted = {
        "name_or_alias": signal.author_alias,
        "profile_url": signal.profile_url,
        "vehicle_type": _extract_vehicle_type(text),
        "patent": _extract_patent(text),
        "jurisdiction": _extract_jurisdiction(text, meta.get("jurisdiction_hint", "")),
        "locality": _extract_locality(text, meta.get("locality_hint", "")),
        "problem_type": _extract_problem_type(text, meta.get("problem_hint", "")),
        "year": _extract_year(text),
        "amount": _extract_amount(text) or meta.get("amount_hint"),
        "source_name": signal.source_id,
        "source_url": signal.source_url,
        "timestamp": meta.get("published_at", signal.detected_at),
        "evidence_text": text,
    }
    return extracted


def signal_to_case(signal: Signal) -> Tuple[Optional[Case], str]:
    """
    Pipeline completo de extracción sobre una señal.

    Returns:
        (Case, status) donde status es 'extracted' o 'rejected_privacy' o 'no_entity'.
    """
    # 1. Privacy filter
    pf = privacy_filter(signal)
    if not pf.passed:
        return None, f"rejected_privacy:{pf.reason}"

    # 2. Extracción
    extracted = extract_with_regex(signal)

    # 3. Validación mínima: si no hay problem_type ni patent ni jurisdiction, descartar
    if not extracted["problem_type"] and not extracted["patent"] and not extracted["jurisdiction"]:
        return None, "no_entity"

    # 4. Crear Case parcial (scoring y dedup se hacen después)
    case = Case(
        case_id=short_id("case", f"{signal.signal_id}|{extracted['timestamp']}"),
        signal_id=signal.signal_id,
        source_id=signal.source_id,
        source_url=signal.source_url,
        profile_url=signal.profile_url,
        timestamp=extracted["timestamp"],
        name_or_alias=extracted["name_or_alias"],
        vehicle_type=extracted["vehicle_type"],
        patent=extracted["patent"],
        jurisdiction=extracted["jurisdiction"],
        locality=extracted["locality"],
        problem_type=extracted["problem_type"],
        year=extracted["year"],
        amount=extracted["amount"],
        evidence_text=extracted["evidence_text"],
        normalized_text_hash=text_hash(signal.raw_text),
    )
    return case, "extracted"


if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    sigs = generate_mock_signals()
    print(f"Procesando {len(sigs)} señales…")
    extracted = 0
    rejected = 0
    for s in sigs[:5]:
        case, status = signal_to_case(s)
        if case:
            extracted += 1
            print(f"  ✓ [{status}] {case.case_id} | {case.problem_type} | {case.jurisdiction} | {case.patent or '—'} | {case.amount or '—'}")
        else:
            rejected += 1
            print(f"  ✗ [{status}] {s.signal_id}")
    print(f"\nResumen: {extracted} extraídos, {rejected} rechazados")
