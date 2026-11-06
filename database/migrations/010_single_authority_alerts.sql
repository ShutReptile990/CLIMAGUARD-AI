-- Apply after 009. Preserve all existing alerts and approval/audit history.
-- The same authenticated authority may explicitly approve and publish a draft.
begin;
alter table public.alerts drop constraint if exists published_requires_independent_review;
alter table public.alerts add constraint published_requires_approval
  check (status <> 'published' or (approved_by is not null and approved_at is not null));

-- Optional, immutable link from an advisory to a verified citizen incident.
alter table public.alerts add column if not exists incident_id uuid references public.incident_reports(id);
create index if not exists alerts_incident_idx on public.alerts(incident_id) where incident_id is not null;
grant select(incident_id) on public.alerts to authenticated;
grant insert(incident_id) on public.alerts to authenticated;

create or replace function private.guard_alert_incident_link() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.incident_id is not null and not exists (
    select 1 from public.incident_reports i
    where i.id = new.incident_id and i.status = 'resolved'
      and i.zone_id = new.zone_id and i.locality_id = new.locality_id
  ) then
    raise exception 'An advisory may link only to a verified incident in the same analysis zone';
  end if;
  return new;
end; $$;
create trigger alert_incident_link before insert or update of incident_id on public.alerts
  for each row execute function private.guard_alert_incident_link();

create or replace function private.guard_alert_update() returns trigger
language plpgsql set search_path = '' as $$
begin
  if private.current_role() not in ('authority','admin') then raise exception 'Authority role required'; end if;
  if new.zone_id is distinct from old.zone_id or new.locality_id is distinct from old.locality_id
     or new.incident_id is distinct from old.incident_id
     or new.created_by is distinct from old.created_by or new.created_at is distinct from old.created_at then
    raise exception 'Alert identity, incident link and target area are immutable';
  end if;
  if (new.title is distinct from old.title or new.body is distinct from old.body
     or new.level is distinct from old.level or new.hazard is distinct from old.hazard
     or new.source is distinct from old.source)
     and not ((old.status = 'draft' and new.status = 'draft' and auth.uid() = old.created_by)
       or (old.status = 'published' and new.status = 'published')) then
    raise exception 'Content may be edited only in a draft or a published alert';
  end if;
  if (new.submitted_at is distinct from old.submitted_at and old.status <> 'draft')
     or (new.reviewed_at is distinct from old.reviewed_at and old.status <> 'pending_approval')
     or (new.review_note is distinct from old.review_note and old.status <> 'pending_approval')
     or (new.approved_by is distinct from old.approved_by and old.status <> 'pending_approval')
     or (new.approved_at is distinct from old.approved_at and old.status <> 'pending_approval')
     or (new.published_at is distinct from old.published_at and old.status <> 'approved')
     or (new.expires_at is distinct from old.expires_at and old.status <> 'approved') then
    raise exception 'Prior approval and publication fields are immutable';
  end if;
  if old.status = 'draft' and new.status = 'draft' then
    if auth.uid() is distinct from old.created_by or new.submitted_at is not null
       or new.reviewed_at is not null or new.approved_by is not null
       or new.approved_at is not null or new.published_at is not null
       or new.expires_at is not null then
      raise exception 'Only the author may edit an unsubmitted draft'; end if;
  elsif old.status = 'draft' and new.status = 'pending_approval' then
    if auth.uid() is distinct from old.created_by or new.submitted_at is null
       or new.approved_by is not null or new.approved_at is not null
       or new.reviewed_at is not null or new.review_note is not null
       or new.published_at is not null or new.expires_at is not null then
      raise exception 'Only the author may submit an unapproved draft'; end if;
    new.submitted_at := now();
  elsif old.status = 'pending_approval' and new.status in ('approved','rejected') then
    if new.reviewed_at is null or new.approved_by is distinct from auth.uid()
       or (new.status = 'approved' and new.approved_at is null)
       or (new.status = 'rejected' and (new.approved_at is not null or nullif(trim(new.review_note), '') is null))
       or new.published_at is not null or new.expires_at is not null then
      raise exception 'Explicit authority approval or explained rejection required'; end if;
    new.reviewed_at := now();
    if new.status = 'approved' then new.approved_at := new.reviewed_at; end if;
  elsif old.status = 'approved' and new.status = 'published' then
    new.published_at := now();
    if old.approved_by is null or old.approved_at is null
       or new.expires_at is null or new.expires_at <= new.published_at
       or new.expires_at > new.published_at + interval '30 days'
       or new.approved_by is distinct from old.approved_by
       or new.approved_at is distinct from old.approved_at then
      raise exception 'Only approved advisories with a valid expiry may be published'; end if;
  elsif old.status = 'published' and new.status = 'published' then
    if new.expires_at is distinct from old.expires_at or new.published_at is distinct from old.published_at
       or new.approved_by is distinct from old.approved_by or new.approved_at is distinct from old.approved_at then
      raise exception 'Published approval and expiry fields are immutable'; end if;
  elsif old.status = 'published' and new.status in ('expired','withdrawn') then
    if new.approved_by is distinct from old.approved_by or new.approved_at is distinct from old.approved_at then
      raise exception 'Approval record is immutable'; end if;
  else raise exception 'Invalid alert state transition'; end if;
  return new;
end; $$;

-- Keep the existing status-change trigger. Replace only the edit audit trigger.
create or replace function private.audit_alert_edit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.audit_logs(actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), 'alerts.edited', 'alerts', new.id,
    pg_catalog.jsonb_build_object('status', new.status,
      'changed_fields', pg_catalog.array_remove(array[
        case when old.title is distinct from new.title then 'title' end,
        case when old.body is distinct from new.body then 'body' end,
        case when old.level is distinct from new.level then 'level' end,
        case when old.hazard is distinct from new.hazard then 'hazard' end,
        case when old.source is distinct from new.source then 'source' end
      ], null)));
  return new;
end; $$;
drop trigger if exists alert_edit_audit on public.alerts;
create trigger alert_edit_audit after update on public.alerts for each row
  when (old.title is distinct from new.title or old.body is distinct from new.body
    or old.level is distinct from new.level or old.hazard is distinct from new.hazard
    or old.source is distinct from new.source)
  execute function private.audit_alert_edit();
commit;
