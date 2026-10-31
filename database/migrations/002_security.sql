-- The private schema is not exposed through the Supabase Data API.
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to authenticated;

create function private.current_role() returns text language sql stable security definer set search_path = '' as $$
  select role from public.profiles where id = (select auth.uid())
$$;
revoke all on function private.current_role() from public;
grant execute on function private.current_role() to authenticated;

create function private.guard_locality_reference() returns trigger language plpgsql set search_path = '' as $$
begin
  if not exists (select 1 from public.zones where id = new.zone_id and slug = new.locality_id) then
    raise exception 'Zone and locality do not match';
  end if;
  return new;
end; $$;
create trigger incident_locality before insert on public.incident_reports for each row execute function private.guard_locality_reference();
create trigger alert_locality before insert on public.alerts for each row execute function private.guard_locality_reference();

-- Direct writes to reports and alerts are checked again by these triggers.
create function private.guard_incident_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if private.current_role() = 'citizen' then
    if old.reporter_id <> auth.uid() or old.status <> 'submitted'
       or new.reporter_id is distinct from old.reporter_id
       or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id
       or new.category is distinct from old.category
       or new.status is distinct from old.status
       or new.review_note is distinct from old.review_note
       or new.reviewed_by is distinct from old.reviewed_by
       or new.location is distinct from old.location then
      raise exception 'Citizens may edit only their own submitted report text and contact';
    end if;
  elsif private.current_role() in ('authority','admin') then
    if new.reporter_id is distinct from old.reporter_id or new.zone_id is distinct from old.zone_id
       or new.locality_id is distinct from old.locality_id or new.category is distinct from old.category
       or new.description is distinct from old.description or new.contact is distinct from old.contact
       or new.location is distinct from old.location or new.created_at is distinct from old.created_at
       or new.reviewed_by is distinct from auth.uid() then
      raise exception 'Reviewers may change only review fields';
    end if;
    if not ((old.status = 'submitted' and new.status = 'under_review')
        or (old.status = 'under_review' and new.status in ('resolved','rejected'))) then
      raise exception 'Invalid report review transition';
    end if;
  else raise exception 'Role cannot update reports'; end if;
  return new;
end; $$;
create trigger guard_incident_update before update on public.incident_reports for each row execute function private.guard_incident_update();

create function private.guard_alert_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if private.current_role() not in ('authority','admin') then raise exception 'Authority role required'; end if;
  if new.zone_id is distinct from old.zone_id or new.locality_id is distinct from old.locality_id
     or new.title is distinct from old.title or new.body is distinct from old.body
     or new.level is distinct from old.level or new.source is distinct from old.source
     or new.created_by is distinct from old.created_by or new.created_at is distinct from old.created_at then
    raise exception 'Alert content is immutable after drafting';
  end if;
  if old.status = 'draft' and new.status = 'published' then
    if auth.uid() = old.created_by or new.approved_by is distinct from auth.uid()
       or new.approved_at is null then raise exception 'Independent reviewer required'; end if;
  elsif old.status = 'published' and new.status = 'withdrawn' then
    if new.approved_by is distinct from old.approved_by or new.approved_at is distinct from old.approved_at then
      raise exception 'Approval record is immutable'; end if;
  else raise exception 'Invalid alert state transition'; end if;
  return new;
end; $$;
create trigger guard_alert_update before update on public.alerts for each row execute function private.guard_alert_update();

create function private.audit_state_change() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.audit_logs(actor_id, action, entity_type, entity_id, details)
  values (auth.uid(), TG_TABLE_NAME || '.updated', TG_TABLE_NAME, new.id,
    jsonb_build_object('old_status', old.status, 'new_status', new.status));
  return new;
end; $$;
create trigger incident_audit after update on public.incident_reports for each row when (old.status is distinct from new.status) execute function private.audit_state_change();
create trigger alert_audit after update on public.alerts for each row when (old.status is distinct from new.status) execute function private.audit_state_change();

