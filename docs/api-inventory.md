# LeadX API inventory

Branch baseline: `feat/leadx-cosmic-completion`.

This inventory was completed before removing `DASHBOARD_HTML` or reducing the Worker surface. Consumers were traced in the React SPA, `generate_payload.py`, `.github/workflows/radar-cron.yml`, the embedded legacy dashboard and operational comments in `worker.js`.

Classification:

- `PUBLIC`: intentionally anonymous and non-sensitive.
- `SESSION_AUTH`: requires a valid signed dashboard session.
- `INGEST_SECRET`: machine-to-machine ingestion only.
- `REMOVE`: obsolete, unsafe, experimental, duplicative or without a maintained legitimate consumer.

## Dependency summary

| Consumer | Required routes |
|---|---|
| React SPA | `/api/auth/login`, `/api/auth/session`, `/api/auth/activity`, `/api/auth/logout`, `/api/leads`, `/api/metrics` |
| Hunter / `radar-cron.yml` | `/api/ingest` only |
| Anonymous smoke / uptime | `/api/health`, `/api/auth/session`, `/api/leads`, `/api/metrics`, `/` |
| Private operation | Auth/session routes plus authenticated `/api/leads` and `/api/metrics` |
| Legacy embedded dashboard | Generic KV, scraping, cookies, WhatsApp validation, VLM, forensic and cron endpoints listed below; these are not used by the React SPA |

## Endpoint decisions

