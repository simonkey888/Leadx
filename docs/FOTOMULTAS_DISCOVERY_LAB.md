# Fotomultas Discovery Lab V1 — diseño operativo

## Objetivo

Preparar un proceso autónomo y continuo, exclusivamente para `fotomultas`, que busque candidatos públicos y produzca candidatos verificados cuya deuda nacional activa acumulada sea igual o superior a ARS 1.000.000.

Este bloque no despliega, no consulta producción, no lee ni escribe KV y no interactúa con la vertical `repuestos_agricolas`.

## Arquitectura

```text
radar público existente en sandbox temporal
        ↓
sanitización: sólo fotomultas, sin patente ni texto crudo
        ↓
contact gate: email, teléfono o WhatsApp público
        ↓
entity fingerprint + deduplicación
        ↓
PENDING_VERIFICATION
        ↓
registro autorizado de consulta SINAI
        ↓
deduplicación de infracciones
        ↓
exclusión de pagadas, anuladas y canceladas
        ↓
suma de infracciones activas
        ↓
ELIGIBLE_VERIFIED si total >= ARS 1.000.000
        ↓
artefacto privado / cola de revisión
```

## Descubrimiento público

El runner `labs/fotomultas_discovery/discovery.py` reutiliza `generate_payload.py` sin ejecutar el workflow legacy.

Controles:

- requiere `--allow-public-network`;
- se ejecuta en un directorio temporal;
- elimina `INGEST_SECRET`, `WORKER_URL`, credenciales Cloudflare, contraseña y secreto de sesión;
- no hereda variables de entorno desconocidas;
- descarta cualquier registro que no sea `fotomultas`;
- no exporta patente, texto crudo ni deuda de fuentes no oficiales;
- usa lock exclusivo para evitar dos ejecuciones simultáneas;
- elimina el sandbox al finalizar;
- sólo escribe un archivo privado mediante reemplazo atómico.

Puede ejecutarse una vez o en modo `--watch`. Un fallo no modifica la última salida válida.

## Decisión sobre repositorios externos

### GoogleScraper

No se integra. El radar actual ya contiene proveedores de búsqueda y normalización. Incorporar una librería histórica duplicaría responsabilidad y aumentaría fragilidad.

### OpenPlanter

No se incorpora como dependencia ni como agente con shell. Se adopta únicamente el patrón conceptual de:

```text
fuente → entidad → relación → evidencia → decisión
```

La ejecución de subagentes, shell y persistencia generalista es innecesaria y demasiado amplia para este bloque.

### IntelX

No se integra en V1. Una futura fuente `public-only` tendría que estar restringida a Web Public, Documents Public, Whois y DNS; nunca Leaks, Darknet, Pastes, Dumpster o material sin base legítima. No se acepta ninguna clave en GitHub.

## Fuente oficial

La fuente primaria prevista es:

`https://consultainfracciones.seguridadvial.gob.ar/`

El portal permite búsqueda por documento o dominio y publica condiciones que limitan la utilización de los datos a la finalidad que motivó su obtención. Por eso V1 no automatiza consultas masivas ni incorpora un browser contra SINAI.

El pipeline consume un registro de verificación que debe contener:

- proveedor `sinai_official`;
- URL oficial;
- base de autorización documentada;
- fecha de consulta;
- hash opaco del sujeto consultado;
- resultado completo;
- infracciones con estado e importe;
- ningún DNI, sexo, dominio o patente en claro.

## Contrato de candidato

Campos mínimos:

```json
{
  "id": "opaque-id",
  "vertical": "fotomultas",
  "entity_name": "Entidad",
  "source_url": "https://fuente-publica.example/caso",
  "contact_public": true,
  "email_publico": "contacto@example.com",
  "telefono_publico": "+54..."
}
```

Un teléfono o email sin `contact_public=true` y sin `source_url` HTTPS no pasa el gate.

## Contrato de verificación

```json
{
  "candidate_id": "opaque-id",
  "provider": "sinai_official",
  "source_url": "https://consultainfracciones.seguridadvial.gob.ar/",
  "authorization_basis": "client_authorized",
  "subject_ref_hash": "sha256-opaco",
  "checked_at": "ISO-8601",
  "result_complete": true,
  "infractions": [
    {
      "id": "opaque-infraction-id",
      "status": "Vigente",
      "amount_ars": 350000
    }
  ]
}
```

## Regla económica

```text
ACTIVE_NATIONAL_DEBT_TOTAL_ARS = suma de infracciones activas únicas
ELIGIBLE = ACTIVE_NATIONAL_DEBT_TOTAL_ARS >= 1_000_000
```

Varias infracciones pueden completar el umbral. Las pagadas, anuladas, canceladas, prescritas o sin deuda se excluyen. Un estado desconocido bloquea el candidato.

## Worker de segundo plano

El worker usa directorios privados:

- `inbox`: jobs nuevos;
- `outbox`: resultados;
- `processed`: jobs terminados;
- `dead-letter`: jobs inválidos.

El procesamiento es atómico. Un archivo pasa a `.processing` antes de ser leído. Los fallos se mueven a dead-letter y no se reintentan automáticamente.

## Estados

- `PENDING_VERIFICATION`: contacto público válido, falta verificación oficial;
- `ELIGIBLE_VERIFIED`: contacto válido, SINAI autorizado, resultado completo y deuda acumulada suficiente;
- `REJECTED`: cualquier gate fail-closed.

## Integración futura con LeadX

No existe en este bloque. Cuando sea autorizada deberá cumplir:

```text
mode=upsert_vertical
vertical=fotomultas
source SHA exacto
idempotencia por ID
sin identificadores oficiales crudos
sin acceso a repuestos_agricolas
```

El import sólo podrá diseñarse después de que el contrato seguro de PR #19 esté validado y activo mediante el flujo Cloudflare-first.

## Estado actual

```text
IMPLEMENTATION=LAB_ONLY
PUBLIC_DISCOVERY=EXISTING_RADAR_SANDBOXED_OPT_IN
LIVE_SINAI_PROVIDER=NOT_INCLUDED
SYNTHETIC_TESTS=REQUIRED
DEPLOY=NO
MERGE=NO
PRODUCTION=UNTOUCHED
```
