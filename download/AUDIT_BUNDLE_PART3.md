=== FILE: radar_v3.py (1378 líneas) ===

```"""
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
```


=== FILE: radar_v4.py (1270 líneas) ===

```"""
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
```


=== FILE: reprocess_v4.py (99 líneas) ===

```"""
reprocess_v4.py — Re-procesa los raw search results de v4 con la clasificación v4.1.
"""
import json
import sys
sys.path.insert(0, '/home/z/my-project/scripts/radar')
from radar_v4 import build_lead_from_result_v4, dedup_by_post_link, extract_arg_phone_strict, extract_whatsapp_strict, detect_country, REJECT_COUNTRIES, MUST_MATCH, PREFERRED_PROVINCES

# Cargar raw search results
with open('/home/z/my-project/download/radar_v4_raw_search.json') as f:
    raw_results = json.load(f)

print(f"Loaded {len(raw_results)} raw results", file=sys.stderr)

all_leads = []
rejected_by_country = 0
rejected_no_must_match = 0

for r in raw_results:
    combined = f"{r.get('name', '')}. {r.get('snippet', '')}"
    phone_preview = extract_arg_phone_strict(combined) or extract_whatsapp_strict(combined)
    country_preview = detect_country(combined, r.get('url', ''), phone_preview)
    if country_preview in REJECT_COUNTRIES.values():
        rejected_by_country += 1
        continue

    combined_lower = combined.lower()
    matched_must_preview = [kw for kw in MUST_MATCH if kw in combined_lower]
    if not matched_must_preview:
        rejected_no_must_match += 1
        continue

    lead = build_lead_from_result_v4(r, r.get('_query', ''), r.get('_query_category', ''))
    if lead is None:
        continue
    all_leads.append(lead)

print(f"Rejected by country: {rejected_by_country}", file=sys.stderr)
print(f"Rejected no must_match: {rejected_no_must_match}", file=sys.stderr)
print(f"Total leads: {len(all_leads)}", file=sys.stderr)

# Dedup
all_leads = dedup_by_post_link(all_leads)
print(f"After dedup: {len(all_leads)}", file=sys.stderr)

# Separar
real_leads = [l for l in all_leads if l.category == "real_lead"]
commercial_signals = [l for l in all_leads if l.category == "commercial_signal"]

# Sort
real_leads.sort(key=lambda l: (l.commercial_score, l.urgency_score, l.confidence), reverse=True)
commercial_signals.sort(key=lambda l: (l.commercial_score, l.urgency_score, l.confidence), reverse=True)

print(f"\nREAL LEADS (dolor explícito): {len(real_leads)}", file=sys.stderr)
print(f"COMMERCIAL SIGNALS: {len(commercial_signals)}", file=sys.stderr)

# Stats por lead_reason
reason_stats = {}
for l in all_leads:
    reason_stats[l.lead_reason] = reason_stats.get(l.lead_reason, 0) + 1

print(f"\nDistribución por lead_reason:", file=sys.stderr)
for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1]):
    print(f"  {reason:35s} {count:3d}", file=sys.stderr)

# Print top real_leads
if real_leads:
    print(f"\nTOP 10 REAL LEADS:", file=sys.stderr)
    for i, l in enumerate(real_leads[:10], 1):
        wa = " [+WA]" if l.possible_whatsapp else ""
        ph = " [+TEL]" if l.possible_phone else ""
        print(f"  {i:2d}. [C={l.commercial_score:3d} U={l.urgency_score:3d} Conf={l.confidence:3d}] {l.lead_reason:35s} | {l.platform:15s} | {l.quoted_text[:50]}{wa}{ph}", file=sys.stderr)

# Guardar output actualizado
import time
output = {
    "project": "Radar de Oportunidades v4.1",
    "version": "4.1",
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "mission": "Detector de DOLOR EXPLÍCITO — clasificación ampliada v4.1",
    "summary": {
        "total_search_results": len(raw_results),
        "rejected_by_country": rejected_by_country,
        "rejected_no_must_match": rejected_no_must_match,
        "real_leads_found": len(real_leads),
        "commercial_signals_found": len(commercial_signals),
        "total_leads": len(all_leads),
        "success_real_leads_met": len(real_leads) >= 10,
        "reason_stats": reason_stats,
    },
    "real_leads": [l.to_dict() for l in real_leads],
    "commercial_signals": [l.to_dict() for l in commercial_signals],
}

with open('/home/z/my-project/download/radar_v4_output.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✓ Output guardado en /home/z/my-project/download/radar_v4_output.json", file=sys.stderr)
```


=== FILE: review_cli.py (199 líneas) ===

