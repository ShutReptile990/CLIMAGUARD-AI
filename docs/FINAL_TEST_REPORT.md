# CLIMAGUARD AI — final readiness evidence

> **Dated local acceptance snapshot.** Later PostGIS infrastructure import, real simulated Nugen guidance and the extreme-rainfall map are documented in [PROJECT_STATUS.md](PROJECT_STATUS.md). This report does not establish a public hosted deployment.

Checked 2 November 2026 in the existing local workspace. **Deployment status: prepared, not hosted.** PASS means an actual check succeeded; PARTIAL identifies a verified subset; BLOCKED means the required account, session or dataset was unavailable. No localhost URL is a production URL.

## Acceptance results

| Area | Result | Evidence and limit |
| --- | --- | --- |
| Backend unit and API regression suite | PASS | `backend/.venv/Scripts/python.exe -m pytest app/tests -q`: 69 passed after the citizen alerts and Pune-wide filtering changes. Final rerun result is recorded below. |
| Frontend TypeScript and production bundle | PASS | `npm run build` runs `tsc -b` and Vite. Final rerun result is recorded below. |
| Dependency check | PASS | `npm audit --omit=dev --audit-level=high`: zero reported production vulnerabilities at check time. |
| Local frontend route refreshes | PASS | Vite production preview returned HTTP 200 for `/`, `/citizen`, `/citizen/map`, `/authority/incidents`, and `/reset-password`. This checks SPA routing, not signed-in browser behavior. |
| Health and public data API | PASS | FastAPI ASGI smoke returned 200 for health, nine GeoJSON analysis cells, B2 environment, B2 analysis, exposure, map infrastructure/roads and Nugen status. |
| Weather, archive and air quality | PASS | Live Open-Meteo Forecast, Historical Archive and Air Quality/CAMS responses. B2 weather valid at `2026-11-01T18:45:00+05:30`, air quality at `2026-11-01T18:30:00+05:30`; current units include °C, %, mm, US AQI and µg/m³. Forecast contained 264 hourly entries at the check. Normal selected-observation persistence reported `stored`. These are provider data and timestamps, not on-site sensor measurements. |
| Geographic coverage | PARTIAL | Nine of nine cells have source-backed WorldPop population, Copernicus slope and mapped-drain distance. PostGIS has 213 OSM waterways. `osm_import_runs=0` and no cell has database-backed facility imports; facility and road map endpoints serve the validated local GeoJSON preview. No verified hazard footprint exists for population exposure, so that estimate is unavailable. |
| Flood prediction | PARTIAL | Deterministic heuristic flood index and rule explanation operate on available features. Verified flood-event labels, held-out evaluation, calibrated probability, and SHAP model explanation remain unavailable. No XGBoost accuracy is claimed. |
| Heat and air screening | PASS | B2 analysis returned available rule-based heat and US AQI classifications. These are screenings, not official heatwave alerts or Indian AQI. |
| Nugen citizen inference | PASS | Real aligned-model request through FastAPI returned HTTP 200, three validated actions and source hazards flood/heat/air quality. An unapproved Supabase recommendation draft insert returned HTTP 201. Model ID `model_01m66gqc3qk10zdy`; no fallback provider was used. |
| Citizen report and authority review | PASS | Migration 009 was confirmed applied by the owner. The owner used the authority UI on an explicitly TEST-labeled report. Supabase readback verified `submitted → under_review → resolved`, two status audit entries, a reviewer timestamp and an authority-role reviewer. The browser screen and HTTP status were user-reported rather than independently captured in this pass. The existing unlabeled incident was left untouched. |
| Single-authority alert approval and publication | PASS | Migration 010 is applied. A real Pune-wide official alert was published during this pass; the owner confirmed it was intentional. Supabase readback found one publication audit entry with the same actor as author and approver. The public API returned it for Pune overview and B2, and the citizen browser showed it on the Alerts page, homepage panel and detail route. No TEST alert was published by the agent. |
| Auth, CORS and security | PARTIAL | Backend tests cover unauthenticated and role-gated routes; live FastAPI returned 401 for unauthenticated `/api/v1/alerts/drafts`, and a preflight from `http://127.0.0.1:5173` returned 200 with that origin allowed. Private evidence bucket and audited authority assignments were confirmed previously. Deployed HTTPS origin, Supabase production redirects and hosted CORS need verification after deployment. Public Nugen generation has only local process caching; production abuse protection should be configured before an open public launch. |
| Deployment | BLOCKED | `render.yaml`, `frontend/vercel.json`, `.python-version` and [DEPLOYMENT.md](DEPLOYMENT.md) are ready. No Render/Vercel account connection or hosted URL was available. |
| Visual and mobile review | PARTIAL | The citizen browser showed the live alert on desktop homepage, Alerts page and details. At 1440 px the panel occupied the far-right column; at 390 px it stacked below the main content without horizontal overflow. An authenticated authority browser layout check remains unverified. |

## Checks and commands

From `backend`: `\.venv\Scripts\python.exe -m pytest -q`, `\.venv\Scripts\python.exe -m compileall -q app scripts`, `\.venv\Scripts\python.exe scripts/smoke_readiness.py`, `\.venv\Scripts\python.exe scripts/check_geographic_coverage.py`, and, only when inference credit use is intended, `\.venv\Scripts\python.exe scripts/smoke_nugen.py pune-grid-r2-c2`.

From `frontend`: `npm run build` and `npm audit --omit=dev --audit-level=high`.

The readiness script uses ASGI transport to exercise FastAPI directly; it does not test a hosted reverse proxy. The Nugen smoke command makes a real provider call and saves an unapproved draft. The geographic coverage script is read-only. The TEST incident inventory script is read-only and does not print report text.

## Remaining acceptance sequence

1. In a safe test context, publish an explicitly TEST-labeled advisory, then update and withdraw it. Read back the content-change and withdrawal audit entries, and confirm withdrawn/expired alerts remain hidden. Migration 010 has already been applied; do not replay it. The real official alert confirmed by the owner must remain published unless the authority decides otherwise.
2. **Completed after this dated report:** On 5 November 2026 the existing project imported 1,030 classified OSM facilities and 5,438 roads into PostGIS. Verify `storage=postgis` again on the deployed project; when it is unconfigured, identify any local preview explicitly.
3. Connect hosting accounts, set the variables in [DEPLOYMENT.md](DEPLOYMENT.md), deploy both services and repeat live data, auth, Nugen and browser checks at the actual HTTPS URLs. Record those URLs and outcomes here when they exist.

No verified flood labels, calibrated model or hazard footprint should be represented as complete during this sequence.

## Final local rerun

On 5 November 2026: backend **69 passed in 5.26 s** (`pytest app/tests -q`, with local loopback enabled because the Windows sandbox blocked asyncio socket-pair creation). Frontend `tsc -b && vite build` passed; Vite still reports a 500 kB chunk-size advisory. A read-only Supabase probe confirmed one published Pune-wide alert, a publication audit entry, and identical author/approver/publisher actor IDs. Live FastAPI public alert requests returned HTTP 200 and one published alert for both Pune overview and B2. Citizen browser checks confirmed page, sidebar and detail visibility without login. The owner confirmed the alert is real, not test data. Separate TEST-only update and withdrawal remain unverified. Earlier checks confirmed Render/Vercel config syntax, zero reported production npm vulnerabilities, and no tracked secret `.env` files.
