create extension if not exists pgcrypto;
create extension if not exists postgis;
create schema if not exists private;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (char_length(display_name) <= 120),
  role text not null default 'citizen' check (role in ('citizen','authority','admin')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.zones (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  city text not null,
  center_lat double precision not null check (center_lat between -90 and 90),
  center_lng double precision not null check (center_lng between -180 and 180),
  boundary geometry(MultiPolygon,4326),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index zones_boundary_gix on public.zones using gist(boundary);
create index zones_city_idx on public.zones(city);

create table public.climate_observations (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  observed_at timestamptz not null,
  temperature_c numeric(5,2),
  humidity_percent numeric(5,2) check (humidity_percent between 0 and 100),
  rainfall_mm numeric(10,2) check (rainfall_mm >= 0),
  aqi integer check (aqi >= 0),
  source text not null,
  created_at timestamptz not null default now(),
  unique(zone_id, observed_at, source)
);
create index climate_observations_zone_time_idx on public.climate_observations(zone_id, observed_at desc);

create table public.weather_forecasts (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  issued_at timestamptz not null,
  valid_at timestamptz not null,
  temperature_c numeric(5,2),
  rainfall_mm numeric(10,2) check (rainfall_mm >= 0),
  source text not null,
  created_at timestamptz not null default now(),
  unique(zone_id, issued_at, valid_at, source)
);
create index weather_forecasts_zone_valid_idx on public.weather_forecasts(zone_id, valid_at);

create table public.risk_predictions (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  hazard text not null check (hazard in ('flood','heat','air_quality')),
  level text not null check (level in ('low','moderate','high','severe')),
  score numeric(5,2) not null check (score between 0 and 100),
  predicted_at timestamptz not null,
  model_version text not null,
  source text not null,
  created_at timestamptz not null default now()
);
create index risk_predictions_zone_time_idx on public.risk_predictions(zone_id, predicted_at desc);

create table public.prediction_explanations (
  id uuid primary key default gen_random_uuid(),
  prediction_id uuid not null references public.risk_predictions(id) on delete cascade,
  factor text not null,
  contribution numeric(7,4),
  explanation text not null,
  source text not null,
  created_at timestamptz not null default now()
);
create index prediction_explanations_prediction_idx on public.prediction_explanations(prediction_id);

create table public.infrastructure (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid references public.zones(id),
  name text not null,
  kind text not null,
  location geometry(Point,4326) not null,
  source text not null,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index infrastructure_location_gix on public.infrastructure using gist(location);
create index infrastructure_zone_idx on public.infrastructure(zone_id);

create table public.impact_assessments (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  prediction_id uuid not null references public.risk_predictions(id),
  population_exposed integer check (population_exposed >= 0),
  infrastructure_exposed integer check (infrastructure_exposed >= 0),
  assessed_at timestamptz not null,
  source text not null,
  created_at timestamptz not null default now()
);
create index impact_assessments_zone_time_idx on public.impact_assessments(zone_id, assessed_at desc);

create table public.priority_assessments (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  score numeric(5,2) not null check (score between 0 and 100),
  rank integer check (rank > 0),
  rationale text not null,
  assessed_at timestamptz not null,
  source text not null,
  created_at timestamptz not null default now()
);
create index priority_assessments_zone_time_idx on public.priority_assessments(zone_id, assessed_at desc);

create table public.ai_recommendations (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  prediction_id uuid references public.risk_predictions(id),
  recommendation text not null,
  model_name text not null check (model_name = 'Nugen'),
  created_at timestamptz not null default now(),
  approved_by uuid references public.profiles(id),
  approved_at timestamptz
);
create index ai_recommendations_zone_time_idx on public.ai_recommendations(zone_id, created_at desc);

create table public.incident_reports (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  locality_id text not null,
  reporter_id uuid not null references public.profiles(id),
  category text not null check (category in ('flood','heat','air_quality','other')),
  description text not null check (char_length(description) between 20 and 2000),
  contact text check (char_length(contact) <= 120),
  location geometry(Point,4326),
  status text not null default 'submitted' check (status in ('submitted','under_review','resolved','rejected')),
  review_note text,
  reviewed_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index incident_reports_reporter_time_idx on public.incident_reports(reporter_id, created_at desc);
create index incident_reports_status_time_idx on public.incident_reports(status, created_at desc);
create index incident_reports_location_gix on public.incident_reports using gist(location);

create table public.alerts (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  locality_id text not null,
  title text not null check (char_length(title) between 5 and 160),
  body text not null check (char_length(body) between 20 and 4000),
  level text not null check (level in ('low','moderate','high','severe')),
  source text not null,
  status text not null default 'draft' check (status in ('draft','published','withdrawn')),
  created_by uuid not null references public.profiles(id),
  approved_by uuid references public.profiles(id),
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint published_requires_independent_review check (status <> 'published' or (approved_by is not null and approved_at is not null and approved_by <> created_by))
);
create index alerts_status_time_idx on public.alerts(status, approved_at desc);
create index alerts_zone_idx on public.alerts(zone_id);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references public.profiles(id),
  action text not null,
  entity_type text not null,
  entity_id uuid,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index audit_logs_actor_time_idx on public.audit_logs(actor_id, created_at desc);
create index audit_logs_entity_idx on public.audit_logs(entity_type, entity_id);

create function private.touch_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end; $$;
create trigger profiles_updated before update on public.profiles for each row execute function private.touch_updated_at();
create trigger zones_updated before update on public.zones for each row execute function private.touch_updated_at();
create trigger infrastructure_updated before update on public.infrastructure for each row execute function private.touch_updated_at();
create trigger incidents_updated before update on public.incident_reports for each row execute function private.touch_updated_at();
create trigger alerts_updated before update on public.alerts for each row execute function private.touch_updated_at();

create function private.handle_new_user() returns trigger language plpgsql security definer set search_path = '' as $$
begin insert into public.profiles(id, role) values (new.id, 'citizen'); return new; end; $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function private.handle_new_user();
insert into public.profiles(id, role)
select id, 'citizen' from auth.users on conflict (id) do nothing;

-- Locality centers are geographic reference points, not hazard or infrastructure observations.
insert into public.zones(slug,name,city,center_lat,center_lng) values
 ('pune','Pune','Pune, Maharashtra',18.5204,73.8567),
 ('shivajinagar','Shivajinagar','Pune, Maharashtra',18.5308,73.8475),
 ('kothrud','Kothrud','Pune, Maharashtra',18.5074,73.8077),
 ('hadapsar','Hadapsar','Pune, Maharashtra',18.4967,73.9414);
