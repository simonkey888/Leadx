# LeadX — importación manual de leads a través del backend

## Autoridad operativa

Éste es el único procedimiento canónico para futuras importaciones manuales de leads privados en LeadX.

La importación se hace directamente desde una estación operativa controlada hacia el backend productivo de LeadX. Se usa una sesión autenticada y el endpoint `POST /api/admin/import`.

No se utiliza ningún servicio intermedio.

## Prohibiciones absolutas

El payload privado no debe:

- entrar al repositorio Git;
- subirse a GitHub Actions;
- viajar por comentarios de PR, issues, artifacts, releases o caches;
- codificarse como blob o Base64 para transportarlo;
- subirse a Google Drive, Deepnote, Colab, notebooks remotos, Slack o servicios equivalentes;
- aparecer en logs, screenshots, documentación, handoffs o evidencias;
- quedar guardado dentro de `artifacts/`.

Deepnote no forma parte de esta operatoria.

El archivo JSON permanece local, fuera del repositorio, con permisos restringidos. No se crean blobs, artifacts ni canales cifrados temporales en GitHub.

## Separación de responsabilidades

- Deploy de código: `bash scripts/deploy-workers-first.sh`.
- Importación de leads: este procedimiento manual por backend.
- Un deploy nunca debe importar leads.
- Una importación nunca debe desplegar ni modificar el Worker.
- El rollback de código de Cloudflare no revierte datos guardados en KV.

## Contrato obligatorio del payload

El archivo debe ser JSON válido y cumplir esta forma:

```json
{
  "mode": "upsert_vertical",
  "vertical": "fotomultas o repuestos_agricolas",
  "leads_all": []
}
```

Controles bloqueantes:

- `mode` debe ser exactamente `upsert_vertical`;
- la vertical debe ser `fotomultas` o `repuestos_agricolas`;
- debe haber entre 1 y 500 leads;
- el archivo no puede superar 2 MiB;
- todos los IDs deben ser strings no vacíos;
- todos los IDs deben ser únicos dentro del payload;
- todos los leads deben pertenecer a la vertical declarada;
- no se admiten registros demo;
- el archivo debe estar fuera del repositorio;
- no se admite un symlink como payload.

La validación local canónica es:

```bash
bash scripts/validate-lead-import-payload.sh /ruta/absoluta/fuera-del-repo/leads-privados.json
```

Debe terminar con `PAYLOAD_VALIDATION=PASS` y mostrar únicamente conteos y hashes.

## Semántica real del backend

`upsert_vertical` no reemplaza ciegamente toda la base.

Para cada ID importado:

- inserta el lead si el ID no existía;
- actualiza el lead si el ID ya existía;
- preserva el estado CRM existente de ese ID;
- conserva los IDs no incluidos en el payload;
- conserva la otra vertical.

El conjunto final esperado de la vertical objetivo es la unión entre los IDs actuales de esa vertical y los IDs del payload.

Un ID del payload que coincida con un ID de la otra vertical es bloqueante. No se importa hasta demostrar `CROSS_VERTICAL_ID_OVERLAP=0`.

## Operatoria obligatoria

### 1. Preparar un directorio temporal local

Usar un directorio temporal fuera del repositorio, con permisos privados. El payload nunca se copia al checkout.

```bash
umask 077
WORK_DIR="$(mktemp -d)"
COOKIE_JAR="$WORK_DIR/session.cookies"
```

Registrar un `trap` para borrar el directorio al salir.

### 2. Validar el payload local

Ejecutar el validador canónico y guardar sólo estos controles:

- vertical objetivo;
- cantidad del payload;
- SHA-256 del archivo;
- SHA-256 del conjunto ordenado de IDs.

No imprimir ni guardar nombres, teléfonos, emails, textos o el contenido del JSON.

### 3. Iniciar sesión contra el backend

La contraseña se obtiene del gestor de secretos autorizado y se mantiene sólo en memoria. Nunca se escribe en un archivo, argumento persistente, documentación o historial.

La autenticación se realiza contra:

```text
POST /api/auth/login
```

La respuesta debe ser HTTP 200 y `ok=true`. La cookie se guarda exclusivamente en el directorio temporal.

Verificar inmediatamente:

```text
GET /api/auth/session
```

La sesión debe devolver `authenticated=true` y `mode=real`.

### 4. Readback obligatorio antes de escribir

Leer las dos verticales con la misma cookie:

