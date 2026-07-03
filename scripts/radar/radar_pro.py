"""
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
