"""
config.py — Configuración y constantes del Radar de Oportunidades (Fase 1).

Idioma: español AR.
Todas las constantes provienen del spec original del usuario.
"""
from __future__ import annotations
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DOWNLOAD_ROOT = Path("/home/z/my-project/download")
SAMPLE_DATA_DIR = DOWNLOAD_ROOT / "sample_data"
EVIDENCE_DIR = SAMPLE_DATA_DIR / "evidence"
AUDIT_TRAIL_PATH = SAMPLE_DATA_DIR / "audit_trail.log"
REVIEW_QUEUE_PATH = SAMPLE_DATA_DIR / "review_queue.csv"
SIGNALS_MOCK_PATH = SAMPLE_DATA_DIR / "signals_mock.jsonl"
CASES_PATH = SAMPLE_DATA_DIR / "cases.jsonl"
DEDUP_INDEX_PATH = SAMPLE_DATA_DIR / "dedup_index.json"

for p in [SAMPLE_DATA_DIR, EVIDENCE_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Google Sheet del spec
# ---------------------------------------------------------------------------
GOOGLE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0/edit?gid=0#gid=0"
)
GOOGLE_SHEET_ID = "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0"
GOOGLE_SHEET_TAB = "radar_cases"

# Credenciales (opcionales en Fase 1). Si no están, sheet_sync entra en dry-run.
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
    "RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", ""
)

# ---------------------------------------------------------------------------
# Fuentes del spec (con prioridad y señales)
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "id": "facebook_public_groups",
        "type": "social_group",
        "access": "public_or_legitimate_member_access",
        "priority": "high",
        "signals": ["fotomulta", "multa", "libre deuda", "transferencia", "radar"],
    },
    {
        "id": "marketplace_public_posts",
        "type": "marketplace",
        "access": "public",
        "priority": "high",
        "signals": ["vendo auto", "transferir", "libre deuda", "patente"],
    },
    {
        "id": "x_search",
        "type": "social_search",
        "access": "public",
        "priority": "medium",
        "signals": ["fotomulta", "radares", "multas", "APSV"],
    },
    {
        "id": "public_forums",
        "type": "forum",
        "access": "public",
        "priority": "high",
        "signals": ["no puedo renovar", "multa de ruta", "consulto por multa"],
    },
    {
        "id": "news_and_comments",
        "type": "news",
        "access": "public",
        "priority": "medium",
        "signals": ["radares", "fotomultas", "reclamo", "denuncia"],
    },
]

# ---------------------------------------------------------------------------
# Campos a extraer (entity_extraction.fields del spec)
# ---------------------------------------------------------------------------
ENTITY_FIELDS = [
    "name_or_alias",
    "profile_url",
    "vehicle_type",
    "patent",
    "jurisdiction",
    "locality",
    "problem_type",
    "year",
    "amount",
    "source_name",
    "source_url",
    "timestamp",
    "evidence_text",
]

# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------
# Mapa de jurisdicciones argentinas + alias comunes → código canónico
JURISDICTION_MAP = {
    "caba": "CABA",
    "ciudad autónoma": "CABA",
    "capital federal": "CABA",
    "capital": "CABA",
    "buenos aires": "PBA",
    "pba": "PBA",
    "provincia de buenos aires": "PBA",
    "gba": "PBA",
    "gran buenos aires": "PBA",
    "córdoba": "CORDOBA",
    "cordoba": "CORDOBA",
    "santa fe": "SANTA_FE",
    "rosario": "SANTA_FE",
    "mendoza": "MENDOZA",
    "tucumán": "TUCUMAN",
    "tucuman": "TUCUMAN",
    "entre ríos": "ENTRE_RIOS",
    "entre rios": "ENTRE_RIOS",
    "neuquén": "NEUQUEN",
    "neuquen": "NEUQUEN",
    "río negro": "RIO_NEGRO",
    "rio negro": "RIO_NEGRO",
    "chubut": "CHUBUT",
    "la pampa": "LA_PAMPA",
    "corrientes": "CORRIENTES",
    "misiones": "MISIONES",
    "salta": "SALTA",
    "jujuy": "JUJUY",
    "formosa": "FORMOSA",
    "chaco": "CHACO",
    "santiago del estero": "SANTIAGO_DEL_ESTERO",
    "la rioja": "LA_RIOJA",
    "catamarca": "CATAMARCA",
    "san juan": "SAN_JUAN",
    "san luis": "SAN_LUIS",
    "santa cruz": "SANTA_CRUZ",
    "tierra del fuego": "TIERRA_DEL_FUEGO",
}

