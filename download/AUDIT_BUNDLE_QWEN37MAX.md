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


=== FILE: policy_engine.py (441 líneas) ===

```"""
policy_engine.py — Motor de políticas (corrección C+D del spec + B contract formal).

================================================================================
CONTRATO FORMAL DE PolicyEngine (corrección B)
================================================================================

Input:
    CaseScored (case con score calculado, score_version, is_canonical, etc.)

Output:
    PolicyDecision (frozen dataclass con actions, reasons, boost_delta,
                    decision_id, ruleset_version)

Garantías (4):
    1. no side effects
       - PolicyEngine.evaluate() no muta el input
       - No escribe a sistemas externos
       - No llama a sinks
       - Es una función pura: input → output

    2. deterministic
       - Para el mismo input (case + config), produce el mismo output
       - Sin random, sin time-dependent behavior, sin I/O
       - Decisiones reproducibles en replay

    3. versioned ruleset
       - POLICY_RULESET_VERSION explicita (ej: "v1.0")
       - Cada PolicyDecision incluye ruleset_version
       - Cambios de reglas → bump de version → migración
       - Permite comparar decisiones entre rulesets

    4. idempotent per case_id
       - Mismo case + mismo ruleset → mismo decision_id
       - decision_id = hash determinista de (case_id, ruleset_version, actions)
       - Re-evaluar el mismo case produce la misma decisión
       - Permite replay sin duplicados

================================================================================
ROL DE PolicyEngine (corrección A — capa congelada)
================================================================================

PolicyEngine es la ÚNICA fuente de decisiones del sistema.
Ningún otro componente decide qué hacer con un caso.

Capas (corrección A del spec de estabilización):
    Extractor       → solo transforma texto → estructura
    Scoring         → solo numérico + versionado
    PolicyEngine    → única fuente de decisiones  ← ESTA CAPA
    Sinks           → ejecución pura (0 lógica de negocio)

Reglas (configurables, default = spec v2.0):
    1. if score >= 80 → generate_whatsapp_intent
    2. if jurisdiction in TARGET → boost_priority (+5)
    3. if duplicate → suppress_output (corta evaluación)
    4. if canonical → publish_to_sheets
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from models import Case, now_iso
import config


# ---------------------------------------------------------------------------
# Versión del ruleset (corrección B: versioned ruleset)
# ---------------------------------------------------------------------------
# Bump cuando cambien las reglas. Permite comparar decisiones entre rulesets
# y migrar casos en replay.
POLICY_RULESET_VERSION = "v1.0"


# ===========================================================================
# PolicyDecision (output del PolicyEngine)
# ===========================================================================
@dataclass(frozen=True)
class PolicyDecision:
    """
    Decisión emitida por PolicyEngine. Inmutable.

    Una PolicyDecision es la INTENCIÓN del sistema sobre un caso. Los sinks
    la ejecutan, pero la decisión vive acá.

    Campos:
        case_id          : ID del caso sobre el que se decidió
        actions          : lista de acciones a ejecutar por sinks
                           ("generate_whatsapp_intent", "boost_priority",
                            "suppress_output", "publish_to_sheets")
        reasons          : una razón legible por cada action
        boost_delta      : delta de score a aplicar (ej: +5 por jurisdiction)
        metadata         : info adicional (target_jurisdiction, etc.)
        decision_id      : ID determinista (idempotencia per case_id)
                           hash(case_id, ruleset_version, actions)
        ruleset_version  : versión del ruleset usado (corrección B)
        timestamp        : ISO8601 de cuándo se emitió
    """
    case_id: str
    actions: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    boost_delta: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    decision_id: str = ""
    ruleset_version: str = POLICY_RULESET_VERSION
    timestamp: str = ""

    def has_action(self, action: str) -> bool:
        return action in self.actions

    def should_suppress(self) -> bool:
        return "suppress_output" in self.actions

    def should_publish_to_sheets(self) -> bool:
        return "publish_to_sheets" in self.actions and not self.should_suppress()

    def should_generate_whatsapp(self) -> bool:
        return "generate_whatsapp_intent" in self.actions and not self.should_suppress()


# ===========================================================================
# PolicyEngine — única fuente de decisiones
# ===========================================================================
class PolicyEngine:
    """
    Motor de políticas. ÚNICA fuente de decisiones del sistema.

    Ver CONTRATO FORMAL arriba (corrección B):
        - no side effects
        - deterministic
        - versioned ruleset (POLICY_RULESET_VERSION)
        - idempotent per case_id (decision_id determinista)
    """

    def __init__(
        self,
        whatsapp_score_threshold: int = 80,
        jurisdiction_boost_delta: int = 5,
        target_jurisdictions: Optional[Set[str]] = None,
        ruleset_version: str = POLICY_RULESET_VERSION,
    ):
        self.whatsapp_score_threshold = whatsapp_score_threshold
        self.jurisdiction_boost_delta = jurisdiction_boost_delta
        self.target_jurisdictions = target_jurisdictions or config.TARGET_JURISDICTIONS
        self.ruleset_version = ruleset_version

    def evaluate(self, case: Case) -> PolicyDecision:
        """
        Evalúa un case contra todas las reglas y devuelve PolicyDecision.

        Pure function (corrección B garantía 1):
            - NO muta el case
            - NO escribe externamente
            - Determinista (corrección B garantía 2)
            - Idempotente (corrección B garantía 4): mismo case + mismo
              ruleset → mismo decision_id
        """
        actions: List[str] = []
        reasons: List[str] = []
        boost_delta = 0
        metadata: Dict[str, Any] = {}

        # Regla 3 (evaluar primero): duplicate → suppress_output
        if not case.is_canonical:
            actions.append("suppress_output")
            reasons.append(f"duplicate of {case.duplicate_of}")
            metadata["duplicate_of"] = case.duplicate_of
            # Si es duplicate, no se evalúan más reglas (supresión total)
            return self._build_decision(
                case=case, actions=actions, reasons=reasons,
                boost_delta=0, metadata=metadata,
            )

        # Regla 1: score >= 80 → generate_whatsapp_intent
        if case.score >= self.whatsapp_score_threshold:
            actions.append("generate_whatsapp_intent")
            reasons.append(
                f"score {case.score} >= {self.whatsapp_score_threshold}"
            )
            metadata["whatsapp_score_threshold"] = self.whatsapp_score_threshold

        # Regla 2: jurisdiction in target → boost_priority
        if case.jurisdiction in self.target_jurisdictions:
            actions.append("boost_priority")
            reasons.append(
                f"jurisdiction {case.jurisdiction} in target {sorted(self.target_jurisdictions)}"
            )
            boost_delta = self.jurisdiction_boost_delta
            metadata["boost_delta"] = boost_delta
            metadata["target_jurisdiction"] = case.jurisdiction

        # Regla 4: canonical → publish_to_sheets
        if case.is_canonical:
            actions.append("publish_to_sheets")
            reasons.append("case is canonical (not duplicate)")

        # Trigger manual: si el case ya tiene whatsapp_number seteado
        # (override desde CLI de revisión humana), generar whatsapp intent
        if case.whatsapp_number and "generate_whatsapp_intent" not in actions:
            actions.append("generate_whatsapp_intent")
            reasons.append("manual whatsapp_number present (review override)")
            metadata["manual_override"] = True

        # Trigger manual: si el case está approved
        if (case.status == "approved" or case.review_state == "approved") and \
           "generate_whatsapp_intent" not in actions:
            actions.append("generate_whatsapp_intent")
            reasons.append("case approved by human review")
            metadata["approved_review"] = True

        return self._build_decision(
            case=case, actions=actions, reasons=reasons,
            boost_delta=boost_delta, metadata=metadata,
        )

    def _build_decision(
        self,
        case: Case,
        actions: List[str],
        reasons: List[str],
        boost_delta: int,
        metadata: Dict[str, Any],
    ) -> PolicyDecision:
        """
        Construye la PolicyDecision final con decision_id determinista.

        Corrección B garantía 4 (idempotent per case_id):
            decision_id = hash(case_id, ruleset_version, sorted(actions))
            Mismo case + mismo ruleset → mismo decision_id
        """
        decision_id = _deterministic_decision_id(
            case.case_id, self.ruleset_version, actions,
        )
        return PolicyDecision(
            case_id=case.case_id,
            actions=actions,
            reasons=reasons,
            boost_delta=boost_delta,
            metadata=metadata,
            decision_id=decision_id,
            ruleset_version=self.ruleset_version,
            timestamp=now_iso(),
        )


def _deterministic_decision_id(
    case_id: str, ruleset_version: str, actions: List[str],
) -> str:
    """
    Genera decision_id determinista (idempotencia per case_id).

    Mismo case_id + mismo ruleset_version + mismas actions → mismo ID.
    Sin timestamp, sin random, sin I/O.
    """
    # sorted(actions) para que el orden no afecte el hash
    actions_canonical = ",".join(sorted(actions))
    seed = f"{case_id}|{ruleset_version}|{actions_canonical}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"dec-{h}"


# ===========================================================================
# Helper: aplicar boost_delta a un case (muta el case)
# ===========================================================================
def apply_boost(case: Case, decision: PolicyDecision) -> Case:
    """
    Aplica el boost_delta de la decisión al score del case.

    IMPORTANTE: esto se hace EXPLÍCITAMENTE fuera del PolicyEngine (que es
    pure function y no muta inputs). El caller decide si aplica el boost.

    Mutates case in-place. Clampea a [0, 100].
    """
    if decision.boost_delta == 0:
        return case
    new_score = max(0, min(100, case.score + decision.boost_delta))
    case.score = new_score
    # Recalcular band
    if new_score >= config.SCORING_THRESHOLDS["critical"]:
        case.score_band = "critical"
    elif new_score >= config.SCORING_THRESHOLDS["high"]:
        case.score_band = "high"
    elif new_score >= config.SCORING_THRESHOLDS["medium"]:
        case.score_band = "medium"
    else:
        case.score_band = "low"
    case.updated_at = now_iso()
    return case


# ===========================================================================
# Smoke test
# ===========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  SMOKE TEST policy_engine.py (con contract formal corrección B)")
    print("=" * 70)

    from models import Case, now_iso

    engine = PolicyEngine()

    # Caso 1: score 85, CABA (target), canonical → whatsapp + boost + sheets
    case1 = Case(
        case_id="case-1", signal_id="sig-1",
        source_id="facebook_public_groups",
        source_url="https://example.com/p/1", profile_url="",
        timestamp=now_iso(), name_or_alias="Test", evidence_text="Test",
        score=85, jurisdiction="CABA", is_canonical=True,
        whatsapp_number="541155551234",
    )
    d1 = engine.evaluate(case1)
    assert d1.has_action("generate_whatsapp_intent")
    assert d1.has_action("boost_priority")
    assert d1.has_action("publish_to_sheets")
    assert d1.boost_delta == 5
    assert not d1.should_suppress()
    print(f"  ✓ Caso crítico CABA: actions={d1.actions}, boost={d1.boost_delta}")
    print(f"    decision_id = {d1.decision_id}")
    print(f"    ruleset_version = {d1.ruleset_version}")

    # Corrección B garantía 4: idempotencia
    d1_bis = engine.evaluate(case1)
    assert d1.decision_id == d1_bis.decision_id, "Should be idempotent"
    assert d1.actions == d1_bis.actions
    assert d1.boost_delta == d1_bis.boost_delta
    print(f"  ✓ Idempotencia: re-evaluar mismo case → mismo decision_id")

    # Corrección B garantía 1: no side effects
    original_score = case1.score
    original_canonical = case1.is_canonical
    _ = engine.evaluate(case1)
    assert case1.score == original_score
    assert case1.is_canonical == original_canonical
    print(f"  ✓ No side effects: case original NO mutado")

    # Corrección B garantía 2: deterministic
    # Mismo case en otra instancia de engine (misma config) → mismo decision_id
    engine2 = PolicyEngine()
    d1_ter = engine2.evaluate(case1)
    assert d1.decision_id == d1_ter.decision_id
    print(f"  ✓ Deterministic: otra instancia con misma config → mismo decision_id")

    # Corrección B garantía 3: versioned ruleset
    assert d1.ruleset_version == POLICY_RULESET_VERSION
    print(f"  ✓ Versioned ruleset: {d1.ruleset_version}")

    # Caso 2: score 50, MENDOZA (no target), canonical → sólo sheets
    case2 = Case(
        case_id="case-2", signal_id="sig-2",
        source_id="x_search",
        source_url="https://example.com/p/2", profile_url="",
        timestamp=now_iso(), name_or_alias="Test2", evidence_text="Test2",
        score=50, jurisdiction="MENDOZA", is_canonical=True,
    )
    d2 = engine.evaluate(case2)
    assert not d2.has_action("generate_whatsapp_intent")
    assert not d2.has_action("boost_priority")
    assert d2.has_action("publish_to_sheets")
    assert d2.boost_delta == 0
    print(f"  ✓ Caso medio no-target: actions={d2.actions}, boost=0")

    # Caso 3: duplicate → suppress_output
    case3 = Case(
        case_id="case-3", signal_id="sig-3",
        source_id="x_search",
        source_url="https://example.com/p/3", profile_url="",
        timestamp=now_iso(), name_or_alias="Test3", evidence_text="Test3",
        score=85, jurisdiction="CABA", is_canonical=False,
        duplicate_of="case-1",
    )
    d3 = engine.evaluate(case3)
    assert d3.should_suppress()
    assert d3.actions == ["suppress_output"]
    assert not d3.should_publish_to_sheets()
    assert not d3.should_generate_whatsapp()
    print(f"  ✓ Duplicate: actions={d3.actions}, suppress=True")

    # Caso 4: score 50 con whatsapp_number manual
    case4 = Case(
        case_id="case-4", signal_id="sig-4",
        source_id="x_search",
        source_url="https://example.com/p/4", profile_url="",
        timestamp=now_iso(), name_or_alias="Test4", evidence_text="Test4",
        score=50, jurisdiction="PBA", is_canonical=True,
        whatsapp_number="541100000000",
    )
    d4 = engine.evaluate(case4)
    assert d4.has_action("generate_whatsapp_intent")
    assert d4.has_action("boost_priority")
    print(f"  ✓ Caso con número manual: actions={d4.actions}")

    # Caso 5: approved por revisión
    case5 = Case(
        case_id="case-5", signal_id="sig-5",
        source_id="x_search",
        source_url="https://example.com/p/5", profile_url="",
        timestamp=now_iso(), name_or_alias="Test5", evidence_text="Test5",
        score=55, jurisdiction="CORDOBA", is_canonical=True,
        whatsapp_number="", status="approved",
    )
    d5 = engine.evaluate(case5)
    assert d5.has_action("generate_whatsapp_intent")
    print(f"  ✓ Caso approved: actions={d5.actions}")

    # Test apply_boost (mutación explícita, fuera del engine)
    case6 = Case(
        case_id="case-6", signal_id="sig-6",
        source_id="x_search",
        source_url="https://example.com/p/6", profile_url="",
        timestamp=now_iso(), name_or_alias="Test6", evidence_text="Test6",
        score=78, jurisdiction="CABA", is_canonical=True,
    )
    d6 = engine.evaluate(case6)
    assert d6.boost_delta == 5
    case6_boosted = apply_boost(case6, d6)
    assert case6_boosted.score == 83
    assert case6_boosted.score_band == "critical"
    print(f"  ✓ apply_boost: 78 + 5 = 83, band=critical")

    # Validación del contrato formal (corrección B)
    print(f"\n  Contrato formal PolicyEngine (corrección B):")
    print(f"    Input:    CaseScored (case con score, score_version, is_canonical)")
    print(f"    Output:   PolicyDecision (actions, reasons, boost_delta, decision_id, ruleset_version)")
    print(f"    Garantías:")
    print(f"      1. no side effects      ✓ (no muta input, no escribe externo)")
    print(f"      2. deterministic        ✓ (mismo input → mismo output)")
    print(f"      3. versioned ruleset    ✓ (POLICY_RULESET_VERSION='{POLICY_RULESET_VERSION}')")
    print(f"      4. idempotent per case  ✓ (decision_id = hash(case_id, ruleset, actions))")

    print("\n" + "=" * 70)
    print("  ✓ Todos los smoke tests OK")
    print("=" * 70)



# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
```


