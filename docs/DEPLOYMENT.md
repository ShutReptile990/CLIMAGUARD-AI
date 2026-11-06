# CLIMAGUARD AI deployment

**Status (1 November 2026): prepared locally, not deployed.** No Vercel or Render account connection or CLI session is available in this workspace. Do not present localhost as a public URL. The existing Supabase project and deployed Nugen model are reused.

## 1. Verify the database and repository

1. Use the existing Supabase project. Migrations 001–008 were previously verified; the project owner reports migrations 009 and 010 applied. A read-only probe confirmed migration 010's new column. Do not replay earlier migrations or reset data. The TEST incident review transitions were read back from Supabase; the alert self-approval still needs live verification.
2. Run from `backend`: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe scripts/check_phase6_schema.py`, `.venv/Scripts/python.exe scripts/check_geographic_coverage.py`, and `.venv/Scripts/python.exe scripts/smoke_readiness.py`.
3. Run from `frontend`: `npm ci` and `npm run build`.
4. Ensure only `.env.example` files are tracked. Do not push real `.env` files, access tokens, raw database exports or credentials. The model ID is a configuration value; the Nugen key stays on the backend.

## 2. Deploy the FastAPI backend on Render

Connect the repository to Render and create a Blueprint from [`render.yaml`](../render.yaml). Its root directory is `backend`; the build installs `requirements.txt`; the start command binds Uvicorn to `0.0.0.0:$PORT`; the health path is `/api/health`. [Render documents these Blueprint fields](https://render.com/docs/blueprint-spec) and [port binding](https://render.com/docs/web-services#port-binding). The repository's `.python-version` pins the tested Python 3.13 line; [Render documents version selection](https://render.com/docs/python-version).

Set the Blueprint's prompted environment variables in Render, never in source:

- `SUPABASE_URL`: existing Supabase project URL.
- `SUPABASE_PUBLISHABLE_KEY`: browser-safe publishable key used for user-scoped PostgREST calls.
- `SUPABASE_SECRET_KEY`: server-side secret/service-role credential; never expose in Vercel.
- `NUGEN_API_KEY`: deployed aligned-model API key; server-side only.
- `NUGEN_MODEL_ID`: `model_01m66gqc3qk10zdy` for the currently verified deployment, unless the model owner has explicitly replaced it.
- `CORS_ORIGINS`: exact HTTPS Vercel origin(s), comma-separated. Include only deployment origins that need browser access.

`APP_ENV=production` is in the Blueprint. The existing Nugen endpoint defaults to `https://api.nugen.in/api/v3/inference/chat/completions`; set `NUGEN_INFERENCE_URL` only if the deployed model's verified endpoint differs. `DATABASE_URL` is not required for normal API operation because the app uses Supabase REST, but direct raster/OSM import scripts may need it. `sync: false` prompts for values at initial Blueprint creation; for an existing Render service, add or update these variables in its Environment page. [Render's secret variable guidance](https://render.com/docs/blueprint-spec#prompting-for-secret-values).

After deployment, record the actual backend URL. Verify `GET https://<backend-host>/api/health` returns HTTP 200. Check that startup logs contain no credentials and that the hosted backend can reach Supabase, Open-Meteo and Nugen.

## 3. Deploy the React frontend on Vercel

Import the same repository into Vercel with **Root Directory `frontend`**. Use framework **Vite**, build command `npm run build`, and output directory `dist`; [`frontend/vercel.json`](../frontend/vercel.json) supplies a SPA rewrite so direct route refreshes return `index.html`. [Vercel's SPA rewrite example](https://vercel.com/docs/project-configuration/vercel-json#rewrites-examples).

Set the following Vercel build environment variables:

- `VITE_API_BASE_URL=https://<actual-backend-host>` (origin only; the client appends `/api/v1`).
- `VITE_SUPABASE_URL=https://<existing-project>.supabase.co`.
- `VITE_SUPABASE_PUBLISHABLE_KEY=<browser-safe-publishable-key>`.

Vite embeds `VITE_` variables in browser JavaScript. Never add `SUPABASE_SECRET_KEY`, `NUGEN_API_KEY` or `DATABASE_URL` to Vercel. Redeploy after changing a Vite build variable. [Vercel's Vite environment guidance](https://vercel.com/docs/frameworks/frontend/vite#environment-variables).

## 4. Complete cross-origin authentication

1. Add the final Vercel HTTPS origin to backend `CORS_ORIGINS` in Render, then redeploy/restart the backend.
2. In the existing Supabase Auth URL configuration, set the production site URL and allow the deployed origin plus `/reset-password` as a redirect destination. Retain localhost redirects only if local development is still needed.
3. Test sign-in, refresh, password reset, logout, citizen ownership, and authority-only navigation using accounts you control. The backend verifies every bearer token and role; frontend navigation is only a convenience layer.

## 5. Post-deployment acceptance

Use [FINAL_TEST_REPORT.md](FINAL_TEST_REPORT.md) as the checklist. Test actual hosted URLs and record them there. In particular: live B2 weather/AQI; all nine grid cells; map layers; explicit Nugen citizen and authority requests; a clearly labeled TEST citizen report; same-authority advisory approval and publication; citizen visibility of an active TEST alert for the selected cell; and absence of expired or unpublished alerts. Withdraw the TEST alert after verification. Never publish an unlabeled emergency warning for demonstration.

**Map data status, 5 November 2026:** The existing Supabase project subsequently imported 1,030 OSM facilities and 5,438 major roads; the readback recorded two import runs and a zero-insert repeat. Recheck the deployed project's `/api/v1/map/infrastructure` and `/api/v1/map/roads` responses for `storage=postgis` before relying on those layers in a hosted demo. With an unconfigured database, the API may return a clearly labeled validated local preview instead.
