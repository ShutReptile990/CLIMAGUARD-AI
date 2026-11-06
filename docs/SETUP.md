# Local setup and configuration

[Project overview](../README.md) · [Database migration notes](../database/README.md) · [Deployment](DEPLOYMENT.md)

## Prerequisites

- Windows PowerShell, Git and Node.js compatible with the installed Vite 7 release.
- Standard CPython **3.13**, matching [`.python-version`](../.python-version), with `py -3.13` available. Do not use an MSYS2 MinGW Python for this virtual environment.
- A Supabase project with PostgreSQL/PostGIS and Auth for persisted workflows. A deployed Nugen-aligned model is required for AI guidance. Weather endpoints can run without those credentials.

## Clone and install

```powershell
git clone https://github.com/ShutReptile990/CLIMAGUARD-AI.git
cd CLIMAGUARD-AI
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes the application and optional geospatial/test dependencies. For a production API build, [`render.yaml`](../render.yaml) installs only `requirements.txt`; the import utilities requiring Rasterio, GeoPandas or Psycopg need `requirements-geo.txt` in the environment where they run.

Edit the two new `.env` files locally. They are ignored by [`.gitignore`](../.gitignore). Start FastAPI from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second PowerShell window, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. API health: `http://127.0.0.1:8000/api/health`; Swagger: `http://127.0.0.1:8000/docs`. If FastAPI uses port 8001 instead, change `VITE_API_BASE_URL` to `http://127.0.0.1:8001` and restart Vite. The client adds `/api/v1` to that **origin**; do not include `/api/v1` in the variable. `CORS_ORIGINS` must contain the exact browser origin, such as `http://127.0.0.1:5173`.

## Environment variables

| Variable | Where | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Frontend | FastAPI origin; example defaults to port 8000 |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | Frontend | Supabase Auth with browser-safe publishable credential |
| `APP_ENV`, `CORS_ORIGINS` | Backend | Runtime label and allowed frontend origins |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Backend | Supabase REST project and user/public requests |
| `SUPABASE_SECRET_KEY` | Backend only | Privileged ingestion and selected server operations |
| `NUGEN_API_KEY`, `NUGEN_MODEL_ID`, `NUGEN_INFERENCE_URL` | Backend only | Aligned-model inference |
| `NUGEN_TIMEOUT_SECONDS`, `EXTERNAL_TIMEOUT_SECONDS` | Backend | Provider timeout bounds |
| `FLOOD_MODERATE_INDEX`, `FLOOD_HIGH_INDEX`, `FLOOD_SEVERE_INDEX` | Backend | Flood category thresholds |
| `HEAT_MODERATE_C`, `HEAT_HIGH_C`, `HEAT_SEVERE_C` | Backend | Heat category thresholds |
| `DATABASE_URL` | Optional, server-side import shell | Direct PostgreSQL route for certain import utilities; not required by ordinary FastAPI requests |
| `WORLDPOP_API_KEY` | Optional, server-side import shell | Dataset import only where required by WorldPop |

Use the placeholder values in [backend/.env.example](../backend/.env.example) and [frontend/.env.example](../frontend/.env.example). Do not commit real `.env` files, copy keys into a `VITE_` variable or paste credentials into an issue. `NUGEN_MODEL_ID` must identify a model actually deployed in the owner's Nugen account; the model ID documented in local verification is `model_01m66gqc3qk10zdy` and may change with a new deployment.

## Database and roles

For a **new** Supabase project, enable PostGIS and apply [`database/migrations/001_schema.sql`](../database/migrations/001_schema.sql) through [`010_single_authority_alerts.sql`](../database/migrations/010_single_authority_alerts.sql) in **numeric order**. Review each migration in the SQL Editor before running it. Migration 005 depends on schema from 003; 006 on the zone metrics and geography schema; 007 on recommendations; 008–010 add guarded citizen/authority workflows. **Do not replay non-idempotent migrations against the existing populated project.** The owner confirmed 009 and 010 were applied there; [database/README.md](../database/README.md) records additional readbacks.

Configure the Supabase Auth site URL and allowed local redirect URL(s), including `/reset-password`. New users begin as `citizen`. Only a project owner should bootstrap the first admin by assigning that known Auth user's profile role in Supabase SQL Editor; subsequent role assignments use the authenticated admin-only API. Confirm account control before granting authority access. Row-level security and backend role dependencies enforce protected operations. Migration 008 creates a private `incident-evidence` Storage bucket.

## Optional geographic imports

The current project already has nine terrain/WorldPop metrics, 213 waterways and imported OSM facilities/roads. Do not rerun imports merely to start the application. For a **new** database, follow the validation and insert-only procedures in [DATA_SOURCES.md](DATA_SOURCES.md) and [FLOOD_GEOGRAPHY.md](FLOOD_GEOGRAPHY.md). Raw files need their documented provenance; mapped drain distance does not prove capacity.

## Checks and troubleshooting

```powershell
# From backend
.\.venv\Scripts\python.exe -m pytest app\tests -q
.\.venv\Scripts\python.exe scripts\check_extreme_demo.py

# From frontend
npm run build
```

The demo readback is read-only but queries Supabase when configured. The optional `scripts/smoke_nugen.py pune-grid-r2-c2 simulation` command makes a **real paid/limited provider inference**; run it deliberately. `npm run build` includes `tsc -b`.

- **Frontend says API unavailable:** Check the API origin/port, `GET /api/health`, exact `/api/v1` path, CORS and restart Vite after changing `.env`.
- **Environment streams unavailable:** Open-Meteo failures remain unavailable; they are never filled with demo measurements. Supabase Auth is not required for public environmental endpoints.
- **Protected pages fail:** Confirm a Supabase Auth session, a matching `profiles` row, required role and applied workflow migrations. Hidden navigation is not authorization.
- **Nugen guidance unavailable:** Confirm the server-side model ID, endpoint and key; inspect sanitized FastAPI logs and `/api/v1/nugen/status`. There is no alternate-provider live fallback.
- **Map context missing:** Check `zone_dataset_metrics`, waterways, facility import status and the selected grid-cell slug. Pune overview intentionally has no synthesized city-wide terrain or population number.