=== FILE: radar_lite.py (503 líneas) ===

```"""
radar_lite.py — Radar de Oportunidades Fase 1 (versión minimalista).

Spec: "Radar de Oportunidades - Fase 1" v1.0

Objetivo: Detectar oportunidades comerciales explícitas en texto público
relacionado con multas, transferencias y libre deuda vehicular, y generar
derivación a WhatsApp.

Componentes EXCLUIDOS por spec:
    - event_bus
    - database
    - sheets
    - policy_engine
    - llm_agents
    - complex_workflows

Reglas:
    - no_external_writes: true
    - no_databases: true
    - no_crm_logic: true
    - no_automation_spam: true
    - manual_review_optional: true
    - focus_only_on_intent_detection: true

Uso:
    python radar_lite.py "texto de la señal pública"
    python radar_lite.py < archivo.txt
    echo "texto" | python radar_lite.py

Output: JSON con score, matched_keywords, snippet, whatsapp_link (si score >= 2)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from urllib.parse import quote

# ===========================================================================
# Configuración del spec (hardcoded, sin config externo)
# ===========================================================================

WHATSAPP_PHONE = "5493425691516"  # +54 9 342 5691516 (sin + ni espacios)
WHATSAPP_ENABLED = True
SCORE_THRESHOLD = 2  # >= 2 genera link de WhatsApp

# Keywords del spec, clasificadas por peso de intención
KEYWORDS_PROBLEM = [
    "multa", "fotomulta", "deuda", "patente",
]
KEYWORDS_CONTEXT = [
    "libre deuda", "transferencia", "urgente",
]
KEYWORDS_ACTION = [
    "vendo auto", "transferir auto", "no puedo vender", "no puedo transferir",
]

# Todas las keywords en una lista (para el campo debug.matched_keywords)
ALL_KEYWORDS = KEYWORDS_PROBLEM + KEYWORDS_CONTEXT + KEYWORDS_ACTION

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",  # AB 123 CD (nuevo)
    r"\b[A-Z]{3}\s?\d{3}\b",              # ABC 123 (viejo)
]

# Tipos de vehículo
VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]

# Jurisdicciones AR (para location extraction)
JURISDICTIONS = [
    "caba", "buenos aires", "pba", "gba", "córdoba", "cordoba", "santa fe",
    "rosario", "mendoza", "tucumán", "tucuman", "neuquén", "neuquen",
    "río negro", "rio negro", "chubut", "la pampa", "corrientes", "misiones",
    "salta", "jujuy", "formosa", "chaco", "santiago del estero", "la rioja",
    "catamarca", "san juan", "san luis", "santa cruz", "tierra del fuego",
]

# Localidades comunes (heurística: "en X", "de X", "vivo en X", "zona X")
LOCATION_PATTERNS = [
    r"(?:estoy en|vivo en|de|zona|en)\s+([A-ZÁÉÍÓÚa-záéíóúñ]+(?:\s[A-ZÁÉÍÓÚa-záéíóúñ]+)?)",
]


# ===========================================================================
# Dataclass de resultado
# ===========================================================================
@dataclass
class RadarResult:
    """Resultado del análisis de una señal pública."""
    # Score 0-3
    score: int = 0
    intent: str = "no_relevant"  # no_relevant / low_intent / medium_intent / high_intent_actionable

    # Entity extraction
    name_or_alias: str = ""
    vehicle_reference: str = ""
    patent_if_present: str = ""
    location: str = ""
    problem_type: str = ""
    source_text_snippet: str = ""

    # Debug (spec: return_raw_score, return_matched_keywords, return_snippet)
    matched_keywords: List[str] = field(default_factory=list)

    # Output
    whatsapp_link: str = ""  # vacío si score < threshold
    triggered: bool = False  # True si score >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Keyword scan
# ===========================================================================
def scan_keywords(text: str) -> Dict[str, List[str]]:
    """
    Escanea el texto y devuelve las keywords matched por categoría.

    Returns:
        {"problem": [...], "context": [...], "action": [...]}
    """
    text_lower = text.lower()

    matched_problem = [kw for kw in KEYWORDS_PROBLEM if kw in text_lower]
    matched_context = [kw for kw in KEYWORDS_CONTEXT if kw in text_lower]
    matched_action = [kw for kw in KEYWORDS_ACTION if kw in text_lower]

    return {
        "problem": matched_problem,
        "context": matched_context,
        "action": matched_action,
    }


# ===========================================================================
# Score calculation (0-3)
# ===========================================================================
def calculate_score(matches: Dict[str, List[str]]) -> int:
    """
    Calcula score 0-3 basado en keywords matched.

    Heurística:
        +1 si hay alguna keyword de problema (multa, fotomulta, deuda, patente)
        +1 si hay alguna keyword de contexto (libre deuda, transferencia, urgente)
        +1 si hay alguna keyword de acción (vendo auto, transferir auto, no puedo...)
        Cap a 3.

    Resultado:
        0 = no_relevant (nada matcheó)
        1 = low_intent (sólo problema mencionado)
        2 = medium_intent (problema + contexto, o acción sola)
        3 = high_intent_actionable (problema + contexto + acción)
    """
    score = 0
    if matches["problem"]:
        score += 1
    if matches["context"]:
        score += 1
    if matches["action"]:
        score += 1
    return min(score, 3)


def score_to_intent(score: int) -> str:
    """Mapea score 0-3 a etiqueta de intención del spec."""
    mapping = {
        0: "no_relevant",
        1: "low_intent",
        2: "medium_intent",
        3: "high_intent_actionable",
    }
    return mapping.get(score, "no_relevant")


# ===========================================================================
# Entity extraction (light regex, optional)
# ===========================================================================
def extract_patent(text: str) -> str:
    """Extrae patente argentina si está presente."""
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    # Patente con palabra "patente" seguida de valor
    m = re.search(r"patente\s+([A-Z]{2,3}\s?\d{3}\s?[A-Z]{0,2})", text, re.IGNORECASE)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def extract_vehicle(text: str) -> str:
    """Extrae tipo de vehículo si está mencionado."""
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
    return ""


def extract_location(text: str) -> str:
    """Extrae localidad usando heurísticas simples."""
    for pattern in LOCATION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().title()
            # Filtrar falsos positivos
            if loc.lower() not in {"el", "la", "los", "las", "mi", "tu", "su", "un", "una"}:
                return loc
    # Buscar jurisdicciones conocidas
    text_lower = text.lower()
    for jur in JURISDICTIONS:
        if jur in text_lower:
            return jur.title()
    return ""


def extract_name(text: str) -> str:
    """
    Intenta extraer nombre/alias del autor.
    Heurísticas: @username, "Hola soy X", "Soy X".
    """
    # @username (X/Twitter)
    m = re.search(r"@(\w{3,20})", text)
    if m:
        return m.group(0)
    # "Hola soy X" / "Soy X"
    m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", text, re.IGNORECASE)
    if m:
        return m.group(1).title()
    return ""


def extract_problem_type(matches: Dict[str, List[str]]) -> str:
    """Deriva el tipo de problema desde las keywords matched."""
    all_matched = matches["problem"] + matches["context"] + matches["action"]
    if "vendo auto" in all_matched or "transferir auto" in all_matched or \
       "no puedo vender" in all_matched or "no puedo transferir" in all_matched or \
       "transferencia" in all_matched:
        return "transferencia"
    if "libre deuda" in all_matched:
        return "libre_deuda"
    if "fotomulta" in all_matched:
        return "fotomulta"
    if "multa" in all_matched:
        return "multa"
    if "patente" in all_matched:
        return "patente"
    if "deuda" in all_matched:
        return "deuda"
    return ""


def make_snippet(text: str, max_len: int = 120) -> str:
    """Crea un snippet truncado del texto original."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


# ===========================================================================
# WhatsApp link generation
# ===========================================================================
def generate_whatsapp_link(score: int, problem_type: str, snippet: str) -> str:
    """
    Genera link de WhatsApp según el template del spec.

    Template: "CASO RADAR\nINTENCION: {score}\nTIPO: {problem_type}\nEXTRACTO: {snippet}"
    URL: https://wa.me/5493425691516?text={encoded_message}
    """
    if not WHATSAPP_ENABLED:
        return ""

    message = (
        f"CASO RADAR\n"
        f"INTENCION: {score}\n"
        f"TIPO: {problem_type}\n"
        f"EXTRACTO: {snippet}"
    )
    encoded = quote(message)
    return f"https://wa.me/{WHATSAPP_PHONE}?text={encoded}"


# ===========================================================================
# Pipeline principal
# ===========================================================================
def analyze(text: str) -> RadarResult:
    """
    Pipeline completo del Radar Lite.

    Workflow del spec:
        1. input_text_received
        2. keyword_scan
        3. score_calculation
        4. intent_filtering
        5. if_score_ge_2_generate_output
        6. generate_whatsapp_link
    """
    # 1. input_text_received
    if not text or not text.strip():
        return RadarResult()

    # 2. keyword_scan
    matches = scan_keywords(text)

    # 3. score_calculation
    score = calculate_score(matches)
    intent = score_to_intent(score)

    # 4. intent_filtering
    triggered = score >= SCORE_THRESHOLD

    # Entity extraction (light regex, optional)
    patent = extract_patent(text)
    vehicle = extract_vehicle(text)
    location = extract_location(text)
    name = extract_name(text)
    problem_type = extract_problem_type(matches)
    snippet = make_snippet(text)

    # 5. if_score_ge_2_generate_output
    whatsapp_link = ""
    if triggered:
        # 6. generate_whatsapp_link
        whatsapp_link = generate_whatsapp_link(score, problem_type, snippet)

    # Debug: matched_keywords (todas las que matchearon, en una lista plana)
    all_matched = matches["problem"] + matches["context"] + matches["action"]

    return RadarResult(
        score=score,
        intent=intent,
        name_or_alias=name,
        vehicle_reference=vehicle,
        patent_if_present=patent,
        location=location,
        problem_type=problem_type,
        source_text_snippet=snippet,
        matched_keywords=all_matched,
        whatsapp_link=whatsapp_link,
        triggered=triggered,
    )


# ===========================================================================
# CLI
# ===========================================================================
def read_input() -> str:
    """Lee texto de argumento o stdin."""
    if len(sys.argv) > 1:
        # Argumento directo
        return " ".join(sys.argv[1:])
    # Stdin (pipe o redirect)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    # Modo interactivo
    print("Radar de Oportunidades - Fase 1 (Lite)", file=sys.stderr)
    print("Ingresá el texto de la señal pública (Ctrl+D para finalizar):", file=sys.stderr)
    return sys.stdin.read()


def main() -> int:
    text = read_input()
    if not text.strip():
        print(json.dumps({"error": "no input text"}, ensure_ascii=False))
        return 1

    result = analyze(text)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


# ===========================================================================
# Smoke tests (ejecutar con: python radar_lite.py --test)
# ===========================================================================
def run_tests():
    """Tests con los 4 tipos de input del spec."""
    print("=" * 70)
    print("  SMOKE TEST radar_lite.py")
    print("=" * 70)

    test_cases = [
        # 1. Facebook group post — high intent
        {
            "name": "FB post: vendo auto + libre deuda + urgente",
            "text": "URGENTE: vendo auto por traslado al exterior. Tengo libre deuda pendiente en Santa Fe, necesito regularizar y transferir antes del 15. Auto en Rafaela, patente ABC 999.",
            "expected_score": 3,
            "expected_trigger": True,
        },
        # 2. X post — medium intent
        {
            "name": "X post: fotomulta + consulta",
            "text": "@usuario_cabildo Otra fotomulta en Cabildo y Juramento. Tercera en 2 meses. Cómo hago el reclamo?? #fotomultas",
            "expected_score_min": 1,
            "expected_trigger": None,  # puede o no según keywords
        },
        # 3. Marketplace listing — high intent
        {
            "name": "Marketplace: vendo auto + transferencia",
            "text": "Vendo auto Peugeot 208 2019. Libre deuda y 08 firmado, listo para transferir. Sin deudas. $4.500.000. Zona Villa Crespo.",
            "expected_score_min": 2,
            "expected_trigger": True,
        },
        # 4. Manual text — no relevant
        {
            "name": "Manual: texto sin keywords",
            "text": "Hola, qué lindo día hace hoy para pasear por la ciudad.",
            "expected_score": 0,
            "expected_trigger": False,
        },
        # 5. Forum post — medium intent
        {
            "name": "Forum: no puedo transferir + multa",
            "text": "No puedo transferir el auto porque tengo 2 multas impagas de Córdoba. Alguien sabe cómo regularizar? Son del 2023.",
            "expected_score_min": 2,
            "expected_trigger": True,
        },
        # 6. Patente + deuda — low intent
        {
            "name": "Patente atrasada",
            "text": "Le debo 2 cuotas de patente de PBA, lo regularizo antes de transferir.",
            "expected_score_min": 1,
            "expected_trigger": None,
        },
    ]

    passed = 0
    failed = 0

    for tc in test_cases:
        result = analyze(tc["text"])
        ok = True
        reasons = []

        if "expected_score" in tc:
            if result.score != tc["expected_score"]:
                ok = False
                reasons.append(f"score={result.score} (expected {tc['expected_score']})")

        if "expected_score_min" in tc:
            if result.score < tc["expected_score_min"]:
                ok = False
                reasons.append(f"score={result.score} (expected >= {tc['expected_score_min']})")

        if tc["expected_trigger"] is not None:
            if result.triggered != tc["expected_trigger"]:
                ok = False
                reasons.append(f"triggered={result.triggered} (expected {tc['expected_trigger']})")

        status = "✓" if ok else "✗"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n  {status} {tc['name']}")
        print(f"    score={result.score} ({result.intent}) | triggered={result.triggered}")
        print(f"    matched_keywords={result.matched_keywords}")
        print(f"    problem_type={result.problem_type} | patent={result.patent_if_present or '—'} | location={result.location or '—'}")
        if result.whatsapp_link:
            print(f"    whatsapp_link={result.whatsapp_link[:80]}…")
        if reasons:
            for r in reasons:
                print(f"    FAIL: {r}")

    print(f"\n{'=' * 70}")
    print(f"  Resultado: {passed} pasaron, {failed} fallaron")
    print(f"{'=' * 70}")

    # Verificar WhatsApp link format
    print("\n  Verificación WhatsApp link:")
    result = analyze("URGENTE: vendo auto. Libre deuda pendiente. Transferir.")
    link = result.whatsapp_link
    assert link.startswith(f"https://wa.me/{WHATSAPP_PHONE}?text="), \
        f"Link mal formateado: {link[:60]}"
    # Decodificar y verificar template
    from urllib.parse import unquote
    encoded_part = link.split("?text=")[1]
    decoded = unquote(encoded_part)
    assert "CASO RADAR" in decoded
    assert f"INTENCION: {result.score}" in decoded
    assert f"TIPO: {result.problem_type}" in decoded
    assert "EXTRACTO:" in decoded
    print(f"  ✓ Link usa teléfono {WHATSAPP_PHONE}")
    print(f"  ✓ Template: CASO RADAR / INTENCION / TIPO / EXTRACTO")
    print(f"  ✓ Score threshold = {SCORE_THRESHOLD} (genera link si score >= {SCORE_THRESHOLD})")

    print(f"\n{'=' * 70}")
    print(f"  ✓ Todos los smoke tests OK")
    print(f"{'=' * 70}")
    return failed == 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if run_tests() else 1)
    sys.exit(main())
```


