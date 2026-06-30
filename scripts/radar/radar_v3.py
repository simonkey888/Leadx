"""
radar_v3.py — Radar de Oportunidades v3 (scoring por evidencia + country filter + lead_reason).

Mejoras vs v2:
  1. Scoring por evidencia (no solo keywords):
     +60 menciona multas/fotomultas
     +40 menciona transferencia
     +30 menciona libre deuda
     +25 es titular del vehículo
     +20 publica teléfono o WhatsApp
     +15 publicación menor a 30 días
     +10 provincia cubierta por el servicio
     -40 otro país
     -30 concesionaria
     -30 agencia
     -50 competidor

  2. Country filter duro:
     required_country: Argentina
     reject_if_detected: México, Colombia, Uruguay, Chile, Perú, Paraguay, Brasil
     preferred_provinces: Buenos Aires, Santa Fe, Córdoba, Entre Ríos, Mendoza, CABA

  3. lead_reason enum (clasifica por qué vale la pena el lead):
     - declara_multas
     - declara_problema_transferencia
     - declara_problema_libre_deuda
     - vende_auto
     - permuta_auto
     - consulta_documentacion
     - potencial_preventivo

  4. Tabla de puntajes por tipo de señal:
     "No puedo transferir"                    100
     "Tengo multas/fotomultas"                100
     "Necesito libre deuda"                    95
     "Me rechazaron la transferencia"          95
     "Problema con patente"                    90
     "Vendo auto" + titular                    70
     "Permuto auto"                            60
     "Compro autos con deudas"                 40 (competidor/intermediario)

  5. Queries cambian de "vendo auto" a conversaciones de problema:
     "no puedo transferir el auto"
     "me saltó una deuda de patente"
     "cómo saco el libre deuda"
     "me llegaron fotomultas"
     "el comprador me pidió el libre deuda"
     "no puedo hacer la transferencia por una multa"
     "alguien sabe cómo reclamar una fotomulta"
     "tengo multas de ruta"
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

OUTPUT_PATH = Path("/home/z/my-project/download/radar_v3_output.json")
RAW_SEARCH_PATH = Path("/home/z/my-project/download/radar_v3_raw_search.json")

MIN_REAL_LEADS = 10
MIN_WHATSAPP_CANDIDATES = 3
MAX_ITERATIONS = 50
RESULTS_PER_QUERY = 10

# ---------------------------------------------------------------------------
# Country filter (corrección del usuario)
# ---------------------------------------------------------------------------
REQUIRED_COUNTRY = "Argentina"

REJECT_COUNTRIES = {
    "méxico": "México", "mexico": "México",
    "colombia": "Colombia",
    "uruguay": "Uruguay",
    "chile": "Chile",
    "perú": "Perú", "peru": "Perú",
    "paraguay": "Paraguay",
    "brasil": "Brasil", "brazil": "Brasil",
}

# Indicadores geográficos de otros países (en snippet o URL)
COUNTRY_INDICATORS = {
    "México": [
        "méxico", "mexico", "cdmx", "guadalajara", "monterrey", "puebla",
        "tijuana", "mérida", "merida", "cancún", "cancun",
        "estado de méxico", "edomex",
        ".mx",  # TLD
    ],
    "Colombia": [
        "colombia", "bogotá", "bogota", "medellín", "medellin",
        "cali", "barranquilla", "cartagena",
        ".co",
    ],
    "Uruguay": [
        "uruguay", "montevideo", "punta del este", "maldonado",
        ".uy",
    ],
    "Chile": [
        "chile", "santiago de chile", "valparaíso", "valparaiso",
        "concepción", "concepcion", "viña del mar", "vina del mar",
        ".cl",
    ],
    "Perú": [
        "perú", "peru", "lima", "arequipa", "trujillo",
        ".pe",
    ],
    "Paraguay": [
        "paraguay", "asunción", "asuncion", "ciudad del este",
        ".py",
    ],
    "Brasil": [
        "brasil", "brazil", "são paulo", "sao paulo", "rio de janeiro",
        "salvador bahia", "porto alegre", "belo horizonte",
        ".br",
    ],
}

# Provincias argentinas preferidas (corrección del usuario)
PREFERRED_PROVINCES = {
    "buenos aires", "pba", "gba",
    "santa fe", "rosario",
    "córdoba", "cordoba",
    "entre ríos", "entre rios", "paraná", "parana", "concordia",
    "mendoza",
    "caba", "capital federal", "ciudad autónoma",
}

# Indicadores telefónicos de otros países (ladas)
PHONE_COUNTRY_CODES = {
    # Argentina: +54, 0xx, 11, 15
    "argentina": ["+54", "549", "011", "0221", "023", "029", "034", "035",
                  "037", "038", "026", "029", "11", "15", "221", "341",
                  "351", "261", "380", "381", "388", "370", "379", "362",
                  "364", "280", "291", "299", "340", "342", "343", "345",
                  "348", "363", "376", "383", "385", "387", "388",
                  # Sin 0: 11, 15, 221, 341, 351, 261, 280, 291, 299, etc.
                  ],
    "México": ["+52", "52", "55", "56", "33", "81"],  # ladas MX
    "Colombia": ["+57", "57", "60", "31"],
    "Uruguay": ["+598", "598", "2 ", "09"],
    "Chile": ["+56", "56", "2 ", "9 "],
    "Perú": ["+51", "51", "1 ", "9 "],
    "Paraguay": ["+595", "595", "21", "09"],
    "Brasil": ["+55", "55", "11", "21", "31", "41", "51", "61", "71", "81", "85", "91"],
}

# ---------------------------------------------------------------------------
# Tabla de puntajes por tipo de señal (corrección del usuario)
# ---------------------------------------------------------------------------
SIGNAL_TYPE_SCORES = {
    "no_puede_transferir": 100,
    "tiene_multas_fotomultas": 100,
    "necesita_libre_deuda": 95,
    "rechazaron_transferencia": 95,
    "problema_patente": 90,
    "vende_auto_titular": 70,
    "permuto_auto": 60,
    "compra_con_deudas": 40,  # competidor/intermediario
}

# ---------------------------------------------------------------------------
# lead_reason enum (corrección del usuario)
# ---------------------------------------------------------------------------
LEAD_REASONS = [
    "declara_multas",
    "declara_problema_transferencia",
    "declara_problema_libre_deuda",
    "vende_auto",
    "permuta_auto",
    "consulta_documentacion",
    "potencial_preventivo",
]

# ---------------------------------------------------------------------------
# Scoring por evidencia (corrección del usuario)
# ---------------------------------------------------------------------------
SCORE_EVIDENCE = {
    "menciona_multas": +60,
    "menciona_transferencia": +40,
    "menciona_libre_deuda": +30,
    "es_titular": +25,
    "publica_contacto": +20,
    "publicacion_reciente": +15,
    "provincia_cubierta": +10,
    "otro_pais": -40,
    "concesionaria": -30,
    "agencia": -30,
    "competidor": -50,
}

# ---------------------------------------------------------------------------
# Queries: ahora conversaciones de problema (mayor conversión potencial)
# ---------------------------------------------------------------------------
QUERIES_PROBLEMA = [
    # Conversaciones de problema (tasas de conversión altas)
    # Site-specific para garantizar conversaciones humanas
    "site:reddit.com multa argentina",
    "site:reddit.com transferencia auto argentina",
    "site:reddit.com libre deuda",
    "site:reddit.com fotomulta",
    "site:facebook.com no puedo transferir auto",
    "site:facebook.com tengo multas",
    "site:facebook.com libre deuda consulta",
    "site:facebook.com fotomulta reclamo",
    # Sin site: pero con frases humanas
    "no puedo transferir el auto multa",
    "me rechazaron transferencia auto",
    "tengo multas impagas transferir",
    "cómo saco libre deuda argentina",
    "alguien sabe fotomulta reclamar",
    "tengo multas de ruta argentina",
    "me llegó fotomulta argentina",
    "no puedo patentar auto argentina",
    "transferencia auto con multas",
    "08 firmado multas argentina",
]

QUERIES_EVENTO_ANTERIOR = [
    # Evento-anterior pero más específico (titular vendiendo)
    "vendo auto titular al dia",
    "vendo auto papeles al dia",
    "permuto auto titular",
    "vendo moto titular",
    "vendo auto urgente argentina",
]

QUERIES_CONSULTA = [
    # Consultas explícitas de documentación
    "cómo hago libre deuda argentina",
    "donde saco libre deuda",
    "transferir auto con multas",
    "se puede transferir con multas",
    "transferencia bloqueada multas",
    "08 firmado multas",
]

# Todas las queries (priorizar problema explícito)
ALL_QUERIES = []
for q in QUERIES_PROBLEMA:
    ALL_QUERIES.append(("problema", q))
for q in QUERIES_EVENTO_ANTERIOR:
    ALL_QUERIES.append(("evento_anterior", q))
for q in QUERIES_CONSULTA:
    ALL_QUERIES.append(("consulta", q))

# ---------------------------------------------------------------------------
# Blacklist de dominios informativos / comerciales
# ---------------------------------------------------------------------------
NEGATIVE_DOMAINS = {
    # Organismos oficiales (.gov.ar — son informativos, no leads humanos)
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    "sistemas.seguridad.mendoza.gov.ar", "cca.org.ar", "cpaer.org.ar",
    "municrespo.gov.ar", "neuquencapital.gov.ar", "medidorosario.net",
    "rentascba.gov.ar",
    # Cualquier .gov.ar es oficial
    ".gov.ar",
    # Páginas oficiales de municipios/provincias (en facebook.com pero son oficiales)
    "rentascba", "municipalidadrosario", "rentas", "arba",
    # Empresas / comparadores / seguros
    "comparaencasa", "viacordoba", "autocosmos",
    # Noticias / medios
    "clarin.com", "lanacion.com.ar", "infobae.com", "cronista.com",
    "ambito.com", "pagina12.com.ar", "perfil.com", "tn.com.ar",
    "cronica.com.ar", "minutouno.com", "infopico.com",
    # Calculadoras / blogs / SEO
    "elcerokm.com", "servidos.ar", "alarfin.com.ar", "autofact.cl",
    "autofact.com.ar", "kavak.com", "bitcar.com.ar",
    # Wikipedia / diccionarios
    "es.wikipedia.org", "en.wikipedia.org", "rae.es", "wiktionary.org",
    # Bancos / fintech
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    "paypal.com", "n26.com", "bingx.com", "bybit.com",
    # Concesionarias / agencias (descuento -30)
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "autocosmos.com.ar", "demotores.com.ar", "encuentra24.com",
    "carone.com.ar", "derby.com.ar", "chrysler.com.ar",
    "derco.com.ar", "veico.com.ar", "chaher.com.ar",
    # YouTube / Instagram / TikTok
    "youtube.com", "tiktok.com", "instagram.com",
    # Empresas de seguros / tasaciones
    "nationwide.com", "allianz.com.ar", "sancor.com.ar",
    # Académico
    "researchgate.net", "academia.edu", "scielo.org",
    # LinkedIn (corporativo, no leads humanos)
    "linkedin.com",
    # Sitios mexicanos / internacionales
    "facebook.com.mx", "mx.", "com.mx",
}

# Indicadores informativos (filtrar)
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

# Indicadores de concesionaria / agencia / competidor (descuentos negativos)
CONCESIONARIA_INDICATORS = [
    "concesionaria", "concesionario", "agencia oficial",
    "representante oficial", "grupo automotor",
    "autódromo", "autoedrom", "ruta", "km",
    # Marcas que suelen ser concesionarias oficiales
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

# Plataformas prioritarias (donde hay conversaciones humanas)
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

# Patrones de persona
PERSON_PATTERNS = [
    r"@(\w{3,20})",
    r"(?:por|de|autor)\s*:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})",
    r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})",
]

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

# Teléfono: códigos argentinos
ARG_PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b0(2[0-9]|3[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",  # 02x, 03x
    r"\b15[\s\-]?\d{4}[\s\-]?\d{4}",  # móvil BSAS
    r"\b11[\s\-]?\d{4}[\s\-]?\d{4}",  # móvil BSAS nuevo
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9]|37[0-9]|36[0-9]|29[0-9]|28[0-9]|22[0-9]|23[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

# Teléfonos de otros países (para rechazar)
FOREIGN_PHONE_PATTERNS = [
    r"\+52\s?\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}",  # México
    r"\b52[\s\-]?\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4}",  # México sin +
    r"\+57\s?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}",  # Colombia
    r"\+598\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",  # Uruguay
    r"\+56\s?\d{2}[\s\-]?\d{4}[\s\-]?\d{4}",  # Chile
    r"\+51\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",  # Perú
    r"\+595\s?\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}",  # Paraguay
    r"\+55\s?\d{2}[\s\-]?\d{4,5}[\s\-]?\d{4}",  # Brasil
]

WHATSAPP_PATTERNS = [
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"wa\.me/(\d{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
]

FACEBOOK_PROFILE_PATTERNS = [
    r"facebook\.com/[^/\s\"']{5,50}",
]

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]

VEHICLE_BRANDS = [
    "ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
    "peugeot", "renault", "citroen", "fiat", "nissan", "hyundai",
    "kia", "seat", "audi", "bmw", "mercedes",
]

# Marcadores de titulariedad (para +25 es_titular)
TITULAR_INDICATORS = [
    "soy titular", "titular del auto", "titular del vehículo",
    "a mi nombre", "está a mi nombre", "esta a mi nombre",
    "papeles a mi nombre", "papeles a mi disposal",
    "tengo los papeles", "los papeles están",
]


# ===========================================================================
# Dataclass de Lead v3
# ===========================================================================
@dataclass
class Lead:
    """Lead humano detectado en contenido público argentino."""
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

    # Scoring 0-100
    commercial_score: int = 0
    urgency_score: int = 0
    confidence: int = 0

    # lead_reason (corrección del usuario)
    lead_reason: str = ""

    # signal_type_score (tabla del usuario)
    signal_type_score: int = 0

    # Contacto
    possible_whatsapp: str = ""
    possible_phone: str = ""

    # Meta
    query: str = ""
    query_category: str = ""
    source_host: str = ""
    country: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Llamadas a z-ai CLI
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    args = json.dumps({"query": query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_v3_search_{hash(query) & 0xFFFFFFFF:x}.json"

    # Backoff exponencial para evitar rate limit 429
    for attempt in range(4):
        try:
            result = subprocess.run(
                ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
                capture_output=True, text=True, timeout=45,
            )
            if result.returncode != 0:
                stderr = result.stderr.lower()
                # 429 = rate limit, reintentar con backoff
                if "429" in stderr or "too many requests" in stderr:
                    wait = 5 * (attempt + 1) * 2  # 10s, 20s, 40s
                    print(f"    [rate-limit] esperando {wait}s antes de reintentar (intento {attempt+1}/4)", file=sys.stderr)
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
# Country filter (corrección del usuario)
# ===========================================================================
def detect_country(text: str, url: str, phone: str) -> str:
    """
    Detecta el país del lead.
    Returns: "Argentina" | "México" | "Colombia" | ... | "Unknown"
    """
    text_lower = text.lower()
    url_lower = url.lower()

    # 1. Por teléfono extranjero (fuerte evidencia)
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

    # 2. Por indicadores geográficos de otros países
    # Para TLDs (.mx, .co, .br, etc.) verificar que sea al final del host
    # NO matchear ".co" dentro de "comments" o ".cl" dentro de "clARin"
    from urllib.parse import urlparse as _up
    host_only = _up(url).netloc.lower()
    for country, indicators in COUNTRY_INDICATORS.items():
        for ind in indicators:
            if ind.startswith("."):
                # TLD: sólo al final del host o antes de /
                if host_only.endswith(ind) or (ind + ".") in host_only or (ind + "/") in host_only:
                    return country
            else:
                # Indicador textual: buscar en texto completo
                if ind in text_lower:
                    return country

    # 3. Por código telefónico argentino
    for pat in ARG_PHONE_PATTERNS:
        if re.search(pat, text):
            return "Argentina"

    # 4. Por provincias argentinas
    for prov in PREFERRED_PROVINCES:
        if prov in text_lower:
            return "Argentina"

    # 5. Por TLD .ar
    if ".ar" in url_lower and "com.ar" not in url_lower:
        # com.ar es comercial, no necesariamente argentina, pero pesa
        return "Argentina"

    return "Unknown"


def is_argentina(country: str) -> bool:
    return country == "Argentina"


# ===========================================================================
# Filtros informativos / comerciales
# ===========================================================================
def is_informational(result: Dict[str, Any]) -> bool:
    url = result.get("url", "").lower()
    host = get_host(result.get("url", ""))
    snippet = (result.get("snippet", "") or "").lower()
    name = (result.get("name", "") or "").lower()
    combined = f"{snippet} {name}"

    # 1. Blacklist de dominios
    for excl in NEGATIVE_DOMAINS:
        if excl in host:
            return True

    # 1b. Blacklist de nombres de página (para páginas oficiales dentro de facebook.com)
    # Se checkea en la URL completa porque facebook.com/rentascba pasa el filtro de dominio
    page_blacklist = [
        "rentascba", "rentascordoba", "municipalidadrosario", "arbaoficial",
        "comparaencasa", "viacordobo", "viacordoba", "autocosmos",
        "municrespo", "neuquencapital", "medidorosario",
        "rentas.gob", "municipalidad", "gov.ar",
    ]
    for excl in page_blacklist:
        if excl in url:
            return True

    # 2. Indicadores informativos
    for ind in INFORMATIONAL_INDICATORS:
        if ind in combined:
            return True

    # 3. Títulos tipo artículo
    article_patterns = [
        r"^(c[oó]mo|gu[íi]a|mejores?|consejos?|tips?|todo lo que|pasos? para)",
        r"(?:calculadora|simulador|arancel|presupuesto|tarifa)",
        r"(?:tr[áa]mite|turno)\s+online",
    ]
    for pat in article_patterns:
        if re.search(pat, name):
            person_signals = [
                "vendo ", "permuto ", "tengo multa", "me llegó", "no puedo",
                "alguien sabe", "hola gente", "me rechazaron",
            ]
            if not any(s in snippet for s in person_signals):
                return True

    return False


def detect_commercial_entity(text: str) -> Tuple[bool, bool, bool]:
    """
    Detecta si el texto sugiere concesionaria, agencia, o competidor.
    Returns: (is_concesionaria, is_agencia, is_competidor)
    """
    text_lower = text.lower()
    is_conc = any(ind in text_lower for ind in CONCESIONARIA_INDICATORS)
    is_ag = any(ind in text_lower for ind in AGENCIA_INDICATORS)
    is_comp = any(ind in text_lower for ind in COMPETIDOR_INDICATORS)
    return is_conc, is_ag, is_comp


# ===========================================================================
# Detector de persona real
# ===========================================================================
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
        "me saltó", "me salto",
    ]
    for phrase in person_phrases:
        if phrase in text:
            return True

    # Plataforma prioritaria + keyword vehicular
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

    m = re.search(r"(?:por|de)\s+:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})", text)
    if m:
        return m.group(1), ""

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


def extract_arg_phone(text: str) -> str:
    """Extrae teléfono argentino (filtra extranjeros)."""
    for pattern in ARG_PHONE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            phone = m.group(0).strip()
            # Verificar que no sea de otro país
            is_foreign = False
            for fp in FOREIGN_PHONE_PATTERNS:
                if re.search(fp, phone):
                    is_foreign = True
                    break
            if not is_foreign:
                return phone
    return ""


def extract_whatsapp(text: str) -> str:
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            num = m.group(1).strip()
            # Filtrar WhatsApps extranjeros
            for fp in FOREIGN_PHONE_PATTERNS:
                if re.search(fp, num):
                    return ""  # extranjero, descartar
            return num
    return ""


def extract_facebook_profile(text: str) -> str:
    for pattern in FACEBOOK_PROFILE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return ""


def extract_location(text: str) -> Tuple[str, str]:
    """Returns: (city, province)"""
    text_lower = text.lower()
    # Buscar provincias preferidas primero
    for prov in PREFERRED_PROVINCES:
        if prov in text_lower:
            return "", prov.title()
    # Buscar localidades específicas
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
        ("concordia", "Entre Ríos"),
        ("la plata", "Buenos Aires"),
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
    """Detecta si la persona se declara titular del vehículo."""
    text_lower = text.lower()
    return any(ind in text_lower for ind in TITULAR_INDICATORS)


def is_publication_recent(date_str: str) -> bool:
    """Verifica si la publicación es menor a 30 días."""
    if not date_str:
        return False
    try:
        # Intentar parsear la fecha
        from datetime import datetime, timedelta
        # Formatos comunes: ISO, "2024-01-15", "Jan 15, 2024"
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%b %d, %Y", "%d/%m/%Y"]:
            try:
                pub_date = datetime.strptime(date_str[:20], fmt)
                if datetime.now() - pub_date < timedelta(days=30):
                    return True
                return False
            except ValueError:
                continue
    except Exception:
        pass
    return False


# ===========================================================================
# Clasificación lead_reason + signal_type (corrección del usuario)
# ===========================================================================
def classify_lead_reason(text: str) -> Tuple[str, int, str]:
    """
    Clasifica el lead según su evidencia.

    Returns: (lead_reason, signal_type_score, signal_type_label)
    """
    text_lower = text.lower()

    # Prioridad alta: declaraciones de problema explícito
    if "no puedo transferir" in text_lower or \
       "no puedo hacer la transferencia" in text_lower or \
       "quiero transferir" in text_lower or \
       "ayuda con transferencia" in text_lower or \
       "transferencia de un auto" in text_lower:
        return "declara_problema_transferencia", 100, "no_puede_transferir"

    if "me rechazaron" in text_lower and "transferencia" in text_lower:
        return "declara_problema_transferencia", 95, "rechazaron_transferencia"

    if "tengo multas" in text_lower or "me llegaron fotomultas" in text_lower or \
       "tengo multas de ruta" in text_lower or "me llegó una fotomulta" in text_lower or \
       "me llego una fotomulta" in text_lower or "tengo una multa" in text_lower or \
       "una multa de caminera" in text_lower or "multa de caminera" in text_lower:
        return "declara_multas", 100, "tiene_multas_fotomultas"

    if "libre deuda" in text_lower and \
       any(w in text_lower for w in ["necesito", "cómo saco", "como saco", "me piden", "me pide", "pedir", "solicitar", "donde"]):
        return "declara_problema_libre_deuda", 95, "necesita_libre_deuda"

    if "patente bloqueada" in text_lower or "patente" in text_lower and \
       any(w in text_lower for w in ["debo", "bloqueada", "problema", "no puedo"]):
        return "declara_problema_libre_deuda", 90, "problema_patente"

    # Competidor / intermediario
    if "compro autos con deudas" in text_lower or "compramos autos con deudas" in text_lower:
        return "potencial_preventivo", 40, "compra_con_deudas"

    # Vende auto (titular o no)
    if "vendo" in text_lower and any(b in text_lower for b in VEHICLE_BRANDS + VEHICLE_TYPES):
        if is_titular(text_lower):
            return "vende_auto", 70, "vende_auto_titular"
        return "vende_auto", 60, "vende_auto_no_titular"

    # Permuto
    if "permuto" in text_lower:
        return "permuta_auto", 60, "permuto_auto"

    # Consulta documentación
    if any(w in text_lower for w in ["cómo hago", "como hago", "alguien sabe", "consulto"]):
        return "consulta_documentacion", 50, "consulta_documentacion"

    # Preventivo: vende pero con señales de posible problema futuro
    if "vendo" in text_lower or "permuto" in text_lower:
        return "potencial_preventivo", 40, "potencial_preventivo"

    return "potencial_preventivo", 30, "generico"


# ===========================================================================
# Scoring por evidencia (corrección del usuario)
# ===========================================================================
def calculate_commercial_score_v3(
    text: str,
    lead_reason: str,
    signal_type_score: int,
    country: str,
    province: str,
    is_concesionaria: bool,
    is_agencia: bool,
    is_competidor: bool,
    has_phone: bool,
    has_whatsapp: bool,
    is_recent: bool,
) -> int:
    """
    Score por evidencia (no solo keywords).

    Tabla del usuario:
      +60 menciona multas/fotomultas
      +40 menciona transferencia
      +30 menciona libre deuda
      +25 es titular del vehículo
      +20 publica teléfono o WhatsApp
      +15 publicación menor a 30 días
      +10 provincia cubierta por el servicio
      -40 otro país
      -30 concesionaria
      -30 agencia
      -50 competidor
    """
    text_lower = text.lower()
    score = 0

    # Base: signal_type_score normalizado
    # (signal_type_score va de 30 a 100, lo llevamos a base 0-50)
    score = (signal_type_score - 30) // 2  # 30→0, 100→35
    score = max(score, 5)  # mínimo 5

    # +60 menciona multas/fotomultas
    if any(w in text_lower for w in ["multa", "fotomulta", "multas"]):
        score += 60

    # +40 menciona transferencia
    if any(w in text_lower for w in ["transferencia", "transferir"]):
        score += 40

    # +30 menciona libre deuda
    if "libre deuda" in text_lower:
        score += 30

    # +25 es titular del vehículo
    if is_titular(text_lower):
        score += 25

    # +20 publica teléfono o WhatsApp
    if has_whatsapp or has_phone:
        score += 20

    # +15 publicación menor a 30 días
    if is_recent:
        score += 15

    # +10 provincia cubierta por el servicio
    if province and province.lower() in PREFERRED_PROVINCES:
        score += 10

    # -40 otro país (ya filtrado, pero por si acaso)
    if country != "Argentina" and country != "Unknown":
        score -= 40

    # -30 concesionaria
    if is_concesionaria:
        score -= 30

    # -30 agencia
    if is_agencia:
        score -= 30

    # -50 competidor
    if is_competidor:
        score -= 50

    return max(0, min(100, score))


def calculate_urgency_score_v3(text: str, lead_reason: str) -> int:
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

    # Problemas declarados son más urgentes
    if lead_reason in ("declara_multas", "declara_problema_transferencia",
                        "declara_problema_libre_deuda"):
        base += 20

    return min(base, 100)


def calculate_confidence_v3(
    is_real_person: bool,
    has_person_name: bool,
    has_profile_link: bool,
    has_post_link: bool,
    platform_priority: int,
    country: str,
) -> int:
    if not is_real_person:
        return 10

    conf = 40
    if has_person_name:
        conf += 20
    if has_profile_link:
        conf += 15
    if has_post_link:
        conf += 10
    conf += min(platform_priority // 10, 15)

    # Penalizar si no se pudo confirmar país
    if country == "Unknown":
        conf -= 10

    return max(0, min(100, conf))


# ===========================================================================
# Construcción de Lead v3
# ===========================================================================
def build_lead_from_result(
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

    # Detectar contacto (antes para usarlo en country detection)
    phone = extract_arg_phone(combined)
    whatsapp = extract_whatsapp(combined)

    # Country filter
    country = detect_country(combined, url, phone or whatsapp)

    # RECHAZO DURO: si detectamos país extranjero, descartar
    if country in REJECT_COUNTRIES.values():
        return None

    # Si Unknown y parece genérico, descartar — PERO aceptar si tiene señales
    # fuertes de persona humana (problema declarado)
    if country == "Unknown":
        host = get_host(url)
        # Hosts que suelen tener leads argentinos
        argentinian_hosts = ["facebook.com", "reddit.com", "twitter.com", "x.com"]
        if not any(h in host for h in argentinian_hosts):
            # Si no es plataforma social, requerir señal argentina fuerte
            arg_strong_signals = ["buenos aires", "córdoba", "rosario", "mendoza",
                                   "caba", "patente", "libre deuda", "fotomulta",
                                   "argentina", "dnrpa", "arba", "rentas"]
            if not any(s in combined.lower() for s in arg_strong_signals):
                return None
        # Aceptar pero marcar como Argentina (asunción razonable)
        country = "Argentina"

    # Detectar persona
    person_name, profile_link = detect_person(result)
    if not profile_link:
        fb = extract_facebook_profile(combined)
        if fb:
            profile_link = fb

    host = get_host(url)
    platform_priority = PRIORITY_PLATFORMS.get(host, 30)

    # Detectar entidades comerciales (para descuentos)
    is_conc, is_ag, is_comp = detect_commercial_entity(combined)

    # Clasificar lead_reason
    lead_reason, signal_type_score, signal_type_label = classify_lead_reason(combined)

    # Si es competidor puro, descartar (no es cliente)
    if is_comp and signal_type_label == "compra_con_deudas":
        return None

    patent = extract_patent(combined)
    city, province = extract_location(combined)
    vehicle = extract_vehicle(combined)
    is_recent = is_publication_recent(date)

    # Scoring v3 por evidencia
    commercial = calculate_commercial_score_v3(
        text=combined,
        lead_reason=lead_reason,
        signal_type_score=signal_type_score,
        country=country,
        province=province,
        is_concesionaria=is_conc,
        is_agencia=is_ag,
        is_competidor=is_comp,
        has_phone=bool(phone),
        has_whatsapp=bool(whatsapp),
        is_recent=is_recent,
    )
    urgency = calculate_urgency_score_v3(combined, lead_reason)
    confidence = calculate_confidence_v3(
        is_real_person=True,
        has_person_name=bool(person_name),
        has_profile_link=bool(profile_link),
        has_post_link=bool(url),
        platform_priority=platform_priority,
        country=country,
    )

    # Problem summary
    problem_summaries = {
        "declara_multas": "Persona declarando multas/fotomultas (alta conversión)",
        "declara_problema_transferencia": "Persona con problema de transferencia bloqueada",
        "declara_problema_libre_deuda": "Persona necesitando libre deuda",
        "vende_auto": "Persona vendiendo vehículo (preventivo)",
        "permuta_auto": "Persona permutando vehículo (preventivo)",
        "consulta_documentacion": "Persona consultando sobre trámite/documentación",
        "potencial_preventivo": "Lead preventivo (potencial necesidad futura)",
    }
    problem_summary = problem_summaries.get(lead_reason, "Lead vehicular")

    return Lead(
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
        commercial_score=commercial,
        urgency_score=urgency,
        confidence=confidence,
        lead_reason=lead_reason,
        signal_type_score=signal_type_score,
        possible_whatsapp=whatsapp,
        possible_phone=phone,
        query=query,
        query_category=query_category,
        source_host=host,
        country=country,
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

    # Expansiones geográficas argentinas
    cities = ["buenos aires", "córdoba", "rosario", "mendoza", "la plata",
              "paraná", "entre ríos", "neuquén"]
    for city in cities:
        for template in [
            "no puedo transferir auto {}", "tengo multas {}", "fotomulta {}",
            "libre deuda {}", "vendo auto titular {}",
        ]:
            q = template.format(city)
            if q not in seen_queries:
                expansions.append((q, "expansion_geografica"))

    # Expansiones de problema específico
    problem_variations = [
        "multa transito argentina consulta",
        "no me llegó la multa argentina",
        "no me llego la multa argentina",
        "fotomulta APSV",
        "multa ruta 2 argentina",
        "multa ruta 8 argentina",
        "registro automotor consulta",
        "08 firmado multas argentina",
        "comprador me pide libre deuda",
        "transferencia rechazada multas",
    ]
    for q in problem_variations:
        if q not in seen_queries:
            expansions.append((q, "expansion_problema"))

    return expansions


def run_pipeline() -> Dict[str, Any]:
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES v3 — Scoring por evidencia + Country filter", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    all_leads: List[Lead] = []
    all_raw_results: List[Dict[str, Any]] = []
    seen_queries: Set[str] = set()
    iterations = 0
    rejected_by_country = 0

    query_queue = list(ALL_QUERIES)

    while iterations < MAX_ITERATIONS:
        whatsapp_count = sum(1 for l in all_leads if l.possible_whatsapp or l.possible_phone)
        if len(all_leads) >= MIN_REAL_LEADS and whatsapp_count >= MIN_WHATSAPP_CANDIDATES:
            print(f"\n  [success] {len(all_leads)} leads + {whatsapp_count} whatsapp. Parando.", file=sys.stderr)
            break

        if not query_queue:
            query_queue = generate_query_expansions(seen_queries)
            if not query_queue:
                print(f"\n  [info] No hay más queries para expandir. Parando.", file=sys.stderr)
                break

        query, category = query_queue.pop(0)
        if query in seen_queries:
            continue
        seen_queries.add(query)
        iterations += 1

        print(f"\n  [iter {iterations}/{MAX_ITERATIONS}] Query ({category}): '{query}'", file=sys.stderr)
        print(f"    Leads hasta ahora: {len(all_leads)}/{MIN_REAL_LEADS} (whatsapp: {sum(1 for l in all_leads if l.possible_whatsapp or l.possible_phone)})", file=sys.stderr)

        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
            r["_query_category"] = category
        all_raw_results.extend(results)

        new_leads_count = 0
        filtered_count = 0
        for r in results:
            # Verificar país antes de construir lead (para contar rechazos)
            combined = f"{r.get('name', '')}. {r.get('snippet', '')}"
            phone_preview = extract_arg_phone(combined) or extract_whatsapp(combined)
            country_preview = detect_country(combined, r.get("url", ""), phone_preview)
            if country_preview in REJECT_COUNTRIES.values():
                rejected_by_country += 1
                filtered_count += 1
                continue

            lead = build_lead_from_result(r, query, category)
            if lead is None:
                filtered_count += 1
                continue
            all_leads.append(lead)
            new_leads_count += 1

        print(f"    Resultados: {len(results)} | Filtrados: {filtered_count} | Nuevos leads: {new_leads_count}", file=sys.stderr)

        # Rate limit cortés — evitar 429 del z-ai SDK
        time.sleep(2.0)

    # Dedup final
    all_leads = dedup_by_post_link(all_leads)

    # Ranking por commercial_score DESC, urgency DESC, confidence DESC
    all_leads.sort(
        key=lambda l: (l.commercial_score, l.urgency_score, l.confidence),
        reverse=True,
    )

    whatsapp_candidates = [l for l in all_leads if l.possible_whatsapp or l.possible_phone]
    success_leads = len(all_leads) >= MIN_REAL_LEADS
    success_whatsapp = len(whatsapp_candidates) >= MIN_WHATSAPP_CANDIDATES

    # Stats por lead_reason
    reason_stats = {}
    for l in all_leads:
        reason_stats[l.lead_reason] = reason_stats.get(l.lead_reason, 0) + 1

    output = {
        "project": "Radar de Oportunidades v3",
        "version": "3.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mission": "Encontrar personas reales que manifiesten públicamente un problema relacionado con multas, transferencia de vehículos, libre deuda o fotomultas. Priorizar evidencia de problema sobre keywords genéricas.",
        "strategy": {
            "scoring": "Por evidencia (no solo keywords): +60 multas, +40 transferencia, +30 libre deuda, +25 titular, +20 contacto, +15 reciente, +10 provincia, -40 otro país, -30 concesionaria, -30 agencia, -50 competidor",
            "country_filter": {
                "required_country": REQUIRED_COUNTRY,
                "rejected_countries": list(REJECT_COUNTRIES.values()),
                "rejected_count": rejected_by_country,
                "preferred_provinces": list(PREFERRED_PROVINCES),
            },
            "lead_reasons": LEAD_REASONS,
            "queries_focus": "Conversaciones de problema explícito (mayor conversión potencial)",
        },
        "summary": {
            "iterations": iterations,
            "queries_executed": len(seen_queries),
            "total_search_results": len(all_raw_results),
            "rejected_by_country": rejected_by_country,
            "leads_found": len(all_leads),
            "whatsapp_candidates": len(whatsapp_candidates),
            "success_leads_met": success_leads,
            "success_whatsapp_met": success_whatsapp,
            "min_required_leads": MIN_REAL_LEADS,
            "min_required_whatsapp": MIN_WHATSAPP_CANDIDATES,
            "reason_stats": reason_stats,
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
            "country_filtered": True,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with RAW_SEARCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_raw_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70, file=sys.stderr)
    print("  RESULTADO FINAL", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Iteraciones:                {iterations}", file=sys.stderr)
    print(f"  Queries ejecutadas:         {len(seen_queries)}", file=sys.stderr)
    print(f"  Resultados de búsqueda:     {len(all_raw_results)}", file=sys.stderr)
    print(f"  Rechazados por país:        {rejected_by_country}", file=sys.stderr)
    print(f"  Leads humanos encontrados:  {len(all_leads)}", file=sys.stderr)
    print(f"  Con whatsapp/teléfono:      {len(whatsapp_candidates)}", file=sys.stderr)
    print(f"  Success leads (>= 10):      {'✓ CUMPLIDO' if success_leads else '✗ NO cumplido'}", file=sys.stderr)
    print(f"  Success whatsapp (>= 3):    {'✓ CUMPLIDO' if success_whatsapp else '✗ NO cumplido'}", file=sys.stderr)
    print(f"  Output:                     {OUTPUT_PATH}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Stats por lead_reason
    if reason_stats:
        print(f"\n  Distribución por lead_reason:", file=sys.stderr)
        for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1]):
            print(f"    {reason:35s} {count:3d}", file=sys.stderr)

    # Top leads
    if all_leads:
        print(f"\n  TOP 15 LEADS:", file=sys.stderr)
        for i, l in enumerate(all_leads[:15], 1):
            wa = " [+WA]" if l.possible_whatsapp else ""
            ph = " [+TEL]" if l.possible_phone else ""
            print(f"    {i:2d}. [C={l.commercial_score:3d} U={l.urgency_score:3d} Conf={l.confidence:3d}] {l.lead_reason:35s} | {l.platform:15s} | {l.problem_summary[:40]}{wa}{ph}", file=sys.stderr)

    return output


if __name__ == "__main__":
    output = run_pipeline()
    print(json.dumps(output, ensure_ascii=False, indent=2))