alter table public.profiles enable row level security;
alter table public.zones enable row level security;
alter table public.climate_observations enable row level security;
alter table public.weather_forecasts enable row level security;
alter table public.risk_predictions enable row level security;
alter table public.prediction_explanations enable row level security;
alter table public.infrastructure enable row level security;
alter table public.impact_assessments enable row level security;
alter table public.priority_assessments enable row level security;
alter table public.ai_recommendations enable row level security;
alter table public.incident_reports enable row level security;
alter table public.alerts enable row level security;
alter table public.audit_logs enable row level security;

-- Explicit table grants replace permissive defaults in public.
revoke all on public.profiles, public.zones, public.climate_observations,
  public.weather_forecasts, public.risk_predictions, public.prediction_explanations,
  public.infrastructure, public.impact_assessments, public.priority_assessments,
  public.ai_recommendations, public.incident_reports, public.alerts, public.audit_logs
  from anon, authenticated;
grant select on public.zones, public.climate_observations, public.weather_forecasts,
  public.risk_predictions, public.prediction_explanations, public.infrastructure,
  public.impact_assessments, public.priority_assessments, public.ai_recommendations,
  public.alerts to anon, authenticated;
grant select on public.profiles to authenticated;
grant update(display_name) on public.profiles to authenticated;
grant select, insert, delete on public.incident_reports to authenticated;
grant update(description, contact, status, review_note, reviewed_by) on public.incident_reports to authenticated;
grant insert on public.alerts to authenticated;
grant update(status, approved_by, approved_at) on public.alerts to authenticated;
grant select on public.audit_logs to authenticated;

create policy profile_self_select on public.profiles for select to authenticated using (id = (select auth.uid()));
create policy profile_self_update on public.profiles for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy zones_public_read on public.zones for select to anon, authenticated using (true);
create policy climate_public_read on public.climate_observations for select to anon, authenticated using (true);
create policy forecasts_public_read on public.weather_forecasts for select to anon, authenticated using (true);
create policy predictions_public_read on public.risk_predictions for select to anon, authenticated using (true);
create policy explanations_public_read on public.prediction_explanations for select to anon, authenticated using (true);
create policy infrastructure_verified_read on public.infrastructure for select to anon, authenticated using (verified_at is not null);
create policy impact_public_read on public.impact_assessments for select to anon, authenticated using (true);
create policy priorities_public_read on public.priority_assessments for select to anon, authenticated using (true);
create policy recommendations_approved_read on public.ai_recommendations for select to anon, authenticated using (approved_at is not null);

create policy incidents_select on public.incident_reports for select to authenticated
  using (reporter_id = (select auth.uid()) or (select private.current_role()) in ('authority','admin'));
create policy incidents_insert on public.incident_reports for insert to authenticated
  with check (reporter_id = (select auth.uid()) and status = 'submitted' and reviewed_by is null and review_note is null);
create policy incidents_update on public.incident_reports for update to authenticated
  using ((reporter_id = (select auth.uid()) and status = 'submitted') or (select private.current_role()) in ('authority','admin'))
  with check ((reporter_id = (select auth.uid()) and status = 'submitted') or (select private.current_role()) in ('authority','admin'));
create policy incidents_delete on public.incident_reports for delete to authenticated
  using (reporter_id = (select auth.uid()) and status = 'submitted');

create policy alerts_public_select on public.alerts for select to anon, authenticated using (status = 'published');
create policy alerts_authority_select on public.alerts for select to authenticated using ((select private.current_role()) in ('authority','admin'));
create policy alerts_authority_insert on public.alerts for insert to authenticated
  with check ((select private.current_role()) in ('authority','admin') and created_by = (select auth.uid()) and status = 'draft' and approved_by is null and approved_at is null);
create policy alerts_authority_update on public.alerts for update to authenticated
  using ((select private.current_role()) in ('authority','admin'))
  with check ((select private.current_role()) in ('authority','admin'));

create policy audit_admin_read on public.audit_logs for select to authenticated using ((select private.current_role()) = 'admin');
