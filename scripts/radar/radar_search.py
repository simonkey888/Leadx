"""
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
