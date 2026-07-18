# LeadX API inventory

Validated branch: `feat/leadx-multi-linea-comercial-v1`.

LeadX retains one contained Worker surface. Multi-line support extends the lead domain without adding providers, scraping, automation, enrichment or arbitrary storage access.

Classification:

- `PUBLIC`: intentionally anonymous and limited to synthetic/demo data.
- `SESSION_AUTH`: requires a valid signed dashboard session.
- `INGEST_SECRET`: machine-to-machine ingestion only.
- `REMOVE`: obsolete, experimental, unsafe or without a maintained legitimate consumer.

## Supported verticals

Only these values are accepted:

- `fotomultas`
- `repuestos_agricolas`

A stored or ingested record with no `vertical` is treated as `fotomultas` for backward compatibility. An explicitly supplied unsupported value is rejected. Fields shared by both lines remain at the lead root; line-specific fields remain inside `vertical_data`.

## Dependency summary

| Consumer | Required routes |
|---|---|
| React SPA | `/api/auth/login`, `/api/auth/session`, `/api/auth/activity`, `/api/auth/logout`, `/api/leads`, `/api/metrics` |
| Hunter / approved ingestion | `/api/ingest` only |
| Anonymous smoke / uptime | `/api/health`, `/api/auth/session`, `/api/leads`, `/api/metrics`, `/` |
| Private operation | Auth/session routes plus authenticated `/api/leads` and `/api/metrics` |

## Retained endpoints

| Method | Path | Authentication | Contract |
|---|---|---|---|
| POST | `/api/auth/login` | Rate limiter + `DASHBOARD_PASSWORD` | Issues a signed, hardened session cookie. Fails closed if required bindings are absent. |
| GET | `/api/auth/session` | Optional signed cookie | Returns only authentication/session state and does not renew polling activity. |
| POST | `/api/auth/activity` | Signed cookie + explicit activity header | Renews idle activity, preserves absolute expiry and rotates the nonce. |
| POST | `/api/auth/logout` | Optional signed cookie | Idempotently revokes the browser session. |
| GET | `/api/leads?vertical=fotomultas` | Optional signed cookie | Anonymous: 12 synthetic Fotomultas records without KV access. Authenticated: only Fotomultas records. |
| GET | `/api/leads?vertical=repuestos_agricolas` | Optional signed cookie | Anonymous: 12 synthetic Repuestos agrícolas records without KV access. Authenticated: only agricultural records. |
| GET | `/api/leads` | Optional signed cookie | Anonymous compatibility response: 12 Fotomultas demos. Authenticated compatibility response: all stored records, with missing vertical migrated to Fotomultas. |
| GET | `/api/metrics?vertical=<allowed>` | Optional signed cookie | Returns metrics calculated only from the selected vertical. |
| GET | `/api/metrics` | Optional signed cookie | Safe compatibility response; anonymous metrics remain fixed demo metrics. |
| POST | `/api/ingest` | `INGEST_SECRET` | Validates the bounded JSON payload, defaults missing vertical to Fotomultas, rejects invalid verticals and preserves CRM state. |
| GET | `/api/health` | None | Sanitized health only; no KV access or private counters. |

All private responses are `no-store, private` and vary on `Cookie`. Anonymous API responses are `no-store`. The React client does not persist real leads or CRM state in browser storage.

## Removed surface

The following remain hard-removed and return runtime `404`: generic KV routes, cookie collection, Reddit/Facebook/Apify scraping, WhatsApp validators/webhooks, plate/VLM analysis, forensic writes, enrichment, cron execution and shadow-OSINT routes. `DASHBOARD_HTML`, `COOKIES_HTML` and scheduled Worker execution are not part of the approved runtime.

## Production rule

`.github/workflows/deploy-containment.yml` accepts one mandatory `target_sha`. It may deploy only when that SHA is the exact current HEAD of `main`, all tests pass, Cloudflare access and required secret names exist, and the previous deployment/version have been recorded for rollback.
