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
2. Borra del entorno credenciales operativas de LeadX y Cloudflare.
3. Conserva sólo candidatos `fotomultas`; descarta Repuestos agrícolas, patente, texto crudo y deuda de fuentes no oficiales.
4. Exige teléfono, WhatsApp o email explícitamente público y con URL de procedencia.
5. Deduplica candidatos por identidad y contacto.
6. Consume una constancia de verificación oficial previamente autorizada.
7. Acepta únicamente `sinai_official` con fuente `https://consultainfracciones.seguridadvial.gob.ar/`.
8. Ignora infracciones pagadas o anuladas, elimina duplicados y suma las activas.
9. Rechaza estados ambiguos, verificaciones vencidas, identificadores crudos y deuda inferior a ARS 1.000.000.
10. Emite `ELIGIBLE_VERIFIED`, `PENDING_VERIFICATION` o `REJECTED` en un artefacto privado.

## Qué no hace

- no consulta SINAI en vivo;
- no automatiza búsquedas por documento, sexo o dominio;
- no guarda documento, dominio o patente en el artefacto;
- no publica contactos o resultados reales en GitHub;
- no llama endpoints de escritura de LeadX;
- no modifica el CRM;
- no ejecuta cron, deploy o promoción.

La consulta oficial informa que los datos no deben utilizarse para finalidades distintas de las que motivaron su obtención. Por eso el adaptador en vivo queda deliberadamente fuera de V1: cualquier futura implementación debe acreditar autorización, límites de frecuencia, trazabilidad y compatibilidad con las condiciones vigentes.

## Descubrimiento público aislado

`generate_payload.py` ya contiene proveedores públicos. El runner lo ejecuta desde un directorio temporal, sin credenciales operativas y sin usar el workflow legacy que también hace commit e ingest.

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

## Supervisor autónomo completo

El supervisor completa descubrimiento y evaluación antes de publicar. Cada archivo se reemplaza de forma atómica y ambos llevan el mismo `cycle_id`; cualquier consumidor debe rechazar un par desfasado.

```bash
python -m labs.fotomultas_discovery.orchestrator \
  --repo-root /ruta/al/repo \
  --candidates-output /ruta/privada/candidates-latest.json \
  --decisions-output /ruta/privada/fotomultas-decisions.json \
  --verifications /ruta/privada/verifications.json \
  --allow-public-network \
  --watch \
  --interval-minutes 180
```

La ausencia del archivo de verificaciones no detiene el ciclo: los contactos válidos quedan en `PENDING_VERIFICATION`. El supervisor nunca clasifica un candidato como verificado sin constancia oficial válida.

## Contenedor OCI genérico

La imagen no está acoplada a Oracle ni a Northflank. Se construye desde la raíz del repositorio:

```bash
docker build \
  -f labs/fotomultas_discovery/container/Dockerfile \
  -t leadx-fotomultas-discovery-lab:local \
  .
```

El contenedor:

- corre como UID/GID `10001:10001`;
- mantiene `/app` sin permisos de escritura;
- usa `/state` como único volumen persistente;
- no arranca salvo que `LEADX_DISCOVERY_PUBLIC_NETWORK=1`;
- no contiene contactos ni verificaciones reales en la imagen;
- incluye healthcheck por frescura y coincidencia de `cycle_id`;
- no contiene integración con LeadX, Cloudflare o SINAI en vivo.

Ejemplo de ejecución local no productiva:

```bash
docker run --rm \
  --name leadx-fotomultas-discovery-lab \
  -e LEADX_DISCOVERY_PUBLIC_NETWORK=1 \
  -e LEADX_INTERVAL_MINUTES=180 \
  -v /ruta/privada/leadx-fotomultas:/state \
  leadx-fotomultas-discovery-lab:local
```

El volumen puede contener opcionalmente `/state/verifications.json`. Los resultados quedan en:

```text
/state/candidates-latest.json
/state/fotomultas-decisions.json
```

Variables admitidas:

```text
LEADX_DISCOVERY_PUBLIC_NETWORK=1
LEADX_INTERVAL_MINUTES=180
LEADX_TIMEOUT_SECONDS=260
LEADX_MAX_HEALTH_AGE_MINUTES=240
LEADX_RUN_ONCE=0|1
LEADX_STATE_DIR=/state
```

No pasar credenciales de LeadX, Cloudflare ni SINAI al contenedor.

## Evaluación de candidatos

Para evaluar archivos existentes sin ejecutar descubrimiento:

```bash
python -m labs.fotomultas_discovery.cli \
  --candidates /ruta/privada/candidates-latest.json \
  --verifications /ruta/privada/verifications.json \
  --output /ruta/privada/fotomultas-decisions.json
```

Las rutas de candidatos, verificaciones y salida deben permanecer fuera del repositorio.

## Worker continuo de jobs

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

Validar la imagen y preparar una configuración no productiva para el proveedor elegido. Iniciar infraestructura externa, conectar SINAI en vivo o integrar LeadX queda bloqueado hasta la autorización correspondiente.