```text
GET /api/leads?vertical=fotomultas
GET /api/leads?vertical=repuestos_agricolas
```

Calcular y congelar:

- conteo de la vertical objetivo;
- hash del conjunto de IDs de la vertical objetivo;
- conteo de la vertical preservada;
- hash del conjunto de IDs de la vertical preservada;
- unión esperada entre IDs actuales de la vertical objetivo e IDs del payload;
- conteo final esperado;
- hash final esperado;
- solapamiento entre payload y vertical preservada.

La escritura queda prohibida salvo que:

```text
SESSION_REAL=PASS
PAYLOAD_VALIDATION=PASS
UNIQUE_IDS=PASS
VERTICAL_CONTAINMENT=PASS
CROSS_VERTICAL_ID_OVERLAP=0
```

### 5. Confirmación humana exacta

Antes del POST deben quedar confirmados explícitamente:

- archivo y SHA-256 correctos;
- vertical correcta;
- conteo del payload;
- conteos productivos previos;
- hash de la vertical preservada;
- conteo final esperado;
- hash final esperado.

Si cambió cualquier control desde el readback, abortar y repetir desde el paso 2. No reutilizar controles viejos.

### 6. Ejecutar una sola escritura

La única escritura autorizada es:

```text
POST /api/admin/import
Content-Type: application/json
Cookie: sesión autenticada temporal
Body: archivo local validado
```

No usar `/api/ingest` para esta operatoria manual. No usar `replace_all`. No ejecutar un segundo POST automáticamente.

La respuesta debe ser HTTP 200 y cumplir:

```text
status=ok
mode=upsert_vertical
vertical=<vertical confirmada>
imported=<cantidad del payload>
inserted+updated=imported
```

### 7. Verificación posterior inmediata

Volver a leer las dos verticales y exigir:

- conjunto final de IDs igual a la unión calculada antes del POST;
- cantidad final exacta;
- IDs únicos;
- todos los registros en su vertical correcta;
- vertical preservada con el mismo conteo y el mismo hash de IDs;
- cero solapamiento entre verticales;
- total general coherente.

El éxito requiere:

```text
IMPORT_STATUS=PASS
TARGET_FINAL_COUNT=EXPECTED
TARGET_FINAL_ID_SET_SHA256=EXPECTED
PRESERVED_COUNT=UNCHANGED
PRESERVED_ID_SET_SHA256=UNCHANGED
VERTICAL_CONTAINMENT=PASS
CROSS_VERTICAL_ID_OVERLAP=0
```

### 8. Logout y limpieza

Ejecutar:

```text
POST /api/auth/logout
GET /api/auth/session
```

La sesión final debe devolver `authenticated=false` y `mode=demo`.

Eliminar el directorio temporal, cookie jar y respuestas locales. No subir evidencia privada a ninguna plataforma.

## Manejo de errores

Antes del POST, cualquier error aborta sin modificar producción.

Después de iniciado el POST, cualquier falla de red o verificación implica:

```text
IMPORT_STATE=INDETERMINATE
ACTION=STOP_DO_NOT_RETRY
NEXT=RUN_READ_ONLY_PRODUCTION_VERIFICATION
```

En ese estado:

- no repetir la importación;
- no enviar un segundo payload;
- no intentar corregir datos a ciegas;
- ejecutar primero una verificación productiva de sólo lectura;
- comparar conteos e ID hashes con los controles congelados;
- decidir una corrección sólo con el estado real confirmado.

## Evidencia permitida

Sólo pueden registrarse:

- fecha y hora;
- vertical;
- conteos;
- hashes SHA-256;
- resultado PASS/FAIL;
- estado de sesión y logout;
- confirmación de que no se generaron artifacts privados.

Nunca deben registrarse nombres, teléfonos, emails, textos de leads, cookies, contraseña ni contenido del payload.

## Cierre obligatorio

Después de cada importación material:

1. verificar producción en modo real y demo;
2. actualizar GitHub únicamente con documentación o código no privado;
3. actualizar `CONTEXTO LEADX` en Drive con conteos, hashes, resultado y método;
4. confirmar expresamente:

```text
IMPORT_METHOD=manual_authenticated_backend
DEEPNOTE_USED=NO
BLOB_OR_ARTIFACT_CHANNEL_USED=NO
PRIVATE_PAYLOAD_PUBLISHED=NO
PERMANENT_PRIVATE_ARTIFACTS_CREATED=NO
```
