#!/usr/bin/env python3
"""
Genera un único bloque de texto con TODO el código del proyecto + prompt de auditoría
para que Qwen3.7-Max lo audite. Output listo para copy-paste.
"""
from pathlib import Path
import datetime

RADAR_DIR = Path("/home/z/my-project/scripts/radar")
OUTPUT = Path("/home/z/my-project/download/AUDIT_BUNDLE_QWEN37MAX.md")

# Prompt de auditoría al inicio
AUDIT_PROMPT = """# AUDITORÍA DE CÓDIGO COMPLETA — Radar de Oportunidades

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

"""

# Collect all .py files sorted
py_files = sorted(RADAR_DIR.glob("*.py"))

# Also include apps_script/Code.gs if exists
gs_file = RADAR_DIR / "apps_script" / "Code.gs"
files_to_include = []
for f in py_files:
    files_to_include.append((f, f.name))
if gs_file.exists():
    files_to_include.append((gs_file, "apps_script/Code.gs"))

# Build the bundle
parts = [AUDIT_PROMPT]

for filepath, display_name in files_to_include:
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        content = f"[ERROR LECTURA: {e}]"

    line_count = content.count("\n") + 1
    parts.append(f"\n\n=== FILE: {display_name} ({line_count} líneas) ===\n\n```")
    parts.append(content)
    if not content.endswith("\n"):
        parts.append("\n")
    parts.append("```\n")

# Final marker
parts.append("\n\n=== FIN DEL CÓDIGO ===\n")
parts.append("\nGenerá ahora el reporte de auditoría completo según el formato especificado arriba.\n")

bundle = "".join(parts)

# Stats
total_lines = sum(len(f.read_text(encoding="utf-8").splitlines()) for f, _ in files_to_include)
total_chars = len(bundle)

OUTPUT.write_text(bundle, encoding="utf-8")

print(f"✓ Bundle generado: {OUTPUT}")
print(f"  Archivos incluidos: {len(files_to_include)}")
print(f"  Líneas de código: {total_lines}")
print(f"  Caracteres totales: {total_chars:,}")
print(f"  Tamaño archivo: {OUTPUT.stat().st_size:,} bytes")
