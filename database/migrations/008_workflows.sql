-- Apply after 001-007. Additive data changes; existing rows and approvals are retained.
alter table public.incident_reports drop constraint if exists incident_reports_category_check;
alter table public.incident_reports add constraint incident_reports_category_check
  check (category in ('flood','waterlogging','blocked_road','fallen_tree','heat','air_quality','other'));
alter table public.incident_reports add column if not exists severity text not null default 'moderate'
  check (severity in ('low','moderate','high','severe'));
alter table public.incident_reports add column if not exists image_path text;
alter table public.incident_reports add column if not exists reviewed_at timestamptz;
alter table public.incident_reports add constraint incident_image_private_path
  check (image_path is null or image_path ~ ('^' || reporter_id::text || '/[0-9a-f-]{36}\.(jpg|jpeg|png|webp)$'));

alter table public.alerts drop constraint if exists alerts_status_check;
alter table public.alerts add constraint alerts_status_check
  check (status in ('draft','pending_approval','approved','rejected','published','expired','withdrawn'));
alter table public.alerts add column if not exists hazard text not null default 'other'
  check (hazard in ('flood','heat','air_quality','other'));
alter table public.alerts add column if not exists submitted_at timestamptz;
alter table public.alerts add column if not exists reviewed_at timestamptz;
alter table public.alerts add column if not exists review_note text;
alter table public.alerts add column if not exists published_at timestamptz;
alter table public.alerts add column if not exists expires_at timestamptz;
alter table public.alerts add constraint alert_expiry_order
  check (expires_at is null or published_at is null or expires_at > published_at);
create index if not exists alerts_active_idx on public.alerts(locality_id, status, expires_at);

-- Existing published alerts retain their approval record and visible status.
-- Their publication timestamp remains unknown; do not invent one from approval time.

create or replace function private.guard_incident_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if private.current_role() = 'citizen' then
    if old.reporter_id <> auth.uid() or old.status <> 'submitted'
       or new.reporter_id is distinct from old.reporter_id or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id or new.category is distinct from old.category
       or new.severity is distinct from old.severity or new.image_path is distinct from old.image_path
       or new.status is distinct from old.status or new.review_note is distinct from old.review_note
       or new.reviewed_by is distinct from old.reviewed_by or new.reviewed_at is distinct from old.reviewed_at
       or new.location is distinct from old.location or new.created_at is distinct from old.created_at then
      raise exception 'Citizens may edit only their own submitted report text and contact';
    end if;
  elsif private.current_role() in ('authority','admin') then
    if new.reporter_id is distinct from old.reporter_id or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id or new.category is distinct from old.category
       or new.severity is distinct from old.severity or new.image_path is distinct from old.image_path
       or new.description is distinct from old.description or new.contact is distinct from old.contact
       or new.location is distinct from old.location or new.created_at is distinct from old.created_at
       or new.reviewed_by is distinct from auth.uid() or new.reviewed_at is null
       or (new.status = 'rejected' and nullif(trim(new.review_note), '') is null) then
      raise exception 'Reviewers may change only review fields and must explain rejection';
    end if;
    if not ((old.status = 'submitted' and new.status = 'under_review')
        or (old.status = 'under_review' and new.status in ('resolved','rejected'))) then
      raise exception 'Invalid report review transition';
    end if;
    new.reviewed_at := now();
  else raise exception 'Role cannot update reports'; end if;
  return new;
end; $$;