| Method | Path | Current authentication | Consumer | Data read / written | Class | Decision |
|---|---|---|---|---|---|---|
| POST | `/api/auth/login` | Rate limiter + `DASHBOARD_PASSWORD` | React SPA | No KV; issues signed cookie | `PUBLIC` | Keep. Fail closed if rate limiter or required secrets are absent. |
| GET | `/api/auth/session` | Optional signed cookie | React SPA | No KV; validates without renewal | `PUBLIC` | Keep. Anonymous output is limited to demo/auth state. |
| POST | `/api/auth/activity` | Signed cookie | React SPA | No KV; rotates nonce and renews idle time | `SESSION_AUTH` | Keep. Explicit user activity only. |
| POST | `/api/auth/logout` | Optional cookie | React SPA | No KV; expires cookie | `PUBLIC` | Keep as idempotent logout. |
| GET | `/api/leads` | Optional signed cookie | React SPA | Anonymous: fixed synthetic data. Authenticated: reads `leads:live` | `PUBLIC` / `SESSION_AUTH` | Keep. Anonymous branch must never read KV. |
| GET | `/api/metrics` | Optional signed cookie | React SPA | Anonymous: fixed demo metrics. Authenticated: reads `leads:live` | `PUBLIC` / `SESSION_AUTH` | Keep. Anonymous branch must never expose real metadata. |
| POST | `/api/ingest` | `INGEST_SECRET` header | Hunter / manual radar workflow | Reads prior `leads:live`; writes validated merged payload | `INGEST_SECRET` | Keep as the only machine ingestion surface. |
| GET | `/api/health` | None | Smoke / uptime | Previously read KV and exposed counts/timestamps/cron | `PUBLIC` | Keep, sanitize and prohibit KV access. |
| GET | `/api/kv` | `INGEST_SECRET` | Legacy dashboard/ad-hoc use | Arbitrary KV read | `REMOVE` | Remove. Generic key access bypasses domain authorization. |
| POST | `/api/kv` | `INGEST_SECRET` | Legacy dashboard/ad-hoc use | Arbitrary KV write | `REMOVE` | Remove. Generic mutation bypasses schemas and audit. |
| GET | `/api/ml-questions` | `INGEST_SECRET` | Experimental only | Calls MercadoLibre; returns contacts/debug | `REMOVE` | Remove. Collection belongs in Hunter providers, not the CRM Worker. |
| GET | `/api/reddit-bio` | `INGEST_SECRET` | Legacy dashboard | Scrapes Reddit and extracts contacts | `REMOVE` | Remove. No React consumer and outside the public-signal containment surface. |
| GET | `/api/ddg-foromoto` | `INGEST_SECRET` | Experimental only | Scrapes DuckDuckGo HTML and contacts | `REMOVE` | Remove. Fragile scraping and incidental data collection. |
| POST | `/api/clasificar-webhook` | `CLASIFICAR_WEBHOOK_SECRET` | Experimental external integration | Writes vehicle reports to KV | `REMOVE` | Remove. Undeclared integration and no maintained consumer. |
| GET | `/api/clasificar-webhook` | None | External probe | No store | `REMOVE` | Remove with integration. |
| POST | `/api/clasificar-patente` | `INGEST_SECRET` | Legacy/manual experiment | Calls external API; writes pending report | `REMOVE` | Remove pending a plate-data ADR and legitimate source. |
| GET | `/api/clasificar-patente` | `INGEST_SECRET` | Legacy/manual experiment | Reads plate report from KV | `REMOVE` | Remove with unsupported plate integration. |
| GET | `/api/clasificar-basic` | `INGEST_SECRET` | Experimental only | Calls external vehicle API | `REMOVE` | Remove pending source/legal review. |
| POST | `/api/apify-facebook` | `INGEST_SECRET` | Legacy operator flow | Reads Facebook cookies; starts scraper | `REMOVE` | Remove. Personal login-cookie scraping violates current Hunter policy. |
| GET | `/cookies`, `/cookies.html` | Secret in query string | Legacy cookie UI | Serves embedded cookie-entry UI | `REMOVE` | Remove. Query-string secrets and personal cookies are prohibited. |
| GET | `/api/cookies` | Secret header/query | Legacy cookie UI | Reads Facebook cookie metadata | `REMOVE` | Remove. |
| POST | `/api/cookies` | Secret header/query | Legacy cookie UI | Writes Facebook cookies | `REMOVE` | Remove. |
| POST | `/api/whatsapp-validate` | Secret header/query | Legacy dashboard | Starts external validator | `REMOVE` | Remove. Not a CRM Worker responsibility. |
| POST | `/api/whatsapp-webhook` | None | External webhook | Writes validation results to KV | `REMOVE` | Remove immediately: unauthenticated write. |
| POST | `/api/apify-webhook` | None | External webhook | Parses scraped posts; writes leads to KV | `REMOVE` | Remove immediately: unauthenticated write and duplicate ingestion path. |
| POST | `/api/enrich-patente` | `INGEST_SECRET` | Historical enrichment flow | Reads/writes `leads:live` | `REMOVE` | Remove. Future enrichment must enter through validated `/api/ingest`. |
| POST | `/api/analyze-acta` | `INGEST_SECRET` | Legacy dashboard | Reads/writes leads and forensic KV; calls VLM | `REMOVE` | Remove from containment release. |
| POST | `/api/forensic-case` | `INGEST_SECRET` | Legacy dashboard | Reads/writes plate, result and fee data | `REMOVE` | Remove. Uses machine credential for operator writes and lacks domain audit controls. |
| GET, POST | `/api/cron-run` | Secret header/query | Manual legacy operation | Invokes disabled Worker pipeline and reads KV | `REMOVE` | Remove. Hunter execution stays separate; no Worker cron. |
| GET, POST | `/api/enrich-all` | Secret header/query | Manual legacy operation | Scrapes profiles and mutates contacts in KV | `REMOVE` | Remove. Broad identity/contact enrichment is outside policy. |
| GET | `/api/reddit-profile-links` | `INGEST_SECRET` | Experimental only | Scrapes cross-platform links | `REMOVE` | Remove. No maintained product consumer. |
| GET | `/api/shadow-osint` | `INGEST_SECRET` | Experimental only | Probes usernames and extracts contacts | `REMOVE` | Remove. Cross-platform identity inference is outside scope. |
| GET | `/api/ventafe-debug` | Secret header/query | Debug only | Scrapes external HTML and returns contact previews | `REMOVE` | Remove. Debug endpoint and contact extraction do not belong in production. |

## Legacy dashboard dependency decision

`DASHBOARD_HTML` is not served by the approved routing path: `/`, `/index.html` and static assets are delegated to the `ASSETS` binding, and the final fallback also delegates to `ASSETS`. Its unique functions depend exclusively on endpoints classified `REMOVE`: generic KV access, profile/contact enrichment, cookie management, external validators, plate/VLM analysis, forensic writes and manual cron execution. The valid capabilities already migrated to React are demo/real modes, authentication, session handling, lead list, filters, detail and contact actions. Therefore no legitimate retained route depends on `DASHBOARD_HTML`; it may be deleted after regression tests assert that the React SPA is the only interface served.
