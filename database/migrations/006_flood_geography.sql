-- Mapped watercourses and optional authoritative drainage lines are context,
-- not evidence of hydraulic capacity, effectiveness, or flood extent.
create table public.waterways (
  id uuid primary key default gen_random_uuid(),
  source_kind text not null check (source_kind in ('OpenStreetMap','municipal')),
  source_dataset text not null,
  external_id text not null,
  name text,
  waterway_class text not null,
  is_culvert boolean not null default false,
  geometry geometry(MultiLineString,4326) not null,
  source_tags jsonb not null default '{}'::jsonb,
  provenance jsonb not null,
  imported_at timestamptz not null default now(),
  unique (source_dataset, external_id),
  check (st_isvalid(geometry) and not st_isempty(geometry))
);
create index waterways_geometry_gix on public.waterways using gist (geometry);
create index waterways_kind_idx on public.waterways (source_kind, waterway_class);
alter table public.waterways enable row level security;
revoke all on public.waterways from anon, authenticated;
grant select on public.waterways to anon, authenticated;
create policy waterways_read on public.waterways for select to anon, authenticated using (true);

alter table public.zone_dataset_metrics
  add column mapped_waterway_distance_m numeric(10,2) check (mapped_waterway_distance_m >= 0),
  add column mapped_drain_distance_m numeric(10,2) check (mapped_drain_distance_m >= 0),
  add column mapped_culvert_count integer check (mapped_culvert_count >= 0);

create function public.analysis_zone_flood_features_all()
returns table (slug text, mapped_waterway_distance_m numeric,
               mapped_drain_distance_m numeric, mapped_culvert_count integer)
language sql stable security invoker set search_path = 'public' as $$
  select z.slug, m.mapped_waterway_distance_m, m.mapped_drain_distance_m, m.mapped_culvert_count
  from public.zones z
  left join lateral (
    select d.mapped_waterway_distance_m, d.mapped_drain_distance_m, d.mapped_culvert_count
    from public.zone_dataset_metrics d where d.zone_id = z.id
    order by d.computed_at desc limit 1
  ) m on true
  where z.metadata->>'kind' = 'analysis_grid'
$$;
revoke all on function public.analysis_zone_flood_features_all() from public;
grant execute on function public.analysis_zone_flood_features_all() to anon, authenticated;

create table public.verified_flood_labels (
  id uuid primary key default gen_random_uuid(),
  event_id text not null unique,
  observed_at timestamptz not null,
  temporal_resolution_hours integer not null check (temporal_resolution_hours between 1 and 168),
  location geometry(Point,4326) not null,
  zone_id uuid references public.zones(id),
  observed_flood boolean not null,
  source text not null,
  verification_reference text not null,
  observation_method text not null,
  provenance jsonb not null default '{}'::jsonb,
  imported_at timestamptz not null default now()
);
create index verified_flood_labels_time_idx on public.verified_flood_labels (observed_at);
create index verified_flood_labels_location_gix on public.verified_flood_labels using gist (location);
alter table public.verified_flood_labels enable row level security;
revoke all on public.verified_flood_labels from anon, authenticated;
-- Verified event labels are held server-side for audited model development.
