# CLIMAGUARD AI

**Predict Earlier. Decide Faster. Protect More.**

Pune-first climate risk and emergency-response interface for the Indradhanu Hackathon 2026. Current figures are clearly labeled illustrative demo scenarios, not live risk assessments.

## Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The app defaults to clearly labeled demo mode. Choose **View live status** for Open-Meteo weather and air quality, the Pune analysis grid, and unavailable states for unsourced risk and facility data.

## Run the API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env`, then enter your Supabase project URL and keys. Set `NUGEN_API_KEY` and `NUGEN_MODEL_ID` server-side using the deployed aligned model from `backend/test_nugen.py`; `NUGEN_INFERENCE_URL` defaults to its verified chat-completions endpoint and `NUGEN_TIMEOUT_SECONDS` defaults to 90. Apply `database/migrations/001_schema.sql` through `007_nugen_recommendations.sql` in order using the Supabase SQL Editor or migration tooling. The API runs at `http://localhost:8000`; `/docs` exposes the contract. Run backend checks with `pytest` from `backend`; `python scripts/smoke_nugen.py` makes a real Open-Meteo and Nugen request through FastAPI. See [OSM import instructions](docs/DATA_SOURCES.md#osm-ingestion) and [flood geography](docs/FLOOD_GEOGRAPHY.md) for the sourced import paths.

Use a standard CPython 3.12+ installation for the backend. The MSYS2 MinGW Python available on this development machine cannot install the `pydantic-core` Windows wheel. The backend tests were run with the bundled standard CPython runtime and project-local dependencies.

New accounts are citizens. To bootstrap the first admin, set that user's `profiles.role` to `admin` once in the Supabase SQL Editor as a project owner. Future assignments use the admin-only backend endpoint. Browser code contains only the publishable key; the secret key belongs exclusively in `backend/.env`.

Open-Meteo current values are model estimates, and its archive is historical reanalysis. The nine map cells are reproducible analysis grid cells, not official wards or validated flood boundaries. Flood screening is a documented heuristic index; heat and US AQI use deterministic rules. Nugen produces guidance from those results and cannot publish an official alert. No labeled flood-event dataset or trained model is available. A verified hazard model, complete facility inventory, and sourced DEM are absent. See [analysis methods](ml/README.md), [data sources](docs/DATA_SOURCES.md), and [current integration status](docs/PROJECT_STATUS.md).

See [architecture](docs/ARCHITECTURE.md) and [project status](docs/PROJECT_STATUS.md).