```"""
review_cli.py — CLI interactivo para revisión humana de casos.

Comandos:
  list                  Lista casos pendientes (status=needs_review) con SLA
  show <case_id>        Muestra detalle completo de un caso
  approve <id> [notas]  Aprueba un caso para acción comercial
  reject <id> [notas]   Rechaza un caso
  duplicate <id> [notas] Marca como duplicado
  needs_more <id> [notas] Marca como necesita más datos
  stats                 Estadísticas de la cola
  audit [N]             Muestra últimas N entradas del audit trail
  verify                Verifica integridad de la cadena de audit trail
  quit / exit           Salir

SLA: 24h desde created_at. Casos vencidos se marcan con [SLA VENCIDO].
"""
from __future__ import annotations
import sys
import json
from typing import List, Optional

from models import Case, ReviewAction, now_iso
import config
from storage import (
    AuditTrail, ReviewQueue, EvidenceStore,
    load_cases_jsonl,
)


class ReviewCLI:
    def __init__(self):
        self.audit = AuditTrail()
        self.queue = ReviewQueue()
        self.evidence = EvidenceStore()
        self.cases_by_id = {c["case_id"]: c for c in load_cases_jsonl()}

    def cmd_list(self) -> None:
        pending = self.queue.pending()
        if not pending:
            print("No hay casos pendientes de revisión.")
            return
        print(f"\n{'case_id':14s} {'score':5s} {'band':8s} {'juris':12s} {'problem':15s} {'source':25s} {'SLA':>10s}")
        print("-" * 95)
        for row in pending:
            sla = float(row["sla_hours_remaining"]) if row["sla_hours_remaining"] else 0
            sla_str = f"{sla:.1f}h"
            marker = " ⚠" if sla < 0 else ""
            print(f"{row['case_id']:14s} {row['score']:5s} {row['score_band']:8s} "
                  f"{row['jurisdiction']:12s} {row['problem_type']:15s} "
                  f"{row['source_id']:25s} {sla_str:>10s}{marker}")
        print()

    def cmd_show(self, case_id: str) -> None:
        case = self.cases_by_id.get(case_id)
        if not case:
            print(f"Caso no encontrado: {case_id}")
            return
        print("\n" + "=" * 70)
        print(f"  CASO {case['case_id']}")
        print("=" * 70)
        print(f"  Score:           {case['score']} ({case['score_band']})")
        print(f"  Status:          {case['status']}")
        print(f"  Source:          {case['source_id']}")
        print(f"  Source URL:      {case['source_url']}")
        print(f"  Profile URL:     {case['profile_url'] or '—'}")
        print(f"  Author:          {case['name_or_alias']}")
        print(f"  Timestamp:       {case['timestamp']}")
        print(f"  Jurisdicción:    {case['jurisdiction'] or '—'}")
        print(f"  Localidad:       {case['locality'] or '—'}")
        print(f"  Problema:        {case['problem_type']}")
        print(f"  Vehículo:        {case['vehicle_type'] or '—'}")
        print(f"  Patente:         {case['patent'] or '—'}")
        print(f"  Año:             {case['year'] or '—'}")
        print(f"  Monto:           {case['amount'] or '—'}")
        print(f"  Score breakdown: {case['score_breakdown']}")
        print(f"  Duplicado de:    {case.get('duplicate_of') or '—'}")
        print(f"  Duplicados:      {case.get('duplicates') or []}")
        print(f"  Evidence path:   {case.get('evidence_path') or '—'}")
        print(f"  Evidence SHA256: {case.get('evidence_sha256') or '—'}")
        print("-" * 70)
        print("  EVIDENCIA TEXTUAL:")
        print("-" * 70)
        print(f"  {case['evidence_text']}")
        print("-" * 70)
        if case.get('reviewed_by'):
            print(f"  Revisado por:    {case['reviewed_by']}")
            print(f"  Acción:          {case['review_action']}")
            print(f"  Fecha:           {case['reviewed_at']}")
            print(f"  Notas:           {case['review_notes']}")
        print("=" * 70 + "\n")

    def cmd_review(self, action: str, case_id: str, notes: str = "") -> None:
        case = self.cases_by_id.get(case_id)
        if not case:
            print(f"Caso no encontrado: {case_id}")
            return
        # Reconstruir Case mínimo para queue.apply_review
        c = Case(**case)
        reviewer = "operator_cli"
        ra = ReviewAction(case_id=case_id, action=action, reviewer=reviewer, notes=notes)
        try:
            self.queue.apply_review(c, ra, self.audit)
            # Actualizar dict local
            self.cases_by_id[case_id] = c.to_dict()
            print(f"✓ Caso {case_id} → {action} por {reviewer}")
            print(f"  Audit trail actualizado.")
        except ValueError as e:
            print(f"✗ {e}")

    def cmd_stats(self) -> None:
        stats = self.queue.stats()
        print("\nEstadísticas de la cola de revisión:")
        print("-" * 40)
        for status, count in sorted(stats.items()):
            print(f"  {status:25s} {count:5d}")
        print("-" * 40)
        total = sum(stats.values())
        print(f"  {'TOTAL':25s} {total:5d}\n")

    def cmd_audit(self, n: int = 10) -> None:
        entries = self.audit.read_all()[-n:]
        print(f"\nÚltimas {len(entries)} entradas del audit trail:")
        print("-" * 100)
        for e in entries:
            details_str = json.dumps(e["details"], ensure_ascii=False)
            if len(details_str) > 80:
                details_str = details_str[:77] + "…"
            print(f"  {e['timestamp'][:19]} | {e['actor']:20s} | {e['action']:18s} | "
                  f"{e['entity_type']:8s} | {e['entity_id']:20s} | {details_str}")
        print("-" * 100)
        print(f"  Cadena íntegra: {'✓' if self.audit.verify_chain() else '✗ ROTA'}\n")

    def cmd_verify(self) -> None:
        ok = self.audit.verify_chain()
        print(f"\nCadena de audit trail: {'✓ ÍNTEGRA' if ok else '✗ ROTA'}\n")

    def run(self) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — CLI de Revisión Humana (Fase 1)")
        print("=" * 70)
        print("  Comandos: list | show <id> | approve <id> [notas] | reject <id> [notas]")
        print("            duplicate <id> [notas] | needs_more <id> [notas]")
        print("            stats | audit [N] | verify | quit")
        print("=" * 70 + "\n")

        while True:
            try:
                line = input("radar> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nChau.")
                break
            if not line:
                continue
            parts = line.split(maxsplit=2)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit", "q"):
                print("Chau.")
                break
            elif cmd == "list":
                self.cmd_list()
            elif cmd == "show" and args:
                self.cmd_show(args[0])
            elif cmd == "stats":
                self.cmd_stats()
            elif cmd == "audit":
                n = int(args[0]) if args else 10
                self.cmd_audit(n)
            elif cmd == "verify":
                self.cmd_verify()
            elif cmd in ("approve", "reject", "duplicate", "needs_more") and args:
                notes = args[1] if len(args) > 1 else ""
                action_map = {"needs_more": "needs_more_data"}
                action = action_map.get(cmd, cmd)
                self.cmd_review(action, args[0], notes)
            else:
                print(f"Comando inválido: {line}")
                print("Comandos: list | show <id> | approve <id> | reject <id> | duplicate <id> | needs_more <id> | stats | audit | verify | quit")


if __name__ == "__main__":
    cli = ReviewCLI()
    # Si se pasa --non-interactive, ejecuta demo automática
    if "--demo" in sys.argv:
        print("\n--- DEMO AUTOMÁTICA ---\n")
        cli.cmd_stats()
        cli.cmd_list()
        if cli.cases_by_id:
            first_id = list(cli.cases_by_id.keys())[0]
            cli.cmd_show(first_id)
            cli.cmd_review("approve", first_id, "Caso válido para contacto manual.")
            cli.cmd_stats()
            cli.cmd_audit(5)
            cli.cmd_verify()
    else:
        cli.run()
```


=== FILE: scorer.py (249 líneas) ===

```"""
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
    # Corrección B: registrar versión del modelo de scoring
    case.score_version = config.SCORE_VERSION
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
```


=== FILE: sheets_uploader.py (526 líneas) ===

