# Architecture

- `frontend/`: React, TypeScript, Vite, Tailwind, shadcn-style UI primitives, React Router, TanStack Query, React Leaflet, Recharts.
- `backend/`: modular FastAPI API, Pydantic validation, Supabase Auth verification, role checks, pooled HTTP integration, and typed repositories.
- `database/`: Supabase PostgreSQL/PostGIS migrations and RLS policies.
- `ml/`: planned hazard models and evaluation.

The frontend starts in an explicitly labeled demo mode with illustrative scenario values. Live mode calls `/api/v1` through the Vite proxy. FastAPI normalizes and caches Open-Meteo forecast, archive, and air-quality responses, and conditionally persists selected current model estimates through Supabase. Versioned deterministic flood, heat and US AQI rules return explanations and missing-data warnings. The simulator substitutes hypothetical inputs without writing forecasts. A deterministic 3×3 Pune analysis grid and screening bins power the Leaflet map. OSM facility and road layers read from PostGIS after a manual import; a security-invoker spatial function returns cell intersections and sourced population metrics. Missing upstream data returns unavailable states. Demo incident reports are stored only in local browser storage and are never sent to authorities.

The backend verifies each protected bearer token with Supabase Auth, then reads the role from the database. PostgREST requests use the user's token so RLS remains in force. Admin role assignment, environmental ingestion, and Nugen draft storage use the server-side secret key. Authority alert publication requires a reviewer other than the draft author. The map grid is not an official ward or flood boundary. DEM and validated hazard footprints remain dependencies. Deployed Nugen inference supplies guidance from deterministic live analysis; no substitute provider is configured.
