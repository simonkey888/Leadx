# AUDITORÍA DE CÓDIGO COMPLETA — Radar de Oportunidades

Sos **Qwen3.7-Max**, auditor de código senior. Tu tarea es auditar TODO el código
del proyecto "Radar de Oportunidades" que aparece abajo en un único bloque.

## Contexto del proyecto

Sistema de detección de oportunidades comerciales públicas relacionadas con
fotomultas, libre deuda, transferencia y regularización vehicular en Argentina.
Evolucionó a través de 5 versiones (v1.0 → v5.0 PRO) que coexisten en el mismo
repositorio:

- **v1.0** (`pipeline.py`, `extractor.py`, `storage.py`): pipeline imperativo con regex extractor
- **v2.0** (`event_pipeline.py`, `event_bus.py`, `event_types.py`, `event_validator.py`,
  `llm_extractor.py`, `sinks.py`, `policy_engine.py`, `event_log.py`): pipeline event-driven
  con LLM extractor, PolicyEngine, EventLog SQLite, sinks separados
- **v3.0 / v4.0 / v5.0** (`radar_search.py`, `radar_v2.py`, `radar_v3.py`, `radar_v4.py`,
  `radar_pro.py`): scripts standalone de búsqueda web que usan z-ai web_search CLI
- **Lite** (`radar_lite.py`): módulo único sin dependencias para detección rápida
- **Shared** (`config.py`, `models.py`, `scorer.py`, `dedup.py`, `mock_sources.py`,
  `sheets_uploader.py`, `webhook_uploader.py`, `review_cli.py`, `main.py`,
  `generate_report.py`, `reprocess_v4.py`)

## Objetivos de la auditoría

Auditá con foco en:

1. **Seguridad**
   - Manejo de credenciales (service account JSON, API keys, webhook URLs)
   - PII handling (teléfonos, DNIs, datos personales)
   - Inyección en subprocess calls (z-ai CLI)
   - Path traversal en EvidenceStore
   - SQL injection en event_log SQLite

2. **Corrección funcional**
   - Bugs lógicos en scoring, dedup, policy engine
   - Edge cases en extractores regex (patentes, teléfonos, fechas)
   - Race conditions en event_bus
   - Manejo de errores silencioso (except Exception: pass)

3. **Calidad arquitectónica**
   - Duplicación de lógica entre versiones (v1/v2/v3/v4/pro)
   - Acoplamiento entre capas (PolicyEngine debe ser pure, sinks deben ser ejecución pura)
   - Contratos: PolicyEngine (no side effects, deterministic, versioned, idempotent)
   - Separación namespaces Signal/Case/Decision en event_types.py

4. **Compliance**
   - `no_llm_side_effects`: extractor LLM no debe escribir externamente
   - `no_direct_external_writes`: pipeline sólo escribe via sinks
   - `requires_event_validation`: todo evento pasa por EventValidator
   - `only_public_information`: no bypass de logins
   - `never_send_messages`: no outreach automático

5. **Performance y robustez**
   - Rate limiting en z-ai CLI (429 backoff)
   - Timeouts en subprocess
   - Memory leaks en loops largos
   - Manejo de encoding (UTF-8, acentos, ñ)

6. **Mantenibilidad**
   - Docstrings actualizados
   - Type hints completos
   - Tests coverage
   - Deprecación clara (policy_evaluated → decision_issued)

## Formato de salida esperado

Generá un reporte de auditoría con esta estructura:

```
# REPORTE DE AUDITORÍA — Radar de Oportunidades

## Resumen ejecutivo
[3-5 líneas con el veredicto general]

## Issues críticos (P0)
[Lista con archivo:línea, descripción, impacto, fix sugerido]

## Issues altos (P1)
[Lista con archivo:línea, descripción, impacto, fix sugerido]

## Issues medios (P2)
[Lista con archivo:línea, descripción, fix sugerido]

## Issues bajos (P3)
[Lista con archivo:línea, descripción, mejora sugerida]

## Compliance
[Estado de cada regla: OK / VIOLACIÓN / PARCIAL]

## Duplicación de código
[Mapa de duplicación entre versiones]

## Recomendaciones arquitectónicas
[3-5 mejoras concretas priorizadas]

## Veredicto final
[Aprobado / Aprobado con observaciones / Rechazado + justificación]
```

## Restricciones

- No reescribas el código. Sólo auditá y sugerí fixes.
- Cita archivo:línea específico para cada issue.
- Distingue entre bugs reales y preferencias de estilo.
- Si algo está bien, decílo explícitamente (no asumas silencio = aprobación).
- Si una versión vieja (v1, v2) tiene código muerto, marcalo.

---

## CÓDIGO FUENTE COMPLETO (28 archivos, ~13.5K líneas)

A continuación, todos los archivos del proyecto en orden alfabético, delimitados
por headers `=== FILE: <path> ===` para que puedas citarlos en tu reporte.



=== FILE: config.py (341 líneas) ===

```"""
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
# Tab/Worksheet destino: el spec del uploader pide "cases"
GOOGLE_SHEET_TAB = "cases"

# Credenciales (opcionales en Fase 1). Si no están, sheet_sync entra en dry-run.
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
    "RADAR_GOOGLE_SERVICE_ACCOUNT_FILE", ""
)

# APIs requeridas por el service account
GOOGLE_APIS_REQUIRED = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Email del service account (para documentación/validación; la auth real va en el JSON)
GOOGLE_SERVICE_ACCOUNT_EMAIL = (
    "radar-sheets-bot@radar-oportunidades-501015.iam.gserviceaccount.com"
)
GOOGLE_PROJECT_ID = "radar-oportunidades-501015"

# ---------------------------------------------------------------------------
# Schema de la Sheet (uploader v1.0)
# ---------------------------------------------------------------------------
# Orden EXACTO de columnas según el spec del uploader.
SHEET_HEADERS = [
    "case_id",
    "timestamp",
    "name_or_alias",
    "profile_url",
    "patent",
    "vehicle_type",
    "jurisdiction",
    "locality",
    "problem_type",
    "year",
    "amount",
    "score",
    "priority_level",
    "source_name",
    "source_url",
    "evidence_text",
    "whatsapp_number",
    "whatsapp_link",
    "status",
    "review_state",
]

# Política de headers
SHEET_HEADER_POLICY = {
    "if_empty_sheet": "create_headers",
    "if_headers_exist": "validate_and_merge_if_missing",
    "never_overwrite_row_1": True,
}

# Modo de escritura
SHEET_WRITE_MODE = "append_only"

# Estrategia ante duplicados (case_id ya existe en la sheet)
SHEET_DUPLICATE_STRATEGY = "update_score_if_higher"

# On failure
SHEET_ON_FAILURE = "retry_once_then_log_error"

# ---------------------------------------------------------------------------
# WhatsApp integration
# ---------------------------------------------------------------------------
WHATSAPP_ENABLED = True
WHATSAPP_NUMBER_COLUMN = "whatsapp_number"
WHATSAPP_DEFAULT_MESSAGE = "Hola, vi tu consulta sobre multas. Te puedo ayudar a revisarlo."

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

# Versión del modelo de scoring (corrección B del spec)
# Permite replay, comparación histórica y debugging real
SCORE_VERSION = "v1.0_weighted_sum"

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
```


=== FILE: dedup.py (172 líneas) ===

```"""
dedup.py — Motor de deduplicación.

Implementa el match por 4 keys del spec:
  - source_url          (misma URL de origen)
  - profile_url         (mismo perfil público del autor)
  - patent              (misma patente, si está presente)
  - normalized_text_hash (mismo texto normalizado, aunque sea de distinto autor)

Merge strategy: keep_highest_confidence_and_latest_timestamp
  - Entre un grupo de duplicados, el caso canónico es el que tiene:
    1. Mayor score (confidence)
    2. A igual score, el timestamp más reciente
  - Los demás se marcan como duplicate_of=<canonical_case_id>, status="duplicate",
    is_canonical=False.
"""
from __future__ import annotations
from typing import List, Dict, Tuple, Set
from collections import defaultdict

from models import Case
import config


# ---------------------------------------------------------------------------
# Indexación por match key
# ---------------------------------------------------------------------------
def _match_key_values(case: Case) -> Dict[str, str]:
    """Devuelve los valores no vacíos de cada match key para el caso."""
    return {
        "source_url": case.source_url,
        "profile_url": case.profile_url,
        "patent": case.patent,
        "normalized_text_hash": case.normalized_text_hash,
    }


def build_dedup_index(cases: List[Case]) -> Dict[str, Dict[str, str]]:
    """
    Construye índices invertidos: para cada match_key, mapea valor → lista de case_ids.
    Sólo se indexan valores no vacíos.
    """
    index: Dict[str, Dict[str, List[str]]] = {k: defaultdict(list) for k in config.DEDUP_MATCH_KEYS}
    for case in cases:
        kv = _match_key_values(case)
        for key, val in kv.items():
            if val:
                index[key][val].append(case.case_id)
    return index


# ---------------------------------------------------------------------------
# Unión-find para agrupar duplicados transitivos
# ---------------------------------------------------------------------------
class UnionFind:
    def __init__(self, ids: List[str]):
        self.parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def find_duplicate_groups(cases: List[Case]) -> List[List[Case]]:
    """
    Agrupa casos duplicados por cualquiera de las 4 match keys (unión transitiva).
    Devuelve grupos de tamaño >= 2.
    """
    if not cases:
        return []
    by_id = {c.case_id: c for c in cases}
    uf = UnionFind(list(by_id.keys()))
    index = build_dedup_index(cases)

    for key in config.DEDUP_MATCH_KEYS:
        for val, ids in index[key].items():
            if len(ids) < 2:
                continue
            # Union de todos los pares en este bucket
            for i in range(1, len(ids)):
                uf.union(ids[0], ids[i])

    groups: Dict[str, List[str]] = defaultdict(list)
    for cid in by_id:
        root = uf.find(cid)
        groups[root].append(cid)

    return [[by_id[cid] for cid in group] for group in groups.values() if len(group) >= 2]


# ---------------------------------------------------------------------------
# Merge strategy
# ---------------------------------------------------------------------------
def pick_canonical(group: List[Case]) -> Case:
    """
    Elige el caso canónico del grupo:
    1. Mayor score
    2. A igual score, timestamp más reciente
    """
    return max(group, key=lambda c: (c.score, c.timestamp))


def merge_duplicates(cases: List[Case]) -> Tuple[List[Case], int]:
    """
    Aplica dedup a la lista de casos.

    Returns:
        cases_processed: lista con todos los casos (canónicos + duplicados marcados)
        duplicates_found: cantidad de duplicados marcados
    """
    groups = find_duplicate_groups(cases)
    duplicates_found = 0

    # Mapear cada case_id a su canonical
    canonical_map: Dict[str, str] = {}
    for group in groups:
        canonical = pick_canonical(group)
        for case in group:
            if case.case_id != canonical.case_id:
                canonical_map[case.case_id] = canonical.case_id

    # Aplicar marcas
    for case in cases:
        if case.case_id in canonical_map:
            case.duplicate_of = canonical_map[case.case_id]
            case.is_canonical = False
            case.status = "duplicate"
            duplicates_found += 1
        else:
            case.is_canonical = True

    # Agregar a cada canónico la lista de case_ids que duplicó
    for group in groups:
        canonical = pick_canonical(group)
        canonical.duplicates = [c.case_id for c in group if c.case_id != canonical.case_id]

    return cases, duplicates_found


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    from extractor import signal_to_case
    from scorer import update_case_score

    sigs = generate_mock_signals()
    cases = []
    for s in sigs:
        case, status = signal_to_case(s)
        if case:
            update_case_score(case)
            cases.append(case)

    print(f"Antes de dedup: {len(cases)} casos")
    cases, ndup = merge_duplicates(cases)
    canonical = [c for c in cases if c.is_canonical]
    print(f"Después de dedup: {len(canonical)} canónicos, {ndup} duplicados marcados\n")

    print("Duplicados:")
    for c in cases:
        if not c.is_canonical:
            print(f"  {c.case_id} → duplicate_of={c.duplicate_of} | {c.problem_type} | {c.jurisdiction}")
```


=== FILE: event_bus.py (223 líneas) ===

```"""
event_bus.py — Bus de eventos in-process síncrono (v2.0).

Características:
- Síncrono: handlers se ejecutan en orden dentro del mismo thread
- Validación obligatoria: todo evento pasa por EventValidator antes del dispatch
- Si un evento es inválido → se emite EventRejected y el original NO se dispatcha
- Audit log: cada publish queda registrado en AuditTrail
- Suscripción por event_type: un handler se suscribe a uno o varios tipos

Uso:
    bus = EventBus(audit=audit_trail)
    bus.subscribe("case_scored", my_handler)
    bus.publish(event)  # valida → dispatch → log
"""
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict

from event_types import (
    SignalCollected, EntitiesExtracted, CaseScored,
    CaseDeduplicated, CasePublished, EventRejected, DecisionIssued,
    make_event_id, event_to_dict,
)
from event_validator import validate_event
from storage import AuditTrail
from models import now_iso


# Tipo handler: recibe un Event y no devuelve nada (o devuelve algo que se ignora)
Handler = Callable[[Any], None]


class EventBus:
    """Bus de eventos in-process síncrono con validación obligatoria."""

    def __init__(self, audit: Optional[AuditTrail] = None):
        self._handlers: Dict[str, List[Handler]] = defaultdict(list)
        self._audit = audit
        self._published_count = 0
        self._rejected_count = 0
        self._dispatched_count = 0

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------
    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Suscribe un handler a un tipo de evento."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Desuscribe un handler."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------
    def publish(self, event) -> bool:
        """
        Publica un evento en el bus.

        Pasos:
        1. Validar evento contra data_contract
        2. Si inválido → emitir EventRejected, NO dispatchear, retornar False
        3. Si válido → dispatchear a todos los handlers suscritos al tipo
        4. Loguear en audit trail

        Returns:
            True si el evento fue válido y dispatcheado, False si fue rechazado
        """
        self._published_count += 1

        # 1. Validar
        result = validate_event(event)
        if not result.valid:
            self._rejected_count += 1
            # Emitir EventRejected
            reject = EventRejected(
                event_id=make_event_id("rej", event.event_id),
                event_type="event_rejected",
                timestamp=now_iso(),
                payload={
                    "reason": "; ".join(result.errors),
                    "original_event_type": getattr(event, "event_type", "unknown"),
                    "original_event_id": getattr(event, "event_id", ""),
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
            )
            self._log_audit(reject, valid=False, errors=result.errors)
            # Los EventRejected NO se dispatchean a handlers (evitar loop infinito)
            # pero sí quedan en audit
            return False

        # 2. Dispatch
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
                self._dispatched_count += 1
            except Exception as e:
                # Un handler que falla no rompe el bus, pero se loguea
                self._log_audit_error(event, e)

        # 3. Log
        self._log_audit(event, valid=True, errors=[])

        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        return {
            "published": self._published_count,
            "dispatched": self._dispatched_count,
            "rejected": self._rejected_count,
            "handlers_total": sum(len(hs) for hs in self._handlers.values()),
        }

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------
    def _log_audit(self, event, valid: bool, errors: List[str]) -> None:
        if self._audit is None:
            return
        self._audit.append(
            actor="system:event_bus",
            action=f"publish:{event.event_type}",
            entity_type="event",
            entity_id=event.event_id,
            details={
                "valid": valid,
                "errors": errors if not valid else [],
                "event_type": event.event_type,
            },
        )

    def _log_audit_error(self, event, exc: Exception) -> None:
        if self._audit is None:
            return
        self._audit.append(
            actor="system:event_bus",
            action=f"handler_error:{event.event_type}",
            entity_type="event",
            entity_id=event.event_id,
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Smoke test event_bus ===\n")

    audit = AuditTrail()
    bus = EventBus(audit=audit)

    # Handler que acumula eventos recibidos
    received = []
    def handler_scored(event):
        received.append(event.case.case_id)

    bus.subscribe("case_scored", handler_scored)

    # 1. Publicar evento válido
    from models import Case, now_iso
    case = Case(
        case_id="case-bus-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test",
        evidence_text="Test evidence",
        score=75,
    )
    evt = CaseScored(
        event_id=make_event_id("case", case.case_id),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": case.to_dict()},
    )
    ok = bus.publish(evt)
    assert ok, "Should publish successfully"
    assert received == ["case-bus-test"]
    print(f"  ✓ Evento válido publicado y dispatcheado a 1 handler")

    # 2. Publicar evento inválido (score fuera de rango)
    bad_case = case.to_dict()
    bad_case["score"] = 250
    evt_bad = CaseScored(
        event_id=make_event_id("case-bad", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case},
    )
    ok2 = bus.publish(evt_bad)
    assert not ok2, "Should reject"
    assert received == ["case-bus-test"], "Handler should NOT have been called for rejected event"
    print(f"  ✓ Evento inválido rechazado, handler no ejecutado")

    # 3. Stats
    s = bus.stats()
    assert s["published"] == 2
    assert s["dispatched"] == 1
    assert s["rejected"] == 1
    print(f"  ✓ Stats: {s}")

    # 4. Audit trail tiene ambas entradas (publish + reject)
    audit_entries = audit.read_all()
    publish_entries = [e for e in audit_entries if e["action"].startswith("publish:")]
    assert len(publish_entries) >= 2
    print(f"  ✓ Audit trail: {len(publish_entries)} publish entries logged")

    print("\n=== Todos los smoke tests OK ===")
```


=== FILE: event_log.py (321 líneas) ===

