# LeadX Fotomultas Discovery Lab V1

Laboratorio aislado para transformar candidatos públicos en candidatos de Fotomultas verificados, sin tocar producción.

## Invariantes

```text
TARGET_VERTICAL=fotomultas
REPUESTOS_AGRICOLAS_ACCESS=NO
NETWORK_ACCESS=NO
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

1. Consume candidatos producidos por una fuente pública o por el radar existente.
2. Exige teléfono, WhatsApp o email explícitamente público y con URL de procedencia.
3. Deduplica candidatos por identidad y contacto.
4. Consume una constancia de verificación oficial previamente autorizada.
5. Acepta únicamente `sinai_official` con fuente `https://consultainfracciones.seguridadvial.gob.ar/`.
6. Ignora infracciones pagadas o anuladas, elimina duplicados y suma las activas.
7. Rechaza estados ambiguos, verificaciones vencidas, identificadores crudos y deuda inferior a ARS 1.000.000.
8. Emite `ELIGIBLE_VERIFIED`, `PENDING_VERIFICATION` o `REJECTED` en un artefacto local.

## Qué no hace

- no consulta SINAI en vivo;
- no automatiza búsquedas por DNI, sexo o dominio;
- no guarda DNI, dominio o patente en el artefacto;
- no publica contactos o resultados reales en GitHub;
- no llama `/api/ingest` ni `/api/admin/import`;
- no modifica el CRM;
- no ejecuta cron, deploy o promoción.

La consulta oficial informa que los datos no deben utilizarse para finalidades distintas de las que motivaron su obtención. Por eso el adaptador en vivo queda deliberadamente fuera de V1: cualquier futura implementación debe acreditar autorización, límites de frecuencia, trazabilidad y compatibilidad con las condiciones vigentes.

## Integración con el radar actual

`generate_payload.py` ya realiza descubrimiento de fuentes públicas. El laboratorio puede consumir su `data/dashboard_payload.json` sin usar el workflow legacy que actualmente también hace commit e ingest.

```bash
python generate_payload.py
python -m labs.fotomultas_discovery.cli \
  --candidates data/dashboard_payload.json \
  --verifications /ruta/privada/verifications.json \
  --output /ruta/privada/fotomultas-decisions.json
```

La ruta de verificaciones y la salida deben permanecer fuera del repositorio.

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

Agregar adaptadores de descubrimiento desacoplados y ejecutarlos en un contenedor no productivo. La integración con SINAI en vivo, Cloudflare o LeadX queda bloqueada hasta una revisión específica y autorización de producción.
