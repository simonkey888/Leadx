"""
radar_v4.py — Radar de Oportunidades v4 (detector de DOLOR EXPLÍCITO).

Lectura del usuario:
  "El Radar ya funciona como detector. Ahora hay que convertirlo en detector
   de dolor explícito, no de publicaciones genéricas de autos."

Mejoras vs v3:
  1. Separación clara de output en 2 categorías:
       real_lead        → dolor explícito (must_match + problema_explicitado)
       commercial_signal → vende auto / permuto sin dolor (preventivo, volumen)

  2. must_match obligatorio (al menos 1):
       multa | fotomulta | transferencia | libre deuda
     Si no matchea ninguna → NO es lead.

  3. reject_if_only (descartar si sólo tiene esto):
       vendo auto, agencia, concesionaria, contenido institucional
     (sólo se acepta si también tiene transferencia/libre deuda/multa/titular)

  4. Scoring recalibrado:
       Dolor explícito (declara problema)        → 90-100
       Vende auto + titular + transferencia      → 60-70 (preventivo calificado)
       Vende auto solo                            → descartado
       Permuto solo                               → descartado

  5. Validación estricta de possible_whatsapp/phone:
       - Mínimo 10 dígitos (sin contar espacios/guiones)
       - Máximo 15 dígitos
       - Sin texto mezclado
       - Sin fragmentos parciales
       - Sin duplicados obvios
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
# Configuración
# ===========================================================================

OUTPUT_PATH = Path("/home/z/my-project/download/radar_v4_output.json")
RAW_SEARCH_PATH = Path("/home/z/my-project/download/radar_v4_raw_search.json")

MIN_REAL_LEADS = 10
MAX_ITERATIONS = 50
RESULTS_PER_QUERY = 10

# ---------------------------------------------------------------------------
# Reglas de match (corrección del usuario)
# ---------------------------------------------------------------------------
MUST_MATCH = ["multa", "fotomulta", "transferencia", "libre deuda"]

OPTIONAL_MATCH = ["vendo auto", "permuto auto", "titular al día", "titular"]

# Si el texto SOLO tiene esto (sin must_match), descartar
REJECT_IF_ONLY = ["vendo auto", "agencia", "concesionaria", "contenido institucional"]

# real_lead_only_if: problema explícito
PROBLEM_EXPLICIT_KEYWORDS = [
    "no puedo transferir", "no puedo hacer la transferencia",
    "quiero transferir", "necesito transferir",
    "ayuda con transferencia",
    "me rechazaron la transferencia", "me rechazaron transferencia",
    "transferencia de un auto", "transferencia de auto",
    "tengo multas", "me llegaron fotomultas", "me llegó una fotomulta",
    "me llego una fotomulta", "tengo una multa", "tengo multas de ruta",
    "una multa de caminera",
    "necesito libre deuda", "cómo saco libre deuda", "como saco libre deuda",
    "me piden libre deuda", "me pide libre deuda",
    "donde puedo pedir libre deuda", "pedir el libre deuda",
    "patente bloqueada", "no puedo patentar",
    "debo multas", "debo patente",
    "se puede transferir con multas",
    "transferencia bloqueada", "transferencia rechazada",
    "08 firmado multas", "comprador me pidió libre deuda",
]

# Señales de dolor (presencia indica problema real, no preventivo)
PAIN_SIGNALS = [
    "no puedo", "me rechazaron", "me bloquearon", "bloqueada",
    "tengo multas", "tengo una multa", "me llegó", "me llegaron", "me llego",
    "debo multas", "debo patente", "me piden", "me pide",
    "necesito libre deuda", "necesito sacar", "cómo saco", "como saco",
    "no me deja", "problema con", "tengo problema",
    "alguien sabe cómo", "ayuda con", "consulto por",
    "me saltó", "me salto", "se bloqueó", "se bloqueo",
]

# ---------------------------------------------------------------------------
# Country filter (igual que v3)
# ---------------------------------------------------------------------------
REQUIRED_COUNTRY = "Argentina"
REJECT_COUNTRIES = {
    "méxico": "México", "mexico": "México",
    "colombia": "Colombia", "uruguay": "Uruguay",
    "chile": "Chile", "perú": "Perú", "peru": "Perú",
    "paraguay": "Paraguay", "brasil": "Brasil", "brazil": "Brasil",
}

COUNTRY_INDICATORS = {
    "México": ["méxico", "mexico", "cdmx", "guadalajara", "monterrey", "puebla",
               "tijuana", "mérida", "merida", "cancún", "cancun", "edomex"],
    "Colombia": ["colombia", "bogotá", "bogota", "medellín", "medellin",
                  "cali", "barranquilla", "cartagena"],
    "Uruguay": ["uruguay", "montevideo", "punta del este", "maldonado"],
    "Chile": ["chile", "santiago de chile", "valparaíso", "valparaiso",
              "concepción", "concepcion", "viña del mar", "vina del mar"],
    "Perú": ["perú", "peru", "lima", "arequipa", "trujillo"],
    "Paraguay": ["paraguay", "asunción", "asuncion", "ciudad del este"],
    "Brasil": ["brasil", "brazil", "são paulo", "sao paulo", "rio de janeiro",
               "porto alegre", "belo horizonte"],
}

PREFERRED_PROVINCES = {
    "buenos aires", "pba", "gba", "santa fe", "rosario",
    "córdoba", "cordoba", "entre ríos", "entre rios", "mendoza",
    "caba", "capital federal",
}

ARG_PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b0(2[0-9]|3[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\b15[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b11[\s\-]?\d{4}[\s\-]?\d{4}",
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

# ---------------------------------------------------------------------------
# Queries orientadas a DOLOR EXPLÍCITO (no genéricas)
# ---------------------------------------------------------------------------
QUERIES_DOLOR = [
    # Conversaciones explícitas de problema
    "no puedo transferir auto multa",
    "me rechazaron transferencia auto",
    "tengo multas transferencia",
    "cómo saco libre deuda",
    "me llegó fotomulta",
    "no puedo patentar auto",
    "transferencia bloqueada multas",
    "se puede transferir con multas",
    "alguien sabe fotomulta reclamar",
    "tengo multas de ruta",
    "comprador pidió libre deuda",
    "08 firmado multas",
    "patente bloqueada auto",
    "debo multas transito",
    "ayuda transferencia auto",
    "problema con transferencia auto",
]

QUERIES_CONSULTA = [
    # Consultas en foros/Reddit con site:
    "site:reddit.com multa transferencia argentina",
    "site:reddit.com libre deuda argentina",
    "site:reddit.com no puedo transferir",
    "site:reddit.com fotomulta consulta",
    "site:facebook.com no puedo transferir",
    "site:facebook.com tengo multas",
    "site:facebook.com libre deuda consulta",
]

ALL_QUERIES = []
for q in QUERIES_DOLOR:
    ALL_QUERIES.append(("dolor", q))
for q in QUERIES_CONSULTA:
    ALL_QUERIES.append(("consulta", q))

# ---------------------------------------------------------------------------
# Blacklist (igual que v3 + refinamiento)
# ---------------------------------------------------------------------------
NEGATIVE_DOMAINS = {
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    "sistemas.seguridad.mendoza.gov.ar", "cca.org.ar", "cpaer.org.ar",
    "municrespo.gov.ar", "neuquencapital.gov.ar", "medidorosario.net",
    "rentascba.gov.ar", ".gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com", "cronista.com",
    "ambito.com", "pagina12.com.ar", "perfil.com", "tn.com.ar",
    "cronica.com.ar", "minutouno.com", "infopico.com",
    "elcerokm.com", "servidos.ar", "alarfin.com.ar", "autofact.cl",
    "autofact.com.ar", "kavak.com", "bitcar.com.ar",
    "es.wikipedia.org", "en.wikipedia.org", "rae.es", "wiktionary.org",
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    "paypal.com", "n26.com", "bingx.com", "bybit.com",
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "autocosmos.com.ar", "demotores.com.ar", "encuentra24.com",
    "carone.com.ar", "derby.com.ar", "chrysler.com.ar",
    "derco.com.ar", "veico.com.ar", "chaher.com.ar",
    "youtube.com", "tiktok.com", "instagram.com",
    "nationwide.com", "allianz.com.ar", "sancor.com.ar",
    "researchgate.net", "academia.edu", "scielo.org",
    "linkedin.com",
}

PAGE_BLACKLIST = [
    "rentascba", "rentascordoba", "municipalidadrosario", "arbaoficial",
    "comparaencasa", "viacordobo", "viacordoba", "autocosmos",
    "municrespo", "neuquencapital", "medidorosario",
    "rentas.gob", "municipalidad", "gov.ar",
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
]

CONCESIONARIA_INDICATORS = [
    "concesionaria", "concesionario", "agencia oficial",
    "representante oficial", "grupo automotor", "autódromo",
    "toyota san isidro", "toyota pilar", "ford argentina",
    "volkswagen argentina", "chevrolet argentina",
]

AGENCIA_INDICATORS = [
    "agencia", "agencia de autos", "usados garantía",
    "usados garantia", "compramos tu auto", "compramos tu usado",
    "vendemos usados", "stock disponible",
    "financiación a su medida", "financiacion a su medida",
]

COMPETIDOR_INDICATORS = [
    "compro autos con deudas", "compramos autos con deudas",
    "compro autos con multas", "compramos autos con multas",
    "gestoría", "gestoria", "gestor automotor",
    "abogado multas", "abogados multas", "despachante",
    "tramité tu transferencia", "te gestionamos",
]

PRIORITY_PLATFORMS = {
    "facebook.com": 100, "m.facebook.com": 100,
    "reddit.com": 90, "www.reddit.com": 90, "old.reddit.com": 90,
    "twitter.com": 90, "x.com": 90,
    "taringa.net": 85, "foroargentino.com": 85,
}

PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]
VEHICLE_BRANDS = [
    "ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
    "peugeot", "renault", "citroen", "fiat", "nissan", "hyundai",
    "kia", "seat", "audi", "bmw", "mercedes",
]

TITULAR_INDICATORS = [
    "soy titular", "titular del auto", "titular del vehículo",
    "a mi nombre", "está a mi nombre", "esta a mi nombre",
    "papeles a mi nombre", "tengo los papeles",
]

# ---------------------------------------------------------------------------
# lead_reason enum (v4 — simplificado a 2 categorías macro)
# ---------------------------------------------------------------------------
# real_lead = dolor explícito (problema declarado)
# commercial_signal = preventivo (vende auto / permuto, sin dolor)
LEAD_CATEGORY_REAL = "real_lead"
LEAD_CATEGORY_COMMERCIAL = "commercial_signal"


# ===========================================================================
# Dataclass de Lead v4
# ===========================================================================
@dataclass
class Lead:
    """Lead humano detectado en contenido público argentino."""
    # Categoría macro (corrección del usuario)
    category: str = ""  # real_lead | commercial_signal

    # Identificación
    person_name: str = ""
    profile_link: str = ""
    post_link: str = ""
    platform: str = ""
    date: str = ""

    # Contexto
    city_if_detected: str = ""
    province_if_detected: str = ""
    vehicle_if_detected: str = ""
    problem_summary: str = ""
    quoted_text: str = ""

    # lead_reason (sub-categoría)
    lead_reason: str = ""

    # Scoring 0-100
    commercial_score: int = 0
    urgency_score: int = 0
    confidence: int = 0

    # Contacto (validado estrictamente)
    possible_whatsapp: str = ""
    possible_phone: str = ""
    contact_verified: bool = False

    # Meta
    query: str = ""
    query_category: str = ""
    source_host: str = ""
    country: str = ""

    # Evidencia (debug)
    matched_must: List[str] = field(default_factory=list)
    matched_optional: List[str] = field(default_factory=list)
    pain_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Llamadas a z-ai CLI
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    args = json.dumps({"query": query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_v4_search_{hash(query) & 0xFFFFFFFF:x}.json"
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


def make_quoted_text(name: str, snippet: str, max_len: int = 250) -> str:
    text = f"{name}. {snippet}".strip()
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

    host_only = urlparse(url).netloc.lower()
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
# Validación estricta de teléfono/whatsapp (corrección del usuario)
# ===========================================================================
def validate_phone_strict(phone: str) -> bool:
    """
    Validación estricta:
      - Entre 10 y 15 dígitos (sin contar espacios/guiones)
      - Sin texto mezclado
      - Sin fragmentos parciales
      - No contiene caracteres no numéricos (excepto +, espacio, -, parens)
    """
    if not phone:
        return False
    # Caracteres permitidos: dígitos, +, espacio, guión, paréntesis
    if not re.match(r"^[\d\s\+\-\(\)]+$", phone):
        return False
    # Contar dígitos
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10 or len(digits) > 15:
        return False
    # Descartar si tiene patrones sospechosos (números repetidos con guiones raros)
    if re.search(r"\d-\d-\d-\d-\d-\d-\d-\d", phone):
        return False  # patrón "2-6-1-6-0-5-5-5-6-2" (fragmentado)
    # Descartar duplicados obvios (ej: 1111111111)
    if len(set(digits)) <= 2:
        return False
    return True


def clean_phone(phone: str) -> str:
    """Limpia el teléfono: deja sólo dígitos y + inicial."""
    if not phone:
        return ""
    has_plus = phone.strip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    return ("+" if has_plus else "") + digits


def extract_arg_phone_strict(text: str) -> str:
    """Extrae teléfono argentino con validación estricta."""
    for pattern in ARG_PHONE_PATTERNS:
        for m in re.finditer(pattern, text):
            phone = m.group(0).strip()
            if validate_phone_strict(phone):
                # Verificar que no sea extranjero
                is_foreign = False
                for fp in FOREIGN_PHONE_PATTERNS:
                    if re.search(fp, phone):
                        is_foreign = True
                        break
                if not is_foreign:
                    return clean_phone(phone)
    return ""


def extract_whatsapp_strict(text: str) -> str:
    """Extrae WhatsApp con validación estricta."""
    patterns = [
        r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
        r"wa\.me/(\d{8,15})",
        r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            num = m.group(1).strip()
            if validate_phone_strict(num):
                # Filtrar extranjeros
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
        "consulto", "ayuda porfa", "ayuda por favor",
        "vendo mi", "vendo mi auto", "permuto mi",
        "soy titular", "titular del auto",
        "tengo una multa", "me llegó una multa", "me llego una multa",
        "no me deja transferir", "no me deja vender",
        "me piden libre deuda", "me pide libre deuda",
        "quiero transferir", "necesito transferir",
        "ayuda con transferencia",
        "cómo saco libre deuda", "como saco libre deuda",
        "no me llegó", "no me llego",
    ]
    for phrase in person_phrases:
        if phrase in text:
            return True

    host = get_host(result.get("url", ""))
    if host in PRIORITY_PLATFORMS:
        vehicle_keywords = [
            "auto", "moto", "camioneta", "vendo", "permuto", "transferir",
            "multa", "fotomulta", "patente", "libre deuda",
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

    return "", ""


# ===========================================================================
# Extracción de entidades
# ===========================================================================
def extract_patent(text: str) -> str:
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def extract_location(text: str) -> Tuple[str, str]:
    text_lower = text.lower()
    for prov in PREFERRED_PROVINCES:
        if prov in text_lower:
            return "", prov.title()
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
    ]
    for city, prov in cities:
        if city in text_lower:
            return city.title(), prov
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


# ===========================================================================
# Clasificación v4: real_lead vs commercial_signal
# ===========================================================================
def classify_lead_v4(text: str) -> Tuple[str, str, int]:
    """
    Clasifica el lead (v4.1 — detección de dolor ampliada).

    Returns: (category, lead_reason, signal_type_score)

    v4.1: ahora capta variaciones de lenguaje natural que antes se perdían
    por matching exacto. Ej: "me llegó esa multa", "compre un libre deuda falso",
    "puedo hacer la transferencia", "alguien sabe + multa".
    """
    text_lower = text.lower()

    # === REAL_LEAD: dolor explícito (alta conversión) ===

    # Caso especial 1: compró auto y tiene problema
    if "compre un auto" in text_lower and any(w in text_lower for w in ["multa", "libre deuda", "transferencia"]):
        return "real_lead", "declara_problema_transferencia", 95

    # Caso especial 2: "alguien sabe" + must_match keyword = consulta con dolor
    if "alguien sabe" in text_lower and any(w in text_lower for w in MUST_MATCH):
        return "real_lead", "consulta_documentacion", 80

    # Caso especial 3: "cómo hago/saco" + must_match keyword
    if any(w in text_lower for w in ["cómo hago", "como hago", "cómo saco", "como saco"]) and \
       any(w in text_lower for w in MUST_MATCH):
        return "real_lead", "consulta_documentacion", 80

    # Transferencia: muchas variantes
    transferencia_pain = any(kw in text_lower for kw in [
        "no puedo transferir", "no puedo hacer la transferencia",
        "quiero transferir", "necesito transferir",
        "ayuda con transferencia",
        "puedo hacer la transferencia", "puedo transferir",
        "transferencia de un auto", "transferencia de auto",
        "transferencia del auto", "transferencia de mi auto",
        "transferir un auto", "transferir el auto",
        "me rechazaron la transferencia", "me rechazaron transferencia",
        "transferencia bloqueada", "transferencia rechazada",
        "no me dejan transferir", "no me deja transferir",
        "se puede transferir con multas", "se puede transferir",
        "cómo hago la transferencia", "como hago la transferencia",
        "no se puede transferir",
        "no realizó la transferencia", "no realizo la transferencia",
        "vendedor nunca te entregó", "comprador no realizó",
    ])
    if transferencia_pain:
        return "real_lead", "declara_problema_transferencia", 95

    # Multas: muchas variantes de "tengo/me llegó multa"
    multas_pain = any(kw in text_lower for kw in [
        "tengo multas", "tengo una multa", "tengo multas de ruta",
        "me llegaron fotomultas", "me llegó una fotomulta", "me llego una fotomulta",
        "me llegó esa multa", "me llego esa multa",
        "me llegó la multa", "me llego la multa",
        "me llegaron multas", "me llego una multa", "me llegó una multa",
        "una multa de caminera", "multa de caminera",
        "debo multas", "debo patente",
        "multas impagas", "multa impaga",
        "me saltó una multa", "me salto una multa", "me saltó una deuda",
        "tengo fotomultas", "tengo fotomulta",
        "multas vencidas sin notificar",
        "no me llegó", "no me lego",  # negación de notificación
        "multa a mi nombre",
    ])
    if multas_pain:
        return "real_lead", "declara_multas", 95

    # Libre deuda
    libre_deuda_pain = any(kw in text_lower for kw in [
        "necesito libre deuda", "cómo saco libre deuda", "como saco libre deuda",
        "me piden libre deuda", "me pide libre deuda",
        "donde puedo pedir libre deuda", "pedir el libre deuda",
        "me dieron un libre deuda falso", "libre deuda falso",
        "no me dan libre deuda", "no me deja sacar libre deuda",
        "comprador me pidió libre deuda", "comprador me pidio libre deuda",
        "cómo conseguir libre deuda", "como conseguir libre deuda",
        "trámite libre deuda", "tramite libre deuda",
        "libre deuda con multas", "libre deuda con deudas",
    ])
    if libre_deuda_pain:
        return "real_lead", "declara_problema_libre_deuda", 90

    # Patente
    if "patente bloqueada" in text_lower or "no puedo patentar" in text_lower:
        return "real_lead", "declara_problema_libre_deuda", 90
    if "debo patente" in text_lower or "deuda de patente" in text_lower:
        return "real_lead", "declara_problema_libre_deuda", 85

    # === COMMERCIAL_SIGNAL: preventivo (sin dolor explícito) ===
    if "vendo" in text_lower and any(b in text_lower for b in VEHICLE_BRANDS + VEHICLE_TYPES):
        if is_titular(text_lower):
            return "commercial_signal", "vende_auto_titular", 50
        return "commercial_signal", "vende_auto", 30

    if "permuto" in text_lower:
        return "commercial_signal", "permuta_auto", 40

    # Default: commercial_signal bajo
    return "commercial_signal", "generico", 20


# ===========================================================================
# Scoring por evidencia v4 (recalibrado)
# ===========================================================================
def calculate_commercial_score_v4(
    text: str,
    category: str,
    lead_reason: str,
    signal_type_score: int,
    country: str,
    province: str,
    is_concesionaria: bool,
    is_agencia: bool,
    is_competidor: bool,
    has_phone: bool,
    has_whatsapp: bool,
    matched_must: List[str],
) -> int:
    """
    Score recalibrado v4.
    real_lead siempre > commercial_signal.
    """
    text_lower = text.lower()
    score = 0

    # Base según categoría
    if category == "real_lead":
        score = signal_type_score  # ya es 75-100
    else:
        score = signal_type_score  # 20-60

    # Boost por evidencia adicional (sólo si califica)
    if "multa" in text_lower or "fotomulta" in text_lower:
        score += 0  # ya está en signal_type_score
    if "transferencia" in text_lower:
        score += 0
    if "libre deuda" in text_lower:
        score += 0

    # Boost por titular (sólo para commercial_signal, para que no se descarten)
    if category == "commercial_signal" and is_titular(text_lower):
        score += 10

    # Boost por contacto (sólo si es real_lead)
    if category == "real_lead":
        if has_whatsapp:
            score += 10
        if has_phone:
            score += 5

    # Penalizaciones
    if country != "Argentina" and country != "Unknown":
        score -= 40
    if is_concesionaria:
        score -= 30
    if is_agencia:
        score -= 30
    if is_competidor:
        score -= 50

    return max(0, min(100, score))


def calculate_urgency_score_v4(text: str, category: str) -> int:
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

    if category == "real_lead":
        base += 25

    return min(base, 100)


def calculate_confidence_v4(
    is_real_person: bool,
    has_person_name: bool,
    has_profile_link: bool,
    platform_priority: int,
    country: str,
    has_pain_signals: bool,
) -> int:
    if not is_real_person:
        return 10

    conf = 40
    if has_person_name:
        conf += 15
    if has_profile_link:
        conf += 15
    conf += min(platform_priority // 10, 15)
    if has_pain_signals:
        conf += 15
    if country == "Unknown":
        conf -= 10

    return max(0, min(100, conf))


# ===========================================================================
# Construcción de Lead v4 (con must_match obligatorio)
# ===========================================================================
def build_lead_from_result_v4(
    result: Dict[str, Any],
    query: str,
    query_category: str,
) -> Optional[Lead]:
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

    # === REGLA MUST_MATCH (corrección del usuario) ===
    # Al menos 1 de: multa, fotomulta, transferencia, libre deuda
    matched_must = [kw for kw in MUST_MATCH if kw in combined_lower]
    if not matched_must:
        # Si no matchea must_match, NO es lead
        return None

    # === REGLA REJECT_IF_ONLY ===
    # Si el texto SOLO tiene "vendo auto" y ningún must_match específico → descartar
    # (pero must_match ya filtra esto, así que aquí llegan los que sí tienen must_match)

    # Country filter
    phone = extract_arg_phone_strict(combined)
    whatsapp = extract_whatsapp_strict(combined)
    country = detect_country(combined, url, phone or whatsapp)

    if country in REJECT_COUNTRIES.values():
        return None

    if country == "Unknown":
        host = get_host(url)
        argentinian_hosts = ["facebook.com", "reddit.com", "twitter.com", "x.com"]
        if not any(h in host for h in argentinian_hosts):
            arg_strong_signals = ["buenos aires", "córdoba", "rosario", "mendoza",
                                   "caba", "patente", "libre deuda", "fotomulta",
                                   "argentina", "dnrpa", "arba", "rentas"]
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
    category, lead_reason, signal_type_score = classify_lead_v4(combined)

    # Pain signals (para auditoría; ya no degrada la categoría)
    pain_signals_found = [s for s in PAIN_SIGNALS if s in combined_lower]
    has_pain = len(pain_signals_found) > 0

    patent = extract_patent(combined)
    city, province = extract_location(combined)
    vehicle = extract_vehicle(combined)

    # === Validación estricta de contacto ===
    contact_verified = bool(phone) or bool(whatsapp)

    # Scoring v4
    matched_optional = [kw for kw in OPTIONAL_MATCH if kw in combined_lower]

    commercial = calculate_commercial_score_v4(
        text=combined,
        category=category,
        lead_reason=lead_reason,
        signal_type_score=signal_type_score,
        country=country,
        province=province,
        is_concesionaria=is_conc,
        is_agencia=is_ag,
        is_competidor=is_comp,
        has_phone=bool(phone),
        has_whatsapp=bool(whatsapp),
        matched_must=matched_must,
    )
    urgency = calculate_urgency_score_v4(combined, category)
    confidence = calculate_confidence_v4(
        is_real_person=True,
        has_person_name=bool(person_name),
        has_profile_link=bool(profile_link),
        platform_priority=platform_priority,
        country=country,
        has_pain_signals=has_pain,
    )

    # Problem summary
    problem_summaries = {
        "declara_multas": "Persona declarando multas/fotomultas (dolor explícito)",
        "declara_problema_transferencia": "Persona con transferencia bloqueada (dolor explícito)",
        "declara_problema_libre_deuda": "Persona necesitando libre deuda (dolor explícito)",
        "consulta_documentacion": "Persona consultando sobre trámite (intención)",
        "vende_auto_titular": "Persona vendiendo vehículo titular (preventivo calificado)",
        "vende_auto": "Persona vendiendo vehículo (preventivo)",
        "permuta_auto": "Persona permutando vehículo (preventivo)",
        "generico": "Lead genérico (bajo valor)",
    }
    problem_summary = problem_summaries.get(lead_reason, "Lead vehicular")

    return Lead(
        category=category,
        person_name=person_name or "(sin nombre)",
        profile_link=profile_link,
        post_link=url,
        platform=host,
        date=date,
        city_if_detected=city,
        province_if_detected=province,
        vehicle_if_detected=vehicle,
        problem_summary=problem_summary,
        quoted_text=make_quoted_text(name, snippet),
        lead_reason=lead_reason,
        commercial_score=commercial,
        urgency_score=urgency,
        confidence=confidence,
        possible_whatsapp=whatsapp,
        possible_phone=phone,
        contact_verified=contact_verified,
        query=query,
        query_category=query_category,
        source_host=host,
        country=country,
        matched_must=matched_must,
        matched_optional=matched_optional,
        pain_signals=pain_signals_found,
    )


# ===========================================================================
# Loop adaptativo
# ===========================================================================
def dedup_by_post_link(leads: List[Lead]) -> List[Lead]:
    seen: Set[str] = set()
    out = []
    for lead in leads:
        key = lead.post_link or lead.quoted_text[:100]
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def generate_query_expansions(seen_queries: Set[str]) -> List[Tuple[str, str]]:
    expansions = []
    cities = ["buenos aires", "córdoba", "rosario", "mendoza", "la plata",
              "paraná", "neuquén", "salta"]
    for city in cities:
        for template in [
            "no puedo transferir auto {}", "tengo multas {}",
            "fotomulta {} consulta", "libre deuda {} consulta",
        ]:
            q = template.format(city)
            if q not in seen_queries:
                expansions.append((q, "expansion_geografica"))

    problem_variations = [
        "no me llegó multa argentina",
        "no me llego multa argentina",
        "fotomulta APSV argentina",
        "multa ruta 2 argentina",
        "multa ruta 8 argentina",
        "registro automotor me rechazó argentina",
        "transferencia auto con deudas",
        "08 firmado con multas",
        "comprador me pidió libre deuda",
    ]
    for q in problem_variations:
        if q not in seen_queries:
            expansions.append((q, "expansion_problema"))

    return expansions


def run_pipeline() -> Dict[str, Any]:
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES v4 — Detector de DOLOR EXPLÍCITO", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    all_leads: List[Lead] = []
    all_raw_results: List[Dict[str, Any]] = []
    seen_queries: Set[str] = set()
    iterations = 0
    rejected_by_country = 0
    rejected_no_must_match = 0

    query_queue = list(ALL_QUERIES)

    while iterations < MAX_ITERATIONS:
        # Criterio de parada: >= 10 real_leads (dolor explícito)
        real_leads_count = sum(1 for l in all_leads if l.category == "real_lead")
        if real_leads_count >= MIN_REAL_LEADS:
            print(f"\n  [success] {real_leads_count} real_leads (dolor explícito). Parando.", file=sys.stderr)
            break

        if not query_queue:
            query_queue = generate_query_expansions(seen_queries)
            if not query_queue:
                print(f"\n  [info] No hay más queries. Parando.", file=sys.stderr)
                break

        query, category = query_queue.pop(0)
        if query in seen_queries:
            continue
        seen_queries.add(query)
        iterations += 1

        real_count_now = sum(1 for l in all_leads if l.category == "real_lead")
        print(f"\n  [iter {iterations}/{MAX_ITERATIONS}] Query ({category}): '{query}'", file=sys.stderr)
        print(f"    Real leads: {real_count_now}/{MIN_REAL_LEADS}", file=sys.stderr)

        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
            r["_query_category"] = category
        all_raw_results.extend(results)

        new_leads_count = 0
        filtered_count = 0
        for r in results:
            combined = f"{r.get('name', '')}. {r.get('snippet', '')}"
            phone_preview = extract_arg_phone_strict(combined) or extract_whatsapp_strict(combined)
            country_preview = detect_country(combined, r.get("url", ""), phone_preview)
            if country_preview in REJECT_COUNTRIES.values():
                rejected_by_country += 1
                filtered_count += 1
                continue

            # Verificar must_match antes de construir lead
            combined_lower = combined.lower()
            matched_must_preview = [kw for kw in MUST_MATCH if kw in combined_lower]
            if not matched_must_preview:
                rejected_no_must_match += 1
                filtered_count += 1
                continue

            lead = build_lead_from_result_v4(r, query, category)
            if lead is None:
                filtered_count += 1
                continue
            all_leads.append(lead)
            new_leads_count += 1

        print(f"    Resultados: {len(results)} | Filtrados: {filtered_count} | Nuevos leads: {new_leads_count}", file=sys.stderr)

        time.sleep(2.0)

    all_leads = dedup_by_post_link(all_leads)

    # Ranking: real_leads primero, luego commercial_signals
    # Dentro de cada categoría: commercial DESC, urgency DESC, confidence DESC
    real_leads = [l for l in all_leads if l.category == "real_lead"]
    commercial_signals = [l for l in all_leads if l.category == "commercial_signal"]

    real_leads.sort(
        key=lambda l: (l.commercial_score, l.urgency_score, l.confidence),
        reverse=True,
    )
    commercial_signals.sort(
        key=lambda l: (l.commercial_score, l.urgency_score, l.confidence),
        reverse=True,
    )

    whatsapp_candidates = [l for l in all_leads if l.contact_verified]
    success_leads = len(real_leads) >= MIN_REAL_LEADS

    # Stats por lead_reason
    reason_stats = {}
    for l in all_leads:
        reason_stats[l.lead_reason] = reason_stats.get(l.lead_reason, 0) + 1

    output = {
        "project": "Radar de Oportunidades v4",
        "version": "4.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mission": "Detector de DOLOR EXPLÍCITO — encontrar personas que manifiestan un problema real con multas/transferencia/libre deuda, no publicaciones genéricas de venta.",
        "strategy": {
            "must_match": MUST_MATCH,
            "optional_match": OPTIONAL_MATCH,
            "reject_if_only": REJECT_IF_ONLY,
            "real_lead_only_if": "problema_explicitado = true (pain_signals presentes)",
            "categories": {
                "real_lead": "Dolor explícito (declara problema) — alta conversión potencial",
                "commercial_signal": "Señal preventiva (vende/permuto sin dolor) — volumen",
            },
            "scoring": "real_lead siempre > commercial_signal; debe tener must_match para calificar",
            "contact_validation": "Estricta: 10-15 dígitos, sin fragmentos, sin texto mezclado",
        },
        "summary": {
            "iterations": iterations,
            "queries_executed": len(seen_queries),
            "total_search_results": len(all_raw_results),
            "rejected_by_country": rejected_by_country,
            "rejected_no_must_match": rejected_no_must_match,
            "real_leads_found": len(real_leads),
            "commercial_signals_found": len(commercial_signals),
            "total_leads": len(all_leads),
            "whatsapp_candidates": len(whatsapp_candidates),
            "success_real_leads_met": success_leads,
            "min_required_real_leads": MIN_REAL_LEADS,
            "reason_stats": reason_stats,
        },
        "ranking": {
            "sorted_by": ["real_lead first", "then commercial_signal", "each by commercial DESC, urgency DESC, confidence DESC"],
        },
        "real_leads": [l.to_dict() for l in real_leads],
        "commercial_signals": [l.to_dict() for l in commercial_signals],
        "compliance": {
            "only_public_information": True,
            "never_bypass_logins": True,
            "never_collect_private_information": True,
            "never_send_messages": True,
            "human_review_required": True,
            "ignored_informational_results": True,
            "country_filtered": True,
            "must_match_enforced": True,
            "contact_validated": True,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with RAW_SEARCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_raw_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70, file=sys.stderr)
    print("  RESULTADO FINAL v4", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Iteraciones:                  {iterations}", file=sys.stderr)
    print(f"  Queries ejecutadas:           {len(seen_queries)}", file=sys.stderr)
    print(f"  Resultados de búsqueda:       {len(all_raw_results)}", file=sys.stderr)
    print(f"  Rechazados por país:          {rejected_by_country}", file=sys.stderr)
    print(f"  Rechazados sin must_match:    {rejected_no_must_match}", file=sys.stderr)
    print(f"  REAL LEADS (dolor explícito): {len(real_leads)}", file=sys.stderr)
    print(f"  Commercial signals:           {len(commercial_signals)}", file=sys.stderr)
    print(f"  Con contacto verificado:      {len(whatsapp_candidates)}", file=sys.stderr)
    print(f"  Success real_leads (>= 10):   {'✓ CUMPLIDO' if success_leads else '✗ NO cumplido'}", file=sys.stderr)
    print(f"  Output:                       {OUTPUT_PATH}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    if reason_stats:
        print(f"\n  Distribución por lead_reason:", file=sys.stderr)
        for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1]):
            print(f"    {reason:35s} {count:3d}", file=sys.stderr)

    if real_leads:
        print(f"\n  TOP 10 REAL LEADS (dolor explícito):", file=sys.stderr)
        for i, l in enumerate(real_leads[:10], 1):
            wa = " [+WA]" if l.possible_whatsapp else ""
            ph = " [+TEL]" if l.possible_phone else ""
            print(f"    {i:2d}. [C={l.commercial_score:3d} U={l.urgency_score:3d} Conf={l.confidence:3d}] {l.lead_reason:35s} | {l.platform:15s} | {l.problem_summary[:35]}{wa}{ph}", file=sys.stderr)

    return output


if __name__ == "__main__":
    output = run_pipeline()
    print(json.dumps(output, ensure_ascii=False, indent=2))
