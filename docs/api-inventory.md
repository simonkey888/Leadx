# LeadX API inventory

Validated baseline: `main@91672001c893815a1f31f9cfdd11b31a18a6968a`.

LeadX retains one contained Worker surface. Multi-line support extends the lead domain without adding arbitrary storage access.

Classification:

- `PUBLIC`: intentionally anonymous and limited to synthetic/demo data.
- `SESSION_AUTH`: requires a valid signed dashboard session.
- `INGEST_SECRET`: machine-to-machine ingestion only.
- `REMOVE`: obsolete, experimental, unsafe or without a maintained legitimate consumer.

## Supported verticals

Only these values are accepted:

- `fotomultas`
- `repuestos_agricolas`

Stored legacy records with no `vertical` are treated as `fotomultas` for backward compatibility. Every new ingest or manual import must provide an explicit allowed vertical. Fields shared by both lines remain at the lead root; line-specific fields remain inside `vertical_data`.

## Import-mode policy

`replace_all` is not an accepted runtime mode.

Both retained write endpoints require exactly:

```text
mode=upsert_vertical
```

Additional containment:

- `/api/ingest` is limited by the server to `vertical=fotomultas`;
- `/api/admin/import` accepts either supported vertical through an authenticated session;
- every lead must match the declared vertical;
- duplicate IDs inside one payload are rejected;
- an incoming ID that already belongs to the other vertical returns `409 cross_vertical_id_conflict` before any KV write;
- matching IDs preserve existing CRM fields;
- records outside the imported vertical are preserved;
- deletion and stale-record pruning are not implicit ingest behavior.

A future full-snapshot operation must use a separately designed `replace_vertical` contract. Global replacement of `leads:live` is forbidden.

## Dependency summary

| Consumer | Required routes |
|---|---|
| React SPA | `/api/auth/login`, `/api/auth/session`, `/api/auth/activity`, `/api/auth/logout`, `/api/leads`, `/api/metrics`, `/api/admin/import` |
| Radar / approved machine ingestion | `/api/ingest` only, with explicit Fotomultas vertical upsert |
| Anonymous smoke / uptime | `/api/health`, `/api/auth/session`, `/api/leads`, `/api/metrics`, `/` |
| Private operation | Auth/session routes plus authenticated `/api/leads`, `/api/metrics` and `/api/admin/import` |

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
| POST | `/api/ingest` | `INGEST_SECRET` | Requires `mode=upsert_vertical`, `vertical=fotomultas` and homogeneous lead verticals. Preserves Repuestos agrícolas and CRM state; rejects cross-vertical ID conflicts. |
| POST | `/api/admin/import` | Signed dashboard session + explicit activity header | Requires `mode=upsert_vertical` for one supported vertical. Preserves the other vertical and existing CRM fields; rejects cross-vertical ID conflicts and returns counters only. |
| GET | `/api/health` | None | Sanitized liveness response; readiness redesign is tracked separately and is not implemented by this ingest-safety change. |

All private responses are `no-store, private` and vary on `Cookie`. Anonymous API responses are `no-store`. The React client does not persist real leads or CRM state in browser storage.

## Removed surface

The following routes remain hard-removed and return runtime `404` without reaching assets or storage:

- `/api/kv`
- `/api/ml-questions`
- `/api/reddit-bio`
- `/api/ddg-foromoto`
- `/api/clasificar-webhook`
- `/api/clasificar-patente`
- `/api/clasificar-basic`
- `/api/apify-facebook`
- `/cookies`
- `/cookies.html`
- `/api/cookies`
- `/api/whatsapp-validate`
- `/api/whatsapp-webhook`
- `/api/apify-webhook`
- `/api/enrich-patente`
- `/api/analyze-acta`
- `/api/forensic-case`
- `/api/cron-run`
- `/api/enrich-all`
- `/api/reddit-profile-links`
- `/api/shadow-osint`
- `/api/ventafe-debug`

`DASHBOARD_HTML`, `COOKIES_HTML` and scheduled Worker execution are not part of the approved runtime.

## Production rule

Code changes are deployed only through the canonical Workers-first operator path documented in `docs/WORKERS_FIRST_DEPLOYMENT.md`. The GitHub legacy deploy workflows remain disabled guards. No ingest or import operation may trigger a Worker deploy, and no code rollback reverts KV data.
