# Database

For a **new** Supabase PostgreSQL project, apply migrations 001 through 009 in numeric order. Migration 005 depends on infrastructure and roads from 003; 006 depends on zones and `zone_dataset_metrics` from 003; 007 depends on `ai_recommendations` from 001; 008 adds citizen/authority workflow fields and guards; 009 fixes the incident guard's PostGIS geometry comparison. Live checks confirmed migrations 001–008 are already applied to the current project. Apply **only 009** there. Do not rerun earlier non-idempotent scripts or delete existing records. `DATABASE_URL` is not configured; data import through the server-side Supabase REST credential remains available.

On 31 October, the DEM importer also persisted nine sourced mean-slope metrics through `--dem-only --import-supabase`, preserving all nine WorldPop estimates and mapped-drain distances. Its readback checks verified every cell; a repeat import wrote zero rows. Direct SQL access remains optional for this path and is still unavailable until server-side `DATABASE_URL` is configured.

New Auth users receive `citizen` automatically. To bootstrap the first admin, create the account, then run this once in the Supabase SQL Editor as the project owner, replacing the UUID with that user's Auth ID:

```sql
update public.profiles set role = 'admin' where id = 'USER_UUID_HERE';
```

Subsequent role changes go through the backend admin endpoint and are audited. Never place the secret key in the frontend.