# Jurisdicciones objetivo comerciales (las que el negocio atiende)
TARGET_JURISDICTIONS = {"CABA", "PBA", "CORDOBA", "SANTA_FE"}

VEHICLE_TYPE_MAP = {
    "auto": "auto",
    "automóvil": "auto",
    "automovil": "auto",
    "moto": "moto",
    "motocicleta": "moto",
    "motocicleta": "moto",
    "camioneta": "camioneta",
    "pickup": "camioneta",
    "camión": "camion",
    "camion": "camion",
    "utilitario": "utilitario",
    "acoplado": "camion",
}

PROBLEM_TYPE_MAP = {
    "fotomulta": "fotomulta",
    "foto multa": "fotomulta",
    "multa": "multa",
    "multas": "multa",
    "libre deuda": "libre_deuda",
    "libre deuda vehicular": "libre_deuda",
    "transferencia": "transferencia",
    "transferir": "transferencia",
    "regularización": "regularizacion",
    "regularizacion": "regularizacion",
    "regularización vehicular": "regularizacion",
    "patente": "patente",
    "patente atrasada": "patente",
    "vencimiento vtv": "vtv",
    "vtv": "vtv",
    "radar": "fotomulta",
    "radares": "fotomulta",
    "apsv": "fotomulta",
    "multa de ruta": "fotomulta",
}

# ---------------------------------------------------------------------------
# Scoring (igual al spec)
# ---------------------------------------------------------------------------
SCORING_RANGE = (0, 100)
SCORING_WEIGHTS = {
    "explicit_intent": 30,
    "urgency": 15,
    "jurisdiction_fit": 15,
    "evidence_quality": 10,
    "commercial_potential": 10,
    "channel_fit": 10,
    "signal_repetition": 10,
}
SCORING_THRESHOLDS = {
    "critical": 80,
    "high": 60,
    "medium": 40,
    "low": 0,
}

# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
DEDUP_MATCH_KEYS = ["source_url", "profile_url", "patent", "normalized_text_hash"]
DEDUP_MERGE_STRATEGY = "keep_highest_confidence_and_latest_timestamp"

# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------
REVIEW_DEFAULT_STATUS = "needs_review"
REVIEW_ACTIONS = ["approve", "reject", "duplicate", "needs_more_data"]
REVIEW_SLA_HOURS = 24

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
ALERT_TRIGGERS = [
    "score_gte_80",
    "new_case_in_target_jurisdiction",
    "repeat_signal_from_same_source",
]

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_REQUIRED_FIELDS = [
    "case_id", "score", "jurisdiction", "problem_type",
    "source", "status", "evidence_link",
]
DASHBOARD_FILTERS = [
    "jurisdiction", "score", "source", "status", "vehicle_type", "date",
]
DASHBOARD_WIDGETS = [
    "new_cases", "high_priority", "trend_by_source", "trend_by_jurisdiction",
]

# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------
COMPLIANCE_RULES = {
    "public_only_preferred": True,
    "respect_platform_terms": True,
    "no_spam": True,
    "no_private_profile_harvesting": True,
    "manual_contact_only": True,
}

# Patrones de PII que el privacy_filter debe rechazar/mascarar
# En Fase 1 usamos patrones estrictos (alta precisión) para evitar falsos positivos
# con montos en pesos y años.
PII_PATTERNS = [
    # DNI argentino: requiere contexto "DNI" o "documento" cerca (para no matchear precios)
    r"(?i)dni\s*:?\s*\d{1,2}\.?\d{3}\.?\d{3}",
    r"(?i)documento\s*:?\s*\d{1,2}\.?\d{3}\.?\d{3}",
    # CUIT/CUIL: XX-XXXXXXXX-X (formato estricto con guiones)
    r"\b\d{2}-\d{8}-\d\b",
    # Teléfono AR: requiere prefijo +54 o 011/15 explícito
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    # Email
    r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b",
]

# Patentes argentinas (formato viejo ABC 123 y nuevo AB 123 CD)
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",  # AB 123 CD (nuevo)
    r"\b[A-Z]{3}\s?\d{3}\b",              # ABC 123 (viejo)
]
