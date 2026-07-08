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
                    "moto", "camioneta", "libre deuda"]  # FIX GEMINI Sabueso: removido '08' suelto (matcheaba '308', '2016', etc.)

REJECT_IF_CONTAINS = [
    "publicado por", "leer más", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso",
    "trámite online", "turno web",
    "wikipedia", "enciclopedia",
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "criptomoneda",
]

# ===========================================================================
# FIX QWEN v2.8: FILTROS ANTI-BASURA (GAMING, USA, GAMING ACHIEVEMENTS, ETC.)
# ===========================================================================
GAMING_KEYWORDS = [
    "playstation", "playstation 3", "playstation 4", "playstation 5", "ps3", "ps4", "ps5",
    "xbox", "xbox one", "xbox series", "nintendo", "switch",
    "gta", "grand theft auto", "gta v", "gta 5",
    "final fantasy", "littlebigplanet", "motorstorm", "need for speed", "silent hill",
    "college hoop", "blur", "call of duty", "cod",
    "logros", "achievements", "logros de", "logros del modo",
    "gaming", "gamer", "gamer argentino", "gamers",
    "steam", "epic games", "steam deck",
    "xbox game pass", "game pass", "xbox gamepass",
    "playstation plus", "ps plus",
    "nintendo switch", "switch oled",
    "how can i prevent", "writer from automatically",
    "font name when i type", "achievements related",
]

GAMING_SUBREDDITS = {
    "gaming", "gamingargentina", "argentinagaming", "argentinagamer",
    "gamerargentina", "argentina_gaming",
    "playstation", "playstationargentina",
    "xboxargentina", "xbox", "nintendo", "nintendoswitch",
    "steam", "steamargentina", "steamdeck", "pcgaming",
    "pcmasterrace", "pcgamingargentina",
}

# Extender REJECT_IF_CONTAINS con keywords de gaming
REJECT_IF_CONTAINS.extend(GAMING_KEYWORDS)

# FILTROS ADICIONALES DE CALIDAD (DeepSeek+Qwen v2.7)
NEGATIVE_KEYWORDS = [
    'accidente', 'choque', 'siniestro', 'colisión',
    'trabajo', 'empleo', 'renunciar', 'laboral',
    'tablet', 'celular', 'notebook', 'electrónica',
    'licitación', 'concurso', 'fraude', 'estafa',
    'alquiler', 'departamento', 'propiedad',
    'médico', 'hospital', 'salud',
]

DISCARD_DOMAINS = {
    'iprofesional.com', 'ciudano.news', 'ciudadano.news', 'iusnoticias.com.ar',
    'parrillacero5.com.ar', 'multas.ar', 'juridicamente.org',
    'hlbpharma.com.ar', 'autodataar.com', 'tiempofinanciero.com.ar',
    'tn.com.ar', 'infobae.com', 'clarin.com', 'lanacion.com.ar',
    'perfil.com', 'cronista.com', 'ambito.com',
    'segurarse.com.ar', 'carchecking.com.ar',
    'multabot.com.ar', 'reclamosonline.com.ar',
    'portaldeabogados.com', 'jus.gov.ar', 'gob.ar', 'gov.ar',
    'wikipedia.org', 'youtube.com',
}

REJECT_COUNTRIES = {
    'brasil', 'chile', 'uruguay', 'paraguay', 'bolivia',
    'perú', 'colombia', 'ecuador', 'venezuela', 'méxico',
    'españa', 'estados unidos', 'italia',
}

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
    # FIX QWEN v2.8: indicadores USA + Gaming más precisos
    "USA": ["usa-tn", "usa-tx", "usa-ca", "usa-ny", "usa-fl", "[usa-", "[h]", "[w]",
            "paypal", "venmo", "zelle"],
    "Gaming": ["playstation", "playstation 3", "ps3", "ps4", "ps5", "xbox",
               "gta", "gta v", "final fantasy"],
}

ARGENTINA_SIGNALS = [
    "DNRPA", "patente argentina", "Buenos Aires", "CABA",
    "Santa Fe", "Córdoba", "Mendoza", "Rosario", "La Plata",
    "ARBA", "Rentas", "PBA", "GBA", "argentina",
    "Entre Ríos", "Neuquén", "Salta", "Paraná",
]

