# CLIMAGUARD AI

**Predict Earlier. Decide Faster. Protect More.**

Pune-first climate risk and emergency-response interface for the Indradhanu Hackathon 2026. Live screens use source-labeled environmental data and transparent screening rules; the separate demo and simulator modes are labeled. Flood scores are heuristic indices, not calibrated probabilities or official warnings.

## Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Configure both `.env` files before using live mode. The existing demo switch remains available; live mode shows provider timestamps, source-backed grid-cell evidence and explicit unavailable states where data is missing.

## Run the API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env`, then enter your existing Supabase project URL and keys. Set `NUGEN_API_KEY` and `NUGEN_MODEL_ID` server-side for the deployed aligned model; `NUGEN_INFERENCE_URL` defaults to the verified chat-completions endpoint. Apply pending SQL migrations in numeric order only after checking the existing project state. The project owner reports migrations 001–009 applied. The local API defaults to port 8000; set `VITE_API_BASE_URL` to the actual backend origin if it runs elsewhere. `/docs` exposes the contract. Run backend checks with `pytest` from `backend`; `python scripts/smoke_nugen.py pune-grid-r2-c2` makes a real Open-Meteo and Nugen request through FastAPI. See [OSM import instructions](docs/DATA_SOURCES.md#osm-ingestion) and [flood geography](docs/FLOOD_GEOGRAPHY.md) for the sourced import paths.

Use a standard CPython 3.12+ installation for the backend. The MSYS2 MinGW Python available on this development machine cannot install the `pydantic-core` Windows wheel. The backend tests were run with the bundled standard CPython runtime and project-local dependencies.

New accounts are citizens. To bootstrap the first admin, set that user's `profiles.role` to `admin` once in the Supabase SQL Editor as a project owner. Future assignments use the admin-only backend endpoint. Browser code contains only the publishable key; the secret key belongs exclusively in `backend/.env`.

An authenticated authority can review citizen reports and, after migration `010_single_authority_alerts.sql` is applied, independently edit, approve and publish an advisory with an expiry. Each action remains separate and audited; Nugen never publishes automatically. See [workflow setup](docs/PHASE6_WORKFLOW_SETUP.md).

Open-Meteo current values are model estimates, and its archive is historical reanalysis. The nine map cells are reproducible analysis grid cells, not official wards or validated flood boundaries. Flood screening is a documented heuristic index; heat and US AQI use deterministic rules. Nugen produces guidance from those results and cannot publish an official alert. The sourced Copernicus slope, WorldPop population and mapped-drain distance cover all nine cells, but verified flood-event labels, a calibrated model and a hazard footprint remain unavailable. Facilities and roads currently use a validated local OSM preview pending PostGIS import. See [analysis methods](ml/README.md), [data sources](docs/DATA_SOURCES.md), and [current integration status](docs/PROJECT_STATUS.md).

See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), [final test report](docs/FINAL_TEST_REPORT.md), [five-minute demo](docs/DEMO_SCRIPT.md), [judge questions](docs/JUDGE_QA.md) and [project status](docs/PROJECT_STATUS.md).