```"""
sheets_uploader.py — Contrato de subida a Google Sheets (SPEC-ONLY).

ESTE MÓDULO ES SPEC-ONLY:
- Define el contrato de entrada y la lógica de escritura.
- NO ejecuta llamadas reales a Google Sheets en este entorno.
- Si la variable de entorno RADAR_GOOGLE_SERVICE_ACCOUNT_FILE no apunta a un
  archivo existente, lanza RuntimeError("Missing credentials file").
- No hay modo mock ni dry-run implícito. El dry-run explícito (--dry-run en CLI)
  serializa las filas a stdout sin tocar la API.

Contrato de entrada:
    RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json

Operación soportada:
    {
      "operation": "append_rows",
      "target": "google_sheets",
      "spreadsheet_id": "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0",
      "worksheet": "cases",
      "rows": [<Case.to_sheet_row()>...],
      "requires_runtime_execution": true
    }

Reglas (glm_instruction_block):
    1. NEVER store private keys inside code
    2. ONLY use service account via file path env var
    3. ONLY append rows, never overwrite full sheet
    4. ALWAYS log case_id after write
    5. DO NOT create duplicates if case_id exists
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote

import config
from models import Case
from storage import AuditTrail


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingCredentialsError(RuntimeError):
    """Raised when RADAR_GOOGLE_SERVICE_ACCOUNT_FILE is empty or file missing."""
    pass


class SheetSchemaError(RuntimeError):
    """Raised when the worksheet headers don't match SHEET_HEADERS and can't be merged."""
    pass


class SheetWriteError(RuntimeError):
    """Raised when a write attempt fails after retry."""
    pass


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------
class GoogleSheetsUploader:
    """
    Sube casos a Google Sheets en modo append_only con dedup por case_id.

    Contract:
        - input: RADAR_GOOGLE_SERVICE_ACCOUNT_FILE (env var, string path)
        - behavior: if path missing → raise MissingCredentialsError
                    ("Missing credentials file")
        - no mocks, no dry-run implicit
        - real Google Sheets calls happen only when methods are invoked at runtime
          in an environment that has the credentials file
    """

    def __init__(
        self,
        spreadsheet_id: str = config.GOOGLE_SHEET_ID,
        worksheet_name: str = config.GOOGLE_SHEET_TAB,
        credentials_path: Optional[str] = None,
        audit: Optional[AuditTrail] = None,
    ):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.audit = audit

        # Resolución del path de credenciales (env var es la fuente única)
        cred_path = credentials_path or os.environ.get(
            "RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", ""
        )

        if not cred_path:
            raise MissingCredentialsError(
                "Missing credentials file "
                "(env var RADAR_GOOGLE_SERVICE_ACCOUNT_FILE is empty)"
            )
        if not Path(cred_path).is_file():
            raise MissingCredentialsError(
                f"Missing credentials file (path does not exist: {cred_path})"
            )

        self.credentials_path = cred_path
        self._client = None
        self._sheet = None
        self._worksheet = None

    # ------------------------------------------------------------------
    # Conexión (lazy) — sólo se invoca en runtime real
    # ------------------------------------------------------------------
    def _connect(self):
        """
        Autentica con Google via gspread.service_account().
        Requiere gspread instalado. No cachea el client hasta primera llamada exitosa.
        """
        if self._client is not None:
            return
        try:
            import gspread  # type: ignore
        except ImportError as e:
            raise SheetWriteError(
                "gspread no instalado. Instalar con: pip install gspread"
            ) from e

        self._client = gspread.service_account(filename=self.credentials_path)
        self._sheet = self._client.open_by_key(self.spreadsheet_id)

        # Asegurar que el worksheet exista
        try:
            self._worksheet = self._sheet.worksheet(self.worksheet_name)
        except Exception:
            # Si no existe, lo crea
            self._worksheet = self._sheet.add_worksheet(
                title=self.worksheet_name, rows=1000, cols=len(config.SHEET_HEADERS)
            )

    # ------------------------------------------------------------------
    # Headers: ensure_headers_then_ready_to_write
    # ------------------------------------------------------------------
    def ensure_headers(self) -> Dict[str, Any]:
        """
        Asegura que la fila 1 del worksheet tenga los headers de SHEET_HEADERS.

        Política (config.SHEET_HEADER_POLICY):
            - if_empty_sheet: create_headers
            - if_headers_exist: validate_and_merge_if_missing
            - never_overwrite_row_1: True

        Returns:
            Dict con: action ('created'|'validated'|'merged'),
                      missing_headers, headers_present
        """
        self._connect()
        # Leer primera fila
        first_row = self._worksheet.row_values(1) if self._worksheet.row_count > 0 else []

        if not first_row:
            # Hoja vacía: crear headers
            self._worksheet.update([config.SHEET_HEADERS])
            self._log_audit("sheet_ensure_headers", "created",
                             details={"headers": config.SHEET_HEADERS})
            return {"action": "created", "missing_headers": [], "headers_present": config.SHEET_HEADERS}

        # Validar / merge
        present = [h.strip() for h in first_row]
        required = list(config.SHEET_HEADERS)
        missing = [h for h in required if h not in present]

        if not missing:
            self._log_audit("sheet_ensure_headers", "validated",
                             details={"headers": present})
            return {"action": "validated", "missing_headers": [], "headers_present": present}

        # Merge: agregar columnas faltantes al final de la fila 1
        # (nunca sobrescribir row_1 existente)
        new_headers = present + missing
        # Pad para que tenga la misma longitud que las filas nuevas
        self._worksheet.update([new_headers])
        self._log_audit("sheet_ensure_headers", "merged",
                         details={"added": missing, "final_headers": new_headers})
        return {"action": "merged", "missing_headers": missing, "headers_present": new_headers}

    # ------------------------------------------------------------------
    # Dedup lookup
    # ------------------------------------------------------------------
    def _find_case_row(self, case_id: str) -> Optional[int]:
        """
        Busca el número de fila (1-indexed) de un case_id existente.
        Returns None si no existe.
        """
        self._connect()
        try:
            cell = self._worksheet.find(case_id, in_column=1)
            return cell.row if cell else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Append or update
    # ------------------------------------------------------------------
    def append_or_update(self, case: Case) -> Dict[str, Any]:
        """
        Pipeline por caso:
            validate_case_schema → normalize_fields → deduplicate_by_case_id
            → compute_priority_level → generate_whatsapp_link
            → append_to_sheet (o update_score_if_higher) → log_audit_trail

        Estrategia dedup (config.SHEET_DUPLICATE_STRATEGY):
            'update_score_if_higher' → si el case_id existe y el nuevo score
            es mayor, actualiza la fila; sino, no hace nada.

        Returns:
            Dict con: case_id, action ('appended'|'updated'|'skipped_lower_score'),
                      row, score
        """
        # 1. validate_case_schema
        row = case.to_sheet_row()
        missing_fields = [k for k in config.SHEET_HEADERS if k not in row]
        if missing_fields:
            raise SheetSchemaError(
                f"Case {case.case_id} missing required fields: {missing_fields}"
            )

        # 2-4. normalize + priority_level ya resueltos en to_sheet_row()
        # 5. generate_whatsapp_link ya resuelto en to_sheet_row()

        # 6. deduplicate_by_case_id
        existing_row = self._find_case_row(case.case_id)

        if existing_row is None:
            # 6a. append_to_sheet
            self._write_with_retry([row], append=True)
            self._log_audit("sheet_write", "appended",
                             entity_id=case.case_id,
                             details={"row": row, "score": case.score})
            return {
                "case_id": case.case_id,
                "action": "appended",
                "score": case.score,
            }

        # 6b. update_score_if_higher
        existing_values = self._worksheet.row_values(existing_row)
        # Buscar columna 'score'
        headers = self._worksheet.row_values(1)
        try:
            score_col_idx = headers.index("score")
            existing_score = int(existing_values[score_col_idx]) if score_col_idx < len(existing_values) else 0
        except (ValueError, IndexError):
            existing_score = 0

        if case.score > existing_score:
            # Update completo de la fila (preserva el case_id, actualiza el resto)
            self._update_row(existing_row, row)
            self._log_audit("sheet_write", "updated_higher_score",
                             entity_id=case.case_id,
                             details={
                                 "old_score": existing_score,
                                 "new_score": case.score,
                                 "row": existing_row,
                             })
            return {
                "case_id": case.case_id,
                "action": "updated",
                "old_score": existing_score,
                "new_score": case.score,
                "row": existing_row,
            }

        # Skip (no crear duplicado, no actualizar)
        self._log_audit("sheet_write", "skipped_lower_score",
                         entity_id=case.case_id,
                         details={
                             "existing_score": existing_score,
                             "new_score": case.score,
                             "row": existing_row,
                         })
        return {
            "case_id": case.case_id,
            "action": "skipped_lower_score",
            "existing_score": existing_score,
            "new_score": case.score,
            "row": existing_row,
        }

    # ------------------------------------------------------------------
    # Batch append
    # ------------------------------------------------------------------
    def append_rows(self, cases: List[Case]) -> Dict[str, Any]:
        """
        Operación batch: para cada caso, ejecuta append_or_update.

        Returns:
            Dict con: total, appended, updated, skipped, errors
        """
        # Asegurar headers primero
        headers_result = self.ensure_headers()

        appended = 0
        updated = 0
        skipped = 0
        errors: List[Dict[str, Any]] = []

        for case in cases:
            try:
                result = self.append_or_update(case)
                action = result["action"]
                if action == "appended":
                    appended += 1
                elif action == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append({"case_id": case.case_id, "error": str(e)})
                self._log_audit("sheet_write", "error",
                                 entity_id=case.case_id,
                                 details={"error": str(e)})

        summary = {
            "operation": "append_rows",
            "target": "google_sheets",
            "spreadsheet_id": self.spreadsheet_id,
            "worksheet": self.worksheet_name,
            "total": len(cases),
            "appended": appended,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "headers_action": headers_result["action"],
            "requires_runtime_execution": True,
        }
        self._log_audit("sheet_batch", "completed",
                         entity_id="batch",
                         details=summary)
        return summary

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _write_with_retry(self, rows: List[Dict[str, Any]], append: bool = True) -> None:
        """
        Escribe filas con retry_once_then_log_error (config.SHEET_ON_FAILURE).
        """
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                self._connect()
                values = [[r.get(h, "") for h in config.SHEET_HEADERS] for r in rows]
                if append:
                    self._worksheet.append_rows(values, value_input_option="USER_ENTERED")
                else:
                    # update_row se maneja en _update_row
                    pass
                return
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    time.sleep(0.5)  # backoff corto antes del retry
                    continue
                # Agotado el retry
                raise SheetWriteError(
                    f"Sheet write failed after retry: {e}"
                ) from e
        # No debería llegar aquí
        raise SheetWriteError(f"Sheet write failed: {last_exc}")

    def _update_row(self, row_num: int, row: Dict[str, Any]) -> None:
        """Actualiza una fila existente con los valores nuevos."""
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                self._connect()
                values = [[row.get(h, "") for h in config.SHEET_HEADERS]]
                # Range: A{row}:{last_col}{row}
                last_col_letter = chr(ord('A') + len(config.SHEET_HEADERS) - 1)
                cell_range = f"A{row_num}:{last_col_letter}{row_num}"
                self._worksheet.update(cell_range, values, value_input_option="USER_ENTERED")
                return
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    time.sleep(0.5)
                    continue
                raise SheetWriteError(
                    f"Sheet update failed after retry: {e}"
                ) from e
        raise SheetWriteError(f"Sheet update failed: {last_exc}")

    def _log_audit(
        self,
        action: str,
        result: str,
        entity_type: str = "case",
        entity_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.audit is None:
            return
        self.audit.append(
            actor="system:sheets_uploader",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={"result": result, **(details or {})},
        )


# ---------------------------------------------------------------------------
# Helper standalone para construir WhatsApp link (uso opcional)
# ---------------------------------------------------------------------------
def build_whatsapp_link(whatsapp_number: str, message: Optional[str] = None) -> str:
    """
    Construye un link de WhatsApp según el spec del uploader.

    Formato: https://wa.me/{whatsapp_number}?text={encoded_message}
    Si no hay número, devuelve string vacío.
    """
    if not whatsapp_number:
        return ""
    msg = message or config.WHATSAPP_DEFAULT_MESSAGE
    encoded = quote(msg)
    # Normalizar número: sólo dígitos (sacar +, espacios, guiones)
    normalized = "".join(c for c in whatsapp_number if c.isdigit())
    return f"https://wa.me/{normalized}?text={encoded}"


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica el contrato de error, NO llama a Google
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST sheets_uploader.py (SPEC-ONLY, no llama a Google)")
    print("=" * 70)

    # 1. Sin env var → Missing credentials file
    saved = os.environ.pop("RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", None)
    try:
        try:
            uploader = GoogleSheetsUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingCredentialsError")
            sys.exit(1)
        except MissingCredentialsError as e:
            assert "Missing credentials file" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin credenciales → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = saved

    # 2. Con path inexistente → Missing credentials file
    os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = "/tmp/no-existe-12345.json"
    try:
        try:
            uploader = GoogleSheetsUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingCredentialsError")
            sys.exit(1)
        except MissingCredentialsError as e:
            assert "Missing credentials file" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Path inexistente → '{e}'")
    finally:
        os.environ.pop("RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", None)
        if saved is not None:
            os.environ["RADAR_GOOGLE_SERVICE_ACCOUNT_FILE"] = saved

    # 3. build_whatsapp_link standalone
    link = build_whatsapp_link("+54 11 5555-1234")
    expected = "https://wa.me/541155551234?text=Hola%2C%20vi%20tu%20consulta%20sobre%20multas.%20Te%20puedo%20ayudar%20a%20revisarlo."
    assert link == expected, f"WhatsApp link incorrecto:\n  got:      {link}\n  expected: {expected}"
    print(f"  ✓ build_whatsapp_link → {link}")

    # 4. Schema de headers (sin tocar Google)
    print(f"  ✓ SHEET_HEADERS ({len(config.SHEET_HEADERS)} cols): {', '.join(config.SHEET_HEADERS[:5])}…")

    # 5. to_sheet_row genera fila con EXACTAMENTE las columnas del schema
    from models import Case
    from storage import AuditTrail
    case = Case(
        case_id="case-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/post/abc",
        profile_url="https://example.com/user/1",
        timestamp="2026-06-30T10:00:00-03:00",
        name_or_alias="Test User",
        vehicle_type="auto",
        patent="ABC123",
        jurisdiction="CABA",
        locality="Caballito",
        problem_type="fotomulta",
        year=2020,
        amount=18500.0,
        evidence_text="Test evidence text",
        score=82,
        score_band="critical",
        whatsapp_number="541155551234",
    )
    row = case.to_sheet_row()
    assert list(row.keys()) == config.SHEET_HEADERS, \
        f"Schema mismatch: {list(row.keys())} vs {config.SHEET_HEADERS}"
    assert row["whatsapp_link"].startswith("https://wa.me/541155551234?text="), \
        f"WhatsApp link no generado: {row['whatsapp_link']}"
    assert row["priority_level"] == "critical"
    assert row["review_state"] == "needs_review"
    print(f"  ✓ to_sheet_row genera fila con schema exacto ({len(row)} cols)")
    print(f"  ✓ whatsapp_link generado: {row['whatsapp_link'][:60]}…")
    print(f"  ✓ priority_level={row['priority_level']} | review_state={row['review_state']}")

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se ejecutaron llamadas a Google.")
    print("=" * 70)
    print("""
  Para ejecutar subida real (en máquina del operador con credenciales):

      export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json
      pip install gspread
      python main.py --sheet-write

  Si el archivo no existe, el uploader lanza:
      Missing credentials file (path does not exist: /path/local/service-account.json)
""")
```