```"""
event_log.py — Append-only event log con persistencia (corrección A).

Storage options (en orden de preferencia):
    1. SQLite (default, recomendado) — atomic, queryable, zero-deps
    2. JSONL (fallback) — simple, human-readable, para Drive o FS simple

Schema (corrección A del spec):
    event_id:    string PK
    event_type:  string
    payload:     JSON string
    timestamp:   iso8601
    version:     string (default "1.0")

El event_log es la fuente de verdad para:
- replay (re-procesar eventos con nuevo código)
- debugging histórico
- auditoría externa (lectura read-only para auditor)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict

from models import now_iso
import config


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "1.0"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    version     TEXT NOT NULL DEFAULT '1.0'
);
CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_ts   ON event_log(timestamp);
"""


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------
class EventLogBackend:
    """Interface común para backends de event_log."""

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        raise NotImplementedError

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SQLite backend (default)
# ---------------------------------------------------------------------------
class SQLiteEventLog(EventLogBackend):
    """Backend SQLite. Recomendado: atomic, queryable, zero-deps."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_CREATE_TABLE_SQL)
        self._conn.commit()

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            "INSERT OR REPLACE INTO event_log (event_id, event_type, payload, timestamp, version) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_id, event_type, payload_str, timestamp, version),
        )
        self._conn.commit()

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT event_id, event_type, payload, timestamp, version FROM event_log"
        clauses = []
        params: List[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "payload": json.loads(r[2]),
                "timestamp": r[3],
                "version": r[4],
            }
            for r in rows
        ]

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM event_log")
        return cur.fetchone()[0]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# JSONL backend (fallback)
# ---------------------------------------------------------------------------
class JSONLEventLog(EventLogBackend):
    """Backend JSONL. Simple, human-readable. Para Drive o FS simple."""

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Crear archivo si no existe
        if not self.file_path.exists():
            self.file_path.touch()

    def append(self, event_id: str, event_type: str, payload: Dict[str, Any],
               timestamp: str, version: str = SCHEMA_VERSION) -> None:
        entry = {
            "event_id": event_id,
            "event_type": event_type,
            "payload": payload,
            "timestamp": timestamp,
            "version": version,
        }
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def query(self, event_type: Optional[str] = None,
              since: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        out = []
        with self.file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and entry.get("event_type") != event_type:
                    continue
                if since and entry.get("timestamp", "") < since:
                    continue
                out.append(entry)
                if limit and len(out) >= limit:
                    break
        return out

    def count(self) -> int:
        if not self.file_path.exists():
            return 0
        n = 0
        with self.file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def create_event_log(
    backend: str = "sqlite",
    path: Optional[Union[str, Path]] = None,
) -> EventLogBackend:
    """
    Factory para crear backend de event_log.

    Args:
        backend: "sqlite" (default) | "jsonl"
        path: path al archivo. Si None, usa default en SAMPLE_DATA_DIR.
    """
    if path is None:
        if backend == "sqlite":
            path = config.SAMPLE_DATA_DIR / "event_log.db"
        elif backend == "jsonl":
            path = config.SAMPLE_DATA_DIR / "event_log.jsonl"
        else:
            raise ValueError(f"Unknown backend: {backend}")

    if backend == "sqlite":
        return SQLiteEventLog(path)
    elif backend == "jsonl":
        return JSONLEventLog(path)
    else:
        raise ValueError(f"Unknown backend: {backend}")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile
    import os

    print("=" * 70)
    print("  SMOKE TEST event_log.py")
    print("=" * 70)

    # Test SQLite
    tmpdir = tempfile.mkdtemp()
    sqlite_path = os.path.join(tmpdir, "test_event_log.db")
    jsonl_path = os.path.join(tmpdir, "test_event_log.jsonl")

    print("\n  [SQLite backend]")
    log = SQLiteEventLog(sqlite_path)
    log.append("evt-1", "signal_collected", {"signal_id": "sig-1"}, "2026-06-30T10:00:00-03:00")
    log.append("evt-2", "case_scored", {"case_id": "case-1", "score": 82}, "2026-06-30T10:01:00-03:00")
    log.append("evt-3", "case_scored", {"case_id": "case-2", "score": 45}, "2026-06-30T10:02:00-03:00")
    assert log.count() == 3
    print(f"    ✓ Append 3 eventos, count={log.count()}")

    all_events = log.query()
    assert len(all_events) == 3
    assert all_events[0]["event_id"] == "evt-1"
    print(f"    ✓ Query all: {len(all_events)} eventos en orden temporal")

    scored = log.query(event_type="case_scored")
    assert len(scored) == 2
    assert scored[0]["payload"]["case_id"] == "case-1"
    print(f"    ✓ Query case_scored: {len(scored)} eventos")

    recent = log.query(since="2026-06-30T10:01:30-03:00")
    assert len(recent) == 1
    assert recent[0]["event_id"] == "evt-3"
    print(f"    ✓ Query since: {len(recent)} eventos (after filter)")

    limited = log.query(limit=2)
    assert len(limited) == 2
    print(f"    ✓ Query limit=2: {len(limited)} eventos")

    log.close()

    # Idempotencia: re-abrir el mismo DB mantiene datos
    log2 = SQLiteEventLog(sqlite_path)
    assert log2.count() == 3
    print(f"    ✓ Re-abrir DB mantiene datos: count={log2.count()}")
    log2.close()

    # Test JSONL
    print("\n  [JSONL backend]")
    jlog = JSONLEventLog(jsonl_path)
    jlog.append("evt-1", "signal_collected", {"signal_id": "sig-1"}, "2026-06-30T10:00:00-03:00")
    jlog.append("evt-2", "case_scored", {"case_id": "case-1", "score": 82}, "2026-06-30T10:01:00-03:00")
    assert jlog.count() == 2
    print(f"    ✓ Append 2 eventos, count={jlog.count()}")

    jall = jlog.query()
    assert len(jall) == 2
    assert jall[1]["payload"]["case_id"] == "case-1"
    print(f"    ✓ Query all: {len(jall)} eventos")

    jscored = jlog.query(event_type="case_scored")
    assert len(jscored) == 1
    print(f"    ✓ Query case_scored: {len(jscored)} eventos")

    # Factory
    print("\n  [Factory]")
    f_log = create_event_log("sqlite", sqlite_path)
    assert f_log.count() == 3
    print(f"    ✓ create_event_log('sqlite', ...) → count={f_log.count()}")
    f_log.close()

    # Limpieza
    import shutil
    shutil.rmtree(tmpdir)

    print("\n" + "=" * 70)
    print("  ✓ Todos los smoke tests OK")
    print("=" * 70)
    print("""
  Schema persistido:
    event_id (PK) | event_type | payload (JSON) | timestamp | version

  Backends disponibles:
    - sqlite (default, recomendado) — atomic, queryable
    - jsonl (fallback) — simple, para Drive

  Uso típico:
    from event_log import create_event_log
    log = create_event_log("sqlite")
    log.append(event_id, event_type, payload, timestamp, version="1.0")
""")
```


=== FILE: event_pipeline.py (572 líneas) ===

```"""
event_pipeline.py — Pipeline event-driven v2.0.

Orquesta:
    1. collect_signals() → para cada signal: publica SignalCollected
    2. handler_on_signal_collected → LLM extract → publica EntitiesExtracted
    3. handler_on_entities_extracted → score → publica CaseScored
    4. handler_on_case_scored → dedup → publica CaseDeduplicated
    5. handler_on_case_deduplicated → si canonical → SinkFanOut → publica CasePublished

Reglas v2.0 cumplidas:
    - no_llm_side_effects: extractor es pure function
    - no_direct_external_writes: sólo los sinks escriben afuera
    - requires_event_validation: bus valida cada evento antes de dispatch

Si RADAR_LLM_API_KEY no está seteada, falla con error explícito al primer extract.
Si RADAR_WEBHOOK_URL no está seteada, el sink de Sheets falla al flush (no fatal).
"""
from __future__ import annotations

import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from models import Case, Signal, now_iso, AR_TZ
import config
from mock_sources import collect_signals
from event_types import (
    SignalCollected, EntitiesExtracted, CaseScored, CaseDeduplicated,
    CasePublished, EventRejected, DecisionIssued, make_event_id, event_to_dict,
    SIGNAL_EVENTS, CASE_EVENTS, DECISION_EVENTS,
)
from event_bus import EventBus
from event_validator import validate_event
from storage import AuditTrail, save_cases_jsonl, save_signals_jsonl
from scorer import update_case_score
from dedup import merge_duplicates
from llm_extractor import LLMExtractor, MissingLLMApiKeyError
from sinks import (
    Sink, WhatsAppLinkSink, GoogleSheetsWebhookSink, SinkFanOut,
)
from policy_engine import PolicyEngine, apply_boost, POLICY_RULESET_VERSION
from event_log import EventLogBackend, create_event_log
from dataclasses import asdict


@dataclass
class EventPipelineResult:
    signals_collected: int = 0
    events_published: int = 0
    events_rejected: int = 0
    cases_extracted: int = 0
    cases_canonical: int = 0
    duplicates_found: int = 0
    policy_decisions: int = 0
    policy_suppressed: int = 0
    policy_whatsapp_intents: int = 0
    policy_boosted: int = 0
    sinks_results: List[Dict[str, Any]] = field(default_factory=list)
    audit_entries: int = 0
    audit_chain_ok: bool = True
    event_log_count: int = 0
    event_log_backend: str = ""
    duration_seconds: float = 0.0
    cases: List[Case] = field(default_factory=list)
    extractor_used: str = ""
    sinks_used: List[str] = field(default_factory=list)
    policy_engine_used: str = ""


class EventPipeline:
    """Pipeline event-driven v2.0 con PolicyEngine + EventLog (correcciones A,B,C,D)."""

    def __init__(
        self,
        audit: Optional[AuditTrail] = None,
        bus: Optional[EventBus] = None,
        extractor: Optional[LLMExtractor] = None,
        sinks: Optional[List[Sink]] = None,
        policy_engine: Optional[PolicyEngine] = None,
        event_log: Optional[EventLogBackend] = None,
        use_real_sources: bool = False,
    ):
        self.audit = audit or AuditTrail()
        self.bus = bus or EventBus(audit=self.audit)
        # LLM extractor: falla explícito si no hay API key
        self.extractor = extractor  # lazy: se inicializa en _ensure_extractor
        # PolicyEngine (corrección C+D)
        self.policy_engine = policy_engine or PolicyEngine()
        # EventLog (corrección A) — default: SQLite
        self.event_log = event_log or create_event_log("sqlite")
        # Sinks: si no se pasan, default = WhatsAppLinkSink + GoogleSheetsWebhookSink
        if sinks is not None:
            self.sinks = sinks
        else:
            self.sinks = [
                WhatsAppLinkSink(audit=self.audit),
                GoogleSheetsWebhookSink(audit=self.audit, batch_size=50),
            ]
        self.fanout = SinkFanOut(self.sinks)
        self.use_real_sources = use_real_sources

        # Estado temporal: casos en proceso (para dedup batch al final)
        self._cases_buffer: List[Case] = []
        self._result = EventPipelineResult()

        # Suscribir handlers
        self._wire_handlers()

    def _ensure_extractor(self) -> LLMExtractor:
        if self.extractor is None:
            # Esto falla con MissingLLMApiKeyError si no hay env var
            self.extractor = LLMExtractor()
        return self.extractor

    def _wire_handlers(self) -> None:
        """Suscribe los handlers del pipeline al bus."""
        self.bus.subscribe("signal_collected", self._on_signal_collected)
        self.bus.subscribe("entities_extracted", self._on_entities_extracted)
        self.bus.subscribe("case_scored", self._on_case_scored)
        self.bus.subscribe("decision_issued", self._on_decision_issued)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_signal_collected(self, event: SignalCollected) -> None:
        """Signal → LLM extract → EntitiesExtracted."""
        signal = event.signal

        # Aplicar privacy filter primero (igual que en v1)
        from extractor import privacy_filter
        pf = privacy_filter(signal)
        if not pf.passed:
            self.audit.append(
                actor="system:handler:signal_collected",
                action="reject_privacy",
                entity_type="signal",
                entity_id=signal.signal_id,
                details={"reason": pf.reason},
            )
            return

        try:
            extractor = self._ensure_extractor()
            case_partial = extractor.extract_to_case(signal)
        except MissingLLMApiKeyError as e:
            raise  # propaga el error explícito
        except Exception as e:
            self.audit.append(
                actor="system:handler:signal_collected",
                action="extract_error",
                entity_type="signal",
                entity_id=signal.signal_id,
                details={"error": str(e), "error_type": type(e).__name__},
            )
            return

        self._cases_buffer.append(case_partial)
        self._result.cases_extracted += 1

        # Publicar EntitiesExtracted
        evt = EntitiesExtracted(
            event_id=make_event_id("ent", case_partial.case_id),
            event_type="entities_extracted",
            timestamp=now_iso(),
            payload={"case_partial": case_partial.to_dict()},
        )
        self.bus.publish(evt)

    def _on_entities_extracted(self, event: EntitiesExtracted) -> None:
        """EntitiesExtracted → score → CaseScored."""
        case = event.case_partial
        update_case_score(case)
        self.audit.append(
            actor="system:handler:entities_extracted",
            action="score",
            entity_type="case",
            entity_id=case.case_id,
            details={"score": case.score, "band": case.score_band},
        )

        # Publicar CaseScored
        evt = CaseScored(
            event_id=make_event_id("score", case.case_id),
            event_type="case_scored",
            timestamp=now_iso(),
            payload={"case": case.to_dict()},
        )
        self.bus.publish(evt)

    def _on_case_scored(self, event: CaseScored) -> None:
        """CaseScored → buffer para dedup batch."""
        # El dedup se hace al final sobre todos los casos del buffer
        # (no podemos dedup evento-por-evento sin conocer el resto)
        pass

    def _on_decision_issued(self, event: DecisionIssued) -> None:
        """
        Decision namespace handler.

        Corrección C: separar Signal/Case/Decision namespaces.
        DecisionIssued es una decisión del sistema, no un evento de estado.

        El handler lo dispara el run() después de dedup, no por evento suelto.
        Aquí sólo registramos auditoría.
        """
        pass

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> EventPipelineResult:
        """Ejecuta el pipeline event-driven end-to-end."""
        t0 = time.time()

        # Pre-flight: si el extractor es LLM y no hay API key, fallar acá
        # con error explícito ANTES de procesar cualquier señal
        if self.extractor is None:
            try:
                self._ensure_extractor()
            except MissingLLMApiKeyError as e:
                self.audit.append(
                    actor="system:event_pipeline",
                    action="pipeline_abort",
                    entity_type="batch",
                    entity_id="run",
                    details={"reason": "missing_llm_api_key", "error": str(e)},
                )
                raise

        self.audit.append(
            actor="system:event_pipeline",
            action="pipeline_start",
            entity_type="batch",
            entity_id="run",
            details={
                "version": "2.0",
                "mode": "event_driven",
                "use_real_sources": self.use_real_sources,
                "sinks": [s.sink_id for s in self.sinks],
                "policy_engine": type(self.policy_engine).__name__,
                "policy_ruleset_version": POLICY_RULESET_VERSION,
                "event_log_backend": type(self.event_log).__name__,
                "score_version": config.SCORE_VERSION,
            },
        )

        # 1. Collect signals
        signals = collect_signals(use_real=self.use_real_sources)
        self._result.signals_collected = len(signals)
        save_signals_jsonl(signals)

        self.audit.append(
            actor="system:event_pipeline",
            action="collect",
            entity_type="batch",
            entity_id="signals",
            details={"count": len(signals)},
        )

        # 2. Publicar SignalCollected por cada señal
        for sig in signals:
            evt = SignalCollected(
                event_id=make_event_id("sig", sig.signal_id),
                event_type="signal_collected",
                timestamp=now_iso(),
                payload={"signal": sig.to_dict()},
            )
            self.bus.publish(evt)
            # Corrección A: persistir en event_log
            self._persist_event(evt)

        # 3. Dedup batch sobre todos los casos extraídos
        if self._cases_buffer:
            self._cases_buffer, ndup = merge_duplicates(self._cases_buffer)
            self._result.duplicates_found = ndup
            self.audit.append(
                actor="system:event_pipeline",
                action="dedup_batch",
                entity_type="batch",
                entity_id="all",
                details={
                    "duplicates_found": ndup,
                    "canonical_count": sum(1 for c in self._cases_buffer if c.is_canonical),
                },
            )

            # 4. Para cada caso (canónico Y duplicate): evaluar policy + ejecutar sinks
            # Corrección C: PolicyEngine decide, sinks ejecutan
            for case in self._cases_buffer:
                # 4a. PolicyEngine.evaluate(case) → PolicyDecision
                decision = self.policy_engine.evaluate(case)
                self._result.policy_decisions += 1
                if decision.should_suppress():
                    self._result.policy_suppressed += 1
                if decision.should_generate_whatsapp():
                    self._result.policy_whatsapp_intents += 1
                if decision.boost_delta > 0:
                    self._result.policy_boosted += 1
                    # Corrección C: aplicar boost al case (PolicyEngine es pure)
                    apply_boost(case, decision)

                # 4b. Publicar DecisionIssued (corrección C: namespace Decision)
                dec_evt = DecisionIssued(
                    event_id=make_event_id("dec", case.case_id),
                    event_type="decision_issued",
                    timestamp=now_iso(),
                    payload={
                        "case_id": case.case_id,
                        "decision": {
                            "case_id": decision.case_id,
                            "actions": list(decision.actions),
                            "reasons": list(decision.reasons),
                            "boost_delta": decision.boost_delta,
                            "decision_id": decision.decision_id,
                            "ruleset_version": decision.ruleset_version,
                            "metadata": decision.metadata,
                        },
                    },
                )
                self.bus.publish(dec_evt)
                self._persist_event(dec_evt)

                # 4c. Publicar CaseDeduplicated (incluso si es duplicate, para auditoría)
                dedup_evt = CaseDeduplicated(
                    event_id=make_event_id("dedup", case.case_id),
                    event_type="case_deduplicated",
                    timestamp=now_iso(),
                    payload={
                        "case": case.to_dict(),
                        "is_canonical": case.is_canonical,
                    },
                )
                self.bus.publish(dedup_evt)
                self._persist_event(dedup_evt)

                # 4d. Si la policy suprime, NO ejecutar sinks
                if decision.should_suppress():
                    self.audit.append(
                        actor="system:event_pipeline",
                        action="case_suppressed",
                        entity_type="case",
                        entity_id=case.case_id,
                        details={
                            "decision_id": decision.decision_id,
                            "actions": decision.actions,
                            "duplicate_of": case.duplicate_of,
                        },
                    )
                    continue

                # 4e. Ejecutar sinks con PolicyDecision (corrección C)
                sinks_result = self.fanout.write_with_decision(case, decision)
                self._result.sinks_results.append({
                    "case_id": case.case_id,
                    "decision_id": decision.decision_id,
                    "actions": decision.actions,
                    "sinks": sinks_result,
                })

                # 4f. Publicar CasePublished
                pub_evt = CasePublished(
                    event_id=make_event_id("pub", case.case_id),
                    event_type="case_published",
                    timestamp=now_iso(),
                    payload={
                        "case_id": case.case_id,
                        "sinks_result": sinks_result,
                        "policy_actions": decision.actions,
                    },
                )
                self.bus.publish(pub_evt)
                self._persist_event(pub_evt)

        # 5. Flush sinks (enviar batch pendiente de Google Sheets)
        flush_results = self.fanout.flush_all()
        if flush_results:
            self.audit.append(
                actor="system:event_pipeline",
                action="sinks_flush",
                entity_type="batch",
                entity_id="all",
                details={"flush_results": flush_results},
            )

        # 6. Stats finales
        bus_stats = self.bus.stats()
        self._result.events_published = bus_stats["published"]
        self._result.events_rejected = bus_stats["rejected"]
        self._result.cases_canonical = sum(1 for c in self._cases_buffer if c.is_canonical)
        self._result.cases = list(self._cases_buffer)
        self._result.extractor_used = type(self._ensure_extractor()).__name__ if self._cases_buffer else "none"
        self._result.sinks_used = [s.sink_id for s in self.sinks]
        self._result.policy_engine_used = type(self.policy_engine).__name__
        self._result.audit_entries = len(self.audit.read_all())
        self._result.audit_chain_ok = self.audit.verify_chain()
        self._result.event_log_count = self.event_log.count()
        self._result.event_log_backend = type(self.event_log).__name__
        self._result.duration_seconds = round(time.time() - t0, 2)

        # 7. Persistir casos
        save_cases_jsonl(self._cases_buffer)

        self.audit.append(
            actor="system:event_pipeline",
            action="pipeline_end",
            entity_type="batch",
            entity_id="run",
            details={
                "duration_seconds": self._result.duration_seconds,
                "signals_collected": self._result.signals_collected,
                "cases_extracted": self._result.cases_extracted,
                "duplicates_found": self._result.duplicates_found,
                "cases_canonical": self._result.cases_canonical,
                "events_published": self._result.events_published,
                "events_rejected": self._result.events_rejected,
                "policy_decisions": self._result.policy_decisions,
                "policy_suppressed": self._result.policy_suppressed,
                "policy_whatsapp_intents": self._result.policy_whatsapp_intents,
                "policy_boosted": self._result.policy_boosted,
                "audit_chain_ok": self._result.audit_chain_ok,
                "event_log_count": self._result.event_log_count,
                "event_log_backend": self._result.event_log_backend,
                "score_version": config.SCORE_VERSION,
            },
        )

        return self._result

    def _persist_event(self, event) -> None:
        """Corrección A: persistir evento en event_log (append-only)."""
        try:
            payload = event_to_dict(event).get("payload", {})
            self.event_log.append(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=payload,
                timestamp=event.timestamp,
                version=config.SCORE_VERSION,  # por ahora = score_version
            )
        except Exception as e:
            self.audit.append(
                actor="system:event_pipeline",
                action="event_log_error",
                entity_type="event",
                entity_id=event.event_id,
                details={"error": str(e)},
            )

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    def print_summary(self, result: EventPipelineResult) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — Event Pipeline v2.0")
        print("=" * 70)
        print(f"  Modo:               event_driven_pipeline")
        print(f"  Extractor:          {result.extractor_used}")
        print(f"  PolicyEngine:       {result.policy_engine_used}")
        print(f"  Score version:      {config.SCORE_VERSION}")
        print(f"  Sinks:              {', '.join(result.sinks_used)}")
        print(f"  Event log backend:  {result.event_log_backend} ({result.event_log_count} eventos)")
        print(f"  Duración:           {result.duration_seconds}s")
        print("-" * 70)
        print(f"  Señales recogidas:  {result.signals_collected}")
        print(f"  Casos extraídos:    {result.cases_extracted}")
        print(f"  Duplicados:         {result.duplicates_found}")
        print(f"  Casos canónicos:    {result.cases_canonical}")
        print("-" * 70)
        print(f"  PolicyEngine:")
        print(f"    Decisiones:       {result.policy_decisions}")
        print(f"    Suprimidos:       {result.policy_suppressed}")
        print(f"    WhatsApp intents: {result.policy_whatsapp_intents}")
        print(f"    Boosted (+5):     {result.policy_boosted}")
        print("-" * 70)
        print(f"  Eventos publicados: {result.events_published}")
        print(f"  Eventos rechazados: {result.events_rejected}")
        print(f"  Audit trail:        {result.audit_entries} entradas")
        print(f"  Cadena íntegra:     {'✓' if result.audit_chain_ok else '✗ ROTA'}")
        print("-" * 70)
        print(f"  Sinks ejecutados:   {len(result.sinks_results)} casos")

        # Resumen sinks
        wa_links = 0
        wa_skipped = 0
        sheets_queued = 0
        sheets_suppressed = 0
        for sr in result.sinks_results:
            wa = sr["sinks"].get("whatsapp", {})
            if wa.get("status") == "ok":
                wa_links += 1
            else:
                wa_skipped += 1
            gs = sr["sinks"].get("google_sheets", {})
            if gs.get("status") == "queued":
                sheets_queued += 1
            elif gs.get("status") == "skipped":
                sheets_suppressed += 1
        print(f"  WhatsApp links:     {wa_links} generados, {wa_skipped} skipped")
        print(f"  Sheets encolados:   {sheets_queued} | suprimidos: {sheets_suppressed}")
        print("=" * 70)

        # Top 3 críticos
        crit = sorted(
            [c for c in result.cases if c.is_canonical and c.score >= 60],
            key=lambda c: c.score, reverse=True,
        )[:3]
        if crit:
            print("\n  TOP 3 CASOS PRIORITARIOS:")
            for c in crit:
                wa_link = " [+WA]" if c.whatsapp_link else ""
                print(f"    [{c.score_band:8s}] {c.score:3d} | {c.case_id} | "
                      f"{c.problem_type:15s} | {c.jurisdiction:12s}{wa_link}")
            print()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST event_pipeline.py")
    print("=" * 70)

    # Sin API key → falla al primer extract (pre-flight)
    os.environ.pop("RADAR_LLM_API_KEY", None)
    os.environ.pop("RADAR_WEBHOOK_URL", None)

    pipeline = EventPipeline(use_real_sources=False)
    try:
        result = pipeline.run()
        print(f"\n  ✗ FAIL: debería fallar sin API key")
        sys.exit(1)
    except MissingLLMApiKeyError as e:
        assert "Missing LLM API key" in str(e)
        print(f"  ✓ Sin API key → '{e}'")

    # Con API key dummy → el pipeline corre, los handlers fallan en HTTP
    # (esperado: no hay endpoint real)
    os.environ["RADAR_LLM_API_KEY"] = "dummy-key-for-wiring-test"
    try:
        pipeline2 = EventPipeline(use_real_sources=False)
        try:
            result = pipeline2.run()
            pipeline2.print_summary(result)
            # Verificaciones del wiring (no del éxito de extracción)
            assert result.signals_collected > 0, "Should have collected signals"
            assert result.events_published > 0, "Should have published events"
            assert "whatsapp" in result.sinks_used
            assert "google_sheets" in result.sinks_used
            assert result.audit_chain_ok, "Audit chain should be intact"
            print(f"\n  ✓ Wiring verificado:")
            print(f"    - Bus publicó {result.events_published} eventos")
            print(f"    - {result.events_rejected} rechazados por validación")
            print(f"    - Sinks registrados: {result.sinks_used}")
            print(f"    - Audit chain íntegra: {result.audit_chain_ok}")
            print(f"    - Casos extraídos: {result.cases_extracted} (0 esperado con API key dummy)")
        except Exception as e:
            # Si hay errores inesperados, mostrar
            print(f"  ⚠ Pipeline corrió con error inesperado: {e}")
            raise
    finally:
        os.environ.pop("RADAR_LLM_API_KEY", None)

    print(f"\n  Para correr el pipeline completo (máquina del operador):")
    print(f"    export RADAR_LLM_API_KEY=<tu-api-key>")
    print(f"    export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec")
    print(f"    python main.py --event-pipeline")
```


