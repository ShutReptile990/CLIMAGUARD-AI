# Phase 6 workflow setup

The repository preserves migrations 001–007. The project owner applied migration 008 on 31 October 2026. Read-only checks confirmed its incident and alert columns, `incident-evidence` bucket, and public active-alert expiry filter. Both named accounts have audited `authority` profiles after the invited second user confirmed signing in. There is no `admin` profile.

## Schema verification

1. From `backend`, run `.venv/Scripts/python.exe scripts/check_phase6_schema.py`. The incident and alert columns, private evidence bucket, and public expiry filter must show **available**. Do not replay migration 008 on this project.
2. Confirm the Supabase Auth redirect allowlist includes the frontend origin plus `/reset-password`, and email invitation/recovery delivery is enabled.

The migration adds incident severity/image/review fields and alert lifecycle fields, tightens transition triggers, creates a private evidence bucket, and adds storage policies.

## Grant test authority access securely

Use two **consenting test users** with confirmed account control. New signups and invitations initially receive `citizen` through the database trigger. Never share passwords or put credentials in source files. Both named accounts are now authority. Do not rerun the role assignment or invitation scripts on them.

The two assignments are complete. `scripts/check_phase6_schema.py` reports two authority profiles, no admin profile, and two server-side role-change audit entries. For a future new test user:

1. After the user confirms account control, run `.venv/Scripts/python.exe scripts/assign_authority.py --email <account-email>` from `backend` to dry-run the exact Auth/profile match and sign-in checks.
2. Run the same command with `--apply` only if the dry run identifies the intended citizen account. It conditionally updates only a `citizen` profile and writes an audit record.
3. For a fresh project, an admin can use **Authority → Role Management**; the backend verifies the admin token and audits the change. A project owner who wants authority-only profiles can use this server-side script instead. Never assign a role based only on the number of profiles.

For a fresh project where the script cannot be used, the project owner can review the following SQL transaction in Supabase SQL Editor. Replace both placeholders; it refuses to run unless both Auth accounts exist and are confirmed, and writes audit entries. Do **not** run it on the current project because the first account is already authority:

```sql
begin;
do $$
begin
  if (select count(*) from auth.users
      where email in ('authority-a@example.com', 'authority-b@example.com')
        and email_confirmed_at is not null) <> 2 then
    raise exception 'Expected two distinct confirmed test Auth users';
  end if;
  if (select count(*) from public.profiles
      where role = 'citizen' and id in (select id from auth.users
        where email in ('authority-a@example.com', 'authority-b@example.com'))) <> 2 then
    raise exception 'Both target profiles must currently have the citizen role';
  end if;
end $$;
with promoted as (
  update public.profiles p
  set role = 'authority'
  where p.role = 'citizen' and p.id in (
    select id from auth.users
    where email in ('authority-a@example.com', 'authority-b@example.com'))
  returning id
)
insert into public.audit_logs(actor_id, action, entity_type, entity_id, details)
select id, 'profile.role_changed', 'profile', id,
       jsonb_build_object('role', 'authority', 'method', 'project_owner_sql', 'purpose', 'Phase 6 two-person test')
from promoted;
commit;
```

Verify exactly two profiles were changed and the read-only role check reports two authority profiles. Do not assign a role based only on the number of existing profiles or an unknown user ID. If a profile is already authority, inspect it first and do not rerun the transaction blindly.

## Verify the journeys

1. Citizen: sign up, confirm email, sign in, select grid B2, inspect live climate data, deliberately generate Nugen guidance, submit a report, and confirm it appears in My Reports as **Unverified**. Optional image uploads must remain in the private bucket.
2. Authority A: sign in, open the report queue, start review, then verify or reject with a reason. Open the response planner, generate the Nugen brief, edit and save an advisory draft, then submit it for approval.
3. Authority B: sign in, review that pending alert and approve it. Authority A must receive HTTP 403 for self-approval. Publish the approved alert with an expiry within 30 days.
4. Citizen: select the alert's grid cell and check **Official Alerts**. The alert should appear while active. After expiry it must disappear from current alerts; an authority can record the expired status in Publication History.

The alert state-change trigger writes to `audit_logs`. Incident state changes also have an audit trail accessible through the report's Review history. A verified citizen report is still not a validated historical flood-event label.