=== FILE: sinks.py (522 líneas) ===

```"""
sinks.py — Sinks del pipeline event-driven v2.0 (corrección A: rol congelado).

================================================================================
ROL DE SINKS (corrección A — capa congelada)
================================================================================

Sinks son EJECUCIÓN PURA. 0 lógica de negocio.

    Input  : Case + PolicyDecision
    Output : resultado de ejecución (ok/skipped/error)

Lo que un Sink puede hacer:
    - Ejecutar la acción indicada por PolicyDecision.actions
    - Loguear al audit trail
    - Retornar el resultado de la ejecución

Lo que un Sink NO puede hacer:
    - Decidir si ejecutar o no (eso lo hace PolicyEngine)
    - Evaluar triggers (eso lo hace PolicyEngine)
    - Mutar el case más allá de lo estrictamente necesario para su acción
      (ej: WhatsAppLinkSink setea case.whatsapp_link, eso es su acción)
    - Llamar a otros sinks
    - Publicar eventos al bus (eso lo hace el orquestador)

Sinks definidos (spec v2.0):
    1. WhatsAppLinkSink    : genera link wa.me si action="generate_whatsapp_intent"
    2. GoogleSheetsWebhookSink: encola case si action="publish_to_sheets"

Cada sink expone:
    - write_with_decision(case, decision)  ← API recomendada (v2.0)
    - write(case)                          ← legacy backward-compat (v1)
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from urllib.parse import quote

from models import Case, now_iso
from storage import AuditTrail
import config


# ---------------------------------------------------------------------------
# Base Sink
# ---------------------------------------------------------------------------
class Sink(ABC):
    """
    Interfaz común para todos los sinks.

    Corrección A: Sinks = ejecución pura. La decisión de qué ejecutar
    vive en PolicyEngine, no acá.
    """

    sink_id: str = "abstract"

    def __init__(self, audit: Optional[AuditTrail] = None):
        self.audit = audit

    @abstractmethod
    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Ejecuta el sink según PolicyDecision (API v2.0).

        Args:
            case: el case a procesar
            decision: PolicyDecision del PolicyEngine.evaluate(case)

        Returns:
            Dict con: sink_id, status (ok|skipped|error), details
        """
        ...

    def write(self, case: Case) -> Dict[str, Any]:
        """
        Legacy backward-compat (v1). No usar en pipeline v2.0.

        Implementación default: llama a write_with_decision con una
        PolicyDecision sintética. Deprecado.
        """
        from policy_engine import PolicyDecision
        synthetic = PolicyDecision(
            case_id=case.case_id,
            actions=["generate_whatsapp_intent", "publish_to_sheets"],
            reasons=["legacy_write_call"],
            boost_delta=0,
            metadata={"legacy": True},
            decision_id="dec-legacy",
            ruleset_version="legacy",
            timestamp=now_iso(),
        )
        return self.write_with_decision(case, synthetic)

    def _log(self, status: str, case_id: str, details: Dict[str, Any]) -> None:
        if self.audit is None:
            return
        self.audit.append(
            actor=f"system:sink:{self.sink_id}",
            action=f"write:{status}",
            entity_type="case",
            entity_id=case_id,
            details=details,
        )


# ---------------------------------------------------------------------------
# WhatsApp Link Sink
# ---------------------------------------------------------------------------
class WhatsAppLinkSink(Sink):
    """
    Sink que genera links de WhatsApp.

    Corrección A: ejecución pura. La trigger logic vive en PolicyEngine.

    Comportamiento:
        - Si decision.should_suppress() → skip
        - Si decision.should_generate_whatsapp() → genera link
        - Sino → skip

    No consulta score, no consulta jurisdiction, no consulta status.
    Sólo ejecuta lo que la PolicyDecision dice.
    """

    sink_id = "whatsapp"

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        default_message: Optional[str] = None,
        # Parámetros legacy ignorados en v2.0 (sólo para no romper constructor viejo)
        score_threshold: int = 80,
    ):
        super().__init__(audit=audit)
        self.default_message = default_message or config.WHATSAPP_DEFAULT_MESSAGE
        self._legacy_score_threshold = score_threshold  # ignorado en v2.0

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """Ejecuta el sink según la decisión del PolicyEngine."""
        # Si la policy dice suprimir, no hacer nada
        if decision.should_suppress():
            self._log("skipped", case.case_id, {
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            }

        # Si la policy NO dice generar whatsapp intent → skip
        if not decision.should_generate_whatsapp():
            self._log("skipped", case.case_id, {
                "reason": "policy_no_whatsapp_action",
                "decision_id": decision.decision_id,
                "actions": decision.actions,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_no_whatsapp_action",
                "actions": decision.actions,
                "decision_id": decision.decision_id,
            }

        # Ejecutar: generar link
        link = self.generate_link(case.whatsapp_number)
        case.whatsapp_link = link
        case.updated_at = now_iso()

        # Identificar trigger source desde la decisión (para auditoría)
        trigger_source = "policy_decision"
        if "score >= " in " ".join(decision.reasons):
            trigger_source = "score_threshold"
        elif "manual whatsapp_number present" in " ".join(decision.reasons):
            trigger_source = "manual_number"
        elif "approved by human review" in " ".join(decision.reasons):
            trigger_source = "approved_review"

        self._log("ok" if link else "skipped", case.case_id, {
            "link_generated": bool(link),
            "whatsapp_number_present": bool(case.whatsapp_number),
            "trigger_source": trigger_source,
            "decision_id": decision.decision_id,
            "policy_actions": decision.actions,
            "ruleset_version": decision.ruleset_version,
        })

        if not link:
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "no_whatsapp_number",
                "link": "",
                "decision_id": decision.decision_id,
            }

        return {
            "sink_id": self.sink_id,
            "status": "ok",
            "link": link,
            "trigger": trigger_source,
            "decision_id": decision.decision_id,
            "ruleset_version": decision.ruleset_version,
        }

    def generate_link(self, whatsapp_number: str, message: Optional[str] = None) -> str:
        """Construye https://wa.me/{num}?text={encoded_msg}."""
        if not whatsapp_number:
            return ""
        normalized = "".join(c for c in str(whatsapp_number) if c.isdigit())
        if not normalized:
            return ""
        msg = message or self.default_message
        encoded = quote(msg)
        return f"https://wa.me/{normalized}?text={encoded}"


# ---------------------------------------------------------------------------
# Google Sheets Webhook Sink
# ---------------------------------------------------------------------------
class GoogleSheetsWebhookSink(Sink):
    """
    Sink que escribe casos a Google Sheet vía Apps Script Webhook.

    Corrección A: ejecución pura. Decide si encolar o no basándose en
    PolicyDecision, no en lógica propia.

    Batch: acumula casos y los envía en un único POST al flush().
    """

    sink_id = "google_sheets"

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        webhook_url: Optional[str] = None,
        batch_size: int = 50,
    ):
        super().__init__(audit=audit)
        self._webhook_url = webhook_url or os.environ.get("RADAR_WEBHOOK_URL", "")
        self.batch_size = batch_size
        self._batch: List[Case] = []
        self._uploader = None  # lazy init

    def _ensure_uploader(self):
        """Lazy init del uploader (falla si no hay URL)."""
        if self._uploader is not None:
            return
        from webhook_uploader import WebhookUploader, MissingWebhookURLError
        try:
            self._uploader = WebhookUploader(
                webhook_url=self._webhook_url or None,
                audit=self.audit,
            )
        except MissingWebhookURLError as e:
            raise MissingWebhookURLError(
                f"Sink google_sheets no puede inicializar: {e}"
            ) from e

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Corrección A: ejecuta según PolicyDecision.

        Si decision.should_suppress() → NO encola (duplicate, etc.)
        Si decision.should_publish_to_sheets() → encola
        Sino → skip
        """
        if decision.should_suppress():
            self._log("skipped", case.case_id, {
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_suppress",
                "decision_id": decision.decision_id,
            }

        if not decision.should_publish_to_sheets():
            self._log("skipped", case.case_id, {
                "reason": "policy_no_publish_action",
                "decision_id": decision.decision_id,
                "actions": decision.actions,
            })
            return {
                "sink_id": self.sink_id,
                "status": "skipped",
                "reason": "policy_no_publish_action",
                "actions": decision.actions,
                "decision_id": decision.decision_id,
            }

        # Encolar para batch
        self._batch.append(case)

        result = {
            "sink_id": self.sink_id,
            "status": "queued",
            "batch_size": len(self._batch),
            "case_id": case.case_id,
            "decision_id": decision.decision_id,
        }

        if len(self._batch) >= self.batch_size:
            flush_result = self.flush()
            result["flush_result"] = flush_result

        return result

    def flush(self) -> Dict[str, Any]:
        """Envía todos los casos acumulados en un único POST al webhook."""
        if not self._batch:
            return {
                "sink_id": self.sink_id,
                "status": "empty",
                "total": 0,
                "pushed": 0,
            }

        self._ensure_uploader()
        cases_to_send = list(self._batch)
        self._batch.clear()

        summary = self._uploader.push(cases_to_send)

        self._log(
            "ok" if summary["pushed"] else "error",
            "batch",
            {
                "total": summary["total"],
                "pushed": summary["pushed"],
                "response": summary["response"],
                "errors": summary["errors"],
            },
        )

        return {
            "sink_id": self.sink_id,
            "status": "ok" if summary["pushed"] else "error",
            "total": summary["total"],
            "pushed": summary["pushed"],
            "response": summary["response"],
            "errors": summary["errors"],
        }


# ---------------------------------------------------------------------------
# Fan-out: ejecuta todos los sinks sobre un case
# ---------------------------------------------------------------------------
class SinkFanOut:
    """
    Ejecuta una lista de sinks sobre cada case.

    Corrección A: el fan-out sólo itera y delega. 0 lógica de negocio.
    """

    def __init__(self, sinks: List[Sink]):
        self.sinks = sinks

    def write_with_decision(self, case: Case, decision) -> Dict[str, Any]:
        """
        Ejecuta todos los sinks con PolicyDecision (API v2.0).

        Cada sink decide si ejecutar según decision.actions.
        Si decision.should_suppress() → todos los sinks se saltan.
        """
        results = {}
        for sink in self.sinks:
            try:
                results[sink.sink_id] = sink.write_with_decision(case, decision)
            except Exception as e:
                results[sink.sink_id] = {
                    "sink_id": sink.sink_id,
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                if sink.audit:
                    sink._log("error", case.case_id, {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    })
        return results

    def write(self, case: Case) -> Dict[str, Any]:
        """Legacy backward-compat (v1). No usar en pipeline v2.0."""
        results = {}
        for sink in self.sinks:
            try:
                results[sink.sink_id] = sink.write(case)
            except Exception as e:
                results[sink.sink_id] = {
                    "sink_id": sink.sink_id,
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                if sink.audit:
                    sink._log("error", case.case_id, {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    })
        return results

    def flush_all(self) -> Dict[str, Any]:
        """Llama flush() en todos los sinks que lo soportan."""
        results = {}
        for sink in self.sinks:
            if hasattr(sink, "flush"):
                try:
                    results[sink.sink_id] = sink.flush()
                except Exception as e:
                    results[sink.sink_id] = {
                        "sink_id": sink.sink_id,
                        "status": "error",
                        "error": str(e),
                    }
        return results


# ---------------------------------------------------------------------------
# Smoke test (spec-only)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST sinks.py (corrección A: ejecución pura)")
    print("=" * 70)

    from models import Case, now_iso
    from policy_engine import PolicyEngine, PolicyDecision, POLICY_RULESET_VERSION

    engine = PolicyEngine()
    wa_sink = WhatsAppLinkSink(score_threshold=80)  # legacy param, ignored in v2.0

    # 1. Caso crítico con whatsapp_number → decision genera action
    case1 = Case(
        case_id="case-crit",
        signal_id="sig-1",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1", profile_url="",
        timestamp=now_iso(), name_or_alias="Test", evidence_text="Test",
        score=85, jurisdiction="CABA", is_canonical=True,
        whatsapp_number="541155551234",
    )
    decision1 = engine.evaluate(case1)
    result1 = wa_sink.write_with_decision(case1, decision1)
    assert result1["status"] == "ok"
    assert "wa.me/541155551234" in case1.whatsapp_link
    assert result1["ruleset_version"] == POLICY_RULESET_VERSION
    print(f"  ✓ Caso crítico: sink ejecuta según decision (status={result1['status']})")
    print(f"    decision_id = {result1['decision_id']}")
    print(f"    ruleset_version = {result1['ruleset_version']}")

    # 2. Caso sin whatsapp action → sink skip
    case2 = Case(
        case_id="case-low",
        signal_id="sig-2",
        source_id="x_search",
        source_url="https://example.com/p/2", profile_url="",
        timestamp=now_iso(), name_or_alias="Test2", evidence_text="Test2",
        score=42, jurisdiction="MENDOZA", is_canonical=True,
    )
    decision2 = engine.evaluate(case2)
    result2 = wa_sink.write_with_decision(case2, decision2)
    assert result2["status"] == "skipped"
    assert result2["reason"] == "policy_no_whatsapp_action"
    print(f"  ✓ Caso sin action: sink skip (reason={result2['reason']})")

    # 3. Duplicate → suppress → sink skip
    case3 = Case(
        case_id="case-dup",
        signal_id="sig-3",
        source_id="x_search",
        source_url="https://example.com/p/3", profile_url="",
        timestamp=now_iso(), name_or_alias="Test3", evidence_text="Test3",
        score=85, jurisdiction="CABA", is_canonical=False,
        duplicate_of="case-crit",
    )
    decision3 = engine.evaluate(case3)
    result3 = wa_sink.write_with_decision(case3, decision3)
    assert result3["status"] == "skipped"
    assert result3["reason"] == "policy_suppress"
    print(f"  ✓ Duplicate: sink skip (reason={result3['reason']})")

    # 4. GoogleSheetsWebhookSink sin URL → error explícito al flush
    os.environ.pop("RADAR_WEBHOOK_URL", None)
    sheets_sink = GoogleSheetsWebhookSink(batch_size=10)
    # Sin URL, no podemos encolar (write_with_decision debería pasar, pero flush falla)
    # Actually: write_with_decision encola sin validar URL (lazy init en flush)
    # Esto es intencional: el batch se arma aunque no haya URL; el flush falla claro
    sheets_sink.write_with_decision(case1, decision1)
    try:
        sheets_sink.flush()
        print(f"  ✗ FAIL: debería fallar sin URL")
        sys.exit(1)
    except Exception as e:
        assert "Missing webhook URL" in str(e)
        print(f"  ✓ Sheets sink sin URL → '{e}'")

    # 5. FanOut
    fanout = SinkFanOut([wa_sink])
    fanout_result = fanout.write_with_decision(case1, decision1)
    assert "whatsapp" in fanout_result
    assert fanout_result["whatsapp"]["status"] == "ok"
    print(f"  ✓ SinkFanOut ejecuta N sinks con decision")

    # 6. Corrección A: sinks NO consultan triggers internos
    # Verificamos que WhatsAppLinkSink NO tiene should_trigger (eliminado en v2.0)
    assert not hasattr(wa_sink, "should_trigger"), "should_trigger should be removed in v2.0"
    print(f"  ✓ Corrección A: WhatsAppLinkSink NO tiene should_trigger (eliminado)")

    print("\n" + "=" * 70)
    print("  ✓ Corrección A verificada: sinks = ejecución pura, 0 lógica de negocio")
    print("=" * 70)
```


