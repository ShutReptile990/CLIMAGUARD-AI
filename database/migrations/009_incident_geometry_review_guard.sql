-- Apply after 008. This replaces only the incident update guard; no data changes.
-- PostgreSQL cannot choose a unique equality operator for PostGIS geometry when
-- IS DISTINCT FROM compares geometry values directly. Compare EWKB bytes instead.
create or replace function private.guard_incident_update()
returns trigger language plpgsql set search_path = '' as $$
begin
  if private.current_role() = 'citizen' then
    if old.reporter_id <> auth.uid() or old.status <> 'submitted'
       or new.reporter_id is distinct from old.reporter_id or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id or new.category is distinct from old.category
       or new.severity is distinct from old.severity or new.image_path is distinct from old.image_path
       or new.status is distinct from old.status or new.review_note is distinct from old.review_note
       or new.reviewed_by is distinct from old.reviewed_by or new.reviewed_at is distinct from old.reviewed_at
       or public.ST_AsEWKB(new.location) is distinct from public.ST_AsEWKB(old.location)
       or new.created_at is distinct from old.created_at then
      raise exception 'Citizens may edit only their own submitted report text and contact';
    end if;
  elsif private.current_role() in ('authority','admin') then
    if new.reporter_id is distinct from old.reporter_id or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id or new.category is distinct from old.category
       or new.severity is distinct from old.severity or new.image_path is distinct from old.image_path
       or new.description is distinct from old.description or new.contact is distinct from old.contact
       or public.ST_AsEWKB(new.location) is distinct from public.ST_AsEWKB(old.location)
       or new.created_at is distinct from old.created_at
       or new.reviewed_by is distinct from auth.uid() or new.reviewed_at is null
       or (new.status = 'rejected' and nullif(trim(new.review_note), '') is null) then
      raise exception 'Reviewers may change only review fields and must explain rejection';
    end if;
    if not ((old.status = 'submitted' and new.status = 'under_review')
        or (old.status = 'under_review' and new.status in ('resolved','rejected'))) then
      raise exception 'Invalid report review transition';
    end if;
    new.reviewed_at := now();
  else
    raise exception 'Role cannot update reports';
  end if;
  return new;
end; $$;