# Phone patterns
# Qwen+Kimi v2: Regex FEDERAL v2 - captura formatos reales argentinos
ARG_PHONE_PATTERNS = [
    # Formato explicito: "whatsapp: 11 1234-5678", "llamame al 341-555-1234"
    r"(?i)(?:whatsapp|wsp|wapp|wp|wasap|celular|cel|tel[eé]fono|tel|llamame|contactame|escribime|mandame)\s*:?\s*([+]?\d[\d\s\-]{8,15})",
    # Formato federal: 11 1234-5678, 341-555-1234, 0351 1234567, +54 9 11 1234 5678
    r"(?<!\d)(?:[+]?\d{0,2}\s?)?(?:0?\s?)?(?:11|15|341|342|343|351|358|381|385|387|388|221|261|264|291|294|297|299|336|362|370|376|379|380|383)\s?[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)",
    # Formato wa.me directo
    r"wa\.me/(\d{8,15})",
    # Formato generico: 11-1234-5678
    r"\b(\d{2}[\s\-]?\d{4}[\s\-]?\d{4})\b",
    # Formato con parentesis: (11) 1234-5678, (341) 555-1234 (Qwen v3 fix)
    r"\((11|15|341|342|343|351|358|381|385|387|388|221|261|264|291|294|297|299|336|362|370|376|379|380|383)\)\s?\d{4}[\s\-]?\d{4}",
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

# FIX GEMINI+KIMI: Regex para emails ofuscados (común en grupos FB/ML).
# Captura: "juan arroba gmail punto com", "user [at] host [dot] com", "user at host dot com"
EMAIL_OBFUSCATED_RE = re.compile(
    r'\b([a-zA-Z0-9._%+\-]+)\s*(?:@|\[at\]|arroba|\(at\)|_at_)\s*'
    r'([a-zA-Z0-9.\-]+)\s*(?:\.|\[dot\]|dot|punto)\s*'
    r'(com|com\.ar|net|org|live|online|yahoo|gmail|hotmail)\b',
    re.IGNORECASE
)

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
    "ventafe.com.ar": "VentaFe",  # FIX GEMINI: evitar que .title() produzca "Ventafe.Com.Ar"
    "www.ventafe.com.ar": "VentaFe",
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
    deuda_clasificar: int = 0  # CAMBIO QWEN v2.7: deuda según clasific.ar

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
    """
    Sakana+GLM: Normaliza cualquier formato AR a E.164: +549112345678
    - Evita duplicar el 9 cuando ya viene con +549
    - Valida códigos de área argentinos conocidos
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""

    # Caso 1: Ya viene con 549 (formato correcto, 12 dígitos)
    if digits.startswith("549") and len(digits) == 12:
        return f"+{digits}"

    # Caso 2: Viene con 54 pero sin 9 (formato internacional incompleto)
    if digits.startswith("54") and len(digits) == 11:
        return f"+549{digits[2:]}"

    # Caso 3: Número local de 10 dígitos (ej: 1123456789, 3421234567)
    valid_ac_2 = ("11", "15")
    valid_ac_3 = ("341", "342", "343", "351", "353", "358", "362", "364",
                  "370", "376", "379", "380", "381", "383", "385", "387", "388",
                  "221", "223", "249", "261", "264", "291", "294", "297", "299")
    if len(digits) == 10:
        if digits[:2] in valid_ac_2 or digits[:3] in valid_ac_3:
            return f"+549{digits}"

    # Caso 4: Número de más de 10 dígitos (tomar últimos 10)
    if len(digits) > 10:
        last_10 = digits[-10:]
        if last_10[:2] in valid_ac_2 or last_10[:3] in valid_ac_3:
            return f"+549{last_10}"

    return ""

def normalize_phone_ar(raw: str) -> str:
    """Alias de phone_to_e164 para compatibilidad."""
    return phone_to_e164(raw)


# ===========================================================================
def normalize_ar_phone_ventafe(raw: str) -> str:
    """Normaliza telefonos AR complejos desde VentaFe (maneja 15, 0, 54)."""
    digits = re.sub(r'\D', '', raw)
    if not digits or len(digits) < 8:
        return ""
    if digits.startswith('54') and len(digits) > 11:
        digits = digits[2:]
    if digits.startswith('0'):
        digits = digits[1:]
    if digits.startswith('15') and len(digits) > 10:
        digits = digits[2:]
    # Manejar 15 en el medio (ej: 342 15 6128372 -> 342156128372)
    if len(digits) == 12 and digits[3:5] == '15':
        digits = digits[:3] + digits[5:]
    elif len(digits) == 11 and digits[2:4] == '15':
        digits = digits[:2] + digits[4:]
    if len(digits) == 10:
        return f"+549{digits}"
    return ""


def try_triangulate_plate(brand: str, model: str, mileage: str, location: str) -> str:
    """
    FIX GEMINI VIA B: Cross-Platform Matcher.
    Busca publicaciones duplicadas en MercadoLibre usando marca+modelo+kilometraje exacto
    para extraer la patente de las Q&A (donde compradores preguntan y vendedores responden).
    Retorna la patente en formato AA111AA o string vacio si no encuentra.
    """
    if not brand or not mileage or mileage == "0":
        return ""
    try:
        from search_providers import search as _osint_search
        # Query altamente especifica: marca + modelo + kilometraje exacto en ML
        query_parts = [f'site:mercadolibre.com.ar "{brand}"']
        if model:
            query_parts.append(f'"{model}"')
        query_parts.append(f'"{mileage}"')
        query = " ".join(query_parts)
        results = _osint_search(query, num=3)
        for r in results:
            text_to_analyze = (r.get("snippet", "") + " " + r.get("title", "") + " " + r.get("name", ""))
            # Buscar patente en formato Mercosur (AA111AA) con espacios opcionales
            patente_m = re.search(r"\b([A-Za-z]{2}\s?\d{3}\s?[A-Za-z]{2})\b", text_to_analyze)
            if patente_m:
                plate = re.sub(r"\s+", "", patente_m.group(1)).upper()
                if len(plate) == 7:  # Validar longitud exacta
                    print(f"      [Triangulacion OSINT] Patente {plate} recuperada de ML espejo", file=sys.stderr)
                    return plate
    except Exception:
        pass
    return ""


def scrape_ventafe_leads() -> List[Dict[str, Any]]:
    """Scrapea VentaFe.com.ar/automoviles (5 paginas) y extrae telefonos visibles."""
    import urllib.request as _urq
    import re as _re

    print("[VentaFe] Scrapeando ventafe.com.ar/automoviles (5 paginas)...", file=sys.stderr)

    BASE_URL = "https://www.ventafe.com.ar/automoviles"
    TOTAL_PAGES = 5  # CAMBIO QWEN v2.7: era 1 pagina, ahora 5 = ~150 autos
    all_blocks: List[str] = []
    seen_phones_global: set = set()

    for page in range(1, TOTAL_PAGES + 1):
        # FIX: VentaFe usa ?p=N (NO ?page=N que devuelve siempre pagina 1)
        url = f"{BASE_URL}?p={page}" if page > 1 else BASE_URL
        print(f"  [VentaFe] Pagina {page}/{TOTAL_PAGES}: {url}", file=sys.stderr)
        req = _urq.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'es-AR,es;q=0.9',
        })
        try:
            with _urq.urlopen(req, timeout=20) as resp:
                html = resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f"  [VentaFe] Error fetching pagina {page}: {e}", file=sys.stderr)
            continue

        print(f"  [VentaFe] HTML size pag {page}: {len(html)}", file=sys.stderr)

        # Split por class="row item tipo-N" (estructura de avisos)
        page_blocks = _re.split(r'class="row item tipo-\d+"', html)[1:]
        print(f"  [VentaFe] Blocks pag {page}: {len(page_blocks)}", file=sys.stderr)
        all_blocks.extend(page_blocks)

        if page < TOTAL_PAGES:
            time.sleep(3)  # CAMBIO QWEN v2.7: rate limit entre paginas (no saturar)

    blocks = all_blocks
    print(f"  [VentaFe] Total blocks acumulados: {len(blocks)}", file=sys.stderr)
    
    leads = []
    seen_phones = set()
    
    for block in blocks:
        # Limpiar HTML
        text = _re.sub(r'<[^>]+>', ' ', block)
        # FIX ENCODING: usar html.unescape() para decodificar entidades HTML correctamente.
        # Antes se hacia _re.sub(r'&[a-z]+;', ' ', text) que reemplazaba TODAS las entidades
        # con un espacio, rompiendo palabras como "transferencia" → "tran ferencia".
        import html as _html_mod
        text = _html_mod.unescape(text)
        text = _re.sub(r'&[a-z]+;', ' ', text)  # Limpiar entidades residuales no decodificables
        text = _re.sub(r'googletag[^;]+;', '', text)
        text = _re.sub(r'\s+', ' ', text).strip()

        if len(text) < 50:
            continue
        
        # Extraer telefonos con regex federal
        raw_phones = _re.findall(r'\(?0?(?:342|341|351|261|221|381|299|11)\)?[\s\-]?\d{6,10}', text)
        valid_phones = []
        for p in raw_phones:
            norm = normalize_ar_phone_ventafe(p)
            if norm and norm not in seen_phones:
                valid_phones.append(norm)
                seen_phones.add(norm)
        
        if not valid_phones:
            continue
        
        # Detectar keywords de dolor o "papeles al dia"
        pain_points = []
        if _re.search(r'multa|deuda|infraccion|patente', text, _re.IGNORECASE):
            pain_points.append('MULTA/DEUDA')
        if _re.search(r'listo para transferir|papeles al dia|papeles al d\u00eda|libre de deuda', text, _re.IGNORECASE):
            pain_points.append('PAPELES_OK')
        
        has_wa_keyword = bool(_re.search(r'whatsapp|wsp|wsp|cel', text, _re.IGNORECASE))
        
        # Titulo: primeras palabras del texto
        title = text[:80].strip()

        # FIX QWEN v2.8: URL unica REAL del aviso (3 estrategias en cascada).
        # 1) href real del HTML (lo mas confiable: VentaFe ya arma el slug correcto)
        # 2) Si no hay href, construir desde #ID del bloque + slug del titulo
        # 3) Si tampoco hay #ID, anchor por telefono (ultimo recurso)
        href_match = _re.search(r'href="(/automoviles/(\d+)-[^"]+)"', block)
        if href_match:
            unique_url = "https://www.ventafe.com.ar" + href_match.group(1)
            aviso_id = href_match.group(2)
        else:
            # Estrategia 2: construir URL desde #ID + slug del titulo
            id_match = _re.search(r'#(\d{6,8})', block)
            if id_match:
                aviso_id = id_match.group(1)
                slug = _re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60] or 'aviso'
                unique_url = f"https://www.ventafe.com.ar/automoviles/{aviso_id}-{slug}"
            else:
                # Estrategia 3: anchor por telefono
                phone_slug = _re.sub(r'\D', '', valid_phones[0])
                unique_url = f"https://www.ventafe.com.ar/automoviles#tel-{phone_slug}"
                aviso_id = phone_slug

        # FIX PERSONA: cada lead VentaFe tiene un identificador unico (aviso_id o telefono)
        # para que no aparezcan todos como "u/Vendedor VentaFe" en el dashboard.
        # Formato: "Vendedor #{aviso_id}" o "Vendedor tel XXXX"
        phone_display = valid_phones[0][-4:] if valid_phones else "????"
        persona_label = f"Vendedor #{aviso_id}" if aviso_id and aviso_id.isdigit() else f"Vendedor tel …{phone_display}"

        # FIX GEMINI TUNEL DETALLE: Scrapear pagina de detalle del aviso para extraer patente.
        # VentaFe NO muestra patentes en el listado, solo en la pagina de detalle.
        # Sin esto, el tunel de clasific.ar nunca se activa porque PATENTE_DETECTED=False.
        # Solo se consulta si unique_url apunta a /automoviles/{id}-{slug} (no anchor).
        patentes_detectadas = []
        if unique_url and "/automoviles/" in unique_url and "#" not in unique_url:
            try:
                detail_req = _urq.Request(unique_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                    'Accept-Language': 'es-AR,es;q=0.9',
                })
                with _urq.urlopen(detail_req, timeout=8) as detail_resp:
                    detail_html = detail_resp.read().decode('utf-8', errors='replace')

                # Limpiar HTML del detalle
                detail_clean = _re.sub(r'<[^>]+>', ' ', detail_html)
                detail_clean = _html_mod.unescape(detail_clean)
                detail_clean = _re.sub(r'\s+', ' ', detail_clean)

                # Regex patentes AR: SOLO formato Mercosur (AA111AA) — 2 letras + 3 digitos + 2 letras.
                # El formato viejo (AAA111) causa falsos positivos (CEL342, CON270, DIR342, etc.)
                # que son abreviaciones seguidas de codigos de area.
                patentes_raw = _re.findall(r'\b([a-zA-Z]{2}\s?\d{3}\s?[a-zA-Z]{2})\b', detail_clean)
                patentes_detectadas = list(set(p.replace(" ", "").upper() for p in patentes_raw if len(p.replace(" ", "")) == 7))

                if patentes_detectadas:
                    print(f"  [VentaFe Detail] Aviso #{aviso_id}: patentes={patentes_detectadas[:3]}", file=sys.stderr)

                time.sleep(0.7)  # Cortesia entre requests (evitar bloqueo IP)
            except Exception as detail_err:
                print(f"  [VentaFe Detail] Error aviso #{aviso_id}: {detail_err}", file=sys.stderr)

        # Patentes finales: las del detalle (prioridad) + las del listado (fallback)
        patentes_finales = patentes_detectadas if patentes_detectadas else _re.findall(r'\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b', text)

        # FIX GEMINI VIA B: Triangulación Cross-Platform Matcher.
        # Si no se encontró patente en VentaFe (listado ni detalle), intentar
        # buscar la publicación espejo en MercadoLibre por marca+modelo+kilometraje.
        # Solo se hace si no hay patentes todavía (para no gastar cuota innecesariamente).
        if not patentes_finales:
            mileage_match = _re.search(r"\b(\d{2,3}\.\d{3})\s*(?:km|kms)\b", text, _re.IGNORECASE)
            if mileage_match:
                mileage_val = mileage_match.group(1)
                title_words = title.split()
                brand_guess = title_words[0] if title_words else ""
                model_guess = title_words[1] if len(title_words) > 1 else ""
                triangulated_plate = try_triangulate_plate(brand_guess, model_guess, mileage_val, "Santa Fe")
                if triangulated_plate:
                    patentes_finales = [triangulated_plate]

        lead = {
            "name": f"[VentaFe] {title}",
            "url": unique_url,
            "source_url": unique_url,  # Para dedup estable entre runs
            "snippet": text[:500],
            "date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            "host_name": "ventafe.com.ar",
            "username": persona_label,
            "author": persona_label,
            "source": "ventafe",
            "_query": "ventafe_automoviles",
            "telefonos": valid_phones,
            "patentes": patentes_finales,
            "problemas": pain_points,
            "zona": "Santa Fe",
            "aviso_id": aviso_id,
        }
        leads.append(lead)
    
    print(f"  [VentaFe] Extraidos {len(leads)} leads con telefonos validos", file=sys.stderr)
    return leads

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
            # FIX QWEN v2.9: Forzar 'argentina' en queries Reddit para reducir ruido foreign.
            # f-string segura, evita dobles espacios y queries mal formadas.
            clean_q = query.lower().replace("site:reddit.com", "").strip()
            if "argentina" not in clean_q:
                clean_q = f"{clean_q} argentina"
            results, got_429 = search_reddit_with_status(
                clean_q,
                num=MAX_RESULTS_PER_QUERY
            )
            if got_429 and _pqm_global:
                rss_url = f"https://www.reddit.com/search.rss?q={clean_q}"
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
        ml_leads = search_mercadolibre_questions(num=50)  # CAMBIO QWEN v2.7: era 15, ahora 50
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

    # VentaFe Scraper (portal de clasificados del interior - SANTA FE ORO)
    # FIX GEMINI: eliminar llamada duplicada (estaba 2 veces, scrapendo 5 paginas x2 = 15s perdido)
    try:
        ventafe_results = scrape_ventafe_leads()
        if ventafe_results:
            all_results.extend(ventafe_results)
            print(f"  [VentaFe] +{len(ventafe_results)} leads inyectados", file=sys.stderr)
    except Exception as e:
        print(f"  [VentaFe] ERROR: {e}", file=sys.stderr)

    # FIX GEMINI MEJORA 2: Dorking Facebook grupos A+B sin cookies.
    # Los buscadores indexan posts de grupos públicos de Facebook, permitiendo
    # extraer fragmentos con teléfonos sin necesidad de sesión/cookies.
    fb_dorks = [
        # Grupo A: Defensa contra multas de tránsito
        'site:facebook.com/groups/276074287942602 "multa" OR "fotomulta" "11" OR "342" OR "341"',
        # Grupo B: Venta de Autos Santa Fe y Alrededores
        'site:facebook.com/groups/1314803566577708 "debe" OR "deuda" OR "08" OR "fallecido" "342" OR "15"',
    ]
    print("[OSINT] Dorking grupos Facebook (sin cookies)...", file=sys.stderr)
    for dork in fb_dorks:
        try:
            print(f"  [FB Dork] {dork[:70]}", file=sys.stderr)
            fb_results = web_search(dork, num=8)
            for r in fb_results:
                r["_query"] = "facebook_group_direct_dork"
                r["source"] = "facebook_groups"
                r["host_name"] = "facebook.com"
            all_results.extend(fb_results)
            if fb_results:
                print(f"  [FB Dork] +{len(fb_results)} resultados", file=sys.stderr)
            time.sleep(2.0)
        except Exception as e:
            print(f"  [FB Dork] Error: {e}", file=sys.stderr)

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
    # FIX GEMINI Sabueso: verificar 08 con word boundary (no matchear '308', '2016', etc.)
    is_ventafe = "ventafe.com.ar" in url or result.get("source") == "ventafe" or result.get("host_name") == "ventafe.com.ar"
    has_must_match = any(kw in combined_lower for kw in MUST_INCLUDE_ONE) or bool(re.search(r"\b08\b", combined_lower))
    if not is_ventafe and not has_must_match:
        return None
    for reject in REJECT_IF_CONTAINS:
        if reject in combined_lower:
            return None

    # FILTRO DE DOMINIOS DE MEDIOS (DeepSeek v2.7)
    host = result.get("host", "") or get_host(url)
    if any(d in host for d in DISCARD_DOMAINS):
        return None

    # FIX QWEN v2.8: Filtro de subreddits de gaming
    subreddit_match = re.search(r'reddit\.com/r/([^/]+)/', url, re.IGNORECASE)
    subreddit = subreddit_match.group(1).lower() if subreddit_match else ""
    if subreddit in GAMING_SUBREDDITS:
        return None

    # FIX QWEN v2.8: Filtro de posts con 2+ keywords de gaming
    gaming_matches = sum(1 for kw in GAMING_KEYWORDS if kw in combined_lower)
    if gaming_matches >= 2:
        return None

    # FILTRO DE PAIS EXTRANJERO (DeepSeek v2.7)
    for country in REJECT_COUNTRIES:
        if country in combined_lower:
            return None

    # FILTRO DE PALABRAS CLAVE NEGATIVAS (DeepSeek v2.7)
    neg_matches = sum(1 for kw in NEGATIVE_KEYWORDS if kw in combined_lower)
    if neg_matches >= 2:
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

    # FIX BOMBA #2 (parte 2): VentaFe SIEMPRE pasa el filtro vehicular.
    # Sus avisos son comerciales (vendedor con auto en venta) y aunque no tengan
    # keywords de "dolor" (multa/transferencia), son leads válidos porque el
    # vehículo está en venta y el teléfono es público.
    is_ventafe = ('ventafe' in (result.get('source', '') or '').lower()
                  or 'ventafe.com.ar' in url
                  or result.get('host_name') == 'ventafe.com.ar')

    # Si NO es VentaFe y no hay contexto vehicular, descartar
    if not is_ventafe and vehicular_count < 2:
        return None

    # Inicializar variables de contacto
    phone = ""
    whatsapp = ""
    email = ""

    # FIX 6 (DeepSeek): Bloquear imagenes/HTML como contenido principal
    if len(combined.strip()) < 50:
        return None
    url_count = len(re.findall(r"https?://", combined))
    html_tag_count = len(re.findall(r"<[^>]+>", combined))
    if len(combined) > 0 and (url_count * 30 + html_tag_count * 10) / len(combined) > 0.5:
        return None

    # VentaFe: campos personalizados
    telefonos_ventafe = result.get('telefonos', [])
    patentes_ventafe = result.get('patentes', [])
    problemas_ventafe = result.get('problemas', [])
    zona_ventafe = result.get('zona', '')
    
    if telefonos_ventafe:
        phone = telefonos_ventafe[0]
        whatsapp = telefonos_ventafe[0]
        contacto_publico = True
    
    if patentes_ventafe:
        patent = patentes_ventafe[0]
    
    if problemas_ventafe:
        combined += ' ' + ' '.join(problemas_ventafe)
        combined_lower = combined.lower()
    
    if zona_ventafe:
        provincia = zona_ventafe

    # Extract phone (si no vino de VentaFe)
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

    # Extract email (FIX SAKANA: filtrar dominios desechables + GEMINI+KIMI: ofuscados)
    email = ""
    _DISPOSABLE = {"tempmail.com", "10minutemail.com", "guerrillamail.com",
                   "mailinator.com", "yopmail.com", "trashmail.com",
                   "dispostable.com", "fakeinbox.com", "temp-mail.org"}
    # 1. Email estándar
    m = re.search(EMAIL_PATTERN, combined)
    if m:
        candidate = m.group(1).lower().strip()
        domain = candidate.split("@")[-1] if "@" in candidate else ""
        if domain not in _DISPOSABLE:
            email = candidate
    # 2. Email ofuscado (FIX GEMINI+KIMI: "juan arroba gmail punto com")
    if not email:
        m_obf = EMAIL_OBFUSCATED_RE.search(combined)
        if m_obf:
            candidate = f"{m_obf.group(1)}@{m_obf.group(2)}.{m_obf.group(3)}".lower().strip()
            domain = candidate.split("@")[-1] if "@" in candidate else ""
            if domain not in _DISPOSABLE:
                email = candidate

    # REGEX CONTEXTUAL (GPT+H.AI consensus v2 — fix BOMBA #2):
    # Solo guardar contacto si el snippet TAMBIEN tiene keyword de dolor O es de VentaFe.
    # VentaFe publica avisos preventivos ("papeles al día", "listo para transferir")
    # que son leads comerciales válidos aunque no expresen "dolor" explícito.
    PAIN_KEYWORDS_RE = re.compile(
        r"\b(?:multa|multas|fotomulta|fotomultas|infracci[oó]n|infracciones|"
        r"libre\s+deuda|transferencia|transferir|patente|08\s+firmado|"
        r"c[eé]dula|veraz|registro\s+automotor|juez\s+de\s+faltas|"
        r"peaje|telepeaje|deuda|vencimiento|prescripci[oó]n|"
        r"papeles\s+al\s+d[ií]a|listo\s+para\s+transferir|sin\s+deuda|"
        r"titular|libre\s+de\s+multas|patente\s+al\s+d[ií]a|sin\s+multas)\b",
        re.IGNORECASE
    )
    has_pain_context = bool(PAIN_KEYWORDS_RE.search(combined))

    # FIX BOMBA #2: VentaFe = lead comercial preventivo, no descartar aunque no haya "dolor"
    is_ventafe = (result.get("source") == "ventafe"
                  or result.get("host_name") == "ventafe.com.ar"
                  or "ventafe.com.ar" in url)
    if not has_pain_context and not is_ventafe:
        # Sin contexto de dolor Y no es VentaFe → descartar contacto (no es lead, es spam)
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

    # FIX GEMINI SABUESO (Paso 2): Filtro de Admisión VentaFe (Pain o Patente).
    # Si el lead viene de VentaFe, solo ingresa al pipeline si:
    #   (a) menciona dolor vehicular explicito en el texto, O
    #   (b) tiene patente declarada (para auditar contra clasific.ar luego)
    # Avisos comunes sin dolor ni patente (ej: Peugeot 308 limpio) se descartan.
    platform_str = (record.get("platform", "") or "").lower()
    source_str = (record.get("source", "") or "").lower()
    is_vf = ("ventafe" in source_str or "ventafe" in platform_str
             or "ventafe.com.ar" in (record.get("source_url", "") or ""))

    if is_vf:
        text_for_pain = record.get("combined_text", "") or record.get("problema", "") or ""
        text_lower_vf = text_for_pain.lower()
        # FIX GEMINI HIBRIDO: Enfoque preventivo + dolor real.
        # Caso 1: Vendedor admite problemas reales → Score Alto (caliente)
        # Caso 2: Vendedor dice estar al día → Score medio (tibio, preventivo)
        # Caso 3: No menciona nada → descartar (ruido)
        has_explicit_pain = any(kw in text_lower_vf for kw in [
            "debo patente", "debe patente", "adeuda", "embargo", "inhibicion", "inhibición",
            "bloqueado", "sin 08", "08 vencido", "08 firmado en blanco",
            "titular fallecido", "no tengo el 08", "titular inubicable",
            "sucesion", "sucesión", "titular no firma", "poseedor", "denuncia de compra",
            "tarjeta rosa", "solo poseedores", "problema de papeles", "faltan papeles",
            "debo multa", "debe multa", "multas impagas", "multa pendiente",
            "me llego multa", "tengo multa", "con multas", "con deuda",
            "no puedo transferir", "transferencia bloqueada",
        ])
        is_preventive = any(kw in text_lower_vf for kw in [
            "papeles al dia", "papeles al día", "listo para transferir",
            "sin deudas", "sin multas", "libre de multas", "al dia", "al día",
            "patente paga", "patente al dia", "patente al día",
        ])
        has_patente = bool(record.get("patente"))

        if has_explicit_pain:
            score += 40
            if "DOLOR_EXPLICITO_REGISTRAL" not in signals:
                signals.append("DOLOR_EXPLICITO_REGISTRAL")
        elif is_preventive or has_patente:
            # Preventivo: score base moderado, etiqueta clara para Sergio
            score += 15
            if "PREVENTIVO_A_VERIFICAR" not in signals:
                signals.append("PREVENTIVO_A_VERIFICAR")
        else:
            # No menciona dolor ni papeles al día → descartar (ruido)
            return None

    # Boost ML Questions Radar (alta calidad - Sakana+Claude)
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

    # VentaFe: scoring especifico para clasificados
    source_str = (record.get("source", "") or "").lower()
    if 'ventafe' in source_str:
        score += 20
        breakdown['ventafe_base'] = 20
        signals.append('VENTAFE_LISTING')
        
        if record.get('patentes'):
            score += 15
            breakdown['ventafe_patente'] = 15
            signals.append('VENTAFE_PATENTE')
        
        problemas = record.get('problemas', [])
        if 'TRANSFERENCIA_BLOQUEADA' in problemas:
            score += 30
            breakdown['ventafe_transferencia'] = 30
            signals.append('VENTAFE_TRANSFERENCIA')
        if 'MULTA' in problemas:
            score += 25
            breakdown['ventafe_multa'] = 25
            signals.append('VENTAFE_MULTA')
        if 'DEUDA' in problemas:
            score += 25
            breakdown['ventafe_deuda'] = 25
            signals.append('VENTAFE_DEUDA')

    # DETECTOR DE CONTRADICCIONES (Qwen: VentaFe vs Clasific.ar)
    promesas_ok = ["papeles al dia", "papeles al día", "listo para transferir",
                   "sin deuda", "sin multas", "libre de deuda", "patente paga",
                   "todo al dia", "todo al día", "transferencia inmediata"]
    vendedor_promete_ok = any(p in text for p in promesas_ok)
    
    tiene_deuda_real = False
    if record.get("clasificar_deuda") or record.get("clasificar_multas"):
        tiene_deuda_real = True
    if any(p in text for p in ["debo patente", "tiene multas", "deuda de patente", "infracciones"]):
        tiene_deuda_real = True
    
    if vendedor_promete_ok and tiene_deuda_real:
        score += 40
        breakdown["contradiccion_detectada"] = 40
        signals.append("CONTRADICCION_VENDEDOR")
    
    admite_problema = any(p in text for p in ["debo patentes", "tiene multas", "falta el 08", "no puedo transferir"])
    if admite_problema:
        score += 30
        breakdown["admite_deuda"] = 30
        signals.append("VENDEDOR_ADMITE_PROBLEMA")

    # multa_or_fotomulta: +60
    if "multa" in text or "fotomulta" in text:
        score += SCORE_RULES["multa_or_fotomulta"]
        breakdown["multa_or_fotomulta"] = SCORE_RULES["multa_or_fotomulta"]
        signals.append("multa_fotomulta")

    # transfer_problem: +45
    # FIX GEMINI SABUESO FASE 2: Evitar inflacion de score por mencion comercial comun.
    # En VentaFe, 95% de avisos dicen "transferencia" o "transferir" sin tener dolor real.
    # Solo sumar +45 si hay palabras de traba/bloqueo (no puedo, problema, traba, etc.)
    # o si NO es VentaFe (Reddit/FB/ML si pueden mencionarlo sin contexto comercial).
    is_generic_transfer_mention = is_vf and not any(
        neg in text for neg in ["no puedo", "problema", "traba", "bloqueo", "demora",
                                 "embargo", "no se puede", "impedimento", "inhibicion"]
    )
    has_transfer_context = ("transferencia" in text or "transferir" in text
                            or "08 firmado" in text or re.search(r"\b08\b", text))
    if has_transfer_context and not is_generic_transfer_mention:
        score += SCORE_RULES["transfer_problem"]
        breakdown["transfer_problem"] = SCORE_RULES["transfer_problem"]
        signals.append("transfer_problem")

    # libre_deuda_problem: +35
    if "libre deuda" in text:
        score += SCORE_RULES["libre_deuda_problem"]
        breakdown["libre_deuda_problem"] = SCORE_RULES["libre_deuda_problem"]
        signals.append("libre_deuda")

    # 08_or_document_problem: +40 (no sumar doble con transfer)
    # FIX GEMINI Sabueso: usar \b08\b (word boundary) para no matchear '308', '2016', '110.000km'
    if re.search(r"\b08\b", text) and "libre deuda" not in text:
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

    # FIX QWEN v2.9: FILTRO ESTRICTO — Reddit SOLO Argentina.
    # Si no hay señal AR explícita en el texto Y la plataforma es Reddit,
    # descartar el lead inmediatamente (no llega al CRM).
    if record.get("platform", "").lower() == "reddit":
        ar_keywords_extra = [
            "argentina", "buenos aires", "caba", "capital federal", "cordoba",
            "cordoba", "santa fe", "rosario", "mendoza", "entre rios",
            "neuquen", "salta", "la plata", "arba", "dnrpa", "rentas",
            "pba", "gba", "patente argentina", "parana", "tigre",
            "avellaneda", "quilmes", "moron", "pilar",
        ]
        if not has_arg_signal and not any(kw in text for kw in ar_keywords_extra):
            return None  # Descarte inmediato, no llega al CRM

    # FIX GEMINI: Validación cruzada geográfica código de área vs provincia.
    # Si el teléfono empieza con 342 (Santa Fe) pero provincia dice "Córdoba",
    # hay inconsistencia → penalizar levemente y marcar signal.
    if record.get("telefono_publico") and record.get("provincia"):
        AREA_PROV_MAP = {
            '342': 'Santa Fe', '341': 'Santa Fe',
            '351': 'Córdoba', '261': 'Mendoza',
            '221': 'Buenos Aires', '11': 'CABA',
            '381': 'Tucumán', '299': 'Neuquén',
        }
        clean_num = re.sub(r"^\+?54\s?9?", "", record["telefono_publico"]).lstrip('0')
        for code, prov in AREA_PROV_MAP.items():
            if clean_num.startswith(code):
                rec_prov_norm = record["provincia"].lower().strip()
                prov_norm = prov.lower().strip()
                if prov_norm not in rec_prov_norm and rec_prov_norm not in prov_norm:
                    signals.append('ORIGEN_MISMATCH')
                    score -= 10
                    breakdown["origen_mismatch"] = -10
                break

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

    # --- PATENTE DETECTION (FIX GEMINI: regex federal con soporte para espacios) ---
    # Soporta: AA111AA, AA 111 AA, AAA111, AAA 111 (mayusculas y minusculas).
    # Comun en ML Q&A y Reddit donde usuarios escriben "AA 111 AA" con espacios.
    patente_clean_text = record.get("combined_text", "")
    patente_match = re.search(r"\b([A-Za-z]{2}\s?\d{3}\s?[A-Za-z]{2}|[A-Za-z]{3}\s?\d{3})\b", patente_clean_text)
    if patente_match:
        # Limpiar espacios y normalizar a mayusculas
        norm_plate = re.sub(r"\s+", "", patente_match.group(1)).upper()
        record["patente"] = norm_plate
        score += 15
        breakdown["patente_detected"] = 15
        if "PATENTE_DETECTED" not in signals:
            signals.append("PATENTE_DETECTED")
        # Marcar para enriquecimiento automatico con clasific.ar

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
    # FIX BOMBA #2 (parte 3): ampliar con keywords preventivas de VentaFe
    has_explicit_pain = any(kw in text for kw in [
        "multa", "multas", "fotomulta", "fotomultas",
        "infraccion", "infracciones", "infracción", "infracciones",
        "libre deuda", "transferencia", "transferir",
        "patente", "08 firmado", "cedula", "cedula verde",
        "veraz", "registro automotor", "juez de faltas",
        "peaje", "telepeaje", "deuda",
        # Keywords preventivas (vendedores con papeles al día = lead comercial)
        "papeles al dia", "papeles al día",
        "listo para transferir", "sin deuda", "sin multas",
        "libre de multas", "patente al dia", "patente al día",
        "titular", "unica mano", "única mano",
    ])
    # VentaFe: no penalizar aunque no haya dolor (avisos comerciales válidos)
    is_ventafe_rec = (record.get("source", "") == "ventafe"
                      or record.get("platform", "") == "VentaFe"
                      or "ventafe.com.ar" in record.get("source_url", ""))
    if not has_explicit_pain and not is_ventafe_rec:
        score -= 50
        breakdown["no_pain_penalty"] = -50
        signals.append("NO_PAIN")
    elif is_ventafe_rec:
        # VentaFe siempre es lead comercial si tiene contacto
        has_explicit_pain = True
        signals.append("VENTAFE_LEAD")

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

    # FIX QWEN v2: Los preventivos sin deuda comprobada NUNCA son calientes.
    # Capar score a 42 para que aparezcan como tibio/frío, no como 🔥.
    # Si además no tienen patente ni dolor explícito, descartar directamente.
    if "PREVENTIVO_A_VERIFICAR" in signals and "DEUDA_COMPROBADA" not in signals:
        score = min(score, 42)
        if "DOLOR_EXPLICITO_REGISTRAL" not in signals and not has_patente:
            return None  # Preventivo puro sin patente ni dolor → descartar

    # --- CLASSIFY (Qwen fix P0: umbrales relajados para VentaFe) ---
    # VentaFe: leads comerciales preventivos (vendedor con auto en venta).
    # Aceptar con umbrales más bajos si tiene contacto, aunque no haya "dolor".
    # Otras fuentes: mantener lógica estricta original.
    if is_ventafe_rec:
        if score >= 40 and has_contact and not is_foreign:
            label = "real_lead"
        elif score >= 25 and has_contact and not is_foreign:
            label = "commercial_signal"
        else:
            label = "reject"
    else:
        # Lógica original para Reddit, FB, etc.
        if score >= 50 and not is_foreign and has_explicit_pain:
            label = "real_lead"
        elif score >= 30 and not is_foreign and has_explicit_pain:
            label = "commercial_signal"
        else:
            label = "reject"

    if label == "reject":
        return None

    # Problem category (FIX GEMINI HIBRIDO: etiquetado preventivo)
    if "DOLOR_EXPLICITO_REGISTRAL" in signals:
        problem_cat = "DOCUMENTATION_ISSUE"
        problem_sum = "Trámite registral complejo detectado"
    elif "PREVENTIVO_A_VERIFICAR" in signals:
        problem_cat = "PREVENTIVE_SCAN"
        problem_sum = "Preventivo — Verificación de deuda sugerida"
    elif "transferencia" in text or "transferir" in text or re.search(r"\b08\b", text):
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
        problem_sum = "Lead vehicular calificado"

    # WhatsApp link (Qwen fix: normalizar a E.164)
    wa_link = ""
    wa_num = record.get("whatsapp_publico", "") or record.get("telefono_publico", "")
    if wa_num:
        normalized = phone_to_e164(wa_num)
        if normalized and normalized.startswith("+54"):
            wa_link = f"https://wa.me/{normalized[1:]}"
        else:
            digits = re.sub(r"\D", "", wa_num)
            if len(digits) >= 8:
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
        # FIX BOMBA #2 (parte 4): Para VentaFe, incluir telefono en el composite
        # para que cada vendedor tenga su propio ID (todos comparten URL base).
        components = [lead.source_url or lead.quoted_text[:50]]
        if lead.telefono_publico or lead.whatsapp_publico:
            components.append(lead.telefono_publico or lead.whatsapp_publico)
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


def enrich_contacts_via_reddit_profile(leads: List[Lead]) -> int:
    """Busca links a otras plataformas en el perfil de Reddit y rastrea contactos."""
    import urllib.request as _urq
    enriched = 0
    worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
    ingest_secret = os.environ.get("INGEST_SECRET", "")
    if not ingest_secret:
        return 0

    for lead in leads:
        if lead.whatsapp_publico or lead.telefono_publico or lead.email_publico:
            continue
        if lead.platform != "Reddit":
            continue
        username = lead.persona.replace("u/", "").strip()
        if len(username) < 3:
            continue

        try:
            profile_url = f"{worker_url}/api/reddit-profile-links?user={username}"
            req = _urq.Request(profile_url)
            req.add_header("X-Webhook-Secret", ingest_secret)
            req.add_header("Accept", "application/json")
            with _urq.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if not data.get("ok") or not data.get("links"):
                    continue

                for link in data["links"][:5]:
                    snippet = ""
                    try:
                        search_results = provider_search(f"site:{link}", num=2)
                        for sr in search_results:
                            snippet += sr.get("snippet", "") + " "
                    except Exception:
                        continue

                    for pat in ARG_PHONE_PATTERNS:
                        m = re.search(pat, snippet)
                        if m:
                            digits = re.sub(r"\D", "", m.group(0))
                            if 10 <= len(digits) <= 15:
                                lead.telefono_publico = m.group(0).strip()
                                lead.contacto_publico = True
                                lead.score = min(100, lead.score + 30)
                                if "PROFILE_LINK_MINING" not in (lead.detected_signals or []):
                                    lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_LINK_MINING"]
                                enriched += 1
                                break
                    if not lead.telefono_publico:
                        m = re.search(EMAIL_PATTERN, snippet)
                        if m:
                            lead.email_publico = m.group(1).lower().strip()
                            lead.contacto_publico = True
                            lead.score = min(100, lead.score + 15)
                            if "PROFILE_LINK_MINING" not in (lead.detected_signals or []):
                                lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_LINK_MINING"]
                            enriched += 1
                time.sleep(0.5)
        except Exception:
            continue
    if enriched:
        print(f"  [ProfileLinkMining] {enriched} leads enriquecidos", file=sys.stderr)
    return enriched


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

    # Step 4.5: Tunel de Auditoria clasific.ar (FIX GEMINI Tunel Automatico)
    # Antes: solo score >= 70 con patente → VentaFe preventivos (score 40) nunca se consultaban
    # Ahora: consultar si (score >= 70 con patente) OR (VentaFe con patente, sin importar score)
    # Esto permite auditar deuda real de leads preventivos que arrancan con score 40.
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        ingest_secret = os.environ.get("INGEST_SECRET", "")
        if ingest_secret:
            enriched_count = 0
            deuda_comprobada_count = 0
            import urllib.request as _urq3
            for lead in leads:
                # FIX GEMINI TUNEL: abrir compuerta para VentaFe con patente (sin importar score)
                is_vf_lead = ("ventafe" in (lead.platform or "").lower()
                              or "ventafe" in (lead.source_url or "").lower())
                has_patente = "PATENTE_DETECTED" in (lead.detected_signals or [])
                should_enrich = has_patente and (lead.score >= 70 or is_vf_lead)
                if not should_enrich:
                    continue

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
                            lead.deuda_clasificar = v.get("deuda", 0)

                            # FIX GEMINI TUNEL — BOOST DINAMICO POR DEUDA COMPROBADA
                            # Si clasific.ar encuentra deuda > 0:
                            #   - score sube a 95 (caliente maximo)
                            #   - label reclasifica como real_lead
                            #   - signal DEUDA_COMPROBADA inyectada
                            if lead.deuda_clasificar > 0:
                                lead.score = 95
                                lead.label = "real_lead"
                                if "DEUDA_COMPROBADA" not in (lead.detected_signals or []):
                                    lead.detected_signals.append("DEUDA_COMPROBADA")
                                deuda_comprobada_count += 1
                            enriched_count += 1
                    except Exception:
                        pass
                    time.sleep(1)  # rate limit clasific.ar (200/mes)
            if enriched_count:
                print(f"  [clasific.ar] {enriched_count} leads enriquecidos, {deuda_comprobada_count} con deuda comprobada", file=sys.stderr)
    except Exception as e:
        print(f"  [clasific.ar] ERROR: {e}", file=sys.stderr)

    # FIX GEMINI SABUESO (Paso 3): Filtro de Salida VentaFe.
    # Si un lead VentaFe paso el filtro de admision (Paso 2) pero:
    #   - su texto NO mencionaba dolor explicito, Y
    #   - clasific.ar respondio deuda=0 (o no se enriquecio),
    # entonces se descarta antes de llegar al CRM de Sergio.
    filtered_leads = []
    sabueso_descartes = 0
    for lead in leads:
        is_vf_out = ("ventafe" in (lead.platform or "").lower()
                     or "ventafe" in (lead.source_url or "").lower())
        if is_vf_out:
            # FIX QWEN v2: Solo pasan si tienen dolor explícito O deuda comprobada por clasific.ar
            has_real_pain = "DOLOR_EXPLICITO_REGISTRAL" in (lead.detected_signals or [])
            has_proven_debt = ("DEUDA_COMPROBADA" in (lead.detected_signals or [])
                               or (getattr(lead, "deuda_clasificar", 0) or 0) > 0)
            if has_real_pain or has_proven_debt:
                filtered_leads.append(lead)
            else:
                sabueso_descartes += 1
                print(f"  [Sabueso Descarte] Lead {lead.id} ({lead.persona}) eliminado: preventivo sin deuda/dolor real",
                      file=sys.stderr)
                continue
        else:
            filtered_leads.append(lead)
    leads = filtered_leads
    if sabueso_descartes:
        print(f"  [Sabueso] {sabueso_descartes} leads VentaFe descartados por falta de dolor/deuda",
              file=sys.stderr)

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

    # Step 4.8: Enriquecer contactos via links del perfil de Reddit (DeepSeek v2.7)
    try:
        enrich_contacts_via_reddit_profile(leads)
    except Exception as e:
        print(f"  [ProfileLinkMining] ERROR: {e}", file=sys.stderr)

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


#===========================================================================
# VentaFe Scraper — Portal de clasificados de Santa Fe (ORO)
#===========================================================================