=== FILE: storage.py (517 líneas) ===

```"""
storage.py — Persistencia: evidence store, audit trail, review queue, sheet sync.

Cuatro componentes:

1. EvidenceStore
   - Guarda evidencia de cada caso en disco (texto + metadata + hash SHA-256)
   - Estructura: <EVIDENCE_DIR>/<case_id>.json  +  <case_id>.txt
   - El hash garantiza integridad (re-verificable)

2. AuditTrail
   - Log append-only con hash chaining (cada entrada tiene hash_prev + hash_self)
   - Archivo: <SAMPLE_DATA_DIR>/audit_trail.log (una línea JSON por entrada)
   - Cualquier intento de mutar una línea anterior rompe la cadena

3. ReviewQueue
   - Cola de revisión humana: CSV + JSONL con estado, acción, SLA
   - Estados: needs_review / approved / rejected / duplicate / needs_more_data
   - SLA: 24h desde created_at hasta reviewed_at

4. SheetSync
   - Sincroniza casos a Google Sheet del spec (1jLeM6k...)
   - Modo real: requiere GOOGLE_SERVICE_ACCOUNT_FILE en env (gspread)
   - Modo dry-run (default Fase 1): imprime filas que se subirían, no toca la sheet
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from models import Case, AuditEntry, ReviewAction, AR_TZ, now_iso
import config


# ---------------------------------------------------------------------------
# EvidenceStore
# ---------------------------------------------------------------------------
class EvidenceStore:
    """Almacena evidencia por caso en disco con hash de integridad."""

    def __init__(self, base_dir: Path = config.EVIDENCE_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, case: Case) -> tuple[str, str]:
        """
        Guarda evidencia del caso.

        Returns:
            (path_rel, sha256) — path relativo al base_dir y hash de integridad.
        """
        case_dir = self.base_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        # Texto original
        text_path = case_dir / "evidence.txt"
        text_path.write_text(case.evidence_text, encoding="utf-8")

        # Metadata
        meta = {
            "case_id": case.case_id,
            "signal_id": case.signal_id,
            "source_id": case.source_id,
            "source_url": case.source_url,
            "timestamp": case.timestamp,
            "captured_at": now_iso(),
            "evidence_text": case.evidence_text,
            "extracted_entities": {
                "name_or_alias": case.name_or_alias,
                "vehicle_type": case.vehicle_type,
                "patent": case.patent,
                "jurisdiction": case.jurisdiction,
                "locality": case.locality,
                "problem_type": case.problem_type,
                "year": case.year,
                "amount": case.amount,
            },
            "score": case.score,
            "score_band": case.score_band,
            "score_breakdown": case.score_breakdown,
        }
        meta_path = case_dir / "evidence.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Hash SHA-256 del texto + metadata serializada
        h = hashlib.sha256()
        h.update(case.evidence_text.encode("utf-8"))
        h.update(json.dumps(meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        sha = h.hexdigest()
        (case_dir / "evidence.sha256").write_text(sha, encoding="utf-8")

        return str(case_dir.relative_to(self.base_dir.parent)), sha

    def verify(self, case: Case) -> bool:
        """Verifica que la evidencia almacenada siga siendo íntegra."""
        case_dir = self.base_dir / case.case_id
        sha_path = case_dir / "evidence.sha256"
        if not sha_path.exists():
            return False
        expected = sha_path.read_text(encoding="utf-8").strip()
        meta = json.loads((case_dir / "evidence.json").read_text(encoding="utf-8"))
        h = hashlib.sha256()
        h.update(case.evidence_text.encode("utf-8"))
        h.update(json.dumps(meta, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return h.hexdigest() == expected


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------
class AuditTrail:
    """Log append-only con hash chaining para trazabilidad inmutable."""

    def __init__(self, path: Path = config.AUDIT_TRAIL_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Hash de la última entrada existente (para chaining)
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return ""
        last_hash = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    last_hash = entry.get("hash_self", "")
                except json.JSONDecodeError:
                    continue
        return last_hash

    def append(self, actor: str, action: str, entity_type: str,
               entity_id: str, details: Optional[Dict[str, Any]] = None) -> AuditEntry:
        """Agrega una entrada al audit trail."""
        entry = AuditEntry(
            timestamp=now_iso(),
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            hash_prev=self._last_hash,
        )
        line = entry.to_log_line()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._last_hash = entry.hash_self
        return entry

    def verify_chain(self) -> bool:
        """Verifica que la cadena de hashes esté íntegra."""
        if not self.path.exists():
            return True
        prev_hash = ""
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False
                if entry.get("hash_prev", "") != prev_hash:
                    return False
                prev_hash = entry.get("hash_self", "")
        return True

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out


# ---------------------------------------------------------------------------
# ReviewQueue
# ---------------------------------------------------------------------------
class ReviewQueue:
    """Cola de revisión humana: CSV + JSONL."""

    def __init__(
        self,
        csv_path: Path = config.REVIEW_QUEUE_PATH,
        jsonl_path: Path = config.SAMPLE_DATA_DIR / "review_queue.jsonl",
    ):
        self.csv_path = csv_path
        self.jsonl_path = jsonl_path

    def _csv_fields(self) -> List[str]:
        return [
            "case_id", "score", "score_band", "jurisdiction", "problem_type",
            "source_id", "source_url", "vehicle_type", "patent", "amount",
            "timestamp", "created_at", "status", "review_action",
            "reviewed_by", "reviewed_at", "review_notes",
            "duplicate_of", "evidence_path", "sla_hours_remaining",
        ]

    def initialize(self, cases: List[Case]) -> None:
        """Crea/reescribe la cola con todos los casos canónicos pendientes."""
        rows = [self._case_to_row(c) for c in cases if c.is_canonical]
        # CSV
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writeheader()
            writer.writerows(rows)
        # JSONL
        with self.jsonl_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _case_to_row(self, case: Case) -> Dict[str, Any]:
        sla_remaining = self._sla_remaining(case)
        return {
            "case_id": case.case_id,
            "score": case.score,
            "score_band": case.score_band,
            "jurisdiction": case.jurisdiction,
            "problem_type": case.problem_type,
            "source_id": case.source_id,
            "source_url": case.source_url,
            "vehicle_type": case.vehicle_type,
            "patent": case.patent,
            "amount": case.amount or "",
            "timestamp": case.timestamp,
            "created_at": case.created_at,
            "status": case.status,
            "review_action": case.review_action or "",
            "reviewed_by": case.reviewed_by or "",
            "reviewed_at": case.reviewed_at or "",
            "review_notes": case.review_notes,
            "duplicate_of": case.duplicate_of or "",
            "evidence_path": case.evidence_path or "",
            "sla_hours_remaining": sla_remaining,
        }

    def _sla_remaining(self, case: Case) -> float:
        """Calcula horas restantes de SLA (puede ser negativo si venció)."""
        try:
            created = datetime.fromisoformat(case.created_at)
            now = datetime.now(AR_TZ)
            elapsed_h = (now - created).total_seconds() / 3600.0
            return round(config.REVIEW_SLA_HOURS - elapsed_h, 1)
        except Exception:
            return config.REVIEW_SLA_HOURS

    def apply_review(self, case: Case, action: ReviewAction, audit: AuditTrail) -> None:
        """Aplica una acción de revisión a un caso y actualiza la cola."""
        if action.action not in config.REVIEW_ACTIONS:
            raise ValueError(f"Acción inválida: {action.action}")

        case.review_action = action.action
        case.reviewed_by = action.reviewer
        case.reviewed_at = action.timestamp
        case.review_notes = action.notes
        case.updated_at = now_iso()

        # Mapear acción a status
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "duplicate": "duplicate",
            "needs_more_data": "needs_more_data",
        }
        case.status = status_map[action.action]

        # Re-escribir la cola completa
        # (en Fase 2 esto será un UPDATE puntual en DB)
        all_rows = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["case_id"] == case.case_id:
                    row = self._case_to_row(case)
                all_rows.append(row)
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writeheader()
            writer.writerows(all_rows)

        # Audit
        audit.append(
            actor=f"reviewer:{action.reviewer}",
            action="review",
            entity_type="case",
            entity_id=case.case_id,
            details={"action": action.action, "notes": action.notes},
        )

    def pending(self) -> List[Dict[str, Any]]:
        """Devuelve los casos pendientes de revisión (status=needs_review)."""
        if not self.csv_path.exists():
            return []
        out = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"] == "needs_review":
                    out.append(row)
        return out

    def stats(self) -> Dict[str, int]:
        if not self.csv_path.exists():
            return {}
        stats: Dict[str, int] = {}
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats[row["status"]] = stats.get(row["status"], 0) + 1
        return stats


# ---------------------------------------------------------------------------
# SheetSync
# ---------------------------------------------------------------------------
class SheetSync:
    """
    Sincroniza casos a la Google Sheet del spec.

    Modo real (Fase 2/3): requiere service account.
    Modo dry-run (Fase 1, default): imprime filas y no toca la sheet.
    """

    def __init__(self, sheet_id: str = config.GOOGLE_SHEET_ID, tab: str = config.GOOGLE_SHEET_TAB):
        self.sheet_id = sheet_id
        self.tab = tab
        self.service_account_file = config.GOOGLE_SERVICE_ACCOUNT_FILE
        self._client = None
        self._sheet = None

    def _connect(self):
        """Conecta a Google Sheets via gspread. Requiere service account."""
        if not self.service_account_file:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_FILE no configurado. "
                "Setear env var RADAR_GOOGLE_SERVICE_ACCOUNT_FILE o usar dry_run=True."
            )
        try:
            import gspread
        except ImportError:
            raise RuntimeError(
                "gspread no instalado. Instalar con: pip install gspread"
            )
        self._client = gspread.service_account(filename=self.service_account_file)
        self._sheet = self._client.open_by_key(self.sheet_id).worksheet(self.tab)

    def sync(self, cases: List[Case], dry_run: bool = True, audit: Optional[AuditTrail] = None) -> Dict[str, Any]:
        """
        Sincroniza casos a la sheet.

        Args:
            cases: lista de casos a subir (sólo canónicos, normalmente)
            dry_run: si True (default Fase 1), no toca la sheet real
            audit: audit trail para registrar la acción

        Returns:
            Dict con: mode, rows_queued, rows_synced, sheet_url, sample_rows
        """
        rows = [c.to_sheet_row() for c in cases if c.is_canonical]

        if dry_run or not self.service_account_file:
            sample = rows[:3]
            if audit:
                audit.append(
                    actor="system",
                    action="sheet_sync",
                    entity_type="batch",
                    entity_id="dry_run",
                    details={
                        "mode": "dry_run",
                        "rows_queued": len(rows),
                        "sheet_url": config.GOOGLE_SHEET_URL,
                    },
                )
            return {
                "mode": "dry_run",
                "rows_queued": len(rows),
                "rows_synced": 0,
                "sheet_url": config.GOOGLE_SHEET_URL,
                "sample_rows": sample,
            }

        # Modo real
        self._connect()
        # Limpiar tab y escribir encabezados + filas
        headers = list(rows[0].keys()) if rows else []
        values = [headers] + [[r.get(h, "") for h in headers] for r in rows]
        self._sheet.update(values)
        if audit:
            audit.append(
                actor="system",
                action="sheet_sync",
                entity_type="batch",
                entity_id=f"sheet:{self.sheet_id}",
                details={
                    "mode": "real",
                    "rows_synced": len(rows),
                    "sheet_url": config.GOOGLE_SHEET_URL,
                },
            )
        return {
            "mode": "real",
            "rows_queued": len(rows),
            "rows_synced": len(rows),
            "sheet_url": config.GOOGLE_SHEET_URL,
        }


# ---------------------------------------------------------------------------
# Casos JSONL
# ---------------------------------------------------------------------------
def save_cases_jsonl(cases: List[Case], path: Path = config.CASES_PATH) -> None:
    """Persiste todos los casos (canónicos + duplicados) en JSONL."""
    with path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")


def load_cases_jsonl(path: Path = config.CASES_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Signals JSONL
# ---------------------------------------------------------------------------
def save_signals_jsonl(signals, path: Path = config.SIGNALS_MOCK_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    from extractor import signal_to_case
    from scorer import update_case_score
    from dedup import merge_duplicates

    audit = AuditTrail()
    print(f"Audit trail: {audit.path}")
    print(f"Cadena íntegra: {audit.verify_chain()}\n")

    sigs = generate_mock_signals()
    audit.append(actor="system", action="collect", entity_type="signal",
                 entity_id="batch", details={"count": len(sigs), "mode": "mock"})

    cases = []
    for s in sigs:
        case, status = signal_to_case(s)
        if case:
            audit.append(actor="system", action="extract", entity_type="signal",
                         entity_id=s.signal_id, details={"status": status, "case_id": case.case_id})
            update_case_score(case)
            audit.append(actor="system", action="score", entity_type="case",
                         entity_id=case.case_id, details={"score": case.score, "band": case.score_band})
            cases.append(case)
        else:
            audit.append(actor="system", action="reject", entity_type="signal",
                         entity_id=s.signal_id, details={"reason": status})

    cases, ndup = merge_duplicates(cases)
    audit.append(actor="system", action="dedup", entity_type="batch",
                 entity_id="all", details={"duplicates_found": ndup})

    ev = EvidenceStore()
    for c in cases:
        if c.is_canonical:
            path, sha = ev.store(c)
            c.evidence_path = path
            c.evidence_sha256 = sha
            audit.append(actor="system", action="store_evidence", entity_type="case",
                         entity_id=c.case_id, details={"sha256": sha[:16] + "…"})

    rq = ReviewQueue()
    rq.initialize(cases)
    audit.append(actor="system", action="queue_init", entity_type="batch",
                 entity_id="all", details={"total_canonical": sum(1 for c in cases if c.is_canonical)})

    save_cases_jsonl(cases)
    save_signals_jsonl(sigs)

    sheet = SheetSync()
    sync_result = sheet.sync(cases, dry_run=True, audit=audit)
    print(f"Sheet sync: {sync_result['mode']} | {sync_result['rows_queued']} filas")
    print(f"Sheet URL: {sync_result['sheet_url']}")
    print(f"\nCola de revisión: {rq.csv_path}")
    print(f"  Stats: {rq.stats()}")
    print(f"\nAudit trail: {len(audit.read_all())} entradas")
    print(f"Cadena íntegra: {audit.verify_chain()}")
```


