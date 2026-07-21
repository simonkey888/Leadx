# LeadX Fotomultas Discovery Lab V1

Laboratorio aislado para buscar candidatos públicos y transformarlos en candidatos de Fotomultas verificados, sin tocar producción.

## Invariantes

```text
TARGET_VERTICAL=fotomultas
REPUESTOS_AGRICOLAS_ACCESS=NO
PUBLIC_WEB_DISCOVERY=OPT_IN_SANDBOXED
PRODUCTION_ACCESS=NO
CLOUDFLARE_ACCESS=NO
KV_READ=NO
KV_WRITE=NO
LEADX_INGEST=NO
OUTPUT=LOCAL_ARTIFACT_OR_PRIVATE_QUEUE
DEBT_THRESHOLD_ARS=1000000
```

El umbral se aplica a la **suma de todas las infracciones activas y únicas**, no a una infracción individual.

## Qué hace

1. Puede ejecutar el radar existente en un sandbox temporal para descubrir fuentes públicas.
2. Borra del entorno `INGEST_SECRET`, `WORKER_URL`, credenciales Cloudflare y secretos de sesión.
3. Conserva sólo candidatos `fotomultas`; descarta Repuestos agrícolas, patente, texto crudo y deuda de fuentes no oficiales.
4. Exige teléfono, WhatsApp o email explícitamente público y con URL de procedencia.
5. Deduplica candidatos por identidad y contacto.
6. Consume una constancia de verificación oficial previamente autorizada.
7. Acepta únicamente `sinai_official` con fuente `https://consultainfracciones.seguridadvial.gob.ar/`.
8. Ignora infracciones pagadas o anuladas, elimina duplicados y suma las activas.
9. Rechaza estados ambiguos, verificaciones vencidas, identificadores crudos y deuda inferior a ARS 1.000.000.
10. Emite `ELIGIBLE_VERIFIED`, `PENDING_VERIFICATION` o `REJECTED` en un artefacto local.

## Qué no hace

- no consulta SINAI en vivo;
- no automatiza búsquedas por DNI, sexo o dominio;
- no guarda DNI, dominio o patente en el artefacto;
- no publica contactos o resultados reales en GitHub;
- no llama `/api/ingest` ni `/api/admin/import`;
- no modifica el CRM;
- no ejecuta cron, deploy o promoción.

La consulta oficial informa que los datos no deben utilizarse para finalidades distintas de las que motivaron su obtención. Por eso el adaptador en vivo queda deliberadamente fuera de V1: cualquier futura implementación debe acreditar autorización, límites de frecuencia, trazabilidad y compatibilidad con las condiciones vigentes.

## Descubrimiento público aislado

`generate_payload.py` ya contiene proveedores públicos. El runner lo ejecuta desde un directorio temporal, sin secretos operativos y sin usar el workflow legacy que también hace commit e ingest.

Ejecución única:

```bash
python -m labs.fotomultas_discovery.discovery \
  --repo-root /ruta/al/repo \
  --output /ruta/privada/candidates-latest.json \
  --allow-public-network
```

Ejecución continua cada tres horas:

```bash
python -m labs.fotomultas_discovery.discovery \
  --repo-root /ruta/al/repo \
  --output /ruta/privada/candidates-latest.json \
  --allow-public-network \
  --watch \
  --interval-minutes 180
```

Sin `--allow-public-network`, el runner termina bloqueado antes de ejecutar el radar. Un archivo `.lock` evita ejecuciones concurrentes. El directorio temporal se elimina al finalizar.

## Evaluación de candidatos

```bash
python -m labs.fotomultas_discovery.cli \
  --candidates /ruta/privada/candidates-latest.json \
  --verifications /ruta/privada/verifications.json \
  --output /ruta/privada/fotomultas-decisions.json
```

Las rutas de candidatos, verificaciones y salida deben permanecer fuera del repositorio.

## Worker continuo

El worker observa un inbox privado de archivos JSON. Cada job se procesa una sola vez. Un job inválido se mueve a dead-letter y no se reintenta ciegamente.

```bash
python -m labs.fotomultas_discovery.worker \
  --inbox /ruta/privada/inbox \
  --outbox /ruta/privada/outbox \
  --processed /ruta/privada/processed \
  --dead-letter /ruta/privada/dead-letter \
  --watch \
  --interval-seconds 30
```

Contrato de job:

```json
{
  "job_id": "opaque-job-id",
  "candidates": [],
  "verifications": []
}
```

## Próxima fase permitida

Ejecutar este runner en un contenedor no productivo y medir calidad de candidatos. La integración con SINAI en vivo, Cloudflare o LeadX queda bloqueada hasta una revisión específica y autorización de producción.