=== FILE: event_types.py (238 líneas) ===

```"""
event_types.py — Eventos del pipeline event-driven v2.0.

Lectura del sistema: lead intelligence + rule-based triage system con auditoría completa.
No es agent system, no es event sourcing puro, no es CRM.

3 namespaces conceptuales separados (corrección C del spec de estabilización):

  ── Signal namespace ──
  Observaciones crudas del mundo exterior. No son decisiones del sistema.
    SignalCollected       : señal cruda detectada en una fuente pública

  ── Case namespace ──
  Estado agregado del sistema sobre una señal. No son decisiones.
    EntitiesExtracted     : caso parcial después de extracción LLM
    CaseScored            : caso con score calculado (estado agregado)
    CaseDeduplicated      : caso después de dedup (estado agregado)

  ── Decision namespace ──
  Intenciones políticas del sistema. Output de PolicyEngine.
    DecisionIssued        : PolicyDecision emitida por PolicyEngine (era PolicyEvaluated)
    CasePublished         : confirmación de ejecución de sinks (post-decision)

  ── Meta ──
    EventRejected         : evento inválido, no se procesa

Cada evento es inmutable (frozen dataclass) y cumple el data_contract del spec v2.0.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from models import Signal, Case, now_iso


# ===========================================================================
# Signal namespace — observaciones crudas del mundo exterior
# ===========================================================================
@dataclass(frozen=True)
class SignalCollected:
    """Señal cruda detectada en una fuente pública. Observación, no decisión."""
    event_id: str
    event_type: str = "signal_collected"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def signal(self) -> Signal:
        return Signal(**self.payload["signal"])


# ===========================================================================
# Case namespace — estado agregado del sistema sobre una señal
# ===========================================================================
@dataclass(frozen=True)
class EntitiesExtracted:
    """Caso parcial después de extracción LLM. Estado agregado."""
    event_id: str
    event_type: str = "entities_extracted"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_partial(self) -> Case:
        return Case(**self.payload["case_partial"])


@dataclass(frozen=True)
class CaseScored:
    """Caso con score calculado. Estado agregado, NO decisión."""
    event_id: str
    event_type: str = "case_scored"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case(self) -> Case:
        return Case(**self.payload["case"])


@dataclass(frozen=True)
class CaseDeduplicated:
    """Caso después de dedup. Estado agregado, NO decisión."""
    event_id: str
    event_type: str = "case_deduplicated"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case(self) -> Case:
        return Case(**self.payload["case"])

    @property
    def is_canonical(self) -> bool:
        return self.payload.get("is_canonical", True)


# ===========================================================================
# Decision namespace — intenciones políticas del sistema
# ===========================================================================
@dataclass(frozen=True)
class DecisionIssued:
    """
    Decisión emitida por PolicyEngine.

    Corrección C del spec de estabilización: renombrado desde PolicyEvaluated
    para que quede claro que esto es una DECISIÓN (intención política), no un
    evento de evaluación intermedia.

    Una DecisionIssued contiene:
      - case_id: caso sobre el que se decidió
      - decision: PolicyDecision serializada (actions, reasons, boost_delta,
                  decision_id, ruleset_version)
    """
    event_id: str
    event_type: str = "decision_issued"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.payload["case_id"]

    @property
    def decision(self) -> Dict[str, Any]:
        return self.payload.get("decision", {})

    @property
    def actions(self) -> List[str]:
        return self.decision.get("actions", [])

    @property
    def should_suppress(self) -> bool:
        return "suppress_output" in self.actions


@dataclass(frozen=True)
class CasePublished:
    """
    Confirmación de ejecución de sinks sobre un caso, post-decisión.

    Es un evento del namespace Decision porque registra la consecuencia de una
    DecisionIssued (los sinks ejecutaron lo que la policy mandó).
    """
    event_id: str
    event_type: str = "case_published"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.payload["case_id"]

    @property
    def sinks_result(self) -> Dict[str, Any]:
        return self.payload.get("sinks_result", {})


# ===========================================================================
# Meta — eventos de control
# ===========================================================================
@dataclass(frozen=True)
class EventRejected:
    """Evento inválido. No se dispatchea a handlers."""
    event_id: str
    event_type: str = "event_rejected"
    timestamp: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        return self.payload.get("reason", "")

    @property
    def original_event_type(self) -> str:
        return self.payload.get("original_event_type", "")


# ===========================================================================
# Registro de tipos (para validación y dispatch)
# ===========================================================================
EVENT_TYPES = {
    # Signal namespace
    "signal_collected": SignalCollected,
    # Case namespace
    "entities_extracted": EntitiesExtracted,
    "case_scored": CaseScored,
    "case_deduplicated": CaseDeduplicated,
    # Decision namespace
    "decision_issued": DecisionIssued,
    "case_published": CasePublished,
    # Meta
    "event_rejected": EventRejected,
}

# Mapeo para backward-compat: PolicyEvaluated → DecisionIssued
DEPRECATED_EVENT_TYPES = {
    "policy_evaluated": "decision_issued",
}


# Namespace helper (para filtros y debugging)
SIGNAL_EVENTS = {"signal_collected"}
CASE_EVENTS = {"entities_extracted", "case_scored", "case_deduplicated"}
DECISION_EVENTS = {"decision_issued", "case_published"}
META_EVENTS = {"event_rejected"}


# ===========================================================================
# Helpers
# ===========================================================================
def make_event_id(prefix: str, seed: str) -> str:
    """Genera ID estable para un evento."""
    import hashlib
    h = hashlib.sha256(f"{seed}|{now_iso()}".encode("utf-8")).hexdigest()[:12]
    return f"evt-{prefix}-{h}"


def event_to_dict(event) -> Dict[str, Any]:
    """Serializa evento a dict (para audit log y event_log)."""
    return asdict(event)


__all__ = [
    # Signal namespace
    "SignalCollected",
    # Case namespace
    "EntitiesExtracted", "CaseScored", "CaseDeduplicated",
    # Decision namespace
    "DecisionIssued", "CasePublished",
    # Meta
    "EventRejected",
    # Registries
    "EVENT_TYPES", "DEPRECATED_EVENT_TYPES",
    "SIGNAL_EVENTS", "CASE_EVENTS", "DECISION_EVENTS", "META_EVENTS",
    # Helpers
    "make_event_id", "event_to_dict",
]
```


=== FILE: event_validator.py (309 líneas) ===