create or replace function private.guard_alert_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if private.current_role() not in ('authority','admin') then raise exception 'Authority role required'; end if;
  if new.zone_id is distinct from old.zone_id or new.locality_id is distinct from old.locality_id
     or new.created_by is distinct from old.created_by or new.created_at is distinct from old.created_at then
    raise exception 'Alert identity and target area are immutable';
  end if;
  if (new.title is distinct from old.title or new.body is distinct from old.body
     or new.level is distinct from old.level or new.hazard is distinct from old.hazard
     or new.source is distinct from old.source)
     and not (old.status = 'draft' and new.status = 'draft' and auth.uid() = old.created_by) then
    raise exception 'Only the author may edit an unsubmitted draft';
  end if;
  if (new.submitted_at is distinct from old.submitted_at and old.status <> 'draft')
     or (new.reviewed_at is distinct from old.reviewed_at and old.status <> 'pending_approval')
     or (new.review_note is distinct from old.review_note and old.status <> 'pending_approval')
     or (new.approved_by is distinct from old.approved_by and old.status <> 'pending_approval')
     or (new.approved_at is distinct from old.approved_at and old.status <> 'pending_approval')
     or (new.published_at is distinct from old.published_at and old.status <> 'approved')
     or (new.expires_at is distinct from old.expires_at and old.status <> 'approved') then
    raise exception 'Prior review and publication fields are immutable';
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
    if auth.uid() = old.created_by or new.reviewed_at is null
       or new.approved_by is distinct from auth.uid()
       or (new.status = 'approved' and new.approved_at is null)
       or (new.status = 'rejected' and (new.approved_at is not null or nullif(trim(new.review_note), '') is null))
       or new.published_at is not null or new.expires_at is not null then
      raise exception 'Independent review and rejection reason required'; end if;
    new.reviewed_at := now();
    if new.status = 'approved' then new.approved_at := new.reviewed_at; end if;
  elsif old.status = 'approved' and new.status = 'published' then
    new.published_at := now();
    if old.approved_by is null or old.approved_at is null or new.published_at is null
       or new.expires_at is null or new.expires_at <= new.published_at
       or new.expires_at > new.published_at + interval '30 days'
       or new.approved_by is distinct from old.approved_by
       or new.approved_at is distinct from old.approved_at then
      raise exception 'Only approved advisories with a valid expiry may be published'; end if;
  elsif old.status = 'published' and new.status in ('expired','withdrawn') then
    if new.approved_by is distinct from old.approved_by or new.approved_at is distinct from old.approved_at then
      raise exception 'Approval record is immutable'; end if;
  else raise exception 'Invalid alert state transition'; end if;
  return new;
end; $$;

-- The existing state-change audit trigger captures each review/publication transition.
create trigger alert_edit_audit after update on public.alerts for each row
  when (old.title is distinct from new.title or old.body is distinct from new.body
    or old.level is distinct from new.level or old.hazard is distinct from new.hazard
    or old.source is distinct from new.source)
  execute function private.audit_state_change();
grant select(severity,image_path,reviewed_at) on public.incident_reports to authenticated;
grant insert(severity,image_path) on public.incident_reports to authenticated;
grant update(reviewed_at) on public.incident_reports to authenticated;
grant select(hazard,submitted_at,reviewed_at,review_note,published_at,expires_at) on public.alerts to anon,authenticated;
grant insert(hazard) on public.alerts to authenticated;
grant update(submitted_at,reviewed_at,review_note,published_at,expires_at) on public.alerts to authenticated;
grant update(title,body,level,hazard,source) on public.alerts to authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('incident-evidence','incident-evidence',false,5242880,array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set public=false,file_size_limit=5242880,allowed_mime_types=excluded.allowed_mime_types;
create policy incident_evidence_owner_insert on storage.objects for insert to authenticated
  with check (bucket_id='incident-evidence' and (storage.foldername(name))[1]=auth.uid()::text);
create policy incident_evidence_read on storage.objects for select to authenticated
  using (bucket_id='incident-evidence' and ((storage.foldername(name))[1]=auth.uid()::text
    or (select private.current_role()) in ('authority','admin')));
create policy incident_evidence_owner_delete on storage.objects for delete to authenticated
  using (bucket_id='incident-evidence' and (storage.foldername(name))[1]=auth.uid()::text
    and not exists (select 1 from public.incident_reports where image_path = name));
