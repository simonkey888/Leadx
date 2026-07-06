#!/usr/bin/env python3
"""
generate_payload.py — Pipeline que genera dashboard_payload.json + stats.json + history.json.

Arquitectura: static_dashboard + dynamic_json.
El HTML del dashboard NUNCA se regenera. Sólo se actualizan los JSONs.

7 pasos:
  1. collect_public_sources (search_providers web_search)
  2. extract_entities
  3. normalize_records
  4. classify_and_score
  5. deduplicate_cases (sha256 composite)
  6. build_dashboard_payload
  7. publish_artifacts (overwrite latest + append history + update stats)

Uso:
    python generate_payload.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Config
# ===========================================================================

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAYLOAD_PATH = DATA_DIR / "dashboard_payload.json"
STATS_PATH = DATA_DIR / "stats.json"
HISTORY_PATH = DATA_DIR / "history.json"

# Performance
MAX_RUNTIME_SECONDS = 200
RATE_LIMIT_MS = 8000  # 8s entre queries (rotacion evita repetir, menos 429)
MAX_RESULTS_PER_QUERY = 10

# ===========================================================================
# Queries (foco: dolor explícito + evento anterior)
# ===========================================================================

# Rotacion de grupos de queries Reddit (Claude v2 idea):
# Cada run usa solo 1 grupo (3 queries). Rota cada 3h.
# Misma query no se repite hasta 18h -> evita 429.
REDDIT_QUERY_GROUPS = [
    # Grupo 0: intencion "acabo de recibir" - momento optimo de venta
    [
        "site:reddit.com me llego multa no es mi auto",
        "site:reddit.com me cobraron fotomulta argentina",
        "site:reddit.com/r/DerechoGenial consulta multa",
    ],
    # Grupo 1: intencion "no puedo resolver" - bloqueo administrativo
    [
        "site:reddit.com no puedo transferir auto multa argentina",
        "site:reddit.com vendedor no entrego 08",
        "site:reddit.com/r/MotosArg multa patente",
    ],
    # Grupo 2: intencion "ayuda/consulta" - abierto a soluciones
    [
        "site:reddit.com consulta ayuda multa fotomulta argentina",
        "site:reddit.com/r/AskArgentina libre deuda transferencia",
        "site:reddit.com patente bloqueada registro automotor",
    ],
    # Grupo 3: intencion "compre con problema" - descubrimiento post-compra
    [
        "site:reddit.com compre auto multas anteriores dueño",
        "site:reddit.com/r/DerechoGenial fotomulta reclamo",
        "site:reddit.com juez de faltas multa reclamo",
    ],
    # Grupo 4: intencion "vendo con problema" - urgencia vendedor
    [
        "site:reddit.com cedula verde perdida transferir",
        "site:reddit.com vendo auto multas pendientes",
        "site:reddit.com multa vencida prescripcion argentina",
    ],
    # Grupo 5: intencion "gestor/abogado" - ya busca profesional (competencia directa)
    [
        "site:reddit.com abogado gestor multa fotomulta argentina",
        "site:reddit.com/r/Cordoba multa transito",
        "site:reddit.com/r/BuenosAires infraccion peaje",
    ],
]

# El grupo activo se elige por timestamp (rota cada run)
import time as _time_mod
_CURRENT_GROUP_IDX = int((_time_mod.time() / 10800) % len(REDDIT_QUERY_GROUPS))  # 10800s = 3h

QUERIES = REDDIT_QUERY_GROUPS[_CURRENT_GROUP_IDX]
print(f"[pipeline] Usando query group {_CURRENT_GROUP_IDX}/{len(REDDIT_QUERY_GROUPS)-1}: {QUERIES}", file=sys.stderr)

# ===========================================================================
# Step 4: Scoring (exacto del spec)
# ===========================================================================

SCORE_RULES = {
    "multa_or_fotomulta": 60,
    "transfer_problem": 45,
    "libre_deuda_problem": 35,
    "08_or_document_problem": 40,
    "public_contact_visible": 25,
    "recent_0_3_days": 20,
    "recent_4_7_days": 10,
    "argentina_signal": 15,
    "institutional_penalty": -40,
    "generic_penalty": -30,
    "foreign_country_penalty": -80,
    "dm_hint": 60,  # KIMI+DEEPSEEK: "mandame privado" = oro
    "urgency_hint": 30,  # "urgente", "ayuda"
}

# Patrones de "contactame por privado" (DM hints) - KIMI+DEEPSEEK idea
DM_HINT_PATTERNS = [
    r"\b(?:mandame|escribime|pasame|enviame|contactame|llamame|hablame)\s+(?:un\s+)?(?:md|dm|mp|privado|mensaje|wa|whatsapp)\b",
    r"\b(?:mandame|escribime|pasame)\s+(?:tu|el|un)\s+(?:whatsapp|wa|wpp|número|numero|cel|tel)",
    r"\b(?:md|dm|mp)\s+(?:para|y)\s+(?:te|lo)\s+(?:paso|mandamos|ayudamos)",
    r"\b(?:whatsapp|wa|wpp)\s+(?:y|para)\s+(?:te|lo)\s+(?:ayudamos|asesoramos|respondemos)",
    r"\bcontactame\s+por\s+(?:privado|mensaje)\b",
    r"\b(?:te|me)\s+(?:dejo|dejas|pasas)\s+(?:mi|tu)\s+(?:whatsapp|wa|cel)\b",
]

URGENCY_HINT_PATTERNS = [
    r"\burgente\b", r"\bayuda\b", r"\bvencimiento\b",
    r"\bmañana\s+vence\b", r"\bhoy\s+último\s+día\b",
]

# Regex AR quirúrgico (CHEVRON+QWEN+PERPLEXITY consensus)
# Captura: 11-1234-5678, +54 9 11 1234 5678, 0342-456-7890, 15-XXXX-XXXX
AR_PHONE_REGEX_QUIRURGICO = re.compile(
    r"(?:(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}"
    r"|\b15[-\s]?\d{4}[-\s]?\d{4}\b"
    r"|\b0?(?:11|2\d{2}|3\d{2})[-\s]?\d{3,4}[-\s]?\d{4}\b)"
)

# WhatsApp patterns específicos (más amplios)
WHATSAPP_HINT_REGEX = re.compile(
    r"(?:wa\.me/(\d{8,15})"
    r"|whatsapp[:\s]+(\+?\d[\d\s\-]{8,15})"
    r"|(?:wp|wpp|wsp|wapp)[:\s]+(\+?\d[\d\s\-]{8,15})"
    r"|(?:celular|cel|contacto|telefono|teléfono)[:\s]+(\+?\d[\d\s\-]{8,15}))",
    re.IGNORECASE
)

# ===========================================================================
# Filtros
# ===========================================================================

MUST_INCLUDE_ONE = ["auto", "transferencia", "vehiculo", "vehículo", "multa", "patente",
                    "moto", "camioneta", "libre deuda", "08"]

REJECT_IF_CONTAINS = [
    "publicado por", "leer más", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso",
    "trámite online", "turno web",
    "wikipedia", "enciclopedia",
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "criptomoneda",
]

INSTITUTIONAL_DOMAINS = {
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    ".gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com",
    "es.wikipedia.org", "en.wikipedia.org",
    "youtube.com", "instagram.com", "tiktok.com",
    "elcerokm.com", "servidos.ar", "alarfin.com.ar",
    "autofact.cl", "autofact.com.ar", "kavak.com",
    "comparaencasa.com", "tuquejasuma.com",
}

GENERIC_DOMAINS = {
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "listado.mercadolibre.com.ar", "auto.mercadolibre.com.ar",
    "autocosmos.com.ar", "demotores.com.ar",
}

FOREIGN_INDICATORS = {
    "México": ["cdmx", "guadalajara", "monterrey", "+52", "méxico", "mexico"],
    "Colombia": ["bogotá", "bogota", "medellín", "+57", "colombia"],
    "Uruguay": ["montevideo", "+598", "uruguay"],
    "Chile": ["santiago de chile", "+56", " chile "],
    "Brasil": ["são paulo", "sao paulo", "+55", "brasil", "brazil"],
    "Italia": ["pisa", "roma", "milano", "italia"],
    "España": ["madrid", "barcelona", "españa", "espana"],
    "EEUU": ["miami", "new york", "california", "estados unidos"],
}

ARGENTINA_SIGNALS = [
    "DNRPA", "patente argentina", "Buenos Aires", "CABA",
    "Santa Fe", "Córdoba", "Mendoza", "Rosario", "La Plata",
    "ARBA", "Rentas", "PBA", "GBA", "argentina",
    "Entre Ríos", "Neuquén", "Salta", "Paraná",
]

# Phone patterns
# MEJORA 1 (Qwen): Regex FEDERAL - cubre TODO el pais
# CABA (11), Rosario (341), Cordoba (351), Mendoza (261),
# La Plata (221), Tucuman (381), Neuquen (299), Santa Fe (342/343)
ARG_PHONE_PATTERNS = [
    r"\+54\s?9?\s?(?:11|341|342|343|351|261|221|381|299)\s?\d{4}[\s\-]?\d{4}",
    r"\b(?:11|341|342|343|351|261|221|381|299)\s?[\s\-]?\d{4}[\s\-]?\d{4}\b",
    r"\b15\s?\d{4}\s?\d{4}\b",
    r"\b0?(?:11|341|342|343|351|261|221|381|299)[\s\-]?\d{3,4}[\s\-]?\d{4}\b",
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9]|22[0-9]|29[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

WHATSAPP_PATTERNS = [
    r"wa\.me/(\d{8,15})",
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    # Formatos argentinos comunes
    r"\b(\+54\s?9?\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})",
    r"\b(11\s?\d{4}[\s\-]?\d{4})",  # CABA mobile
    r"\b(15\s?\d{4}[\s\-]?\d{4})",  # old mobile format
    r"(?:contacto|celular|tel|fono|telefono)\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    # Pattern generico para "11-1234-5678"
    r"\b(\d{2}[\s\-]?\d{4}[\s\-]?\d{4})\b",
]

# Email pattern
EMAIL_PATTERN = r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"

# Reddit username pattern (u/username)
REDDIT_USERNAME_PATTERN = r"\bu/([A-Za-z0-9_\-]{3,20})\b"

PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

VEHICLE_KEYWORDS = [
    "auto", "moto", "camioneta", "camion", "utilitario",
    "ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
    "peugeot", "renault", "citroen", "fiat", "nissan",
]

PROVINCE_MAP = {
    "buenos aires": "Buenos Aires", "pba": "Buenos Aires", "gba": "Buenos Aires",
    "caba": "CABA", "capital federal": "CABA", "capital": "CABA",
    "santa fe": "Santa Fe", "rosario": "Santa Fe",
    "córdoba": "Córdoba", "cordoba": "Córdoba",
    "mendoza": "Mendoza",
    "entre ríos": "Entre Ríos", "entre rios": "Entre Ríos", "paraná": "Entre Ríos", "parana": "Entre Ríos",
    "neuquén": "Neuquén", "neuquen": "Neuquén",
    "salta": "Salta",
    "la pampa": "La Pampa",
    "río negro": "Río Negro", "rio negro": "Río Negro",
}

CITY_MAP = {
    "la plata": "La Plata", "lanús": "Lanús", "lanus": "Lanús",
    "avellaneda": "Avellaneda", "quilmes": "Quilmes",
    "pilar": "Pilar", "tigre": "Tigre", "morón": "Morón", "moron": "Morón",
    "rosario": "Rosario", "rafaela": "Rafaela",
    "córdoba": "Córdoba", "cordoba": "Córdoba",
    "mendoza": "Mendoza", "paraná": "Paraná", "parana": "Paraná",
    "neuquén": "Neuquén", "neuquen": "Neuquén",
    "salta": "Salta",
}

PLATFORM_MAP = {
    "facebook.com": "Facebook", "m.facebook.com": "Facebook",
    "reddit.com": "Reddit", "www.reddit.com": "Reddit",
    "twitter.com": "X", "x.com": "X",
    "mercadolibre.com.ar": "MercadoLibre",
    "listado.mercadolibre.com.ar": "MercadoLibre",
    "auto.mercadolibre.com.ar": "MercadoLibre",
}


# ===========================================================================
# Dataclass
# ===========================================================================
@dataclass
class Lead:
    id: str = ""
    score: int = 0
    label: str = ""  # real_lead | commercial_signal | reject
    problem_category: str = ""
    problem_summary: str = ""
    persona: str = ""
    provincia: str = ""
    ciudad: str = ""
    pais: str = ""
    vehiculo: str = ""
    patente: str = ""
    fecha_visible: str = ""
    fecha_iso: str = ""
    platform: str = ""
    source_url: str = ""
    quoted_text: str = ""
    contacto_publico: bool = False
    whatsapp_publico: str = ""
    whatsapp_link: str = ""
    telefono_publico: str = ""
    telefono_e164: str = ""
    email_publico: str = ""
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    detected_signals: List[str] = field(default_factory=list)
    discovery_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# search_providers web_search
# ===========================================================================
# Import search providers (DuckDuckGo + Reddit + RSS, sin search_providers)
from search_providers import search as provider_search
from source_registry import run_discovery_and_update, get_approved_sources
from pending_queries_kv import PendingQueryManager
from search_providers import search_reddit_with_status, search_foroargentina
from search_providers import enrich_reddit_post


def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Wrapper que usa search_providers en vez de search_providers CLI."""
    try:
        results = provider_search(query, num=num)
        adapted = []
        for r in results:
            adapted.append({
                "name": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "date": r.get("date", ""),
                "host_name": r.get("url", ""),
                "username": r.get("username", "") or r.get("author", ""),
                "author": r.get("author", "") or r.get("username", ""),
            })
        return adapted
    except Exception as e:
        print(f"  [search error] {e}", file=sys.stderr)
        return []