```"""
event_validator.py — Validación de eventos contra el data_contract v2.0.

Regla del spec: `requires_event_validation: true`

Cada evento debe pasar por validate() antes de ser dispatchado por el bus.
Si falla, se emite un EventRejected y el original no se procesa.

Data_contract:
    case_id: string (no vacío)
    patent: string (puede estar vacío)
    jurisdiction: string (puede estar vacío)
    score: number (0-100)
    source: string (no vacío)
    evidence: string (no vacío)
    timestamp: iso8601 (parseable)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

from event_types import EVENT_TYPES


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]


# ---------------------------------------------------------------------------
# Validators por tipo de dato
# ---------------------------------------------------------------------------
def _is_string(v) -> bool:
    return isinstance(v, str)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_iso8601(v) -> bool:
    if not isinstance(v, str) or not v:
        return False
    try:
        # fromisoformat soporta tz offsets desde 3.11+; para 3.10 fallback
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Validator principal
# ---------------------------------------------------------------------------
def validate_event(event) -> ValidationResult:
    """
    Valida un evento contra el data_contract.

    Cada tipo de evento tiene campos obligatorios distintos:
        - SignalCollected: requiere signal con raw_text + source_id + source_url + detected_at
        - EntitiesExtracted: requiere case_partial con case_id + source_id + evidence_text + timestamp
        - CaseScored: requiere case con case_id + score + source_id + evidence_text + timestamp
        - CaseDeduplicated: requiere case + is_canonical
        - CasePublished: requiere case_id + sinks_result
        - EventRejected: siempre válido (es el fallback)
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Campos base (todos los eventos concretos los tienen)
    if not getattr(event, "event_id", ""):
        errors.append("event_id is empty")
    if not getattr(event, "event_type", ""):
        errors.append("event_type is empty")
    if not _is_iso8601(getattr(event, "timestamp", "")):
        errors.append(f"timestamp is not iso8601: {getattr(event, 'timestamp', '')!r}")
    if not isinstance(getattr(event, "payload", None), dict):
        errors.append("payload is not a dict")
        return ValidationResult(False, errors, warnings)

    event_type = event.event_type
    payload = event.payload

    # Validación por tipo
    if event_type == "signal_collected":
        sig = payload.get("signal")
        if not isinstance(sig, dict):
            errors.append("payload.signal must be a dict")
        else:
            for f in ("source_id", "source_url", "raw_text", "detected_at"):
                if not sig.get(f):
                    errors.append(f"signal.{f} is empty")
            if sig.get("detected_at") and not _is_iso8601(sig["detected_at"]):
                errors.append(f"signal.detected_at is not iso8601: {sig.get('detected_at')!r}")

    elif event_type == "entities_extracted":
        cp = payload.get("case_partial")
        if not isinstance(cp, dict):
            errors.append("payload.case_partial must be a dict")
        else:
            for f in ("case_id", "source_id", "evidence_text", "timestamp"):
                if not cp.get(f):
                    errors.append(f"case_partial.{f} is empty")
            if cp.get("timestamp") and not _is_iso8601(cp["timestamp"]):
                errors.append(f"case_partial.timestamp is not iso8601")
            if "score" in cp and not _is_number(cp["score"]):
                errors.append(f"case_partial.score is not a number: {cp.get('score')!r}")

    elif event_type == "case_scored":
        c = payload.get("case")
        if not isinstance(c, dict):
            errors.append("payload.case must be a dict")
        else:
            errors.extend(_validate_case_contract(c))
            # Corrección B: score_version recomendado (warning si falta)
            if not c.get("score_version"):
                warnings.append("case.score_version is empty (recommended: v1.0_weighted_sum)")

    elif event_type == "case_deduplicated":
        c = payload.get("case")
        if not isinstance(c, dict):
            errors.append("payload.case must be a dict")
        else:
            errors.extend(_validate_case_contract(c))
            if not c.get("score_version"):
                warnings.append("case.score_version is empty (recommended: v1.0_weighted_sum)")
        if "is_canonical" not in payload:
            errors.append("payload.is_canonical is missing")

    elif event_type == "case_published":
        if not payload.get("case_id"):
            errors.append("payload.case_id is empty")
        if "sinks_result" not in payload:
            errors.append("payload.sinks_result is missing")

    elif event_type == "event_rejected":
        pass  # siempre válido

    elif event_type == "decision_issued":
        # Corrección C: renombrado desde policy_evaluated
        # Namespace Decision: contiene PolicyDecision serializada
        if not payload.get("case_id"):
            errors.append("payload.case_id is empty")
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            errors.append("payload.decision must be a dict")
        else:
            if not isinstance(decision.get("actions"), list):
                errors.append("decision.actions must be a list")
            if not isinstance(decision.get("reasons"), list):
                errors.append("decision.reasons must be a list")
            if not isinstance(decision.get("boost_delta"), int):
                errors.append(f"decision.boost_delta must be int: {decision.get('boost_delta')!r}")
            # Corrección B: ruleset_version obligatorio (contrato formal de PolicyEngine)
            if not decision.get("ruleset_version"):
                errors.append("decision.ruleset_version is empty (PolicyEngine contract requires it)")
            if not decision.get("decision_id"):
                errors.append("decision.decision_id is empty (idempotency key)")

    elif event_type == "policy_evaluated":
        # Backward-compat alias (deprecado, ver DEPRECATED_EVENT_TYPES)
        # Mismo schema que decision_issued
        warnings.append("event_type 'policy_evaluated' is deprecated, use 'decision_issued'")
        if not payload.get("case_id"):
            errors.append("payload.case_id is empty")
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            errors.append("payload.decision must be a dict")
        else:
            if not isinstance(decision.get("actions"), list):
                errors.append("decision.actions must be a list")
            if not isinstance(decision.get("reasons"), list):
                errors.append("decision.reasons must be a list")
            if not isinstance(decision.get("boost_delta"), int):
                errors.append(f"decision.boost_delta must be int: {decision.get('boost_delta')!r}")

    else:
        warnings.append(f"unknown event_type: {event_type}")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def _validate_case_contract(c: dict) -> List[str]:
    """
    Valida un case contra el data_contract del spec v2.0:
        case_id: string (no vacío)
        patent: string
        jurisdiction: string
        score: number (0-100)
        source: string (no vacío)  → en nuestro modelo es source_id
        evidence: string (no vacío) → en nuestro modelo es evidence_text
        timestamp: iso8601
    """
    errors: List[str] = []

    if not _is_string(c.get("case_id")) or not c["case_id"]:
        errors.append("case.case_id must be non-empty string")
    if not _is_string(c.get("patent")):
        errors.append("case.patent must be string (can be empty)")
    if not _is_string(c.get("jurisdiction")):
        errors.append("case.jurisdiction must be string (can be empty)")
    if not _is_number(c.get("score")):
        errors.append(f"case.score must be number: {c.get('score')!r}")
    elif not (0 <= c["score"] <= 100):
        errors.append(f"case.score out of range [0,100]: {c['score']}")
    if not _is_string(c.get("source_id")) or not c["source_id"]:
        errors.append("case.source_id must be non-empty string (data_contract: source)")
    if not _is_string(c.get("evidence_text")) or not c["evidence_text"]:
        errors.append("case.evidence_text must be non-empty string (data_contract: evidence)")
    if not _is_iso8601(c.get("timestamp", "")):
        errors.append(f"case.timestamp must be iso8601: {c.get('timestamp')!r}")

    return errors


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from event_types import SignalCollected, CaseScored, make_event_id
    from models import Signal, Case, now_iso
    from mock_sources import generate_mock_signals

    print("=== Smoke test event_validator ===\n")

    sigs = generate_mock_signals()
    sig = sigs[0]
    sig_dict = sig.to_dict()

    # 1. SignalCollected válido
    evt = SignalCollected(
        event_id=make_event_id("sig", sig.signal_id),
        event_type="signal_collected",
        timestamp=now_iso(),
        payload={"signal": sig_dict},
    )
    r = validate_event(evt)
    assert r.valid, f"Should be valid: {r.errors}"
    print(f"  ✓ SignalCollected válido ({len(r.warnings)} warnings)")

    # 2. SignalCollected inválido (sin source_id)
    bad_sig = dict(sig_dict)
    bad_sig["source_id"] = ""
    evt2 = SignalCollected(
        event_id=make_event_id("sig-bad", "x"),
        event_type="signal_collected",
        timestamp=now_iso(),
        payload={"signal": bad_sig},
    )
    r2 = validate_event(evt2)
    assert not r2.valid, "Should be invalid"
    assert any("source_id" in e for e in r2.errors)
    print(f"  ✓ SignalCollected inválido detectado: {r2.errors[0]}")

    # 3. CaseScored válido
    case = Case(
        case_id="case-test",
        signal_id="sig-test",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1",
        profile_url="",
        timestamp=now_iso(),
        name_or_alias="Test",
        evidence_text="Test evidence",
        score=75,
    )
    evt3 = CaseScored(
        event_id=make_event_id("case", case.case_id),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": case.to_dict()},
    )
    r3 = validate_event(evt3)
    assert r3.valid, f"Should be valid: {r3.errors}"
    print(f"  ✓ CaseScored válido (data_contract OK)")

    # 4. CaseScored inválido (score fuera de rango)
    bad_case = case.to_dict()
    bad_case["score"] = 150
    evt4 = CaseScored(
        event_id=make_event_id("case-bad", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case},
    )
    r4 = validate_event(evt4)
    assert not r4.valid
    assert any("out of range" in e for e in r4.errors)
    print(f"  ✓ CaseScored inválido detectado: {r4.errors[0]}")

    # 5. Timestamp inválido
    bad_case2 = case.to_dict()
    bad_case2["timestamp"] = "not-a-date"
    evt5 = CaseScored(
        event_id=make_event_id("case-bad2", "x"),
        event_type="case_scored",
        timestamp=now_iso(),
        payload={"case": bad_case2},
    )
    r5 = validate_event(evt5)
    assert not r5.valid
    assert any("iso8601" in e for e in r5.errors)
    print(f"  ✓ Timestamp inválido detectado: {r5.errors[0]}")

    print("\n=== Todos los smoke tests OK ===")
```


=== FILE: extractor.py (333 líneas) ===

```"""
extractor.py — Extracción de entidades, normalización y privacy filter.

Pipeline de extracción:
  raw_text → privacy_filter → regex_extractor → normalize → Case (parcial)

El extractor usa reglas (regex + keyword matching) en Fase 1. El LLM extractor
se documenta como stub para Fase 2 (ver LLMExtractor al final).

Privacy filter: rechaza señales que contengan PII explícita (DNI, CUIT/CUIL,
email, teléfono, dirección) o marcadas como privadas. Las señales rechazadas
se loguean en audit trail pero no generan caso.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from models import Signal, Case, AR_TZ, now_iso, short_id
import config


# ---------------------------------------------------------------------------
# Privacy filter
# ---------------------------------------------------------------------------
@dataclass
class PrivacyFilterResult:
    passed: bool
    reason: str = ""
    matched_patterns: List[str] = field(default_factory=list)
    masked_text: str = ""


def privacy_filter(signal: Signal) -> PrivacyFilterResult:
    """
    Aplica filtro de privacidad a una señal.

    Rechaza si:
    - Contiene DNI, CUIT/CUIL, email, teléfono o dirección explícita
    - La fuente es marcada como privada en raw_metadata
    """
    text = signal.raw_text
    matched: List[str] = []

    for pattern in config.PII_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append(pattern)

    # Verificar flag de privacidad en metadata
    if signal.raw_metadata.get("is_private", False):
        return PrivacyFilterResult(
            passed=False,
            reason="metadata marks signal as private",
            matched_patterns=matched,
        )

    if matched:
        return PrivacyFilterResult(
            passed=False,
            reason=f"PII detected: {len(matched)} pattern(s)",
            matched_patterns=matched,
        )

    # Masking opcional (no se aplica en Fase 1: rechazamos directo)
    return PrivacyFilterResult(passed=True, masked_text=text)


# ---------------------------------------------------------------------------
# Extracción regex
# ---------------------------------------------------------------------------
def _extract_patent(text: str) -> str:
    """Extrae patente argentina (formato nuevo AB123CD o viejo ABC123)."""
    for pattern in config.PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    # Patentes con palabra "patente" seguida de valor
    m = re.search(r"patente\s+([A-Z]{2,3}\s?\d{3}\s?[A-Z]{0,2})", text, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def _extract_amount(text: str) -> Optional[float]:
    """Extrae monto en pesos argentinos."""
    # $18.500 / $4.500.000 / 18500 pesos / $45.000
    patterns = [
        r"\$\s?(\d{1,3}(?:[.,]\d{3})+)",
        r"\$\s?(\d+(?:[.,]\d{3})*)",
        r"(\d{1,3}(?:[.,]\d{3})+)\s?pesos",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _extract_year(text: str) -> Optional[int]:
    """Extrae año entre 1990 y año actual+1."""
    import datetime
    current_year = datetime.datetime.now().year
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    for y in matches:
        year = int(y)
        if 1990 <= year <= current_year + 1:
            return year
    return None


def _map_value(text: str, mapping: Dict[str, str]) -> str:
    """Mapea texto a valor canónico usando un diccionario de alias."""
    text_lower = text.lower()
    for alias, canonical in mapping.items():
        if alias in text_lower:
            return canonical
    return ""


def _extract_jurisdiction(text: str, hint: str = "") -> str:
    """Extrae jurisdicción: usa hint de metadata si está, sino regex."""
    if hint:
        # Hint ya viene como código canónico
        return hint
    text_lower = text.lower()
    for alias, canonical in config.JURISDICTION_MAP.items():
        if alias in text_lower:
            return canonical
    return ""


def _extract_locality(text: str, hint: str = "") -> str:
    """Extrae localidad. En Fase 1 usa el hint de metadata o heuristicas simples."""
    if hint:
        return hint
    # Heurística: "estoy en X", "zona X", "vivo en X"
    patterns = [
        r"(?:estoy en|zona|vivo en|de)\s+([A-ZÁÉÍÓÚa-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚa-záéíóúñ]+)?)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            loc = m.group(1).strip().title()
            # Filtrar falsos positivos comunes
            if loc.lower() not in {"el", "la", "los", "las", "mi", "tu", "su"}:
                return loc
    return ""


def _extract_problem_type(text: str, hint: str = "") -> str:
    """Extrae tipo de problema."""
    if hint:
        return hint
    text_lower = text.lower()
    # Orden de prioridad: problemas específicos antes que genéricos
    priority_order = [
        "fotomulta", "foto multa", "multa de ruta", "apsv",
        "libre deuda", "transferencia", "transferir",
        "regularización vehicular", "regularizacion", "regularización",
        "patente", "vtv", "multas", "multa",
    ]
    for kw in priority_order:
        if kw in text_lower:
            return config.PROBLEM_TYPE_MAP.get(kw, kw)
    return ""


def _extract_vehicle_type(text: str) -> str:
    """Extrae tipo de vehículo."""
    return _map_value(text, config.VEHICLE_TYPE_MAP)


# ---------------------------------------------------------------------------
# Normalización de texto para dedup
# ---------------------------------------------------------------------------
def normalize_text_for_hash(text: str) -> str:
    """
    Normaliza texto para hashing en dedup:
    - lowercase
    - sin acentos
    - sin puntuación
    - sin whitespace múltiple
    - sin URLs/menciones/hashtags
    """
    import unicodedata
    # Quitar URLs, menciones, hashtags
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"@\w+", " ", t)
    t = re.sub(r"#\w+", " ", t)
    # Lowercase
    t = t.lower()
    # Sin acentos
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    # Sin puntuación
    t = re.sub(r"[^\w\s]", " ", t)
    # Sin whitespace múltiple
    t = re.sub(r"\s+", " ", t).strip()
    return t


def text_hash(text: str) -> str:
    """SHA-256 del texto normalizado (para dedup)."""
    return hashlib.sha256(normalize_text_for_hash(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LLM extractor (stub para Fase 2)
# ---------------------------------------------------------------------------
class LLMExtractor:
    """
    Stub de extractor LLM para Fase 2.

    En Fase 1 usamos extractor regex (más simple, determinista, sin costo API).
    En Fase 2 se puede reemplazar por una llamada a un LLM (GLM-4, GPT-4, etc.)
    que tome el raw_text y devuelva JSON con los campos de ENTITY_FIELDS.

    Ventajas del LLM:
    - Mejor extracción de contexto implícito
    - Mejor manejo de ambigüedad
    - Mejor normalización de jerga local

    Desventajas:
    - Costo por llamada
    - Latencia
    - No determinista (usar temperature=0 + cache)
    - Riesgo de alucinación (siempre validar con regex post-extracción)

    Firma esperada (Fase 2):
        def extract(self, signal: Signal) -> Dict[str, Any]:
            prompt = f"Extraer entidades del texto: {signal.raw_text}"
            response = llm.chat(prompt, schema=ENTITY_FIELDS)
            return response
    """

    def extract(self, signal: Signal) -> Dict[str, Any]:
        raise NotImplementedError(
            "LLMExtractor requiere API key. Usar extract_with_regex() en Fase 1."
        )


# ---------------------------------------------------------------------------
# Extractor principal (Fase 1: regex)
# ---------------------------------------------------------------------------
def extract_with_regex(signal: Signal) -> Dict[str, Any]:
    """
    Extrae entidades de una señal usando regex + keyword matching.

    Returns:
        Dict con campos de ENTITY_FIELDS normalizados.
    """
    text = signal.raw_text
    meta = signal.raw_metadata

    extracted = {
        "name_or_alias": signal.author_alias,
        "profile_url": signal.profile_url,
        "vehicle_type": _extract_vehicle_type(text),
        "patent": _extract_patent(text),
        "jurisdiction": _extract_jurisdiction(text, meta.get("jurisdiction_hint", "")),
        "locality": _extract_locality(text, meta.get("locality_hint", "")),
        "problem_type": _extract_problem_type(text, meta.get("problem_hint", "")),
        "year": _extract_year(text),
        "amount": _extract_amount(text) or meta.get("amount_hint"),
        "source_name": signal.source_id,
        "source_url": signal.source_url,
        "timestamp": meta.get("published_at", signal.detected_at),
        "evidence_text": text,
    }
    return extracted


def signal_to_case(signal: Signal) -> Tuple[Optional[Case], str]:
    """
    Pipeline completo de extracción sobre una señal.

    Returns:
        (Case, status) donde status es 'extracted' o 'rejected_privacy' o 'no_entity'.
    """
    # 1. Privacy filter
    pf = privacy_filter(signal)
    if not pf.passed:
        return None, f"rejected_privacy:{pf.reason}"

    # 2. Extracción
    extracted = extract_with_regex(signal)

    # 3. Validación mínima: si no hay problem_type ni patent ni jurisdiction, descartar
    if not extracted["problem_type"] and not extracted["patent"] and not extracted["jurisdiction"]:
        return None, "no_entity"

    # 4. Crear Case parcial (scoring y dedup se hacen después)
    case = Case(
        case_id=short_id("case", f"{signal.signal_id}|{extracted['timestamp']}"),
        signal_id=signal.signal_id,
        source_id=signal.source_id,
        source_url=signal.source_url,
        profile_url=signal.profile_url,
        timestamp=extracted["timestamp"],
        name_or_alias=extracted["name_or_alias"],
        vehicle_type=extracted["vehicle_type"],
        patent=extracted["patent"],
        jurisdiction=extracted["jurisdiction"],
        locality=extracted["locality"],
        problem_type=extracted["problem_type"],
        year=extracted["year"],
        amount=extracted["amount"],
        evidence_text=extracted["evidence_text"],
        normalized_text_hash=text_hash(signal.raw_text),
    )
    return case, "extracted"


if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    sigs = generate_mock_signals()
    print(f"Procesando {len(sigs)} señales…")
    extracted = 0
    rejected = 0
    for s in sigs[:5]:
        case, status = signal_to_case(s)
        if case:
            extracted += 1
            print(f"  ✓ [{status}] {case.case_id} | {case.problem_type} | {case.jurisdiction} | {case.patent or '—'} | {case.amount or '—'}")
        else:
            rejected += 1
            print(f"  ✗ [{status}] {s.signal_id}")
    print(f"\nResumen: {extracted} extraídos, {rejected} rechazados")
```


