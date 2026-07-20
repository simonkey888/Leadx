# LeadX — canonical Workers-first deployment pipeline

## Authority order

1. Cloudflare Workers production is the operational deployment source.
2. The exact source tree and bundle are deployed from a clean working tree.
3. GitHub is reconciled afterward with the exact source SHA already deployed.
4. GitHub Actions validates reconciliation; it does not initiate the canonical production deploy.
5. The `CONTEXTO LEADX` headline tab in Drive is updated after every deploy, rollback, import or material change.

## Secret names

Values must never appear in code, logs, artifacts, pull requests, documentation or chat handoffs.

### GitHub repository secrets

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `DASHBOARD_PASSWORD`
- `INGEST_SECRET`
- `SESSION_SECRET`

### Names matched between GitHub and the Cloudflare deployment environment

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `DASHBOARD_PASSWORD`

### Cloudflare Worker runtime application secrets verified before deploy

- `DASHBOARD_PASSWORD`
- `INGEST_SECRET`
- `SESSION_SECRET`

Only names are documented. Values remain private.

## Canonical command

Run from a clean, committed checkout containing the exact release candidate:

```bash
bash scripts/deploy-workers-first.sh
```

The deployment environment must expose the three matched names:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
DASHBOARD_PASSWORD
```

Optional count overrides:

```text
EXPECTED_FOTOMULTAS_COUNT
EXPECTED_AGRO_COUNT
```

Defaults are `9` and `40`.

## Blocking sequence

The script stops before production on any failure in:

1. required command and environment-name checks;
2. clean Git working tree and valid source SHA;
3. `npm ci`;
4. frontend build;
5. complete test suite;
6. TypeScript typecheck;
7. Cloudflare authentication;
8. Worker runtime secret-name inventory;
9. previous deployment/version capture;
10. Wrangler dry-run and deterministic bundle hash.

It then performs exactly one production deployment.

## Post-deploy gates

The new version must:

- be the only active version;
- receive exactly 100% of traffic;
- return a valid `/api/health`;
- keep anonymous sessions in demo;
- accept authenticated login;
- preserve the expected real counts for both verticals;
- keep IDs unique and verticals isolated;
- complete logout back to demo;
- pass the existing desktop/mobile production browser smoke.

Any blocking failure after deployment triggers an immediate rollback to the previously captured version. Rollback is verified by version ID and health.

## Evidence

The script writes redacted evidence under:

```text
artifacts/workers-first/<UTC_RUN_ID>/
```

The final `summary.txt` records:

- exact source SHA;
- deterministic bundle SHA-256;
- previous and new deployment IDs;
- previous and new version IDs;
- 100% traffic;
- HTTP/authenticated/browser gate results;
- rollback state;
- mandatory GitHub reconciliation state.

Private lead payloads, cookies and login responses are deleted. Evidence is scanned for secret values and private-contact fields.

## Data imports are a separate operation

A code deployment must never be used as a substitute for a lead import, and a lead import must never trigger a Worker deployment.

The only canonical manual lead-import procedure is:

```text
docs/MANUAL_BACKEND_LEAD_IMPORT.md
scripts/validate-lead-import-payload.sh
```

The payload stays local and outside Git. The operator performs a mandatory local validation and authenticated production readback before the single manual `POST /api/admin/import`.

GitHub Actions, artifacts, blobs, Drive and Deepnote are not private-data transport channels for this operation.

## GitHub reconciliation

Only after the Workers deployment succeeds:

1. commit and push the exact source tree that produced `SOURCE_SHA`;
2. ensure `main` resolves to that exact SHA;
3. run `LeadX Workers-first Reconciliation`;
4. provide:
   - `target_sha`;
   - `expected_version_id`;
   - `expected_deployment_id`;
   - `expected_bundle_sha256`;
5. require the workflow to finish `success`;
6. update `CONTEXTO LEADX` in Drive with the final IDs, SHA, artifact and rollback state.

Do not modify source between the successful Workers deployment and GitHub reconciliation. If the source changes, it is a new release candidate and must be deployed again from step 1.

## Disabled legacy paths

The former automatic GitHub-originated workflows are guards only:

- `.github/workflows/deploy-once.yml`
- `.github/workflows/deploy-containment.yml`

They intentionally do not deploy. The canonical production path is `scripts/deploy-workers-first.sh`.
