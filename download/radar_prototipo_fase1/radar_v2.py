"""
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