=== FILE: generate_report.py (399 líneas) ===

```"""
generate_report.py — Genera reporte CRM legible a partir de radar_v4_output.json.

El JSON es para máquinas. Este reporte es para personas comerciales:
responde en 10 segundos: ¿quién tiene el problema? ¿cómo lo contacto? ¿vale la pena?
"""
import json
import sys
from pathlib import Path
from datetime import datetime

OUTPUT_PATH = Path("/home/z/my-project/download/radar_v4_reporte.md")
OUTPUT_TXT_PATH = Path("/home/z/my-project/download/radar_v4_reporte.txt")


def stars(score: int) -> str:
    """Mapea urgency 0-100 a 5 estrellas."""
    if score >= 80:
        return "⭐⭐⭐⭐⭐"
    elif score >= 60:
        return "⭐⭐⭐⭐☆"
    elif score >= 40:
        return "⭐⭐⭐☆☆"
    elif score >= 20:
        return "⭐⭐☆☆☆"
    return "⭐☆☆☆☆"


def confidence_pct(score: int) -> str:
    return f"{score}%"


def problem_short(lead: dict) -> str:
    """Resume el problema en 1 línea clara."""
    reasons = {
        "declara_multas": "Tiene multas/fotomultas",
        "declara_problema_transferencia": "Problema con transferencia",
        "declara_problema_libre_deuda": "Necesita libre deuda",
        "consulta_documentacion": "Consulta sobre trámite",
        "vende_auto_titular": "Vende vehículo (titular)",
        "vende_auto": "Vende vehículo",
        "permuta_auto": "Permuta vehículo",
        "generico": "Lead vehicular genérico",
    }
    base = reasons.get(lead.get("lead_reason", ""), "Lead vehicular")

    # Sumar dolor del quote si está disponible
    qt = lead.get("quoted_text", "").lower()
    if "no es mi auto" in qt or "nisiquiera es" in qt:
        return "Multa que no es suya (error de patente)"
    if "libre deuda falso" in qt:
        return "Compró auto con libre deuda falso"
    if "no me entregó" in qt or "nunca te entregó" in qt:
        return "Vendedor no entregó formulario 08"
    if "multas vencidas sin notificar" in qt:
        return "Multas vencidas sin notificación"
    if "radicado en otra" in qt:
        return "Auto radicado en otra provincia"
    if "con multas impagas" in qt:
        return "Transferencia con multas impagas"
    if "desvinculacion de multas" in qt:
        return "Quiere desvincular multas del vehículo"
    if "par d multas" in qt:
        return "Vender moto con multas"
    if "no me deja transferir" in qt:
        return "No le dejan transferir"
    if "me llegó" in qt and "multa" in qt:
        return "Le llegó multa"
    return base


def vehicle_display(lead: dict) -> str:
    v = lead.get("vehicle_if_detected", "")
    return v.title() if v else "No mencionado"


def city_display(lead: dict) -> str:
    c = lead.get("city_if_detected", "")
    return c if c else "No detectada"


def province_display(lead: dict) -> str:
    p = lead.get("province_if_detected", "")
    return p if p else "No detectada"


def platform_display(lead: dict) -> str:
    p = lead.get("platform", "")
    mapping = {
        "facebook.com": "Facebook",
        "reddit.com": "Reddit",
        "twitter.com": "X (Twitter)",
        "x.com": "X (Twitter)",
        "taringa.net": "Taringa",
    }
    return mapping.get(p, p.title() if p else "Desconocida")


def date_display(lead: dict) -> str:
    d = lead.get("date", "")
    if not d:
        return "No disponible"
    # Intentar formatear
    try:
        if "T" in d:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        return d[:10]
    except Exception:
        return d


def contact_display(lead: dict, field: str) -> str:
    val = lead.get(field, "")
    return val if val else "No encontrado públicamente."


def person_display(lead: dict) -> str:
    name = lead.get("person_name", "")
    if not name or name == "(sin nombre)":
        return "Anónimo (no publicado)"
    return name


def quote_clean(lead: dict, max_len: int = 200) -> str:
    qt = lead.get("quoted_text", "")
    if not qt:
        return ""
    # Limpiar el quote: sacar el nombre del sitio al inicio si está repetido
    if " - " in qt[:80]:
        # Ej: "Hola buenas... - Facebook. Hola buenas..."
        # tomar la parte después del " - "
        parts = qt.split(" - ", 1)
        if len(parts) > 1:
            qt = parts[1]
    # Truncar
    if len(qt) > max_len:
        qt = qt[:max_len - 1] + "…"
    return qt


def generate_report():
    with open("/home/z/my-project/download/radar_v4_output.json") as f:
        data = json.load(f)

    real_leads = data.get("real_leads", [])
    commercial_signals = data.get("commercial_signals", [])

    lines_md = []
    lines_txt = []

    # Header
    lines_md.append("# 🔍 RADAR DE OPORTUNIDADES — Reporte Comercial")
    lines_md.append("")
    lines_md.append(f"**Generado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines_md.append(f"**Misión:** Encontrar personas con problemas vehiculares reales")
    lines_md.append("")
    lines_md.append("---")
    lines_md.append("")

    # Versión texto plano del header
    lines_txt.append("=" * 70)
    lines_txt.append("  RADAR DE OPORTUNIDADES - REPORTE COMERCIAL")
    lines_txt.append("=" * 70)
    lines_txt.append("")
    lines_txt.append(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines_txt.append("")

    # ===== SECCIÓN 1: LEADS CALIENTES =====
    lines_md.append("## 🔥 LEADS CALIENTES (Dolor explícito)")
    lines_md.append("")
    lines_md.append(f"_{len(real_leads)} personas declarando un problema real con multas, transferencia o libre deuda._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  LEADS CALIENTES (Dolor explicito)")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(real_leads)} personas declarando un problema real.")
    lines_txt.append("")

    for i, lead in enumerate(real_leads, 1):
        problem = problem_short(lead)
        person = person_display(lead)
        province = province_display(lead)
        city = city_display(lead)
        vehicle = vehicle_display(lead)
        platform = platform_display(lead)
        date = date_display(lead)
        urgency = stars(lead.get("urgency_score", 0))
        confidence = confidence_pct(lead.get("confidence", 0))
        whatsapp = contact_display(lead, "possible_whatsapp")
        phone = contact_display(lead, "possible_phone")
        profile = lead.get("profile_link", "No disponible")
        post = lead.get("post_link", "No disponible")
        quote = quote_clean(lead)

        # Markdown version
        lines_md.append(f"### Lead #{i}")
        lines_md.append("")
        lines_md.append(f"**Problema:** {problem}  ")
        lines_md.append(f"**Persona:** {person}  ")
        lines_md.append(f"**Provincia:** {province} | **Ciudad:** {city}  ")
        lines_md.append(f"**Vehículo:** {vehicle} | **Plataforma:** {platform}  ")
        lines_md.append(f"**Fecha:** {date}  ")
        lines_md.append(f"**Urgencia:** {urgency}  ")
        lines_md.append(f"**Confianza:** {confidence}  ")
        lines_md.append(f"**WhatsApp:** {whatsapp}  ")
        lines_md.append(f"**Teléfono:** {phone}  ")
        lines_md.append(f"**Perfil:** {profile if profile else 'No disponible'}  ")
        lines_md.append(f"**Publicación:** {post}  ")
        lines_md.append("")
        lines_md.append(f"> {quote}")
        lines_md.append("")
        lines_md.append("---")
        lines_md.append("")

        # Texto plano
        lines_txt.append(f"  Lead #{i}")
        lines_txt.append(f"  Problema: {problem}")
        lines_txt.append(f"  Persona: {person}")
        lines_txt.append(f"  Provincia: {province} | Ciudad: {city}")
        lines_txt.append(f"  Vehiculo: {vehicle} | Plataforma: {platform}")
        lines_txt.append(f"  Fecha: {date}")
        lines_txt.append(f"  Urgencia: {urgency}")
        lines_txt.append(f"  Confianza: {confidence}")
        lines_txt.append(f"  WhatsApp: {whatsapp}")
        lines_txt.append(f"  Telefono: {phone}")
        lines_txt.append(f"  Perfil: {profile}")
        lines_txt.append(f"  Publicacion: {post}")
        lines_txt.append(f"  Comentario:")
        # Wrap quote en texto plano
        for line_wrap in [quote[i:i+68] for i in range(0, len(quote), 68)]:
            lines_txt.append(f"    {line_wrap}")
        lines_txt.append("")

    # ===== SECCIÓN 2: LEADS COMERCIALES =====
    lines_md.append("## 🟡 LEADS COMERCIALES")
    lines_md.append("")
    lines_md.append(f"_{len(commercial_signals)} señales preventivas: personas vendiendo o permutando vehículos (sin dolor explícito declarado, pero con posible necesidad futura de gestión)._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  LEADS COMERCIALES (preventivos)")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(commercial_signals)} senales preventivas.")
    lines_txt.append("")

    for i, lead in enumerate(commercial_signals, 1):
        problem = problem_short(lead)
        province = province_display(lead)
        vehicle = vehicle_display(lead)
        platform = platform_display(lead)
        whatsapp = contact_display(lead, "possible_whatsapp")
        phone = contact_display(lead, "possible_phone")
        post = lead.get("post_link", "No disponible")
        quote = quote_clean(lead, max_len=120)

        # Versión compacta (los comerciales van en una línea cada uno)
        contact_info = []
        if lead.get("possible_whatsapp"):
            contact_info.append(f"WA: {lead['possible_whatsapp']}")
        if lead.get("possible_phone"):
            contact_info.append(f"Tel: {lead['possible_phone']}")
        contact_str = " | ".join(contact_info) if contact_info else "Sin contacto público"

        lines_md.append(f"**Lead #{i}** — {problem}  ")
        lines_md.append(f"📍 {province} | 🚗 {vehicle} | 📱 {platform} | {contact_str}  ")
        lines_md.append(f"📝 _{quote}_  ")
        lines_md.append(f"🔗 {post}")
        lines_md.append("")

        lines_txt.append(f"  Lead #{i}: {problem}")
        lines_txt.append(f"    Provincia: {province} | Vehiculo: {vehicle} | Plataforma: {platform}")
        lines_txt.append(f"    Contacto: {contact_str}")
        lines_txt.append(f"    Publicacion: {post}")
        lines_txt.append("")

    # ===== SECCIÓN 3: CONTACTOS PÚBLICOS =====
    contacts = []
    for lead in real_leads + commercial_signals:
        wa = lead.get("possible_whatsapp", "")
        ph = lead.get("possible_phone", "")
        if wa or ph:
            contacts.append({
                "persona": person_display(lead),
                "whatsapp": wa or "—",
                "telefono": ph or "—",
                "perfil": lead.get("profile_link", "—"),
                "plataforma": platform_display(lead),
            })

    lines_md.append("## 📞 CONTACTOS PÚBLICOS ENCONTRADOS")
    lines_md.append("")
    lines_md.append(f"_{len(contacts)} personas con contacto publicado (solo si fue publicado por la propia persona en su post público)._")
    lines_md.append("")
    if contacts:
        lines_md.append("| Persona | WhatsApp | Teléfono | Plataforma | Perfil |")
        lines_md.append("|---------|----------|----------|------------|--------|")
        for c in contacts:
            perfil_short = c["perfil"][:40] + "…" if len(c["perfil"]) > 40 else c["perfil"]
            lines_md.append(f"| {c['persona']} | {c['whatsapp']} | {c['telefono']} | {c['plataforma']} | {perfil_short} |")
    else:
        lines_md.append("_No se encontraron contactos públicos en este lote._")
    lines_md.append("")

    lines_txt.append("-" * 70)
    lines_txt.append("  CONTACTOS PUBLICOS ENCONTRADOS")
    lines_txt.append("-" * 70)
    lines_txt.append(f"  {len(contacts)} personas con contacto publicado.")
    lines_txt.append("")
    if contacts:
        lines_txt.append(f"  {'Persona':<25} {'WhatsApp':<18} {'Teléfono':<18} {'Plataforma':<12}")
        lines_txt.append(f"  {'-'*25} {'-'*18} {'-'*18} {'-'*12}")
        for c in contacts:
            lines_txt.append(f"  {c['persona'][:25]:<25} {c['whatsapp'][:18]:<18} {c['telefono'][:18]:<18} {c['plataforma'][:12]:<12}")
    else:
        lines_txt.append("  No se encontraron contactos publicos.")
    lines_txt.append("")

    # ===== SECCIÓN 4: RESUMEN =====
    platform_counts = {}
    for lead in real_leads + commercial_signals:
        p = platform_display(lead)
        platform_counts[p] = platform_counts.get(p, 0) + 1

    reason_counts = {}
    for lead in real_leads:
        r = lead.get("lead_reason", "")
        reason_counts[r] = reason_counts.get(r, 0) + 1

    lines_md.append("## 📊 RESUMEN")
    lines_md.append("")
    lines_md.append(f"- **Leads calientes (dolor explícito):** {len(real_leads)}")
    lines_md.append(f"- **Leads comerciales (preventivos):** {len(commercial_signals)}")
    lines_md.append(f"- **Contactos públicos encontrados:** {len(contacts)}")
    lines_md.append("")
    lines_md.append("**Por plataforma:**")
    for p, n in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines_md.append(f"- {p}: {n}")
    lines_md.append("")
    lines_md.append("**Tipos de dolor (leads calientes):**")
    reason_labels = {
        "declara_multas": "Declaró multas/fotomultas",
        "declara_problema_transferencia": "Problema con transferencia",
        "declara_problema_libre_deuda": "Necesita libre deuda",
        "consulta_documentacion": "Consulta documentación",
    }
    for r, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
        label = reason_labels.get(r, r)
        lines_md.append(f"- {label}: {n}")
    lines_md.append("")
    lines_md.append("---")
    lines_md.append("")
    lines_md.append("_Este reporte fue generado automáticamente por el Radar de Oportunidades v4.1._")
    lines_md.append("_Todas las publicaciones son de fuentes públicas. No se accedió a contenido privado._")
    lines_md.append("_La revisión humana es obligatoria antes de cualquier contacto._")

    lines_txt.append("=" * 70)
    lines_txt.append("  RESUMEN")
    lines_txt.append("=" * 70)
    lines_txt.append(f"  Leads calientes (dolor explicito): {len(real_leads)}")
    lines_txt.append(f"  Leads comerciales (preventivos):  {len(commercial_signals)}")
    lines_txt.append(f"  Contactos publicos:               {len(contacts)}")
    lines_txt.append("")
    lines_txt.append("  Por plataforma:")
    for p, n in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines_txt.append(f"    {p}: {n}")
    lines_txt.append("")
    lines_txt.append("  Tipos de dolor (leads calientes):")
    for r, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
        label = reason_labels.get(r, r)
        lines_txt.append(f"    {label}: {n}")
    lines_txt.append("")
    lines_txt.append("=" * 70)
    lines_txt.append("  Este reporte fue generado automaticamente por el Radar de Oportunidades v4.1")
    lines_txt.append("  Todas las publicaciones son de fuentes publicas.")
    lines_txt.append("  La revision humana es obligatoria antes de cualquier contacto.")
    lines_txt.append("=" * 70)

    # Guardar archivos
    md_content = "\n".join(lines_md)
    txt_content = "\n".join(lines_txt)

    OUTPUT_PATH.write_text(md_content, encoding="utf-8")
    OUTPUT_TXT_PATH.write_text(txt_content, encoding="utf-8")

    print(f"✓ Reporte Markdown: {OUTPUT_PATH}", file=sys.stderr)
    print(f"✓ Reporte texto plano: {OUTPUT_TXT_PATH}", file=sys.stderr)
    print(f"✓ Leads calientes: {len(real_leads)}", file=sys.stderr)
    print(f"✓ Leads comerciales: {len(commercial_signals)}", file=sys.stderr)
    print(f"✓ Contactos públicos: {len(contacts)}", file=sys.stderr)

    # También imprimir el contenido a stdout para que el usuario lo vea
    print(md_content)


if __name__ == "__main__":
    generate_report()
```


=== FILE: llm_extractor.py (390 líneas) ===