# ===========================================================================
# Helpers
# ===========================================================================
def get_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    t = text.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def canonicalize_url(url: str) -> str:
    # Quitar tracking params, normalizar https
    try:
        parsed = urlparse(url)
        # Quitar query params except paths
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return url


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%b %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str[:25], fmt)
        except ValueError:
            continue
    return None


def phone_to_e164(phone: str) -> str:
    """Normaliza telefono a formato +54XXXXXXXXXX (Claude version mejorada).
    Cubre: +54 9 11 1234 5678 / 11-1234-5678 / 011 1234-5678 / etc.
    """
    digits = re.sub(r"\D", "", phone)
    if not digits or len(digits) < 8:
        return ""
    # Quitar prefijo pais si existe
    if digits.startswith("54"):
        digits = digits[2:]
    # Quitar 0 inicial (prefix interurbano AR)
    if digits.startswith("0"):
        digits = digits[1:]
    # Quitar 9 inicial (mobile prefix AR)
    if digits.startswith("9") and len(digits) == 11:
        digits = digits[1:]
    # Si tiene 10 digitos y empieza con 11 (CABA mobile), agregar 9
    if len(digits) == 10 and digits.startswith("11"):
        digits = "9" + digits
    return f"+54{digits}" if len(digits) >= 8 else ""


