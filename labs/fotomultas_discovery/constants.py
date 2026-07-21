"""Non-production policy constants for the Fotomultas laboratory."""

TARGET_VERTICAL = "fotomultas"
DEBT_THRESHOLD_ARS = 1_000_000
MAX_VERIFICATION_AGE_DAYS = 7

SINAI_PROVIDER = "sinai_official"
SINAI_HOST = "consultainfracciones.seguridadvial.gob.ar"
SINAI_SOURCE_URL = f"https://{SINAI_HOST}/"

ALLOWED_AUTHORIZATION_BASES = frozenset(
    {
        "owner_provided",
        "client_authorized",
        "legal_basis_documented",
        "synthetic_test",
    }
)

ACTIVE_STATUSES = frozenset(
    {
        "activa",
        "adeudada",
        "impaga",
        "pendiente",
        "vigente",
    }
)

INACTIVE_STATUSES = frozenset(
    {
        "anulada",
        "cancelada",
        "descartada",
        "pagada",
        "prescripta",
        "sin deuda",
    }
)

RAW_IDENTIFIER_FIELDS = frozenset(
    {
        "dni",
        "document",
        "documento",
        "domain",
        "dominio",
        "patente",
        "raw_identifier",
        "sexo",
    }
)