```"""
llm_extractor.py — Extractor LLM para pipeline v2.0 (SPEC-ONLY).

Regla del spec v2.0: `no_llm_side_effects: true`
→ El extractor LLM es una función pura: input = signal, output = {entities, normalized_fields}
→ No escribe a ningún sistema externo (no tool calls, no function calling que muta estado)
→ Sólo hace chat completion con schema JSON estricto

Contract:
    input: RADAR_LLM_API_KEY (env var)
           RADAR_LLM_BASE_URL (optional, default: GLM endpoint)
           RADAR_LLM_MODEL    (optional, default: glm-4-flash)
    behavior: si API key falta → raise MissingLLMApiKeyError
              ("Missing LLM API key")

Stub behavior en este entorno:
    - El método extract() está implementado con urllib + JSON schema
    - Pero NO se llama en este entorno (no hay API key)
    - Si se llama sin API key, falla con error explícito
    - Si se llama con API key en un entorno real, hace POST al endpoint
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from models import Signal, Case, now_iso, short_id


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingLLMApiKeyError(RuntimeError):
    """Raised when RADAR_LLM_API_KEY is empty."""
    pass


class LLMExtractionError(RuntimeError):
    """Raised when the LLM call fails or returns invalid JSON."""
    pass


# ---------------------------------------------------------------------------
# Schema de salida esperado del LLM
# ---------------------------------------------------------------------------
LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "object",
            "properties": {
                "name_or_alias": {"type": "string"},
                "profile_url": {"type": "string"},
                "vehicle_type": {"type": "string"},
                "patent": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "locality": {"type": "string"},
                "problem_type": {"type": "string"},
                "year": {"type": ["integer", "null"]},
                "amount": {"type": ["number", "null"]},
            },
            "required": ["name_or_alias", "profile_url", "vehicle_type",
                         "patent", "jurisdiction", "locality", "problem_type"],
        },
        "normalized_fields": {
            "type": "object",
            "properties": {
                "jurisdiction_canonical": {"type": "string"},
                "vehicle_type_canonical": {"type": "string"},
                "problem_type_canonical": {"type": "string"},
                "amount_normalized": {"type": ["number", "null"]},
                "year_normalized": {"type": ["integer", "null"]},
            },
        },
    },
    "required": ["entities", "normalized_fields"],
}


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Sos un extractor de entidades para el sistema Radar de Oportunidades.
Tu única tarea es extraer entidades estructuradas de un texto de señal pública
sobre fotomultas, libre deuda, transferencia o regularización vehicular en Argentina.

NO escribas código, NO hagas comentarios, NO agregues campos extra.
Devolvé EXACTAMENTE un JSON con este schema:

{
  "entities": {
    "name_or_alias": "string (alias público del autor, vacío si no se infiere)",
    "profile_url": "string (URL del perfil público, vacío si no aplica)",
    "vehicle_type": "string (auto|moto|camioneta|camion|utilitario, vacío si no se menciona)",
    "patent": "string (patente argentina normalizada sin espacios, vacío si no se menciona)",
    "jurisdiction": "string (CABA|PBA|CORDOBA|SANTA_FE|MENDOZA|TUCUMAN|... vacío si no se infiere)",
    "locality": "string (localidad argentina, vacío si no se infiere)",
    "problem_type": "string (fotomulta|multa|libre_deuda|transferencia|regularizacion|patente|vtv, vacío si no se infiere)",
    "year": integer o null (año del vehículo mencionado, null si no se menciona),
    "amount": number o null (monto en pesos argentinos, null si no se menciona)
  },
  "normalized_fields": {
    "jurisdiction_canonical": "string (jurisdicción en mayúsculas SIN espacios)",
    "vehicle_type_canonical": "string (vehículo en minúsculas singular)",
    "problem_type_canonical": "string (problema en snake_case)",
    "amount_normalized": number o null,
    "year_normalized": integer o null
  }
}

Reglas de compliance:
- NO extraigas DNI, CUIT, email, teléfono, dirección del autor
- Si el texto contiene PII explícita, dejá los campos de entidad vacíos y respondé con un JSON vacío
- Sólo extraé lo que esté explícito en el texto
- No inventes información
"""


USER_PROMPT_TEMPLATE = """Extraé entidades del siguiente texto de señal pública:

---
Texto: {signal_text}
Source ID: {source_id}
Source URL: {source_url}
Author alias: {author_alias}
---

Devolvé sólo el JSON, sin markdown ni texto adicional."""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class LLMExtractor:
    """
    Extractor LLM para pipeline v2.0.

    Pure function: input = Signal, output = {entities, normalized_fields}
    No side effects: no tool calls, no API writes besides chat completion.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
    ):
        key = api_key or os.environ.get("RADAR_LLM_API_KEY", "")

        if not key:
            raise MissingLLMApiKeyError(
                "Missing LLM API key (env var RADAR_LLM_API_KEY is empty)"
            )

        self.api_key = key
        self.base_url = base_url or os.environ.get(
            "RADAR_LLM_BASE_URL",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )
        self.model = model or os.environ.get("RADAR_LLM_MODEL", "glm-4-flash")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Construcción del prompt
    # ------------------------------------------------------------------
    def _build_user_prompt(self, signal: Signal) -> str:
        return USER_PROMPT_TEMPLATE.format(
            signal_text=signal.raw_text,
            source_id=signal.source_id,
            source_url=signal.source_url,
            author_alias=signal.author_alias,
        )

    # ------------------------------------------------------------------
    # Llamada al LLM (real, pero no se ejecuta en este entorno sin API key)
    # ------------------------------------------------------------------
    def _call_llm(self, user_prompt: str) -> str:
        """Hace POST al endpoint de chat completion. Devuelve el content string."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,  # determinista
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "radar-oportunidades/2.0 (llm_extractor.py)",
        }

        req = urllib.request.Request(
            self.base_url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                response = json.loads(body)
                # Estructura típica OpenAI-compatible:
                # {"choices": [{"message": {"content": "..."}}]}
                content = response["choices"][0]["message"]["content"]
                return content
        except urllib.error.HTTPError as e:
            raise LLMExtractionError(
                f"LLM HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
            ) from e
        except urllib.error.URLError as e:
            raise LLMExtractionError(f"LLM URL error: {e.reason}") from e
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMExtractionError(f"LLM response parse error: {e}") from e

    # ------------------------------------------------------------------
    # Extract principal
    # ------------------------------------------------------------------
    def extract(self, signal: Signal) -> Dict[str, Any]:
        """
        Extract entities + normalized fields from a signal.

        Pure function: no side effects.
        Returns: {"entities": {...}, "normalized_fields": {...}}
        """
        user_prompt = self._build_user_prompt(signal)
        content = self._call_llm(user_prompt)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMExtractionError(
                f"LLM returned invalid JSON: {content[:200]}"
            ) from e

        # Validación mínima del schema
        if "entities" not in parsed or "normalized_fields" not in parsed:
            raise LLMExtractionError(
                f"LLM response missing required keys: {list(parsed.keys())}"
            )

        return parsed

    # ------------------------------------------------------------------
    # Convenience: signal → case_partial
    # ------------------------------------------------------------------
    def extract_to_case(self, signal: Signal) -> Case:
        """
        Extract entities y devuelve un Case parcial (sin scoring ni dedup).

        Mapea el output del LLM a los campos del modelo Case.
        """
        result = self.extract(signal)
        ents = result.get("entities", {})
        norm = result.get("normalized_fields", {})

        # Si el LLM detectó PII y devolvió entidades vacías, no crear caso
        if not ents.get("problem_type") and not ents.get("patent") and not ents.get("jurisdiction"):
            raise LLMExtractionError(
                "LLM returned empty entities (possible PII detected or no signal)"
            )

        case = Case(
            case_id=short_id("case", f"{signal.signal_id}|{signal.detected_at}"),
            signal_id=signal.signal_id,
            source_id=signal.source_id,
            source_url=signal.source_url,
            profile_url=ents.get("profile_url", signal.profile_url),
            timestamp=signal.raw_metadata.get("published_at", signal.detected_at),
            name_or_alias=ents.get("name_or_alias", signal.author_alias),
            vehicle_type=norm.get("vehicle_type_canonical") or ents.get("vehicle_type", ""),
            patent=ents.get("patent", ""),
            jurisdiction=norm.get("jurisdiction_canonical") or ents.get("jurisdiction", ""),
            locality=ents.get("locality", ""),
            problem_type=norm.get("problem_type_canonical") or ents.get("problem_type", ""),
            year=norm.get("year_normalized") or ents.get("year"),
            amount=norm.get("amount_normalized") or ents.get("amount"),
            evidence_text=signal.raw_text,
            normalized_text_hash=_text_hash(signal.raw_text),
        )
        return case


def _text_hash(text: str) -> str:
    """Reutilizamos la normalización del extractor v1 para compatibilidad."""
    import hashlib
    import re
    import unicodedata
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"@\w+", " ", t)
    t = re.sub(r"#\w+", " ", t)
    t = t.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica contrato de error, NO llama al LLM
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST llm_extractor.py (SPEC-ONLY, no llama al LLM)")
    print("=" * 70)

    # 1. Sin env var → Missing LLM API key
    saved = os.environ.pop("RADAR_LLM_API_KEY", None)
    try:
        try:
            extractor = LLMExtractor()
            print(f"  ✗ FAIL: debería haber lanzado MissingLLMApiKeyError")
            sys.exit(1)
        except MissingLLMApiKeyError as e:
            assert "Missing LLM API key" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin API key → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_LLM_API_KEY"] = saved

    # 2. Con API key dummy → constructor OK (no hace HTTP hasta extract())
    os.environ["RADAR_LLM_API_KEY"] = "dummy-key-for-construction-test"
    try:
        extractor = LLMExtractor()
        assert extractor.api_key == "dummy-key-for-construction-test"
        assert extractor.model == "glm-4-flash"
        assert "bigmodel.cn" in extractor.base_url
        print(f"  ✓ API key dummy → constructor OK (sin HTTP)")
        print(f"    model = {extractor.model}")
        print(f"    base_url = {extractor.base_url}")

        # 3. Prompt building
        from mock_sources import generate_mock_signals
        sig = generate_mock_signals()[0]
        prompt = extractor._build_user_prompt(sig)
        assert sig.raw_text in prompt
        assert sig.source_id in prompt
        assert sig.source_url in prompt
        print(f"  ✓ _build_user_prompt incluye signal_text, source_id, source_url")
        print(f"    prompt length = {len(prompt)} chars")

        # 4. SYSTEM_PROMPT incluye las reglas de compliance
        assert "DNI" in SYSTEM_PROMPT
        assert "CUIT" in SYSTEM_PROMPT
        assert "no inventes" in SYSTEM_PROMPT.lower()
        print(f"  ✓ SYSTEM_PROMPT incluye reglas anti-PII y no-alucinación")

        # 5. LLM_OUTPUT_SCHEMA está bien formado
        assert "entities" in LLM_OUTPUT_SCHEMA["properties"]
        assert "normalized_fields" in LLM_OUTPUT_SCHEMA["properties"]
        required_ents = LLM_OUTPUT_SCHEMA["properties"]["entities"]["required"]
        assert "problem_type" in required_ents
        assert "patent" in required_ents
        print(f"  ✓ LLM_OUTPUT_SCHEMA tiene {len(required_ents)} entidades requeridas")
    finally:
        os.environ.pop("RADAR_LLM_API_KEY", None)
        if saved is not None:
            os.environ["RADAR_LLM_API_KEY"] = saved

    # 6. _text_hash determinista
    h1 = _text_hash("Hola MUNDO!! Test https://example.com @user #tag")
    h2 = _text_hash("Hola MUNDO!! Test https://example.com @user #tag")
    h3 = _text_hash("Hola MUNDO!! Test diferente")
    assert h1 == h2, "Same text should produce same hash"
    assert h1 != h3, "Different text should produce different hash"
    print(f"  ✓ _text_hash determinista y sensible a cambios")

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se llamó al LLM.")
    print("=" * 70)
    print("""
  Reglas del spec v2.0 cumplidas:
    ✓ no_llm_side_effects: extractor es pure function (sólo chat completion)
    ✓ Sin tool calls ni function calling que escriba a sistemas externos
    ✓ SYSTEM_PROMPT prohíbe extraer PII explícita
    ✓ Sin API key → error explícito "Missing LLM API key"

  Para usar en runtime real (máquina del operador):
    export RADAR_LLM_API_KEY=<tu-api-key>
    # opcional: export RADAR_LLM_BASE_URL=https://...
    # opcional: export RADAR_LLM_MODEL=glm-4-flash
    python main.py --event-pipeline
""")
```


=== FILE: main.py (260 líneas) ===

```"""
main.py — Entry point del Radar de Oportunidades.

v1.0 (default): pipeline imperativo con extractor regex
v2.0 (--event-pipeline): event-driven con LLM extractor + sinks

Uso:
    python main.py                                # pipeline v1 (regex, mock)
    python main.py --event-pipeline               # pipeline v2 (LLM, event-driven)
    python main.py --review                       # CLI de revisión
    python main.py --review --demo                # demo automática
    python main.py --sheet-write                  # subir vía gspread (v1 output)
    python main.py --sheet-push-webhook           # subir vía webhook (v1 output)
    python main.py --help

Requisitos:
    Python 3.10+
    Sólo stdlib para Fase 1 (gspread opcional para --sheet-write)
    LLM API key (RADAR_LLM_API_KEY) obligatoria para --event-pipeline
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from pipeline import RadarPipeline
from review_cli import ReviewCLI
from storage import load_cases_jsonl, AuditTrail
from sheets_uploader import GoogleSheetsUploader, MissingCredentialsError
from webhook_uploader import WebhookUploader, MissingWebhookURLError
from llm_extractor import LLMExtractor, MissingLLMApiKeyError
from event_pipeline import EventPipeline
import config


def cmd_event_pipeline() -> int:
    """Ejecuta el pipeline event-driven v2.0 (requiere RADAR_LLM_API_KEY)."""
    audit = AuditTrail()
    pipeline = EventPipeline(audit=audit, use_real_sources=False)
    try:
        result = pipeline.run()
    except MissingLLMApiKeyError as e:
        print(f"✗ {e}", file=sys.stderr)
        print(
            "  Setear env var: export RADAR_LLM_API_KEY=<tu-api-key>",
            file=sys.stderr,
        )
        return 2
    pipeline.print_summary(result)
    return 0


def cmd_sheet_write(dry_run: bool) -> int:
    """
    Sube los casos canónicos de cases.jsonl a Google Sheets.

    Comportamiento:
        - Si dry_run=True: imprime las filas serializadas y NO toca Google.
        - Si dry_run=False: requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE apuntando
          a un archivo existente. Si falta, lanza MissingCredentialsError con
          mensaje "Missing credentials file ...".
        - Sin modo mock ni dry-run implícito.
    """
    cases_data = load_cases_jsonl()
    if not cases_data:
        print("No hay casos en cases.jsonl. Ejecutá `python main.py` primero.")
        return 1

    # Filtrar sólo canónicos
    from models import Case
    cases = [Case(**c) for c in cases_data if c.get("is_canonical")]
    print(f"Casos canónicos a subir: {len(cases)}")

    if dry_run:
        print("\n--- DRY-RUN: filas que se subirían (NO se toca Google) ---\n")
        for c in cases:
            row = c.to_sheet_row()
            print(json.dumps(row, ensure_ascii=False, indent=2))
            print("---")
        print(f"\nTotal: {len(cases)} filas. Para subida real, correr sin --dry-run.")
        return 0

    # Modo real: el constructor falla si faltan credenciales
    audit = AuditTrail()
    try:
        uploader = GoogleSheetsUploader(audit=audit)
    except MissingCredentialsError as e:
        print(f"✗ {e}", file=sys.stderr)
        print(
            "  Setear env var: export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json",
            file=sys.stderr,
        )
        return 2

    print(f"  Credenciales: {uploader.credentials_path}")
    print(f"  Spreadsheet:  {uploader.spreadsheet_id}")
    print(f"  Worksheet:    {uploader.worksheet_name}")
    print()

    summary = uploader.append_rows(cases)
    print("\n" + "=" * 70)
    print("  RESULTADO DE SUBIDA (gspread)")
    print("=" * 70)
    print(f"  Total casos:   {summary['total']}")
    print(f"  Appended:      {summary['appended']}")
    print(f"  Updated:       {summary['updated']}")
    print(f"  Skipped:       {summary['skipped']}")
    print(f"  Errors:        {len(summary['errors'])}")
    if summary["errors"]:
        print("\n  ERRORES:")
        for err in summary["errors"]:
            print(f"    - {err['case_id']}: {err['error']}")
    print(f"\n  Sheet URL:     https://docs.google.com/spreadsheets/d/{uploader.spreadsheet_id}/edit")
    print("=" * 70)
    return 0 if not summary["errors"] else 3


def cmd_sheet_push_webhook(dry_run: bool) -> int:
    """
    Sube los casos canónicos a Google Sheets vía Apps Script Web App (HTTP POST).

    Comportamiento:
        - Si dry_run=True: imprime el payload JSON y NO hace HTTP.
        - Si dry_run=False: requiere RADAR_WEBHOOK_URL seteada. Si falta,
          lanza MissingWebhookURLError con mensaje "Missing webhook URL".
        - Sin modo mock ni dry-run implícito.
        - Sólo stdlib (urllib), no requiere gspread ni service account.
    """
    cases_data = load_cases_jsonl()
    if not cases_data:
        print("No hay casos en cases.jsonl. Ejecutá `python main.py` primero.")
        return 1

    from models import Case
    cases = [Case(**c) for c in cases_data if c.get("is_canonical")]
    print(f"Casos canónicos a pushear: {len(cases)}")

    if dry_run:
        print("\n--- DRY-RUN: payload que se enviaría (NO se hace HTTP) ---\n")
        # Usar static method para no requerir URL (dry-run puro)
        from webhook_uploader import WebhookUploader
        payload = {"cases": [WebhookUploader.case_to_payload(c) for c in cases]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\nTotal: {len(cases)} casos. Para push real, correr sin --dry-run.")
        print(f"Requiere: export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec")
        return 0

    audit = AuditTrail()
    try:
        uploader = WebhookUploader(audit=audit)
    except MissingWebhookURLError as e:
        print(f"✗ {e}", file=sys.stderr)
        print(
            "  Setear env var: export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec",
            file=sys.stderr,
        )
        return 2

    print(f"  Webhook URL:   {uploader.webhook_url}")
    print(f"  Timeout:       {uploader.timeout}s")
    print()

    summary = uploader.push(cases)
    print("\n" + "=" * 70)
    print("  RESULTADO DE PUSH (webhook)")
    print("=" * 70)
    print(f"  Total casos:   {summary['total']}")
    print(f"  Pushed:        {summary['pushed']}")
    print(f"  Response:      {summary['response']!r}")
    print(f"  Errors:        {len(summary['errors'])}")
    if summary["errors"]:
        print("\n  ERRORES:")
        for err in summary["errors"]:
            print(f"    - {err.get('error', err)}")
    print(f"\n  Sheet URL:     https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/edit")
    print("=" * 70)
    return 0 if not summary["errors"] else 3


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="radar",
        description="Radar de Oportunidades — Prototipo Fase 1",
    )
    parser.add_argument(
        "--review", action="store_true",
        help="Lanza CLI de revisión humana en vez del pipeline",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="En modo --review, ejecuta demo automática (no interactivo)",
    )
    parser.add_argument(
        "--event-pipeline", action="store_true",
        help="Usa pipeline v2.0 event-driven con LLM extractor (requiere RADAR_LLM_API_KEY)",
    )
    parser.add_argument(
        "--sheet-write", action="store_true",
        help="Sube casos canónicos a Google Sheet vía gspread (requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE)",
    )
    parser.add_argument(
        "--sheet-push-webhook", action="store_true",
        help="Sube casos vía POST a Apps Script Web App (requiere RADAR_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Con --sheet-write o --sheet-push-webhook: no toca Google, sólo serializa",
    )
    parser.add_argument(
        "--no-mock", action="store_true",
        help="Usa fuentes reales en vez de mock (Fase 2/3, requiere conectores implementados)",
    )
    args = parser.parse_args()

    if args.review:
        cli = ReviewCLI()
        if args.demo:
            import review_cli
            sys.argv = ["review_cli.py", "--demo"]
            review_cli.__name__ = "__main__"
            exec(open(review_cli.__file__).read(), review_cli.__dict__)
        else:
            cli.run()
        return 0

    if args.event_pipeline:
        return cmd_event_pipeline()

    if args.sheet_write:
        return cmd_sheet_write(dry_run=args.dry_run)

    if args.sheet_push_webhook:
        return cmd_sheet_push_webhook(dry_run=args.dry_run)

    # Pipeline end-to-end (sin tocar Google)
    use_real = args.no_mock
    pipeline = RadarPipeline(use_real_sources=use_real, sheet_dry_run=True)
    result = pipeline.run()
    pipeline.print_summary(result)

    print(f"\n  Outputs generados en: /home/z/my-project/download/sample_data/")
    print(f"    - signals_mock.jsonl     ({result.signals_collected} señales)")
    print(f"    - cases.jsonl            ({len(result.cases)} casos)")
    print(f"    - review_queue.csv       ({result.cases_canonical} pendientes)")
    print(f"    - audit_trail.log        ({result.audit_entries} entradas)")
    print(f"    - evidence/              ({result.cases_canonical} carpetas)")
    print(f"\n  Para revisar casos: python main.py --review")
    print(f"  Para demo automática: python main.py --review --demo")
    print(f"  Para subir a Sheet (gspread):    python main.py --sheet-write")
    print(f"    (requiere RADAR_GOOGLE_SERVICE_ACCOUNT_FILE)")
    print(f"  Para subir a Sheet (webhook):    python main.py --sheet-push-webhook")
    print(f"    (requiere RADAR_WEBHOOK_URL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


=== FILE: mock_sources.py (532 líneas) ===

```"""
mock_sources.py — Generador de señales sintéticas + stubs documentados para Fase 2/3.

Filosofía:
- Fase 1 (este archivo): genera señales mock realistas en español AR para validar
  extracción, scoring, dedup, review queue y audit trail SIN tocar plataformas reales.
- Fases 2/3: los conectores reales (Facebook, X, marketplace, foros, news) se documentan
  como stubs con la firma exacta que deberían tener, pero no se ejecutan. Ver
  `RealSourceStub` al final del archivo.

Compliance: todas las señales mock usan datos sintéticos. Ningún dato real de personas
reales es recolectado o generado.
"""
from __future__ import annotations
import hashlib
import json
import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Callable
from dataclasses import asdict