# ===========================================================================
# Step 1: Collect
# ===========================================================================
def collect_public_sources() -> List[Dict[str, Any]]:
    """Recolecta resultados de búsquedas públicas via search_providers web_search.
    
    Si una query Reddit devuelve 429, la agrega a PendingQueryManager global.
    """
    print("[Step 1] Collecting public sources...", file=sys.stderr)
    all_results = []
    # PQM global accesible desde collect_public_sources
    global _pqm_global
    for i, query in enumerate(QUERIES):
        elapsed = time.time() - START_TIME
        if elapsed > MAX_RUNTIME_SECONDS:
            print(f"  [timeout] {elapsed:.1f}s", file=sys.stderr)
            break
        print(f"  [{i+1}/{len(QUERIES)}] {query[:60]}", file=sys.stderr)
        
        # Si es query Reddit, usar wrapper con status para detectar 429
        if "site:reddit.com" in query.lower():
            results, got_429 = search_reddit_with_status(
                query.lower().replace("site:reddit.com", "").strip(),
                num=MAX_RESULTS_PER_QUERY
            )
            if got_429 and _pqm_global:
                rss_url = f"https://www.reddit.com/search.rss?q={query}"
                _pqm_global.add(rss_url, query, _CURRENT_GROUP_IDX)
                print(f"  [PQM] 429 en '{query[:40]}' → agregado a pending", file=sys.stderr)
        else:
            results = web_search(query, num=MAX_RESULTS_PER_QUERY)
        
        for r in results:
            r["_query"] = query
        all_results.extend(results)
        time.sleep(RATE_LIMIT_MS / 1000)
    print(f"  Collected {len(all_results)} raw results", file=sys.stderr)

    # Nota: el enrich separado fue reemplazado por la logica inline en search_reddit
    # que trae selftext completo + top 10 comments por post en una sola pasada.
    reddit_count = sum(1 for r in all_results if "reddit.com" in r.get("url", ""))
    print(f"  Reddit posts in results: {reddit_count}", file=sys.stderr)

    # ML Questions Radar — siempre corre (no depende del grupo rotativo)
    try:
        from search_providers import search_mercadolibre_questions
        ml_leads = search_mercadolibre_questions(num=15)
        if ml_leads:
            for ml in ml_leads:
                ml["_query"] = "mercadolibre_questions_radar"
            all_results.extend(ml_leads)
            print(f"  ML Questions Radar: +{len(ml_leads)} leads", file=sys.stderr)
        else:
            print(f"  ML Questions Radar: 0 leads (posible 403 o sin resultados)", file=sys.stderr)
    except Exception as e:
        print(f"  ML Questions Radar ERROR: {e}", file=sys.stderr)

    # Foros AR via DDG (ForoMoto + ClasificadosLaVoz + Demotores)
    # Llama al endpoint /api/ddg-foromoto del Worker (Cloudflare edge IP)
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        secret = os.environ.get("INGEST_SECRET", "")
        if secret:
            import urllib.request as _urq
            foro_url = f"{worker_url}/api/ddg-foromoto"
            req = _urq.Request(foro_url)
            req.add_header("X-Webhook-Secret", secret)
            req.add_header("Accept", "application/json")
            with _urq.urlopen(req, timeout=45) as resp:
                foro_data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if foro_data.get("ok"):
                foro_leads = foro_data.get("leads", [])
                if foro_leads:
                    for fl in foro_leads:
                        fl["_query"] = "ddg_foros_ar"
                    all_results.extend(foro_leads)
                    print(f"  Foros AR (DDG): +{len(foro_leads)} leads con contacto", file=sys.stderr)
                else:
                    print(f"  Foros AR (DDG): 0 leads", file=sys.stderr)
    except Exception as e:
        print(f"  Foros AR ERROR: {e}", file=sys.stderr)

    # Facebook Groups via Apify (con cookies FB reales)
    # Llama al endpoint /api/apify-facebook del Worker
    # Scrapea grupos publicos de multas AR con sesion autenticada
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        secret = os.environ.get("INGEST_SECRET", "")
        if secret:
            import urllib.request as _urq2
            apify_url = f"{worker_url}/api/apify-facebook"
            apify_input = json.dumps({
                "groupUrls": [
                    "https://www.facebook.com/groups/276074287942602",  # Defensas contra Multas AR
                ],
                "maxPosts": 20,
                "fetchComments": True,
                "maxCommentsPerPost": 5,
            }).encode("utf-8")
            req2 = _urq2.Request(apify_url, data=apify_input, method="POST")
            req2.add_header("X-Webhook-Secret", secret)
            req2.add_header("Content-Type", "application/json")
            with _urq2.urlopen(req2, timeout=120) as resp2:
                fb_data = json.loads(resp2.read().decode("utf-8", errors="replace"))
            if fb_data.get("ok"):
                fb_leads = fb_data.get("leads", [])
                if fb_leads:
                    for fl in fb_leads:
                        fl["_query"] = "facebook_apify"
                    all_results.extend(fb_leads)
                    with_contact = sum(1 for fl in fb_leads if fl.get("has_contact"))
                    print(f"  Facebook (Apify): +{len(fb_leads)} leads ({with_contact} con contacto)", file=sys.stderr)
                else:
                    print(f"  Facebook (Apify): 0 leads", file=sys.stderr)
            else:
                print(f"  Facebook (Apify) ERROR: {fb_data.get('error','?')}", file=sys.stderr)
    except Exception as e:
        print(f"  Facebook (Apify) ERROR: {e}", file=sys.stderr)

    return all_results