=== FILE: radar_pro.py (1195 líneas) ===

```"""
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
```


=== FILE: radar_search.py (739 líneas) ===

```"""
radar_search.py — Radar de Oportunidades v1.1 (búsqueda real de contenido público).

Mission: Descubrir automáticamente oportunidades comerciales públicas relacionadas
con fotomultas, libre deuda y transferencias vehiculares, presentándolas para
revisión humana.

Phase 1 goal: Demostrar que el Radar puede encontrar oportunidades reales sin Ads.
Success: Encontrar al menos 10 oportunidades reales utilizando únicamente información pública.

Sin: CRM, Google Sheets, Database, Dashboards, Event Bus, Policy Engine, LLM Workflow, Cloud, Docker.

Estrategia:
  1. Buscar contenido público (vía z-ai web_search CLI)
  2. Leer publicaciones (vía z-ai page_reader CLI para top resultados)
  3. Extraer señales (regex + heurísticas)
  4. Calificar (intent_score, urgency_score, commercial_score, confidence — 0-100)
  5. Mostrar ranking (top 25, ordenado por commercial_score DESC, urgency_score DESC, confidence DESC)

Compliance:
  - only_public_information: True
  - never_bypass_logins: True
  - never_collect_private_information: True
  - never_send_messages: True
  - human_review_required: True
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
from typing import List, Dict, Any, Optional, Set
from urllib.parse import quote, urlparse

# ===========================================================================
# Configuración del spec v1.1
# ===========================================================================

QUERIES = [
    "fotomulta argentina",
    "multa transito argentina",
    "libre deuda vehicular argentina",
    "transferencia auto argentina",
    "vendo auto argentina",
    "no puedo transferir auto",
    "patente auto argentina",
    "radares fotomultas argentina",
    "APSV multa",
    "multa ruta argentina",
]

# Contexto argentino para mejor relevancia
QUERY_CONTEXT = ""  # ya incluido en queries

# Cuántos resultados por query
RESULTS_PER_QUERY = 8

# Cuántas páginas leer a fondo (top candidates)
PAGES_TO_READ_FULL = 8

# Timeout para page_reader (segundos)
PAGE_READ_TIMEOUT = 45

# Top resultados a mostrar
TOP_RESULTS = 25

# Success criterion
MIN_OPORTUNIDADES_REALES = 10

# Output path
OUTPUT_PATH = Path("/home/z/my-project/download/radar_v1.1_output.json")
RAW_SEARCH_PATH = Path("/home/z/my-project/download/radar_v1.1_raw_search.json")
RAW_PAGES_PATH = Path("/home/z/my-project/download/radar_v1.1_raw_pages.json")

# ===========================================================================
# Keywords para scoring (basadas en el spec)
# ===========================================================================

# Indicadores de intención explícita de acción comercial
INTENT_KEYWORDS = [
    "vendo", "vender", "venta", "transferir", "transferencia", "traspaso",
    "regularizar", "necesito arreglar", "libre deuda", "sacar libre",
    "consulto", "consulta", "necesito asesor", "defender", "reclamar",
    "no puedo transferir", "no puedo vender", "no puedo renovar",
]

# Indicadores de urgencia
URGENCY_KEYWORDS = [
    "urgente", "hoy", "mañana", "ahora", "ya", "rápido", "rapido",
    "antes de", "lo antes posible", "vencimiento", "vence",
    "mudanza", "traslado", "mudo", "viaje",
]

# Indicadores de potencial comercial (problemas que el negocio puede cobrar)
COMMERCIAL_PROBLEMS = {
    "transferencia": 0.9,
    "regularizacion": 0.8,
    "libre_deuda": 0.8,
    "patente": 0.5,
    "fotomulta": 0.4,
    "multa": 0.4,
    "vtv": 0.3,
}

# Patentes argentinas
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

# Teléfonos argentinos públicos
PHONE_PATTERNS = [
    r"\+54\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}",
    r"\b011[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b11[\s\-]?\d{4}[\s\-]?\d{4}",
    r"\b15[\s\-]?\d{4}[\s\-]?\d{4}",
]

WHATSAPP_PATTERNS = [
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"wa\.me/(\d{8,15})",
]

FACEBOOK_PROFILE_PATTERNS = [
    r"facebook\.com/[^/\s\"']{5,50}",
]

# Jurisdicciones AR
JURISDICTIONS = [
    "caba", "buenos aires", "pba", "gba", "córdoba", "cordoba", "santa fe",
    "rosario", "mendoza", "tucumán", "tucuman", "neuquén", "neuquen",
    "río negro", "rio negro", "chubut", "la pampa", "corrientes", "misiones",
    "salta", "jujuy", "formosa", "chaco", "santiago del estero", "la rioja",
    "catamarca", "san juan", "san luis", "santa cruz", "tierra del fuego",
]

VEHICLE_TYPES = ["auto", "moto", "camioneta", "camion", "utilitario", "pick up", "pickup"]

# Dominios a filtrar (no son oportunidades comerciales vehiculares)
EXCLUDED_DOMAINS = {
    # Bancos / fintech / transferencias dinero
    "bbva.com.ar", "galicia.ar", "bna.com.ar", "prexcard.com.ar",
    "wise.com", "revolut.com", "moneygram.com", "global66.com",
    "paypal.com", "n26.com", "bingx.com", "bybit.com",
    # Wikipedia / diccionarios
    "es.wikipedia.org", "en.wikipedia.org", "rae.es",
    # Sitios institucionales gubernamentales (no leads)
    "argentina.gob.ar", "buenosaires.gob.ar",
    # YouTube shorts (no texto útil)
    "youtube.com", "instagram.com",
}

# Palabras que indican que NO es una oportunidad comercial (filtro de snippet)
NEGATIVE_INDICATORS = [
    "wikipedia", "enciclopedia", "definición",
    "transferencia bancaria", "transferir dinero", "transferencia internacional",
    "enviar dinero", "giro", "remesa",
    "criptomoneda", "bitcoin", "exchange",
]


# ===========================================================================
# Dataclass de señal
# ===========================================================================
@dataclass
class Signal:
    """Señal extraída de contenido público."""
    # Identificación
    source: str  # host_name (ej: clarin.com)
    url: str
    name: str  # título de la página/post
    snippet: str  # texto extraído (snippet de search o texto de página)
    date: str  # fecha de publicación si está disponible

    # Entidades extraídas
    nombre_o_alias: str = ""
    ubicacion: str = ""
    tipo_problema: str = ""
    patente_si_aparece: str = ""
    telefono_si_es_publico: str = ""
    whatsapp_si_es_publico: str = ""
    facebook_profile_si_es_publico: str = ""

    # Scoring 0-100
    intent_score: int = 0
    urgency_score: int = 0
    commercial_score: int = 0
    confidence: int = 0

    # Output
    recommended_action: str = "Ignorar"  # Ignorar / Revisar / Posible cliente

    # Meta
    query: str = ""  # query que la encontró
    read_full: bool = False  # si se leyó la página completa

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Búsqueda web (vía z-ai CLI)
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Ejecuta búsqueda web vía z-ai CLI."""
    full_query = f"{query} {QUERY_CONTEXT}".strip()
    args = json.dumps({"query": full_query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_search_{hash(query) & 0xFFFFFFFF:x}.json"

    try:
        result = subprocess.run(
            ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  [warn] search failed for '{query}': {result.stderr[:200]}", file=sys.stderr)
            return []

        with open(tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []
        return data
    except subprocess.TimeoutExpired:
        print(f"  [warn] search timeout for '{query}'", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [warn] search error for '{query}': {e}", file=sys.stderr)
        return []
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def read_page(url: str) -> Optional[Dict[str, Any]]:
    """Lee contenido de una página vía z-ai page_reader CLI."""
    args = json.dumps({"url": url}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_page_{hash(url) & 0xFFFFFFFF:x}.json"

    try:
        result = subprocess.run(
            ["z-ai", "function", "-n", "page_reader", "-a", args, "-o", tmp_file],
            capture_output=True, text=True, timeout=PAGE_READ_TIMEOUT,
        )
        if result.returncode != 0:
            return None

        with open(tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # El formato puede ser {data: {...}} o directo
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except subprocess.TimeoutExpired:
        print(f"    [timeout] {url[:60]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    [error] {e}", file=sys.stderr)
        return None
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


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
    for jur in JURISDICTIONS:
        if jur in text_lower:
            return jur.title()
    return ""


def extract_vehicle(text: str) -> str:
    text_lower = text.lower()
    for v in VEHICLE_TYPES:
        if v in text_lower:
            return v
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
        ("transferencia", "transferencia"),
        ("transferir", "transferencia"),
        ("no puedo transferir", "transferencia"),
        ("no puedo vender", "transferencia"),
        ("vendo auto", "transferencia"),
        ("regularizar", "regularizacion"),
        ("regularizacion", "regularizacion"),
        ("patente", "patente"),
        ("multa", "multa"),
        ("multas", "multa"),
        ("deuda", "deuda"),
    ]
    for kw, problem in priority:
        if kw in text_lower:
            return problem
    return ""


def extract_name(text: str, title: str) -> str:
    """Intenta extraer nombre/alias del autor."""
    m = re.search(r"@(\w{3,20})", text)
    if m:
        return m.group(0)
    m = re.search(r"(?:por|de|autor)\s*:?\s*([A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20}\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]{2,20})", text)
    if m:
        return m.group(1)
    return ""


# ===========================================================================
# Scoring (0-100)
# ===========================================================================
def count_keywords(text: str, keywords: List[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def calculate_intent_score(text: str) -> int:
    """
    Intención explícita de acción comercial.
    0-100 basado en cantidad y peso de keywords de intención.
    """
    matches = count_keywords(text, INTENT_KEYWORDS)
    if matches == 0:
        return 10
    if matches == 1:
        return 40
    if matches == 2:
        return 65
    if matches == 3:
        return 85
    return 100


def calculate_urgency_score(text: str) -> int:
    """
    Urgencia temporal declarada.
    0-100 basado en keywords de urgencia.
    """
    matches = count_keywords(text, URGENCY_KEYWORDS)
    if matches == 0:
        return 10
    if matches == 1:
        return 50
    if matches == 2:
        return 80
    return 100


def calculate_commercial_score(text: str, problem_type: str) -> int:
    """
    Potencial comercial del problema.
    0-100 basado en tipo de problema + monto + presencia de patente/vehículo.
    """
    base = COMMERCIAL_PROBLEMS.get(problem_type, 0.0)
    score = int(base * 70)  # base 0-70

    # Boost si hay patente (lead más concreto)
    if extract_patent(text):
        score += 15
    # Boost si hay vehículo mencionado
    if extract_vehicle(text):
        score += 10
    # Boost si hay ubicación
    if extract_location(text):
        score += 5

    return min(score, 100)


def calculate_confidence(signal: Signal, has_full_text: bool) -> int:
    """
    Confianza en la extracción.
    0-100 basado en:
      - si se leyó la página completa (+30)
      - si hay entidades concretas (patente, teléfono, ubicación)
      - si la fuente es confiable
    """
    conf = 30  # base
    if has_full_text:
        conf += 30
    if signal.patente_si_aparece:
        conf += 15
    if signal.telefono_si_es_publico or signal.whatsapp_si_es_publico:
        conf += 15
    if signal.ubicacion:
        conf += 10
    return min(conf, 100)


def assign_recommended_action(commercial: int, urgency: int, confidence: int) -> str:
    """
    Asigna acción recomendada según scores.
    - Posible cliente: commercial >= 60 AND confidence >= 50
    - Revisar: commercial >= 35 OR urgency >= 60
    - Ignorar: resto
    """
    if commercial >= 60 and confidence >= 50:
        return "Posible cliente"
    if commercial >= 35 or urgency >= 60:
        return "Revisar"
    return "Ignorar"


# ===========================================================================
# Pipeline principal
# ===========================================================================
def build_signal_from_search_result(result: Dict[str, Any], query: str) -> Signal:
    """Construye una Signal a partir de un resultado de búsqueda."""
    text = (result.get("snippet", "") or "")
    title = result.get("name", "") or ""
    combined = f"{title}. {text}"

    problem = extract_problem_type(combined)

    return Signal(
        source=result.get("host_name", ""),
        url=result.get("url", ""),
        name=title,
        snippet=text,
        date=result.get("date", ""),
        nombre_o_alias=extract_name(combined, title),
        ubicacion=extract_location(combined),
        tipo_problema=problem,
        patente_si_aparece=extract_patent(combined),
        telefono_si_es_publico=extract_phone(combined),
        whatsapp_si_es_publico=extract_whatsapp(combined),
        facebook_profile_si_es_publico=extract_facebook_profile(combined),
        intent_score=calculate_intent_score(combined),
        urgency_score=calculate_urgency_score(combined),
        commercial_score=calculate_commercial_score(combined, problem),
        confidence=0,  # se calcula después
        query=query,
        read_full=False,
    )


def enrich_signal_with_page(signal: Signal, page_data: Dict[str, Any]) -> Signal:
    """Enriquece la señal con el contenido completo de la página."""
    html = page_data.get("html", "") or ""
    # Convertir HTML a texto plano (simple)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Tomar primeros 3000 chars para no saturar
    full_text = f"{signal.name}. {text[:3000]}"

    # Re-extraer con texto completo
    problem = extract_problem_type(full_text) or signal.tipo_problema
    signal.tipo_problema = problem
    if not signal.patente_si_aparece:
        signal.patente_si_aparece = extract_patent(full_text)
    if not signal.telefono_si_es_publico:
        signal.telefono_si_es_publico = extract_phone(full_text)
    if not signal.whatsapp_si_es_publico:
        signal.whatsapp_si_es_publico = extract_whatsapp(full_text)
    if not signal.facebook_profile_si_es_publico:
        signal.facebook_profile_si_es_publico = extract_facebook_profile(full_text)
    if not signal.ubicacion:
        signal.ubicacion = extract_location(full_text)
    if not signal.nombre_o_alias:
        signal.nombre_o_alias = extract_name(full_text, signal.name)

    # Re-calcular scores con texto completo
    signal.intent_score = calculate_intent_score(full_text)
    signal.urgency_score = calculate_urgency_score(full_text)
    signal.commercial_score = calculate_commercial_score(full_text, problem)

    # Actualizar snippet con texto más rico
    if len(text) > len(signal.snippet):
        signal.snippet = text[:500]

    signal.read_full = True
    if page_data.get("publishedTime") and not signal.date:
        signal.date = page_data.get("publishedTime", "")

    return signal


def is_relevant_result(result: Dict[str, Any]) -> bool:
    """
    Filtra resultados que no son oportunidades comerciales vehiculares.
    Descarta bancos, fintech, wikipedia, etc.
    """
    url = result.get("url", "").lower()
    host = result.get("host_name", "").lower()
    snippet = (result.get("snippet", "") or "").lower()
    name = (result.get("name", "") or "").lower()

    # Filtro por dominio excluido
    for excl in EXCLUDED_DOMAINS:
        if excl in host:
            return False

    # Filtro por indicadores negativos en snippet o título
    combined = f"{snippet} {name}"
    for neg in NEGATIVE_INDICATORS:
        if neg in combined:
            return False

    return True


def dedup_by_url(signals: List[Signal]) -> List[Signal]:
    """Deduplica señales por URL."""
    seen: Set[str] = set()
    out = []
    for s in signals:
        if s.url in seen:
            continue
        seen.add(s.url)
        out.append(s)
    return out


def run_pipeline() -> Dict[str, Any]:
    """Ejecuta el pipeline completo de búsqueda y scoring."""
    print("=" * 70, file=sys.stderr)
    print("  RADAR DE OPORTUNIDADES v1.1 — Búsqueda de contenido público", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # 1. Buscar contenido público
    print(f"\n[1/5] Buscando {len(QUERIES)} queries en contenido público…", file=sys.stderr)
    all_search_results: List[Dict[str, Any]] = []
    for i, query in enumerate(QUERIES, 1):
        print(f"  [{i}/{len(QUERIES)}] Buscando: '{query} {QUERY_CONTEXT}'", file=sys.stderr)
        results = web_search(query, num=RESULTS_PER_QUERY)
        for r in results:
            r["_query"] = query
        all_search_results.extend(results)
        time.sleep(0.3)  # rate limit cortés

    print(f"\n  Total resultados de búsqueda: {len(all_search_results)}", file=sys.stderr)

    # Guardar raw search
    RAW_SEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_SEARCH_PATH.open("w", encoding="utf-8") as f:
        json.dump(all_search_results, f, ensure_ascii=False, indent=2)

    # 2. Construir señales iniciales desde snippets (filtrando irrelevantes)
    print(f"\n[2/5] Extrayendo señales de snippets (con filtro de relevancia)…", file=sys.stderr)
    signals = []
    filtered_out = 0
    for r in all_search_results:
        if not r.get("url") or not r.get("snippet"):
            continue
        if not is_relevant_result(r):
            filtered_out += 1
            continue
        sig = build_signal_from_search_result(r, r.get("_query", ""))
        signals.append(sig)

    print(f"  Filtrados (no relevantes): {filtered_out}", file=sys.stderr)

    # Dedup por URL
    signals = dedup_by_url(signals)
    print(f"  Señales únicas (post-dedup): {len(signals)}", file=sys.stderr)

    # 3. Leer páginas completas para top candidates
    # Ordenar por commercial_score + intent_score (preliminar) y tomar top N
    signals.sort(key=lambda s: (s.commercial_score + s.intent_score), reverse=True)
    candidates_to_read = signals[:PAGES_TO_READ_FULL]

    print(f"\n[3/5] Leyendo {len(candidates_to_read)} páginas a fondo…", file=sys.stderr)
    raw_pages: Dict[str, Dict[str, Any]] = {}
    for i, sig in enumerate(candidates_to_read, 1):
        print(f"  [{i}/{len(candidates_to_read)}] {sig.source}{sig.url[:60]}", file=sys.stderr)
        page_data = read_page(sig.url)
        if page_data:
            raw_pages[sig.url] = page_data
            enrich_signal_with_page(sig, page_data)
        time.sleep(0.5)  # rate limit cortés

    # Guardar raw pages
    with RAW_PAGES_PATH.open("w", encoding="utf-8") as f:
        json.dump(raw_pages, f, ensure_ascii=False, indent=2)

    # 4. Calcular confidence y recommended_action para todas
    print(f"\n[4/5] Calculando confidence y recommended_action…", file=sys.stderr)
    for sig in signals:
        sig.confidence = calculate_confidence(sig, sig.read_full)
        sig.recommended_action = assign_recommended_action(
            sig.commercial_score, sig.urgency_score, sig.confidence
        )

    # 5. Ranking y top 25
    print(f"\n[5/5] Ranking (commercial DESC, urgency DESC, confidence DESC)…", file=sys.stderr)
    signals.sort(
        key=lambda s: (s.commercial_score, s.urgency_score, s.confidence),
        reverse=True,
    )
    top = signals[:TOP_RESULTS]

    # Success criterion
    oportunities = [s for s in signals if s.recommended_action in ("Revisar", "Posible cliente")]
    success = len(oportunities) >= MIN_OPORTUNIDADES_REALES

    # Output final
    output = {
        "project_name": "Radar de Oportunidades",
        "version": "1.1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "queries_executed": len(QUERIES),
            "total_search_results": len(all_search_results),
            "unique_signals": len(signals),
            "pages_read_full": len(raw_pages),
            "opportunities_found": len(oportunities),
            "success_criterion_met": success,
            "min_required": MIN_OPORTUNIDADES_REALES,
        },
        "ranking": {
            "sort_by": ["commercial_score DESC", "urgency_score DESC", "confidence DESC"],
            "top_results": TOP_RESULTS,
        },
        "results": [
            {
                "score": s.commercial_score,
                "confidence": s.confidence,
                "source": s.source,
                "url": s.url,
                "name": s.name,
                "problem": s.tipo_problema,
                "snippet": s.snippet[:300] if s.snippet else "",
                "phone_if_public": s.telefono_si_es_publico,
                "whatsapp_if_public": s.whatsapp_si_es_publico,
                "recommended_action": s.recommended_action,
                "scores": {
                    "intent": s.intent_score,
                    "urgency": s.urgency_score,
                    "commercial": s.commercial_score,
                },
                "entities": {
                    "nombre_o_alias": s.nombre_o_alias,
                    "ubicacion": s.ubicacion,
                    "patente_si_aparece": s.patente_si_aparece,
                    "facebook_profile_si_es_publico": s.facebook_profile_si_es_publico,
                },
                "date": s.date,
                "query": s.query,
                "read_full": s.read_full,
            }
            for s in top
        ],
        "compliance": {
            "only_public_information": True,
            "never_bypass_logins": True,
            "never_collect_private_information": True,
            "never_send_messages": True,
            "human_review_required": True,
        },
    }

    # Guardar output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "=" * 70, file=sys.stderr)
    print("  RESULTADO", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Queries ejecutadas:        {len(QUERIES)}", file=sys.stderr)
    print(f"  Resultados de búsqueda:    {len(all_search_results)}", file=sys.stderr)
    print(f"  Señales únicas:            {len(signals)}", file=sys.stderr)
    print(f"  Páginas leídas a fondo:    {len(raw_pages)}", file=sys.stderr)
    print(f"  Oportunidades encontradas: {len(oportunities)}", file=sys.stderr)
    print(f"  Success criterion:         {'✓ CUMPLIDO' if success else '✗ NO cumplido'} ({len(oportunities)}/{MIN_OPORTUNIDADES_REALES})", file=sys.stderr)
    print(f"  Top {TOP_RESULTS} guardado en: {OUTPUT_PATH}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Print top 10
    print(f"\n  TOP 10 OPORTUNIDADES:", file=sys.stderr)
    for i, s in enumerate(top[:10], 1):
        print(f"    {i:2d}. [{s.recommended_action:15s}] C={s.commercial_score:3d} U={s.urgency_score:3d} I={s.urgency_score:3d} Conf={s.confidence:3d} | {s.source:20s} | {s.tipo_problema:15s} | {s.name[:50]}", file=sys.stderr)

    return output


if __name__ == "__main__":
    output = run_pipeline()
    # Print JSON a stdout
    print(json.dumps(output, ensure_ascii=False, indent=2))
```