from models import Signal, now_iso, AR_TZ
import config

random.seed(42)  # reproducibilidad para Fase 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(days_ago: int, hour: int = 10) -> str:
    dt = datetime.now(AR_TZ) - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)
    return dt.isoformat()


def _url(source_id: str, slug: str) -> str:
    h = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:10]
    return f"https://{source_id.replace('_', '.')}/post/{h}"


# ---------------------------------------------------------------------------
# Plantillas de señales mock realistas (español AR)
# ---------------------------------------------------------------------------
# Cada plantilla produce 1-N señales. Las señales se mezclan y se randomizan.
# Las patentes usan formato AR. Las jurisdicciones son las del spec.

TEMPLATES: List[Dict[str, Any]] = [
    # --- Facebook public groups -------------------------------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Mariela G.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=1000{rand}",
        "text": "Hola gente, tengo una fotomulta de CABA del mes pasado, no sé cómo hacer el reclamo. Me llegó a mi domicilio de Caballito. Alguien sabe si conviene ir a defenderme o pagar? Son $18.500.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Caballito",
        "problem_hint": "fotomulta",
        "amount_hint": 18500,
        "days_ago": 2,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "El Tano Automotores",
        "profile_url_tpl": "https://facebook.com/eltanoautomotores",
        "text": "Vendo Ford Fiesta Kinetic 2015, tengo el libre deuda al día, listo para transferir. Patente ABC 123. Estoy en Lanús. Mandar MP.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Lanús",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 1,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Caro",
        "profile_url_tpl": "https://facebook.com/profile.php?id=2000{rand}",
        "text": "Consulto por una multa de ruta en la 2, me dicen que son de APSV pero nunca me llegó la notificación. Vivo en Rosario. Alguien pasó lo mismo?",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rosario",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 4,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Jorge M.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=3000{rand}",
        "text": "Gente, no puedo renovar el registro porque tengo 3 multas impagas de Córdoba capital. Alguien sabe si hay plan de pago? Son como $45.000 en total.",
        "jurisdiction_hint": "CORDOBA",
        "locality_hint": "Córdoba",
        "problem_hint": "regularizacion",
        "amount_hint": 45000,
        "days_ago": 3,
    },
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Anónimo (no comparte perfil)",
        "profile_url_tpl": "",
        "text": "Multas de fotomulta en PBA, me llegaron 5 de una sola vez, todas de la misma cámara en Panamericana. Alguien sabe si se puede reclamar? Vivo en San Martín.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "San Martín",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 5,
    },

    # --- Marketplace -----------------------------------------------------------
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Lucía Ventas",
        "profile_url_tpl": "https://marketplace.com/user/lucia_ventas",
        "text": "Vendo auto Peugeot 208 2019. Libre deuda y 08 firmado, listo para transferir. Sin deudas. $4.500.000. Zona Villa Crespo.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Villa Crespo",
        "problem_hint": "transferencia",
        "amount_hint": 4500000,
        "days_ago": 1,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Diego A.",
        "profile_url_tpl": "https://marketplace.com/user/diego_a",
        "text": "Vendo moto Honda CG 150 titán 2018. Patente AB 456 CD. Le debo 2 cuotas de patente de PBA, lo regularizo antes de transferir. Avisanos.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "patente",
        "amount_hint": None,
        "days_ago": 2,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "VendoYa Autoplanes",
        "profile_url_tpl": "https://marketplace.com/user/vendoya",
        "text": "Toyota Corolla 2020, transferir con libre deuda al día. Cliente necesita urgente, se muda al sur. Precio conversable.",
        "jurisdiction_hint": "",
        "locality_hint": "",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 1,
    },

    # --- X / Twitter -----------------------------------------------------------
    {
        "source_id": "x_search",
        "author_alias": "@usuario_cabildo",
        "profile_url_tpl": "https://x.com/usuario_cabildo",
        "text": "Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. @GCBAComunas cómo hago el reclamo?? #fotomultas #CABA",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Belgrano",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 1,
    },
    {
        "source_id": "x_search",
        "author_alias": "@radares_arg",
        "profile_url_tpl": "https://x.com/radares_arg",
        "text": "Listado de radares nuevos en Panamericana. Cuidado con las multas gente, ya caen varias. #APSV #multas",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 6,
    },
    {
        "source_id": "x_search",
        "author_alias": "@martinros",
        "profile_url_tpl": "https://x.com/martinros",
        "text": "Me llegó una multa de la ciudad de Rosario pero yo nunca estuve ahí. Alguien sabe cómo defenderse? #santafe",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rosario",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 3,
    },

    # --- Public forums --------------------------------------------------------
    {
        "source_id": "public_forums",
        "author_alias": "foro_user_8821",
        "profile_url_tpl": "https://foro-auto.com.ar/user/foro_user_8821",
        "text": "No puedo renovar el registro porque tengo 2 multas de Córdoba que no me llegaron nunca. Fui a hacer el trámite y me aparecen. Cómo las regularizo? Son del 2023.",
        "jurisdiction_hint": "CORDOBA",
        "locality_hint": "Córdoba",
        "problem_hint": "regularizacion",
        "amount_hint": None,
        "days_ago": 7,
    },
    {
        "source_id": "public_forums",
        "author_alias": "comunidad_motorista",
        "profile_url_tpl": "https://foro-motos.com/user/comunidad_motorista",
        "text": "Consulto por multa de ruta en RN8, la cámara me tomó a 110 km/h donde era 100. Vale la pena defenderla? Patente AB 789 EF. Vivo en Pilar.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Pilar",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 4,
    },
    {
        "source_id": "public_forums",
        "author_alias": "transferencias_dudas",
        "profile_url_tpl": "https://foro-auto.com.ar/user/transferencias_dudas",
        "text": "Para transferir un auto necesito libre deuda, pero el dueño anterior dejó multas impagas. Quién las paga? Es en CABA.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 2,
    },
    {
        "source_id": "public_forums",
        "author_alias": "anon_foro",
        "profile_url_tpl": "",
        "text": "Alguien sabe el costo del libre deuda en Mendoza? Tengo que transferir una camioneta y no sé los aranceles.",
        "jurisdiction_hint": "MENDOZA",
        "locality_hint": "Mendoza",
        "problem_hint": "libre_deuda",
        "amount_hint": None,
        "days_ago": 8,
    },

    # --- News + comments -----------------------------------------------------
    {
        "source_id": "news_and_comments",
        "author_alias": "infobae_comment_8821",
        "profile_url_tpl": "",
        "text": "Comentario en nota sobre radares: 'A mí me clavaron 3 en el mismo lugar sin cartel de aviso. Denuncia presentada en defensoría'.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 5,
    },
    {
        "source_id": "news_and_comments",
        "author_alias": "lanacion_comment_4455",
        "profile_url_tpl": "",
        "text": "Reclamo colectivo por fotomultas en Acceso Oeste. Vecinos de Moreno y Ituzaingó se organizan para presentación judicial.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "Moreno",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 9,
    },
    {
        "source_id": "news_and_comments",
        "author_alias": "cronista_comment_1199",
        "profile_url_tpl": "",
        "text": "Denuncia en defensoría del pueblo de CABA por cobro de multas sin notificación previa. Suma 12 reclamos.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "CABA",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 12,
    },

    # --- Duplicados intencionales (para probar dedup) -------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Mariela G.",
        "profile_url_tpl": "https://facebook.com/profile.php?id=1000{rand}",
        "text": "Hola gente, tengo una fotomulta de CABA del mes pasado, no sé cómo hacer el reclamo. Me llegó a mi domicilio de Caballito. Alguien sabe si conviene ir a defenderme o pagar? Son $18.500.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Caballito",
        "problem_hint": "fotomulta",
        "amount_hint": 18500,
        "days_ago": 0,  # mismo día: simulamos repost
        "_duplicate_of_text": True,
    },
    {
        "source_id": "x_search",
        "author_alias": "@usuario_cabildo",
        "profile_url_tpl": "https://x.com/usuario_cabildo",
        "text": "Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. @GCBAComunas cómo hago el reclamo?? #fotomultas #CABA",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Belgrano",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 0,
        "_duplicate_of_text": True,
    },

    # --- Caso crítico comercial (score esperado >=80) -------------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "Vendedor Rafaela",
        "profile_url_tpl": "https://facebook.com/profile.php?id=5000{rand}",
        "text": "URGENTE: vendo auto por traslado al exterior. Tengo libre deuda pendiente en Santa Fe, necesito regularizar y transferir antes del 15 del mes que viene. Auto en Rafaela, patente ABC 999. Escucho ofertas.",
        "jurisdiction_hint": "SANTA_FE",
        "locality_hint": "Rafaela",
        "problem_hint": "transferencia",
        "amount_hint": None,
        "days_ago": 0,
    },
    {
        "source_id": "marketplace_public_posts",
        "author_alias": "Familia Pérez",
        "profile_url_tpl": "https://marketplace.com/user/familia_perez",
        "text": "VENDO URGENTE Ford EcoSport 2018. Libre deuda vencido, hay 2 multas en CABA que necesito regularizar antes de transferir. Zona Flores. Atiendo consultas hoy.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "Flores",
        "problem_hint": "regularizacion",
        "amount_hint": None,
        "days_ago": 0,
    },

    # --- Señales que deben ser RECHAZADAS por privacy filter ------------------
    {
        "source_id": "facebook_public_groups",
        "author_alias": "usuario_test_pii",
        "profile_url_tpl": "",
        "text": "Hola, mi DNI es 30.123.456 y me llegó una multa. Pasen datos por privado por favor. Tel: +54 11 5555-1234.",
        "jurisdiction_hint": "CABA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 1,
        "_should_be_rejected": True,
    },
    {
        "source_id": "x_search",
        "author_alias": "@anon_pii",
        "profile_url_tpl": "",
        "text": "Contacto: juan.perez@example.com para asesoramiento sobre multas. CUIT 20-12345678-5.",
        "jurisdiction_hint": "PBA",
        "locality_hint": "",
        "problem_hint": "fotomulta",
        "amount_hint": None,
        "days_ago": 2,
        "_should_be_rejected": True,
    },
]


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------
def generate_mock_signals() -> List[Signal]:
    """Genera la lista de señales mock para Fase 1."""
    signals: List[Signal] = []
    for i, t in enumerate(TEMPLATES):
        rand_suffix = f"{random.randint(10000, 99999)}"
        profile_url = t["profile_url_tpl"].replace("{rand}", rand_suffix) if t["profile_url_tpl"] else ""
        text = t["text"]
        slug = f"{t['source_id']}|{text[:60]}|{i}"
        sig = Signal(
            source_id=t["source_id"],
            source_url=_url(t["source_id"], slug),
            raw_text=text,
            author_alias=t["author_alias"],
            profile_url=profile_url,
            detected_at=now_iso(),
            signal_keywords=[k for k in config.SOURCES if k["id"] == t["source_id"]][0]["signals"],
            raw_metadata={
                "published_at": _ts(t["days_ago"]),
                "jurisdiction_hint": t["jurisdiction_hint"],
                "locality_hint": t["locality_hint"],
                "problem_hint": t["problem_hint"],
                "amount_hint": t["amount_hint"],
                "_duplicate_of_text": t.get("_duplicate_of_text", False),
            },
        )
        signals.append(sig)
    random.shuffle(signals)
    return signals


