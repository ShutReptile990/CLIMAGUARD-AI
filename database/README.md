# Database

For a **new** Supabase PostgreSQL project, apply migrations 001 through 010 in numeric order. Migration 005 depends on infrastructure and roads from 003; 006 depends on zones and `zone_dataset_metrics` from 003; 007 depends on `ai_recommendations` from 001; 008 adds citizen/authority workflow fields and guards; 009 fixes the incident guard's PostGIS geometry comparison; 010 enables the single-authority alert workflow. The project owner confirmed migrations 009 and 010 succeeded, and live checks confirmed the preceding schema. Do not rerun earlier non-idempotent scripts or delete existing records. `DATABASE_URL` is not configured; data import through the server-side Supabase REST credential remains available.

On 31 October, the DEM importer also persisted nine sourced mean-slope metrics through `--dem-only --import-supabase`, preserving all nine WorldPop estimates and mapped-drain distances. Its readback checks verified every cell; a repeat import wrote zero rows. Direct SQL access remains optional for this path and is still unavailable until server-side `DATABASE_URL` is configured.

On 5 November, the validated OSM GeoJSON import populated PostGIS with 1,030 facilities and 5,438 roads. The repeat run inserted zero records. To validate or rerun this insert-only import from PowerShell with the configured backend environment:

```powershell
cd backend
.venv\Scripts\python.exe scripts\import_pune_infrastructure.py
.venv\Scripts\python.exe scripts\import_pune_infrastructure.py --import-supabase
.venv\Scripts\python.exe scripts\audit_osm_postgis.py
```

The write mode requires server-side `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. `SUPABASE_PUBLISHABLE_KEY` is used for the read-only public-access audit; `DATABASE_URL` is needed only for the alternative `--import-db` path. The importer validates EPSG:4326 geometry, source IDs and names, inserts only missing IDs, and verifies readback. It preserves existing rows.

New Auth users receive `citizen` automatically. To bootstrap the first admin, create the account, then run this once in the Supabase SQL Editor as the project owner, replacing the UUID with that user's Auth ID:

```sql
update public.profiles set role = 'admin' where id = 'USER_UUID_HERE';
```

Subsequent role changes go through the backend admin endpoint and are audited. Never place the secret key in the frontend.