=== FILE: radar_v2.py (977 líneas) ===

```"""
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
```


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


=== FILE: webhook_uploader.py (399 líneas) ===

```"""
webhook_uploader.py — Vía alternativa de subida vía Apps Script Web App (SPEC-ONLY).

En vez de usar gspread + service account JSON, este módulo hace POST HTTP a la
URL de un Google Apps Script Web App (desplegado por el operador) que se
encarga de append las filas a la Sheet.

Contrato de entrada:
    RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec

Comportamiento:
    - Si la env var no está seteada → raise MissingWebhookURLError
      ("Missing webhook URL")
    - Si la URL no es http(s):// → raise ValueError
    - No hay modo mock ni dry-run implícito.
    - Dry-run explícito vía --dry-run flag en CLI.

Payload enviado (JSON):
    {
      "cases": [
        {
          "case_id": "...",
          "timestamp": "...",       # se reemplaza por el script con Date().toISOString()
          "name_or_alias": "...",
          "profile_url": "...",
          "patent": "...",
          "vehicle_type": "...",
          "jurisdiction": "...",
          "locality": "...",
          "problem_type": "...",
          "year": ...,
          "amount": ...,
          "score": ...,
          "source_name": "...",
          "source_url": "...",
          "evidence_text": "...",
          "whatsapp_number": "..."
        },
        ...
      ]
    }

Respuesta esperada del Apps Script:
    - "OK" si todo bien
    - "NO_CASES" si el payload no tiene cases
    - Cualquier otro string: error reportado por el script

Reglas (glm_instruction_block):
    1. NEVER store private keys inside code (no aplica: no hay keys, sólo URL pública)
    2. ONLY use webhook URL via env var
    3. ONLY append rows (el script hace append, no overwrite)
    4. ALWAYS log case_id after write
    5. DO NOT create duplicates if case_id exists (⚠️ el script actual NO deduplica;
       esta lógica queda del lado del cliente: filtramos cases ya enviados en runs
       previos leyendo cases.jsonl con flag `pushed_to_webhook=True`)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import config
from models import Case
from storage import AuditTrail


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------
class MissingWebhookURLError(RuntimeError):
    """Raised when RADAR_WEBHOOK_URL is empty."""
    pass


class WebhookWriteError(RuntimeError):
    """Raised when the webhook POST fails after retry."""
    pass


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------
class WebhookUploader:
    """
    Sube casos a Google Sheets vía Apps Script Web App (HTTP POST).

    Contract:
        - input: RADAR_WEBHOOK_URL (env var, string URL)
        - behavior: if URL missing → raise MissingWebhookURLError
                    ("Missing webhook URL")
        - no mocks, no dry-run implicit
        - real HTTP POST happens only when push() is invoked at runtime
          in an environment that has the URL configured
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        audit: Optional[AuditTrail] = None,
        timeout: int = 30,
    ):
        url = webhook_url or os.environ.get("RADAR_WEBHOOK_URL", "")

        if not url:
            raise MissingWebhookURLError(
                "Missing webhook URL (env var RADAR_WEBHOOK_URL is empty)"
            )

        # Validar esquema
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MissingWebhookURLError(
                f"Missing webhook URL (invalid scheme: {parsed.scheme})"
            )

        self.webhook_url = url
        self.audit = audit
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Construcción del payload
    # ------------------------------------------------------------------
    @staticmethod
    def case_to_payload(case: Case) -> Dict[str, Any]:
        """
        Convierte un Case al formato que espera el Apps Script.

        El script ignora: priority_level, whatsapp_link, status, review_state
        (los computa él). Sólo necesita los 15 campos de entrada.

        Static method: se puede usar sin instanciar (útil para dry-run sin URL).
        """
        return {
            "case_id": case.case_id,
            "timestamp": case.timestamp,  # el script lo reemplaza con now()
            "name_or_alias": case.name_or_alias,
            "profile_url": case.profile_url,
            "patent": case.patent,
            "vehicle_type": case.vehicle_type,
            "jurisdiction": case.jurisdiction,
            "locality": case.locality,
            "problem_type": case.problem_type,
            "year": case.year if case.year is not None else "",
            "amount": case.amount if case.amount is not None else "",
            "score": case.score,
            "source_name": case.source_id,
            "source_url": case.source_url,
            "evidence_text": case.evidence_text,
            "whatsapp_number": case.whatsapp_number,
        }

    def _case_to_payload(self, case: Case) -> Dict[str, Any]:
        """Backwards-compat wrapper around the static method."""
        return WebhookUploader.case_to_payload(case)

    # ------------------------------------------------------------------
    # POST con retry_once_then_log_error
    # ------------------------------------------------------------------
    def _post(self, payload: Dict[str, Any]) -> str:
        """
        Hace POST JSON al webhook. Retry una vez. Devuelve el body como string.

        Raises WebhookWriteError si falla después del retry.
        """
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "radar-oportunidades/1.0 (webhook_uploader.py)",
        }

        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    self.webhook_url, data=data, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return body
            except urllib.error.HTTPError as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(
                    f"Webhook POST failed (HTTP {e.code}): {e.reason}"
                ) from e
            except urllib.error.URLError as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(f"Webhook POST failed: {e.reason}") from e
            except Exception as e:
                last_exc = e
                if attempt == 1:
                    continue
                raise WebhookWriteError(f"Webhook POST failed: {e}") from e

        # No debería llegar aquí
        raise WebhookWriteError(f"Webhook POST failed: {last_exc}")

    # ------------------------------------------------------------------
    # Push batch
    # ------------------------------------------------------------------
    def push(self, cases: List[Case]) -> Dict[str, Any]:
        """
        Envía un batch de casos al webhook.

        Returns:
            Dict con: total, pushed, response, errors
        """
        if not cases:
            return {
                "operation": "push_cases",
                "target": "webhook",
                "total": 0,
                "pushed": 0,
                "response": "NO_CASES",
                "errors": [],
            }

        payload = {"cases": [self._case_to_payload(c) for c in cases]}

        try:
            response = self._post(payload)
        except WebhookWriteError as e:
            self._log_audit("webhook_push", "error",
                             details={"error": str(e), "total": len(cases)})
            return {
                "operation": "push_cases",
                "target": "webhook",
                "webhook_url": self.webhook_url,
                "total": len(cases),
                "pushed": 0,
                "response": "",
                "errors": [{"error": str(e)}],
            }

        # Interpretar respuesta del Apps Script
        response_clean = response.strip()
        pushed = len(cases) if response_clean == "OK" else 0

        # Log por caso (glm_instruction_block: ALWAYS log case_id after write)
        if pushed:
            for case in cases:
                self._log_audit("webhook_push", "appended",
                                 entity_id=case.case_id,
                                 details={"score": case.score})
        else:
            self._log_audit("webhook_push", "failed",
                             details={"response": response_clean, "total": len(cases)})

        return {
            "operation": "push_cases",
            "target": "webhook",
            "webhook_url": self.webhook_url,
            "total": len(cases),
            "pushed": pushed,
            "response": response_clean,
            "errors": [] if pushed else [{"error": f"Unexpected response: {response_clean}"}],
        }

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
            actor="system:webhook_uploader",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={"result": result, **(details or {})},
        )


# ---------------------------------------------------------------------------
# Smoke test (spec-only): verifica el contrato de error, NO hace HTTP real
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("  SMOKE TEST webhook_uploader.py (SPEC-ONLY, no hace HTTP real)")
    print("=" * 70)

    # 1. Sin env var → Missing webhook URL
    saved = os.environ.pop("RADAR_WEBHOOK_URL", None)
    try:
        try:
            uploader = WebhookUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingWebhookURLError")
            sys.exit(1)
        except MissingWebhookURLError as e:
            assert "Missing webhook URL" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Sin URL → '{e}'")
    finally:
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    # 2. URL con esquema inválido → Missing webhook URL
    os.environ["RADAR_WEBHOOK_URL"] = "ftp://example.com/script"
    try:
        try:
            uploader = WebhookUploader()
            print(f"  ✗ FAIL: debería haber lanzado MissingWebhookURLError")
            sys.exit(1)
        except MissingWebhookURLError as e:
            assert "invalid scheme" in str(e), f"Mensaje incorrecto: {e}"
            print(f"  ✓ Esquema inválido → '{e}'")
    finally:
        os.environ.pop("RADAR_WEBHOOK_URL", None)
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    # 3. URL válida → constructor OK (no hace HTTP hasta llamar a push())
    test_url = "https://script.google.com/macros/s/AKfycbyTest/exec"
    os.environ["RADAR_WEBHOOK_URL"] = test_url
    try:
        uploader = WebhookUploader()
        assert uploader.webhook_url == test_url
        print(f"  ✓ URL válida → constructor OK (sin HTTP)")
        print(f"    webhook_url = {uploader.webhook_url}")

        # 4. _case_to_payload genera exactamente los 15 campos esperados por el script
        from models import Case
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
        payload = uploader._case_to_payload(case)
        expected_keys = {
            "case_id", "timestamp", "name_or_alias", "profile_url", "patent",
            "vehicle_type", "jurisdiction", "locality", "problem_type", "year",
            "amount", "score", "source_name", "source_url", "evidence_text",
            "whatsapp_number",
        }
        assert set(payload.keys()) == expected_keys, \
            f"Payload keys mismatch: {set(payload.keys())} vs {expected_keys}"
        print(f"  ✓ _case_to_payload genera {len(payload)} campos esperados por el script")
        print(f"    keys = {sorted(payload.keys())}")

        # 5. push([]) retorna NO_CASES sin hacer HTTP
        empty_result = uploader.push([])
        assert empty_result["response"] == "NO_CASES"
        assert empty_result["pushed"] == 0
        print(f"  ✓ push([]) → 'NO_CASES' (sin HTTP)")
    finally:
        os.environ.pop("RADAR_WEBHOOK_URL", None)
        if saved is not None:
            os.environ["RADAR_WEBHOOK_URL"] = saved

    print("\n" + "=" * 70)
    print("  ✓ Contrato spec-only verificado. No se ejecutaron POSTs HTTP.")
    print("=" * 70)
    print("""
  Para ejecutar push real (en máquina del operador con Web App desplegada):

      # 1. En Apps Script: Implementar > Implementar > Nueva implementación
      #    Tipo: App web
      #    Ejecutar como: Yo
      #    Quién puede acceder: Cualquiera (o solo dominio)
      #    → Copiar URL de implementación
      #
      # 2. Setear env var:
      export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
      #
      # 3. Ejecutar:
      python main.py --sheet-push-webhook

  Si la URL no está seteada, el uploader lanza:
      Missing webhook URL (env var RADAR_WEBHOOK_URL is empty)
""")
```