# ===========================================================================
# Step 2: Extract entities
# ===========================================================================
def extract_entities(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrae entidades de un resultado de búsqueda."""
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")
    date = result.get("date", "")
    combined = f"{name}. {snippet}"

    # Content filter
    combined_lower = combined.lower()
    if not any(kw in combined_lower for kw in MUST_INCLUDE_ONE):
        return None
    for reject in REJECT_IF_CONTAINS:
        if reject in combined_lower:
            return None

    # FIX 2 (DeepSeek): Filtro de idioma portugués
    PORTUGUESE_INDICATORS = [
        r"\b(?:eu|voc[êe]|voc[êe]s|n[óo]s|eles|elas|meu|sua|suas|nosso|nossa)\b",
        r"\b(?:comprei|vendi|fiz|est[áa]|s[ãa]o|tem|fazer|pagar|transferir|consegui)\b",
        r"\b(?:n[ãa]o|tamb[ée]m|j[áa]|ainda|ent[ãa]o|porque|mas|por[ée]m|s[óo]|depois|antes)\b",
        r"\b(?:boa tarde|bom dia|boa noite|povo|galera|pessoal|abra[çc]o|obrigado|obrigada)\b",
        r"\b(?:carro|moto|ve[íi]culo|multa|transfer[êe]ncia|documento|detran|cnh|emplacamento)\b",
    ]
    pt_matches = sum(1 for pattern in PORTUGUESE_INDICATORS if re.search(pattern, combined, re.IGNORECASE))
    if pt_matches >= 3:
        return None

    # FIX 5 (DeepSeek): Filtro de contexto vehicular mas estricto
    VEHICULAR_KEYWORDS_STRICT = [
        "multa", "multas", "fotomulta", "fotomultas", "infraccion", "infracciones",
        "infracción", "transferencia", "transferir", "08", "08 firmado", "cedula verde",
        "libre deuda", "libredeuda", "patente", "registro automotor",
        "veraz", "juez de faltas", "deuda patente", "inhibicion",
        "titulo", "titular", "denuncia de venta", "formulario 08",
    ]
    vehicular_count = sum(1 for kw in VEHICULAR_KEYWORDS_STRICT if kw in combined_lower)
    # Inicializar variables antes del check (fix UnboundLocalError)
    phone = ""
    whatsapp = ""
    email = ""
    has_contact = bool(phone or whatsapp or email)
    # Qwen fix: Solo descartar si NO tiene keywords vehiculares Y NO tiene contacto
    if vehicular_count < 2 and not has_contact:
        return None

    # FIX 6 (DeepSeek): Bloquear imagenes/HTML como contenido principal
    if len(combined.strip()) < 50:
        return None
    url_count = len(re.findall(r"https?://", combined))
    html_tag_count = len(re.findall(r"<[^>]+>", combined))
    if len(combined) > 0 and (url_count * 30 + html_tag_count * 10) / len(combined) > 0.5:
        return None

    # Extract phone (ya inicializado arriba)
    for pattern in ARG_PHONE_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 15:
                phone = m.group(0).strip()
                break

    # Extract whatsapp
    whatsapp = ""
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            num = m.group(1) if m.groups() else m.group(0)
            digits = re.sub(r"\D", "", num)
            if 8 <= len(digits) <= 15:
                # Si empieza con 54 o 549, dejarlo; si tiene 10 digitos y arranca con 11, agregar 549
                if len(digits) == 10 and digits.startswith("11"):
                    digits = "549" + digits
                elif len(digits) == 10 and not digits.startswith("5"):
                    digits = "54" + digits
                whatsapp = digits
                break

    # Extract email
    email = ""
    m = re.search(EMAIL_PATTERN, combined)
    if m:
        email = m.group(1).lower().strip()

    # REGEX CONTEXTUAL (GPT+H.AI consensus):
    # Solo guardar contacto si el snippet TAMBIEN tiene keyword de dolor
    # Esto evita el spam de wa.me random sin contexto
    PAIN_KEYWORDS_RE = re.compile(
        r"\b(?:multa|multas|fotomulta|fotomultas|infracci[oó]n|infracciones|"
        r"libre\s+deuda|transferencia|transferir|patente|08\s+firmado|"
        r"c[eé]dula|veraz|registro\s+automotor|juez\s+de\s+faltas|"
        r"peaje|telepeaje|deuda|vencimiento|prescripci[oó]n)\b",
        re.IGNORECASE
    )
    has_pain_context = bool(PAIN_KEYWORDS_RE.search(combined))
    if not has_pain_context:
        # Sin contexto de dolor, descartar contacto (no es lead, es spam)
        phone = ""
        whatsapp = ""
        email = ""

    # Extract patent
    patent = ""
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            patent = re.sub(r"\s+", "", m.group(0)).upper()
            break

    # Extract vehicle
    vehicle = ""
    for v in VEHICLE_KEYWORDS:
        if v in combined_lower:
            vehicle = v
            break

    # Extract persona (username o nombre)
    persona = ""
    username = ""
    # 1. Provider ya trae username (Reddit author)
    provider_username = result.get("username", "") or result.get("author", "")
    if provider_username:
        username = provider_username
        persona = f"u/{username}"
    # 2. Buscar @username en el texto
    if not username:
        m = re.search(r"@(\w{3,20})", combined)
        if m:
            username = m.group(1)
            persona = m.group(0)
    # 3. Buscar u/username en el texto (Reddit-style)
    if not username:
        m = re.search(REDDIT_USERNAME_PATTERN, combined)
        if m:
            username = m.group(1)
            persona = f"u/{username}"
    # 4. "soy X"
    if not persona:
        m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", combined, re.IGNORECASE)
        if m:
            persona = m.group(1).title()

    # Reddit username from URL (rare path /user/X)
    host = get_host(url)
    if not username and "reddit.com" in host:
        m = re.search(r"/user/(\w+)", url)
        if m:
            username = m.group(1)
            persona = f"u/{username}"

    # Extract province/city
    provincia = ""
    ciudad = ""
    for city, prov in CITY_MAP.items():
        if city in combined_lower:
            ciudad = city.title()
            provincia = prov
            break
    if not provincia:
        for prov_key, prov_name in PROVINCE_MAP.items():
            if prov_key in combined_lower:
                provincia = prov_name
                break

    # Platform
    platform = PLATFORM_MAP.get(host, host.title() if host else "Unknown")

    return {
        "persona": persona or "(anónimo)",
        "username": username,
        "problema": combined,
        "provincia": provincia,
        "ciudad": ciudad,
        "vehiculo": vehicle,
        "patente": patent,
        "fecha_visible": date,
        "contacto_publico": bool(phone or whatsapp or email),
        "whatsapp_publico": whatsapp,
        "telefono_publico": phone,
        "email_publico": email,
        "source_url": url,
        "platform": platform,
        "quoted_text": snippet[:300] if snippet else "",
        "host": host,
        "combined_text": combined,
        # Campos extra de ML Questions (passthrough)
        "source": result.get("source", ""),
        "question_text": result.get("question_text", ""),
        "has_answer": result.get("has_answer", True),
        "price": result.get("price", 0),
        "seller_id": result.get("seller_id", ""),
        "provincia_ml": result.get("provincia_ml", ""),
    }


# ===========================================================================
# Step 3: Normalize
# ===========================================================================
def normalize_record(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un record."""
    # Date
    fecha_iso = ""
    dt = parse_date(extracted.get("fecha_visible", ""))
    if dt:
        fecha_iso = dt.isoformat()

    # Phone to E.164
    telefono_e164 = ""
    if extracted.get("telefono_publico"):
        telefono_e164 = phone_to_e164(extracted["telefono_publico"])
    if not telefono_e164 and extracted.get("whatsapp_publico"):
        telefono_e164 = phone_to_e164(extracted["whatsapp_publico"])

    # Canonical URL
    source_url = canonicalize_url(extracted.get("source_url", ""))

    # Trim snippet
    quoted_text = extracted.get("quoted_text", "").strip()

    # Standardize province
    provincia = extracted.get("provincia", "")

    return {
        **extracted,
        "fecha_iso": fecha_iso,
        "telefono_e164": telefono_e164,
        "source_url": source_url,
        "quoted_text": quoted_text,
        "provincia": provincia,
    }


# ===========================================================================
# Step 4: Classify & Score
# ===========================================================================
def classify_and_score(record: Dict[str, Any]) -> Optional[Lead]:
    """Clasifica y puntúa un record."""
    text = record.get("combined_text", "").lower()
    host = record.get("host", "")
    score = 0
    breakdown = {}
    signals = []

    # --- Scoring ---

    # Boost ML Questions Radar (alta calidad - Sakana+Claude)
    platform_str = (record.get("platform", "") or "").lower()
    source_str = (record.get("source", "") or "").lower()
    if "mercadolibre" in platform_str or "mercadolibre" in source_str:
        score += 25
        breakdown["ml_questions"] = 25
        signals.append("ML_QUESTION_RADAR")
        q_text = (record.get("question_text", "") or "").lower()
        if "puede transferir" in q_text or "libre deuda" in q_text:
            score += 15
            breakdown["ml_urgencia"] = 15
            signals.append("ML_URGENCIA_TRANSFERENCIA")
        if not record.get("has_answer", True):
            score += 5
            breakdown["ml_no_answer"] = 5
        try:
            price = float(record.get("price", 0) or 0)
            if price > 15000:
                score += 10
                breakdown["ml_premium"] = 10
                signals.append("ML_AUTO_PREMIUM")
        except (ValueError, TypeError):
            pass

    # DM_HINTS boost (KIMI+DEEPSEEK): posts que piden contacto por privado
    import re as _re_dm
    for pattern in DM_HINT_PATTERNS:
        if _re_dm.search(pattern, text):
            score += SCORE_RULES["dm_hint"]
            breakdown["dm_hint"] = SCORE_RULES["dm_hint"]
            signals.append("DM_HINT")
            break

    # URGENCY boost
    for pattern in URGENCY_HINT_PATTERNS:
        if _re_dm.search(pattern, text):
            score += SCORE_RULES["urgency_hint"]
            breakdown["urgency_hint"] = SCORE_RULES["urgency_hint"]
            signals.append("URGENCY")
            break

    # multa_or_fotomulta: +60
    if "multa" in text or "fotomulta" in text:
        score += SCORE_RULES["multa_or_fotomulta"]
        breakdown["multa_or_fotomulta"] = SCORE_RULES["multa_or_fotomulta"]
        signals.append("multa_fotomulta")

    # transfer_problem: +45
    if "transferencia" in text or "transferir" in text or "08 firmado" in text:
        score += SCORE_RULES["transfer_problem"]
        breakdown["transfer_problem"] = SCORE_RULES["transfer_problem"]
        signals.append("transfer_problem")

    # libre_deuda_problem: +35
    if "libre deuda" in text:
        score += SCORE_RULES["libre_deuda_problem"]
        breakdown["libre_deuda_problem"] = SCORE_RULES["libre_deuda_problem"]
        signals.append("libre_deuda")

    # 08_or_document_problem: +40 (no sumar doble con transfer)
    if "08" in text and "libre deuda" not in text:
        score += SCORE_RULES["08_or_document_problem"]
        breakdown["08_or_document_problem"] = SCORE_RULES["08_or_document_problem"]
        signals.append("document_08")

    # public_contact_visible: +25
    if record.get("contacto_publico"):
        score += SCORE_RULES["public_contact_visible"]
        breakdown["public_contact_visible"] = SCORE_RULES["public_contact_visible"]
        signals.append("contact_visible")

    # recent_0_3_days: +20 / recent_4_7_days: +10
    fecha_iso = record.get("fecha_iso", "")
    dt = parse_date(fecha_iso)
    recent_label = ""
    if dt:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now - dt
        if diff <= timedelta(days=3):
            score += SCORE_RULES["recent_0_3_days"]
            breakdown["recent_0_3_days"] = SCORE_RULES["recent_0_3_days"]
            recent_label = "recent_0_3"
            signals.append("recent_0_3_days")
        elif diff <= timedelta(days=7):
            score += SCORE_RULES["recent_4_7_days"]
            breakdown["recent_4_7_days"] = SCORE_RULES["recent_4_7_days"]
            recent_label = "recent_4_7"
            signals.append("recent_4_7_days")

    # argentina_signal: +15
    has_arg_signal = any(s.lower() in text for s in ARGENTINA_SIGNALS)
    if has_arg_signal:
        score += SCORE_RULES["argentina_signal"]
        breakdown["argentina_signal"] = SCORE_RULES["argentina_signal"]
        signals.append("argentina")

    # --- Penalties ---

    # foreign_country_penalty: -80
    is_foreign = False
    for country, indicators in FOREIGN_INDICATORS.items():
        for ind in indicators:
            if ind in text:
                is_foreign = True
                break
        if is_foreign:
            break
    if is_foreign:
        score += SCORE_RULES["foreign_country_penalty"]
        breakdown["foreign_country_penalty"] = SCORE_RULES["foreign_country_penalty"]

    # institutional_penalty: -40
    is_institutional = any(d in host for d in INSTITUTIONAL_DOMAINS)
    if is_institutional:
        score += SCORE_RULES["institutional_penalty"]
        breakdown["institutional_penalty"] = SCORE_RULES["institutional_penalty"]

    # generic_penalty: -30
    is_generic = any(d in host for d in GENERIC_DOMAINS)
    if is_generic:
        score += SCORE_RULES["generic_penalty"]
        breakdown["generic_penalty"] = SCORE_RULES["generic_penalty"]

    # --- PATENTE DETECTION (H.AI insight + GPT filter) ---
    # Detectar patente AR en texto y boost +15
    patente_match = re.search(r"\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b", record.get("combined_text", ""), re.IGNORECASE)
    if patente_match:
        score += 15
        breakdown["patente_detected"] = 15
        signals.append("PATENTE_DETECTED")
        # Marcar para enriquecimiento automatico con clasific.ar
        # (se hace en run_pipeline despues de classify_and_score)

    # --- INTENCION EXTREMA BOOST (GPT insight: filtrar ruido) ---
    # Solo leads con dolor MUY explicito merecen boost
    extreme_intent = any(phrase in text for phrase in [
        "me llego", "me llegue", "me cobraron", "me quieren cobrar",
        "no puedo transferir", "no me dejan transferir",
        "me retuvieron", "me secuestraron",
        "necesito ayuda", "necesito asesoramiento",
        "alguien sabe", "alguien me puede",
        "ayuda por favor", "urgente",
    ])
    if extreme_intent:
        score += 20
        breakdown["extreme_intent"] = 20
        signals.append("EXTREME_INTENT")

    # --- PENALTY: sin dolor explicito = ruido (GPT insight) ---
    # Si el texto NO tiene ninguna keyword de dolor, penalizar fuerte
    has_explicit_pain = any(kw in text for kw in [
        "multa", "multas", "fotomulta", "fotomultas",
        "infraccion", "infracciones", "infracción", "infracciones",
        "libre deuda", "transferencia", "transferir",
        "patente", "08 firmado", "cedula", "cedula verde",
        "veraz", "registro automotor", "juez de faltas",
        "peaje", "telepeaje", "deuda",
    ])
    if not has_explicit_pain:
        score -= 50
        breakdown["no_pain_penalty"] = -50
        signals.append("NO_PAIN")

    # --- CONTACTO BOOST (GPT: lo que importa es el contacto) ---
    has_contact = bool(
        record.get("whatsapp_publico") or
        record.get("telefono_publico") or
        record.get("email_publico") or
        record.get("phone") or
        record.get("whatsapp") or
        record.get("email")
    )
    if has_contact:
        score += 30
        breakdown["has_contact"] = 30
        signals.append("HAS_CONTACT")

    # Clamp
    score = max(0, min(100, score))

    # --- CLASSIFY (GPT: umbral mas alto para CRM) ---
    # Antes: 60 = real_lead. Ahora: 50 = real_lead (con filtro de dolor)
    if score >= 50 and not is_foreign and has_explicit_pain:
        label = "real_lead"
    elif score >= 30 and not is_foreign and has_explicit_pain:
        label = "commercial_signal"
    else:
        label = "reject"

    if label == "reject":
        return None

    # Problem category
    if "transferencia" in text or "transferir" in text or "08" in text:
        problem_cat = "TRANSFER_PROBLEM"
        problem_sum = "Problema de transferencia"
    elif "multa" in text or "fotomulta" in text:
        problem_cat = "FINE_DISPUTE"
        problem_sum = "Disputa de multa/fotomulta"
    elif "libre deuda" in text or "patente" in text:
        problem_cat = "DOCUMENTATION_ISSUE"
        problem_sum = "Problema documental"
    elif "no es mi auto" in text or "titular" in text:
        problem_cat = "OWNERSHIP_ISSUE"
        problem_sum = "Problema de titularidad"
    else:
        problem_cat = "OTHER"
        problem_sum = "Lead vehicular"

    # WhatsApp link
    wa_link = ""
    wa_num = record.get("whatsapp_publico", "") or record.get("telefono_publico", "")
    if wa_num:
        digits = re.sub(r"\D", "", wa_num)
        if not digits.startswith("54"):
            digits = "54" + digits.lstrip("0")
        wa_link = f"https://wa.me/{digits}"

    return Lead(
        score=score,
        label=label,
        problem_category=problem_cat,
        problem_summary=problem_sum,
        persona=record.get("persona", "(anónimo)"),
        provincia=record.get("provincia", ""),
        ciudad=record.get("ciudad", ""),
        pais="Argentina" if has_arg_signal and not is_foreign else ("Unknown" if not has_arg_signal else "Foreign"),
        vehiculo=record.get("vehiculo", ""),
        patente=record.get("patente", ""),
        fecha_visible=record.get("fecha_visible", ""),
        fecha_iso=fecha_iso,
        platform=record.get("platform", ""),
        source_url=record.get("source_url", ""),
        quoted_text=record.get("quoted_text", ""),
        contacto_publico=record.get("contacto_publico", False),
        whatsapp_publico=record.get("whatsapp_publico", ""),
        whatsapp_link=wa_link,
        email_publico=record.get("email_publico", ""),
        telefono_publico=record.get("telefono_publico", ""),
        telefono_e164=record.get("telefono_e164", ""),
        score_breakdown=breakdown,
        detected_signals=signals,
        discovery_timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ===========================================================================
# Step 5: Deduplicate
# ===========================================================================
def deduplicate_cases(leads: List[Lead]) -> List[Lead]:
    """Dedup por sha256 composite hash."""
    print("[Step 5] Deduplicating...", file=sys.stderr)
    seen: Set[str] = set()
    out = []
    for lead in leads:
        # Qwen fix: Solo usar URL para ID (estable entre runs)
        components = [lead.source_url or lead.quoted_text[:50]]
        composite = "|".join(components)
        h = hashlib.sha256(composite.encode("utf-8")).hexdigest()[:16]
        lead.id = h
        if h in seen:
            continue
        seen.add(h)
        out.append(lead)
    print(f"  Before: {len(leads)} → After: {len(out)}", file=sys.stderr)
    return out


# ===========================================================================
# Step 6: Build payload
# ===========================================================================
def generate_insights(leads: List[Lead]) -> List[str]:
    """Genera insights automáticos del lote."""
    insights = []
    if not leads:
        return ["Sin datos suficientes para generar insights."]

    # Pattern 1: top platform en hot leads
    hot = [l for l in leads if l.label == "real_lead"]
    if hot:
        plat_counts = {}
        for l in hot:
            plat_counts[l.platform] = plat_counts.get(l.platform, 0) + 1
        top_plat = max(plat_counts, key=plat_counts.get)
        top_pct = round(plat_counts[top_plat] / len(hot) * 100)
        insights.append(f"El {top_pct}% de los leads calientes provienen de {top_plat}.")

    # Pattern 2: top province
    prov_counts = {}
    for l in hot:
        if l.provincia:
            prov_counts[l.provincia] = prov_counts.get(l.provincia, 0) + 1
    if prov_counts:
        top_prov = max(prov_counts, key=prov_counts.get)
        top_prov_pct = round(prov_counts[top_prov] / len(hot) * 100)
        insights.append(f"El {top_prov_pct}% de los leads calientes son de {top_prov}.")

    # Pattern 3: top problem
    prob_counts = {}
    for l in hot:
        prob_counts[l.problem_summary] = prob_counts.get(l.problem_summary, 0) + 1
    if prob_counts:
        top_prob = max(prob_counts, key=prob_counts.get)
        insights.append(f"El problema más frecuente es: {top_prob}.")

    # Pattern 4: contact rate
    with_contact = sum(1 for l in hot if l.contacto_publico)
    if hot:
        contact_pct = round(with_contact / len(hot) * 100)
        insights.append(f"{contact_pct}% de los leads calientes tienen contacto público visible.")

    # Pattern 5: urgency
    urgent = sum(1 for l in hot if "urgency" in str(l.detected_signals).lower() or
                 any(kw in l.quoted_text.lower() for kw in ["urgente", "hoy", "mañana", "ya"]))
    if urgent > 0:
        insights.append(f"{urgent} leads calientes muestran señales de urgencia temporal.")

    return insights


def build_dashboard_payload(leads: List[Lead]) -> Dict[str, Any]:
    """Construye el payload final del dashboard."""
    print("[Step 6] Building dashboard payload...", file=sys.stderr)

    run_id = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
    generated_at = datetime.now(timezone.utc).isoformat()

    hot = [l for l in leads if l.label == "real_lead"]
    warm = [l for l in leads if l.label == "commercial_signal"]

    # Sort each by score desc, date desc
    hot.sort(key=lambda l: (l.score, l.fecha_iso or l.discovery_timestamp), reverse=True)
    warm.sort(key=lambda l: (l.score, l.fecha_iso or l.discovery_timestamp), reverse=True)

    summary = {
        "total_leads": len(leads),
        "hot_leads": len(hot),
        "warm_leads": len(warm),
        "contactable": sum(1 for l in leads if l.contacto_publico),
        "with_whatsapp": sum(1 for l in leads if l.whatsapp_publico),
        "with_phone": sum(1 for l in leads if l.telefono_publico),
        "with_email": sum(1 for l in leads if l.email_publico),
        "avg_score": round(sum(l.score for l in leads) / len(leads), 1) if leads else 0,
        "avg_score_hot": round(sum(l.score for l in hot) / len(hot), 1) if hot else 0,
        "conversion_probability": round(len(hot) / len(leads) * 100, 1) if leads else 0,
        "by_category": {},
        "by_platform": {},
        "by_province": {},
    }
    for l in leads:
        summary["by_category"][l.problem_category] = summary["by_category"].get(l.problem_category, 0) + 1
        summary["by_platform"][l.platform] = summary["by_platform"].get(l.platform, 0) + 1
        if l.provincia:
            summary["by_province"][l.provincia] = summary["by_province"].get(l.provincia, 0) + 1

    insights = generate_insights(leads)

    all_leads_sorted = sorted(leads, key=lambda l: l.score if hasattr(l, "score") else 0, reverse=True)
    payload = {
        "generated_at": generated_at,
        "run_id": run_id,
        "summary": summary,
        "leads_all": [l.to_dict() for l in all_leads_sorted],
        "leads_hot": [l.to_dict() for l in hot],
        "leads_warm": [l.to_dict() for l in warm],
        "insights": insights,
        "meta": {
            "version": "1.0",
            "pipeline_steps": ["collect", "extract", "normalize", "classify_score", "dedup", "build_payload", "publish"],
            "scoring_rules": SCORE_RULES,
            "runtime_seconds": round(time.time() - START_TIME, 2),
            "queries_executed": QUERIES_EXECUTED,
        },
    }

    print(f"  Hot: {len(hot)} | Warm: {len(warm)} | Insights: {len(insights)}", file=sys.stderr)
    return payload


# ===========================================================================
# Step 7: Publish
# ===========================================================================
def publish_artifacts(payload: Dict[str, Any], leads: List[Lead]) -> None:
    """Publica los artefactos: overwrite latest + append history + update stats."""
    print("[Step 7] Publishing artifacts...", file=sys.stderr)

    # Overwrite dashboard_payload.json
    PAYLOAD_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {PAYLOAD_PATH} ({PAYLOAD_PATH.stat().st_size:,} bytes)", file=sys.stderr)

    # Append to history.json
    history_entry = {
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "summary": payload["summary"],
    }
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(history_entry)
    history = history[-100:]  # keep last 100 runs
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {HISTORY_PATH} ({len(history)} runs)", file=sys.stderr)

    # Update stats.json (cumulative)
    stats = {
        "total_runs": len(history),
        "last_run": payload["generated_at"],
        "last_run_id": payload["run_id"],
        "total_leads_all_time": sum(h["summary"]["total_leads"] for h in history),
        "total_hot_leads_all_time": sum(h["summary"]["hot_leads"] for h in history),
        "avg_hot_per_run": round(sum(h["summary"]["hot_leads"] for h in history) / len(history), 1) if history else 0,
        "runs_today": sum(1 for h in history if h["generated_at"][:10] == payload["generated_at"][:10]),
        "last_7_days": [h for h in history[-7:]],
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {STATS_PATH}", file=sys.stderr)


# ===========================================================================
# Main pipeline
# ===========================================================================

START_TIME = time.time()
QUERIES_EXECUTED = 0
_pqm_global = None  # PendingQueryManager global, seteado en run_pipeline
_CURRENT_GROUP_IDX = 0


#===========================================================================
# Step 4.6: Comment Mining — Extraer contactos de comentarios del post
#===========================================================================
def mine_comments_for_contacts(leads: List[Lead]) -> int:
    """Scrapea comentarios del post y busca telefonos/emails del autor."""
    print("[Step 4.6] Mining comments for contacts...", file=sys.stderr)
    enriched_count = 0

    for lead in leads:
        if lead.platform != "Reddit":
            continue
        if lead.whatsapp_publico or lead.telefono_publico or lead.email_publico:
            continue

        url_parts = lead.source_url.rstrip("/").split("/")
        if len(url_parts) < 7 or "comments" not in url_parts:
            continue
        post_id = url_parts[6]

        comments_url = f"https://old.reddit.com/comments/{post_id}.json?limit=50"

        try:
            import urllib.request as _urq
            req = _urq.Request(comments_url)
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            req.add_header("Accept", "application/json")
            with _urq.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if not isinstance(data, list) or len(data) < 2:
                    continue

                comments_listing = data[1]
                all_comment_text = ""
                lead_author = lead.persona.replace("u/", "").strip().lower()

                for child in comments_listing.get("data", {}).get("children", []):
                    comment = child.get("data", {})
                    author = comment.get("author", "")
                    body = comment.get("body", "")

                    if author and author != "[deleted]" and body:
                        if author.lower() == lead_author:
                            all_comment_text += " " + body

                if not all_comment_text:
                    continue

                for pattern in ARG_PHONE_PATTERNS:
                    m = re.search(pattern, all_comment_text)
                    if m:
                        digits = re.sub(r"\D", "", m.group(0))
                        if 10 <= len(digits) <= 15:
                            lead.telefono_publico = m.group(0).strip()
                            lead.contacto_publico = True
                            lead.score = min(100, (lead.score or 0) + 25)
                            lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_PHONE"]
                            enriched_count += 1
                            break

                if not lead.whatsapp_publico:
                    for pattern in WHATSAPP_PATTERNS:
                        m = re.search(pattern, all_comment_text, re.IGNORECASE)
                        if m:
                            num = m.group(1) if m.groups() else m.group(0)
                            digits = re.sub(r"\D", "", num)
                            if 8 <= len(digits) <= 15:
                                if len(digits) == 10 and digits.startswith("11"):
                                    digits = "549" + digits
                                lead.whatsapp_publico = digits
                                lead.contacto_publico = True
                                lead.score = min(100, (lead.score or 0) + 30)
                                lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_WHATSAPP"]
                                enriched_count += 1
                                break

                if not lead.email_publico:
                    m = re.search(EMAIL_PATTERN, all_comment_text)
                    if m:
                        lead.email_publico = m.group(1).lower().strip()
                        lead.contacto_publico = True
                        lead.score = min(100, (lead.score or 0) + 15)
                        lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_EMAIL"]
                        enriched_count += 1

                time.sleep(2.0)  # Qwen fix: Rate limit
        except Exception:
            continue

    if enriched_count:
        print(f"  [Comment Mining] {enriched_count} leads enriquecidos", file=sys.stderr)
    return enriched_count


#===========================================================================
# Step 4.7: Profile Mining — Extraer contactos del perfil de Reddit del autor
#===========================================================================
def mine_profile_for_contacts(leads: List[Lead]) -> int:
    """Scrapea el perfil del autor (comments.rss) y busca contacto en bio/historial."""
    print("[Step 4.7] Mining user profiles for contacts...", file=sys.stderr)
    enriched_count = 0

    for lead in leads:
        if lead.platform != "Reddit":
            continue
        if lead.whatsapp_publico or lead.telefono_publico or lead.email_publico:
            continue

        username = lead.persona.replace("u/", "").strip()
        if not username or len(username) < 3:
            continue

        profile_url = f"https://www.reddit.com/user/{username}/comments/.rss?limit=25"

        try:
            import urllib.request as _urq
            req = _urq.Request(profile_url)
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            req.add_header("Accept", "application/atom+xml,application/xml,text/xml")
            with _urq.urlopen(req, timeout=15) as resp:
                xml_content = resp.read().decode("utf-8", errors="replace")

                entries = re.findall(r"<entry>([\s\S]*?)</entry>", xml_content, re.DOTALL)
                all_profile_text = ""

                for entry in entries:
                    content_m = re.search(r"<content[^>]*>([\s\S]*?)</content>", entry, re.DOTALL)
                    if content_m:
                        raw = content_m.group(1)
                        cleaned = re.sub(r"<[^>]+>", " ", raw)
                        cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        cleaned = cleaned.replace("&quot;", '"').replace("&#39;", "'")
                        all_profile_text += " " + cleaned

                if not all_profile_text:
                    continue

                for pattern in ARG_PHONE_PATTERNS:
                    m = re.search(pattern, all_profile_text)
                    if m:
                        digits = re.sub(r"\D", "", m.group(0))
                        if 10 <= len(digits) <= 15:
                            lead.telefono_publico = m.group(0).strip()
                            lead.contacto_publico = True
                            lead.score = min(100, (lead.score or 0) + 25)
                            lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_PHONE"]
                            enriched_count += 1
                            break

                if not lead.whatsapp_publico:
                    for pattern in WHATSAPP_PATTERNS:
                        m = re.search(pattern, all_profile_text, re.IGNORECASE)
                        if m:
                            num = m.group(1) if m.groups() else m.group(0)
                            digits = re.sub(r"\D", "", num)
                            if 8 <= len(digits) <= 15:
                                if len(digits) == 10 and digits.startswith("11"):
                                    digits = "549" + digits
                                lead.whatsapp_publico = digits
                                lead.contacto_publico = True
                                lead.score = min(100, (lead.score or 0) + 30)
                                lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_WHATSAPP"]
                                enriched_count += 1
                                break

                if not lead.email_publico:
                    m = re.search(EMAIL_PATTERN, all_profile_text)
                    if m:
                        lead.email_publico = m.group(1).lower().strip()
                        lead.contacto_publico = True
                        lead.score = min(100, (lead.score or 0) + 15)
                        lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_EMAIL"]
                        enriched_count += 1

                time.sleep(2.0)  # Qwen fix: Rate limit
        except Exception:
            continue

    if enriched_count:
        print(f"  [Profile Mining] {enriched_count} leads enriquecidos", file=sys.stderr)
    return enriched_count


def run_pipeline() -> Dict[str, Any]:
    global QUERIES_EXECUTED, _pqm_global
    _pqm_global = None  # se setea en Step 0.5

    print("=" * 60, file=sys.stderr)
    print("  LeadX Pipeline v2 (Python = unico cerebro)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # GPT FIX: Descargar KV existente para merge correcto
    # (Worker hace deep merge, pero Python necesita saber que ya existe)
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        ingest_secret = os.environ.get("INGEST_SECRET", "")
        if ingest_secret:
            import urllib.request as _urq_kv
            kv_url = f"{worker_url}/api/kv?key=leads:live"
            req_kv = _urq_kv.Request(kv_url)
            req_kv.add_header("X-Webhook-Secret", ingest_secret)
            with _urq_kv.urlopen(req_kv, timeout=15) as resp_kv:
                kv_data = json.loads(resp_kv.read().decode("utf-8", errors="replace"))
            existing_count = len(kv_data.get("value", {}).get("leads_all", []))
            print(f"  [KV] Leads existentes en KV: {existing_count}", file=sys.stderr)
    except Exception as e:
        print(f"  [KV] WARNING: {e}", file=sys.stderr)
    print("  RADAR LEADS — Payload Generator v1.0", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Step 0: Source discovery (SourceHunterAR v10.2)
    try:
        run_discovery_and_update()
    except Exception as e:
        print(f"  [SourceHunter] WARNING: {e}", file=sys.stderr)

    # Step 0.5: PendingQueryManager — reintenta queries que fallaron con 429
    worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
    ingest_secret = os.environ.get("INGEST_SECRET", "")
    pqm = None
    recovered_leads = []
    if ingest_secret:
        try:
            pqm = PendingQueryManager(worker_url, ingest_secret)
            _pqm_global = pqm  # accesible desde collect_public_sources
            pqm.load()
            # Reintentar pending primero (máx 2, antes del grupo rotativo)
            recovered_raw = pqm.retry_pending(search_reddit_with_status)
            print(f"  [PQM] Recuperadas {len(recovered_raw)} queries pendientes → {len(recovered_raw)} posts",
                  file=sys.stderr)
            # Agregar a raw_results para que pasen por extract_entities
            for r in recovered_raw:
                r["_query"] = f"pending_retry:{r.get('query','')}"
                raw_results_pending = [r]  # placeholder
            recovered_leads = recovered_raw
        except Exception as e:
            print(f"  [PQM] WARNING: {e}", file=sys.stderr)
            pqm = None
    else:
        print("  [PQM] SKIP: INGEST_SECRET no configurado", file=sys.stderr)

    # Step 1: Collect
    raw_results = collect_public_sources()

    # Agregar recovered_leads al inicio de raw_results
    if recovered_leads:
        for r in recovered_leads:
            r["_query"] = r.get("_query", "pending_retry")
        raw_results = recovered_leads + raw_results
        print(f"  [PQM] Agregados {len(recovered_leads)} posts recuperados al pipeline",
              file=sys.stderr)

    # Step 1.5: Guardar PQM al final del run (en try/finally para que siempre guarde)
    # Lo movemos al final del pipeline
    QUERIES_EXECUTED = len(set(r.get("_query", "") for r in raw_results))

    # Step 2: Extract
    print("[Step 2] Extracting entities...", file=sys.stderr)
    extracted = []
    for r in raw_results:
        ext = extract_entities(r)
        if ext:
            extracted.append(ext)
    print(f"  Extracted {len(extracted)} entities", file=sys.stderr)

    # Step 3: Normalize
    print("[Step 3] Normalizing records...", file=sys.stderr)
    normalized = [normalize_record(e) for e in extracted]
    print(f"  Normalized {len(normalized)} records", file=sys.stderr)

    # Step 4: Classify & Score
    print("[Step 4] Classifying and scoring...", file=sys.stderr)
    leads = []
    for rec in normalized:
        lead = classify_and_score(rec)
        if lead:
            leads.append(lead)
    print(f"  Scored {len(leads)} leads (rejected rest)", file=sys.stderr)

    # Step 4.5: Enriquecer leads con patente detectada via clasific.ar
    # H.AI insight + GPT filter: solo enriquecer si hay patente + dolor
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        ingest_secret = os.environ.get("INGEST_SECRET", "")
        if ingest_secret:
            enriched_count = 0
            import urllib.request as _urq3
            for lead in leads:
                if "PATENTE_DETECTED" in (lead.detected_signals or []):
                    # Buscar patente en el texto
                    patente_m = re.search(r"\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b", lead.quoted_text or "", re.IGNORECASE)
                    if patente_m:
                        patente = patente_m.group(1).upper()
                        try:
                            basic_url = f"{worker_url}/api/clasificar-basic?plate={patente}"
                            req3 = _urq3.Request(basic_url)
                            req3.add_header("X-Webhook-Secret", ingest_secret)
                            req3.add_header("Accept", "application/json")
                            with _urq3.urlopen(req3, timeout=10) as resp3:
                                veh_data = json.loads(resp3.read().decode("utf-8", errors="replace"))
                            if veh_data.get("ok") and veh_data.get("data", {}).get("data"):
                                v = veh_data["data"]["data"]
                                lead.vehiculo = f"{v.get('make','')} {v.get('model','')} {v.get('year','')}".strip()
                                lead.provincia = v.get("currentLocation", {}).get("province", "") or lead.provincia
                                enriched_count += 1
                        except Exception:
                            pass
                        time.sleep(0.5)  # rate limit clasific.ar
            if enriched_count:
                print(f"  [clasific.ar] {enriched_count} leads enriquecidos con datos vehiculares", file=sys.stderr)
    except Exception as e:
        print(f"  [clasific.ar] ERROR: {e}", file=sys.stderr)

    # Step 4.6: Comment Mining (DeepSeek+Qwen insight)
    mine_comments_for_contacts(leads)

    # Step 4.7: Profile Mining (DeepSeek+Qwen insight)
    mine_profile_for_contacts(leads)

    # MEJORA 2 (Qwen): OSINT Shadow Profile - triangulacion de identidad
    # Si un lead de Reddit no tiene contacto, buscar username en ML/FB via DDG
    try:
        from search_providers import search as _osint_search
        osint_count = 0
        for lead in leads:
            if lead.whatsapp_publico or lead.email_publico or lead.telefono_publico:
                continue  # Ya tiene contacto, saltar
            if not lead.persona or not lead.persona.startswith("u/"):
                continue  # No es Reddit user
            username = lead.persona.replace("u/", "").strip()
            if len(username) < 3:
                continue
            # Buscar username en MercadoLibre y Facebook
            for q in [f'site:mercadolibre.com.ar "{username}"',
                      f'site:facebook.com "{username}"']:
                try:
                    results = _osint_search(q, num=3)
                    for r in results:
                        snippet = r.get("snippet", "") + " " + r.get("title", "")
                        # Reusar regex federal para extraer telefono
                        for pattern in ARG_PHONE_PATTERNS:
                            m = re.search(pattern, snippet)
                            if m:
                                digits = re.sub(r"\D", "", m.group(0))
                                if 10 <= len(digits) <= 15:
                                    lead.telefono_publico = m.group(0).strip()
                                    lead.contacto_publico = True
                                    lead.score = min(100, (lead.score or 0) + 20)
                                    if "OSINT_SHADOW" not in (lead.detected_signals or []):
                                        lead.detected_signals = (lead.detected_signals or []) + ["OSINT_SHADOW_PROFILE"]
                                    osint_count += 1
                                    break
                        if lead.telefono_publico:
                            break
                    if lead.telefono_publico:
                        break
                except Exception:
                    continue
            time.sleep(1)  # rate limit DDG
        if osint_count:
            print(f"  [OSINT] {osint_count} leads enriquecidos via shadow profile", file=sys.stderr)
    except Exception as e:
        print(f"  [OSINT] ERROR: {e}", file=sys.stderr)

    # Step 5: Dedup
    leads = deduplicate_cases(leads)

    # Step 6: Build payload
    payload = build_dashboard_payload(leads)

    # Step 7: Publish
    publish_artifacts(payload, leads)

    elapsed = time.time() - START_TIME
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ✓ Complete in {elapsed:.1f}s", file=sys.stderr)
    print(f"  Hot: {payload['summary']['hot_leads']} | Warm: {payload['summary']['warm_leads']}", file=sys.stderr)
    print(f"  Payload: {PAYLOAD_PATH}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Step 7.5: Guardar PQM al final
    if pqm:
        try:
            pqm.save()
            print(f"  [PQM] Estado final: {pqm.status()}", file=sys.stderr)
        except Exception as e:
            print(f"  [PQM] ERROR guardando: {e}", file=sys.stderr)

    return payload


if __name__ == "__main__":
    payload = run_pipeline()
    # Output summary to stdout
    print(json.dumps({
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "summary": payload["summary"],
        "insights": payload["insights"],
    }, ensure_ascii=False, indent=2))