# ---------------------------------------------------------------------------
# Stubs para conectores reales (Fases 2/3)
# ---------------------------------------------------------------------------
class RealSourceStub:
    """
    Stubs documentados de conectores reales para Fases 2 y 3.

    Cada método tiene la firma y comportamiento esperados, pero NO se ejecuta.
    El equipo de operación debe implementar la lógica real respetando:
    - Solo contenido público o accesible con consentimiento legítimo
    - Sin scraping de perfiles privados
    - Respeto a los Términos de Servicio de cada plataforma
    - Rate limiting y backoff exponencial
    - Logging completo al audit trail

    Para activar un conector en Fase 2/3:
    1. Implementar el método `_fetch_*` con la API oficial del plataforma
    2. Reemplazar la firma del método público (sin _ inicial)
    3. Agregar credenciales a config.py
    4. Documentar el alcance legal en el README
    """

    @staticmethod
    def fetch_facebook_public_groups(group_ids: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para Facebook Public Groups.

        ⚠️ No implementado en Fase 1. Consideraciones:
        - Facebook Graph API no expone búsqueda pública de grupos sin app review
        - Alternativa viable: usar CrowdTangle (descontinuado) o Meta Content Library
          (solo para investigadores acreditados)
        - Alternativa práctica Fase 2: miembro humano del equipo con acceso legítimo
          al grupo pega las señales relevantes en la Google Sheet
        - Alternativa Fase 3: integración con Meta Content Library API si se obtiene
          acceso investigador

        Args:
            group_ids: IDs de grupos públicos donde el negocio tiene acceso legítimo
            since_hours: ventana de tiempo hacia atrás

        Returns:
            Lista de Signal crudas, con source_id="facebook_public_groups"
        """
        raise NotImplementedError(
            "Conector Facebook real requiere acceso investigador a Meta Content Library "
            "o ingreso manual por miembro del equipo con acceso legítimo al grupo."
        )

    @staticmethod
    def fetch_x_search(query: str, since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para X (Twitter) Search.

        Viable vía X API v2 (tier Basic $100/mes o Pro $5000/mes).
        Endpoint: GET /2/tweets/search/recent
        Requiere Bearer Token en env var X_BEARER_TOKEN.

        Args:
            query: query de búsqueda con operadores de X (lang:es -is:retweet, etc.)
            since_hours: ventana de tiempo hacia atrás (máx 7 días en tier Basic)

        Returns:
            Lista de Signal con source_id="x_search"
        """
        raise NotImplementedError(
            "Conector X real requiere X_API_BEARER_TOKEN. "
            "Ver https://developer.x.com/en/docs/x-api"
        )

    @staticmethod
    def fetch_marketplace_public_posts(keywords: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para Marketplace.

        ⚠️ Facebook Marketplace no expone API pública de búsqueda.
        Alternativas viables:
        - Scraping con Playwright + sesión autenticada (violaría ToS de Meta)
        - Ingreso manual por operador del equipo
        - Monitoreo de grupos de Marketplace vía API de grupos (ver fetch_facebook_public_groups)

        Returns:
            Lista de Signal con source_id="marketplace_public_posts"
        """
        raise NotImplementedError(
            "Marketplace no tiene API pública. Usar ingreso manual en Fase 2."
        )

    @staticmethod
    def fetch_public_forums(forum_rss_urls: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para foros públicos vía RSS/Atom.

        ✓ Viable y recomendado. La mayoría de foros (phpBB, Discourse, etc.) exponen RSS.
        Implementar con feedparser + filtros por keywords.

        Args:
            forum_rss_urls: lista de URLs RSS de foros públicos
            since_hours: ventana de tiempo hacia atrás

        Returns:
            Lista de Signal con source_id="public_forums"
        """
        raise NotImplementedError(
            "Implementar con feedparser. RSS URLs a configurar en config.py FORUM_RSS_URLS."
        )

    @staticmethod
    def fetch_news_and_comments(news_rss_urls: List[str], since_hours: int = 24) -> List[Signal]:
        """
        Fase 2/3 — Conector real para noticias y comentarios vía RSS.

        ✓ Viable. Fuentes sugeridas:
        - Infobae, La Nación, Clarín: secciones policía/tránsito
        - Defensoría del Pueblo de CABA y PBA: RSS de comunicados
        - Agencias provinciales de seguridad vial

        Returns:
            Lista de Signal con source_id="news_and_comments"
        """
        raise NotImplementedError(
            "Implementar con feedparser + parser de comentarios si disponible."
        )


# ---------------------------------------------------------------------------
# Selector de fuente (mock en Fase 1, real en Fase 2/3)
# ---------------------------------------------------------------------------
def collect_signals(use_real: bool = False, **kwargs) -> List[Signal]:
    """
    Punto de entrada del collector.

    Fase 1 (use_real=False): devuelve señales mock.
    Fase 2/3 (use_real=True): intenta usar conectores reales (requiere credenciales).
    """
    if not use_real:
        return generate_mock_signals()

    # Fase 2/3 — llamada a conectores reales
    signals: List[Signal] = []
    stub = RealSourceStub()
    try:
        signals.extend(stub.fetch_x_search(query="fotomulta OR libre deuda OR transferencia", **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] X no disponible: {e}")
    try:
        signals.extend(stub.fetch_public_forums(forum_rss_urls=[], **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] Foros no disponible: {e}")
    try:
        signals.extend(stub.fetch_news_and_comments(news_rss_urls=[], **kwargs))
    except NotImplementedError as e:
        print(f"  [warn] News no disponible: {e}")
    return signals


if __name__ == "__main__":
    # Smoke test
    sigs = generate_mock_signals()
    print(f"Generadas {len(sigs)} señales mock")
    for s in sigs[:3]:
        print(f"  - {s.signal_id} [{s.source_id}] {s.raw_text[:80]}...")
```


=== FILE: models.py (193 líneas) ===

```"""
models.py — Dataclasses del Radar de Oportunidades.

Signal: señal cruda detectada en una fuente pública.
Case: caso normalizado, extraído, puntúa do y deduplicado.
AuditEntry: entrada append-only del audit trail.
ReviewAction: acción de revisión humana sobre un caso.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any


AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def now_iso() -> str:
    return datetime.now(AR_TZ).isoformat()


def short_id(prefix: str, seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{h}"


@dataclass
class Signal:
    """Señal cruda detectada en una fuente pública."""
    source_id: str             # ej: facebook_public_groups
    source_url: str            # URL pública del post/comentario
    raw_text: str              # texto original tal cual apareció
    author_alias: str          # alias/name público (no se recolecta si es privado)
    profile_url: str           # URL pública del perfil (vacío si no aplica)
    detected_at: str           # ISO timestamp de detección
    signal_keywords: List[str] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def signal_id(self) -> str:
        seed = f"{self.source_id}|{self.source_url}|{self.raw_text[:120]}"
        return short_id("sig", seed)


@dataclass
class Case:
    """Caso normalizado, extraído, puntúa do y deduplicado."""
    # Identidad
    case_id: str
    signal_id: str
    source_id: str
    source_url: str
    profile_url: str
    timestamp: str                  # ISO timestamp de la señal original

    # Entidades extraídas
    name_or_alias: str = ""
    vehicle_type: str = ""
    patent: str = ""
    jurisdiction: str = ""
    locality: str = ""
    problem_type: str = ""
    year: Optional[int] = None
    amount: Optional[float] = None
    evidence_text: str = ""

    # Scoring
    score: int = 0
    score_band: str = "low"          # critical/high/medium/low
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    score_version: str = ""          # corrección B: "v1.0_weighted_sum"

    # Dedup
    normalized_text_hash: str = ""
    duplicate_of: Optional[str] = None   # case_id del caso padre si es dup
    duplicates: List[str] = field(default_factory=list)
    is_canonical: bool = True

    # Review queue
    status: str = "needs_review"      # needs_review/approved/rejected/duplicate/needs_more_data
    review_action: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: str = ""

    # Evidence
    evidence_path: Optional[str] = None
    evidence_sha256: Optional[str] = None

    # Uploader v1.0 — WhatsApp + sheet schema
    whatsapp_number: str = ""           # vacío si no se puede inferir
    whatsapp_link: str = ""             # https://wa.me/<num>?text=...
    priority_level: str = ""            # = score_band (critical/high/medium/low)
    review_state: str = "needs_review"  # espejo de status para la sheet

    # Audit
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_sheet_row(self) -> Dict[str, Any]:
        """
        Fila lista para Google Sheet — schema EXACTO del uploader v1.0.

        Las columnas y su orden están definidas en config.SHEET_HEADERS.
        Nunca devolver campos que no estén en SHEET_HEADERS (la sheet es append-only).
        """
        # WhatsApp link (se construye aquí si hay número, para no duplicar lógica)
        from urllib.parse import quote
        import config as _cfg
        if self.whatsapp_number and not self.whatsapp_link:
            msg = quote(_cfg.WHATSAPP_DEFAULT_MESSAGE)
            self.whatsapp_link = f"https://wa.me/{self.whatsapp_number}?text={msg}"

        # priority_level = score_band (espejo del spec del uploader)
        self.priority_level = self.score_band
        # review_state = status (espejo del spec del uploader)
        self.review_state = self.status

        row = {
            "case_id": self.case_id,
            "timestamp": self.timestamp,
            "name_or_alias": self.name_or_alias,
            "profile_url": self.profile_url,
            "patent": self.patent,
            "vehicle_type": self.vehicle_type,
            "jurisdiction": self.jurisdiction,
            "locality": self.locality,
            "problem_type": self.problem_type,
            "year": self.year if self.year is not None else "",
            "amount": self.amount if self.amount is not None else "",
            "score": self.score,
            "priority_level": self.priority_level,
            "source_name": self.source_id,
            "source_url": self.source_url,
            "evidence_text": self.evidence_text,
            "whatsapp_number": self.whatsapp_number,
            "whatsapp_link": self.whatsapp_link,
            "status": self.status,
            "review_state": self.review_state,
        }
        # Garantizar que el orden de las keys = SHEET_HEADERS
        return {k: row.get(k, "") for k in _cfg.SHEET_HEADERS}


@dataclass
class AuditEntry:
    """Entrada append-only del audit trail."""
    timestamp: str
    actor: str               # system / reviewer:<nombre>
    action: str              # collect / extract / normalize / score / dedup / store_evidence / review / export / alert
    entity_type: str         # signal / case / review / alert
    entity_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    hash_prev: str = ""      # hash de la entrada anterior (cadena inmutable)
    hash_self: str = ""      # hash de esta entrada

    def to_log_line(self) -> str:
        payload = {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "hash_prev": self.hash_prev,
        }
        # hash_self = sha256 del payload serializado
        self.hash_self = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        payload["hash_self"] = self.hash_self
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass
class ReviewAction:
    """Acción de revisión humana sobre un caso."""
    case_id: str
    action: str              # approve / reject / duplicate / needs_more_data
    reviewer: str
    notes: str = ""
    timestamp: str = field(default_factory=now_iso)
```


=== FILE: pipeline.py (237 líneas) ===

```"""
pipeline.py — Orquestador end-to-end del Radar de Oportunidades (Fase 1).

Flujo:
  collect → privacy_filter → extract → normalize → score → dedup
          → store_evidence → queue → sheet_sync → audit_trail (en cada paso)

Cada paso escribe en el audit trail. El pipeline es idempotente: si se ejecuta
de nuevo sobre las mismas señales, produce los mismos casos (excepto timestamps).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from models import Case, Signal, AuditEntry, now_iso
import config
from mock_sources import collect_signals
from extractor import signal_to_case, privacy_filter
from scorer import update_case_score
from dedup import merge_duplicates
from storage import (
    AuditTrail, EvidenceStore, ReviewQueue, SheetSync,
    save_cases_jsonl, save_signals_jsonl,
)


@dataclass
class PipelineResult:
    signals_collected: int = 0
    signals_rejected_privacy: int = 0
    signals_no_entity: int = 0
    cases_extracted: int = 0
    cases_canonical: int = 0
    duplicates_found: int = 0
    critical_cases: int = 0
    high_cases: int = 0
    medium_cases: int = 0
    low_cases: int = 0
    sheet_mode: str = ""
    sheet_rows: int = 0
    audit_entries: int = 0
    audit_chain_ok: bool = True
    duration_seconds: float = 0.0
    cases: List[Case] = field(default_factory=list)


class RadarPipeline:
    """Pipeline completo del Radar de Oportunidades."""

    def __init__(
        self,
        use_real_sources: bool = False,
        sheet_dry_run: bool = True,
        audit: Optional[AuditTrail] = None,
        evidence: Optional[EvidenceStore] = None,
        queue: Optional[ReviewQueue] = None,
        sheet: Optional[SheetSync] = None,
    ):
        self.use_real_sources = use_real_sources
        self.sheet_dry_run = sheet_dry_run
        self.audit = audit or AuditTrail()
        self.evidence = evidence or EvidenceStore()
        self.queue = queue or ReviewQueue()
        self.sheet = sheet or SheetSync()

    def run(self) -> PipelineResult:
        import time
        t0 = time.time()
        result = PipelineResult()

        # 1. Collect
        self.audit.append(
            actor="system", action="pipeline_start",
            entity_type="batch", entity_id="run",
            details={"use_real_sources": self.use_real_sources, "sheet_dry_run": self.sheet_dry_run},
        )
        signals = collect_signals(use_real=self.use_real_sources)
        result.signals_collected = len(signals)
        self.audit.append(
            actor="system", action="collect",
            entity_type="batch", entity_id="signals",
            details={"count": len(signals)},
        )
        save_signals_jsonl(signals)

        # 2-3. Extract + Privacy filter
        cases: List[Case] = []
        for sig in signals:
            case, status = signal_to_case(sig)
            if case is None:
                if status.startswith("rejected_privacy"):
                    result.signals_rejected_privacy += 1
                else:
                    result.signals_no_entity += 1
                self.audit.append(
                    actor="system", action="reject",
                    entity_type="signal", entity_id=sig.signal_id,
                    details={"reason": status, "source_id": sig.source_id},
                )
                continue
            # Log extract
            self.audit.append(
                actor="system", action="extract",
                entity_type="signal", entity_id=sig.signal_id,
                details={"case_id": case.case_id, "problem_type": case.problem_type,
                         "jurisdiction": case.jurisdiction, "patent": case.patent},
            )
            cases.append(case)

        result.cases_extracted = len(cases)

        # 4. Score
        for case in cases:
            update_case_score(case)
            self.audit.append(
                actor="system", action="score",
                entity_type="case", entity_id=case.case_id,
                details={"score": case.score, "band": case.score_band,
                         "breakdown": case.score_breakdown},
            )

        # 5. Dedup
        cases, ndup = merge_duplicates(cases)
        result.duplicates_found = ndup
        self.audit.append(
            actor="system", action="dedup",
            entity_type="batch", entity_id="all",
            details={"duplicates_found": ndup,
                     "canonical_count": sum(1 for c in cases if c.is_canonical)},
        )

        # 6. Store evidence (sólo canónicos)
        for case in cases:
            if case.is_canonical:
                path, sha = self.evidence.store(case)
                case.evidence_path = path
                case.evidence_sha256 = sha
                self.audit.append(
                    actor="system", action="store_evidence",
                    entity_type="case", entity_id=case.case_id,
                    details={"sha256": sha, "path": path},
                )

        # 7. Review queue
        canonical = [c for c in cases if c.is_canonical]
        self.queue.initialize(canonical)
        self.audit.append(
            actor="system", action="queue_init",
            entity_type="batch", entity_id="all",
            details={"total_canonical": len(canonical)},
        )

        # 8. Sheet sync
        sync_result = self.sheet.sync(canonical, dry_run=self.sheet_dry_run, audit=self.audit)
        result.sheet_mode = sync_result["mode"]
        result.sheet_rows = sync_result["rows_queued"]

        # 9. Stats por banda
        for c in canonical:
            if c.score_band == "critical":
                result.critical_cases += 1
            elif c.score_band == "high":
                result.high_cases += 1
            elif c.score_band == "medium":
                result.medium_cases += 1
            else:
                result.low_cases += 1

        result.cases_canonical = len(canonical)
        result.cases = cases
        result.audit_entries = len(self.audit.read_all())
        result.audit_chain_ok = self.audit.verify_chain()
        result.duration_seconds = round(time.time() - t0, 2)

        # Persistir casos
        save_cases_jsonl(cases)

        self.audit.append(
            actor="system", action="pipeline_end",
            entity_type="batch", entity_id="run",
            details={
                "duration_seconds": result.duration_seconds,
                "signals_collected": result.signals_collected,
                "cases_canonical": result.cases_canonical,
                "duplicates_found": result.duplicates_found,
                "critical": result.critical_cases,
                "high": result.high_cases,
                "medium": result.medium_cases,
                "low": result.low_cases,
            },
        )

        return result

    def print_summary(self, result: PipelineResult) -> None:
        print("=" * 70)
        print("  RADAR DE OPORTUNIDADES — Pipeline Fase 1")
        print("=" * 70)
        print(f"  Duración:          {result.duration_seconds}s")
        print(f"  Señales recogidas: {result.signals_collected}")
        print(f"  Rechazadas (PII):  {result.signals_rejected_privacy}")
        print(f"  Sin entidad:       {result.signals_no_entity}")
        print(f"  Casos extraídos:   {result.cases_extracted}")
        print(f"  Duplicados:        {result.duplicates_found}")
        print(f"  Casos canónicos:   {result.cases_canonical}")
        print("-" * 70)
        print(f"  CRÍTICOS (>=80):   {result.critical_cases}")
        print(f"  ALTOS     (>=60):  {result.high_cases}")
        print(f"  MEDIOS    (>=40):  {result.medium_cases}")
        print(f"  BAJOS     (<40):   {result.low_cases}")
        print("-" * 70)
        print(f"  Audit trail:       {result.audit_entries} entradas")
        print(f"  Cadena íntegra:    {'✓' if result.audit_chain_ok else '✗ ROTA'}")
        print(f"  Sheet sync:        {result.sheet_mode} | {result.sheet_rows} filas")
        print(f"  Sheet URL:         {config.GOOGLE_SHEET_URL}")
        print("=" * 70)

        # Top 5 críticos
        crit = sorted(
            [c for c in result.cases if c.is_canonical and c.score >= 60],
            key=lambda c: c.score, reverse=True,
        )[:5]
        if crit:
            print("\n  TOP 5 CASOS PRIORITARIOS:")
            for c in crit:
                print(f"    [{c.score_band:8s}] {c.score:3d} | {c.case_id} | "
                      f"{c.problem_type:15s} | {c.jurisdiction:12s} | "
                      f"{c.patent or '—':8s} | {c.source_id}")
            print()


if __name__ == "__main__":
    p = RadarPipeline(use_real_sources=False, sheet_dry_run=True)
    result = p.run()
    p.print_summary(result)
```