=== FILE: apps_script/Code.gs (178 líneas) ===

```/**
 * Radar de Oportunidades — Apps Script Web App (Code.gs)
 *
 * Este script se despliega como Web App en Google Apps Script y recibe POST
 * HTTP desde `webhook_uploader.py` (Python) para appendar casos a la Sheet.
 *
 * Despliegue:
 *   1. Abrir la Sheet: https://docs.google.com/spreadsheets/d/1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0/edit
 *   2. Extensiones > Apps Script
 *   3. Pegar este código
 *   4. Implementar > Nueva implementación > Tipo: App web
 *      - Ejecutar como: Yo (tu cuenta)
 *      - Quién puede acceder: Cualquiera (con el link)
 *   5. Copiar URL de implementación (termina en /exec)
 *   6. Setear en la máquina del operador:
 *      export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
 *
 * Compliance:
 *   - El script sólo escribe en la Sheet especificada, no lee otras Sheets
 *   - No expone datos: sólo acepta POST con payload JSON
 *   - El acceso queda logueado en el execution log de Apps Script
 */

const SHEET_ID = "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0";
const SHEET_NAME = "cases";

/**
 * Append batch cases to Google Sheets
 */
function appendCases(cases) {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);

  // Si la hoja no existe, crearla
  if (!sheet) {
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const newSheet = ss.insertSheet(SHEET_NAME);
    ensureHeaders(newSheet);
    return appendCasesToSheet(newSheet, cases);
  }

  // Asegurar headers si la hoja está vacía
  if (sheet.getLastRow() === 0) {
    ensureHeaders(sheet);
  }

  return appendCasesToSheet(sheet, cases);
}

/**
 * Asegura que la fila 1 tenga los headers correctos
 */
function ensureHeaders(sheet) {
  const headers = [
    "case_id", "timestamp", "name_or_alias", "profile_url", "patent",
    "vehicle_type", "jurisdiction", "locality", "problem_type", "year",
    "amount", "score", "priority_level", "source_name", "source_url",
    "evidence_text", "whatsapp_number", "whatsapp_link", "status", "review_state"
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
}

/**
 * Append cases to a sheet que ya tiene headers
 */
function appendCasesToSheet(sheet, cases) {
  const rows = cases.map(c => [
    c.case_id || "",
    new Date().toISOString(),
    c.name_or_alias || "",
    c.profile_url || "",
    c.patent || "",
    c.vehicle_type || "",
    c.jurisdiction || "",
    c.locality || "",
    c.problem_type || "",
    c.year || "",
    c.amount || "",
    c.score || 0,
    computePriority(c.score),
    c.source_name || "",
    c.source_url || "",
    c.evidence_text || "",
    c.whatsapp_number || "",
    buildWhatsApp(c.whatsapp_number),
    "new",
    "pending_review"
  ]);

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length)
        .setValues(rows);

  return rows.length;
}

/**
 * Priority scoring
 */
function computePriority(score) {
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 40) return "medium";
  return "low";
}

/**
 * WhatsApp link builder
 */
function buildWhatsApp(number) {
  if (!number) return "";
  // Normalizar: sólo dígitos
  const normalized = String(number).replace(/\D/g, "");
  if (!normalized) return "";
  return "https://wa.me/" + normalized;
}

/**
 * Entry point for GLM webhook-style push
 * Recibe: { "cases": [ {case_id, ...}, ... ] }
 * Devuelve: "OK" | "NO_CASES" | "ERROR: <msg>"
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput("ERROR: no post data");
    }

    const payload = JSON.parse(e.postData.contents);

    if (!payload.cases || !Array.isArray(payload.cases) || payload.cases.length === 0) {
      return ContentService.createTextOutput("NO_CASES");
    }

    const appended = appendCases(payload.cases);

    // Log en execution log de Apps Script (visible en el editor)
    console.log(`Appended ${appended} cases from webhook push`);

    return ContentService.createTextOutput("OK");
  } catch (err) {
    console.error("Error en doPost:", err);
    return ContentService.createTextOutput("ERROR: " + err.message);
  }
}

/**
 * Test manual desde el editor de Apps Script
 */
function testDoPost() {
  const mockEvent = {
    postData: {
      contents: JSON.stringify({
        cases: [
          {
            case_id: "test-001",
            timestamp: "2026-06-30T10:00:00-03:00",
            name_or_alias: "Test User",
            profile_url: "https://example.com/user/1",
            patent: "ABC123",
            vehicle_type: "auto",
            jurisdiction: "CABA",
            locality: "Caballito",
            problem_type: "fotomulta",
            year: 2020,
            amount: 18500,
            score: 82,
            source_name: "facebook_public_groups",
            source_url: "https://example.com/post/abc",
            evidence_text: "Test evidence text",
            whatsapp_number: "541155551234"
          }
        ]
      })
    }
  };
  const result = doPost(mockEvent);
  Logger.log("Resultado: " + result.getContent());
}
```


=== FIN DEL CÓDIGO ===

Generá ahora el reporte de auditoría completo según el formato especificado arriba.
