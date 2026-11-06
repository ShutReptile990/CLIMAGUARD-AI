# Citizen and single-authority workflow setup

The existing Supabase project has migrations 001–008; the project owner confirmed migrations 009 and 010 applied. A read-only probe confirmed migration 010's `alerts.incident_id` column. [`010_single_authority_alerts.sql`](../database/migrations/010_single_authority_alerts.sql) preserves existing alerts and audits, removes the different-reviewer constraint, adds an optional verified-incident link, and permits audited edits to published alert content. Do not replay earlier migrations or reset data.

## Role and storage setup

- A new account starts as `citizen`. Grant `authority` only after confirming control of the intended Supabase Auth account. Use the server-side `backend/scripts/assign_authority.py` dry run, then `--apply` for a verified account. Existing authority assignments do not need to be repeated. One authority account is sufficient for incident review and official advisories; additional authority accounts may still exist.
- The `incident-evidence` bucket remains private. Reporters can upload and view their own images; authorities can view evidence using short-lived signed access. Do not move privileged credentials to the browser.
- Run `backend/scripts/check_phase6_schema.py` to check the existing incident/alert fields and bucket. `backend/scripts/check_single_authority_schema.py` confirms the `alerts.incident_id` marker. The marker alone does not prove the trigger or constraint changed; test an authenticated self-approval with a clearly labeled TEST draft.

## Verified state path

1. A citizen submits a report. The backend stores it as `submitted` and shows it in My Reports.
2. The authenticated authority starts review (`under_review`) and verifies (`resolved`) or rejects (`rejected`) it. Supabase records reviewer, time and status audit entries. A verified citizen report is **not** automatically a historical flood-event training label.
3. For a verified report, the authority follows its Response Planner link. Explicit Nugen generation uses the selected grid cell's sourced risk analysis; it does not send citizen report text or contact details to the model. The authority reviews and edits any proposed advisory; saving creates an unpublished draft optionally linked to that verified incident.
4. The **same** authority submits, explicitly approves and separately publishes the draft with an expiry. Backend role checks and database RLS/transition guards apply at each step. Publication is never automatic. The authority may update published content or withdraw the alert; the changes are audited.
5. Citizens see only published, unexpired alerts for the selected cell. Withdraw the clearly labeled TEST alert after verification.

## Live acceptance

Use a separate citizen test account and a report/advisory beginning `TEST —`. Verify saved status, actor and audit readback after each transition, citizen visibility when published, and absence after withdrawal. The 1 November 2026 TEST incident already completed `submitted → under_review → resolved` with two Supabase audit entries. Single-authority alert publication is still unverified until a signed-in authority completes the flow.
