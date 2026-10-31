-- Screening context only: grid intersections do not establish damage or inundation.
alter table public.zone_dataset_metrics add column slope_mean_degrees numeric(8,3)
  check (slope_mean_degrees >= 0 and slope_mean_degrees <= 90);
alter table public.zone_dataset_metrics add column vulnerability_index numeric(6,4)
  check (vulnerability_index between 0 and 1);

create table public.osm_import_runs (
  id uuid primary key default gen_random_uuid(),
  imported_at timestamptz not null default now(),
  source text not null default 'OpenStreetMap via Overpass',
  facility_count integer not null check (facility_count >= 0),
  road_count integer not null check (road_count >= 0),
  provenance jsonb not null default '{}'::jsonb
);
alter table public.osm_import_runs enable row level security;
revoke all on public.osm_import_runs from anon, authenticated;
grant select on public.osm_import_runs to anon, authenticated;
create policy osm_import_runs_read on public.osm_import_runs for select to anon, authenticated using (true);

create function public.analysis_zone_context_all()
returns table (
  slug text,
  dataset_version text,
  dem_mean_m numeric,
  slope_mean_degrees numeric,
  drainage_index numeric,
  historical_flood_exposure numeric,
  population_estimate bigint,
  vulnerability_index numeric,
  provenance jsonb,
  mapped_hospitals integer,
  mapped_schools integer,
  mapped_emergency_services integer,
  road_length_km numeric
)
language sql stable security invoker set search_path = 'public' as $$
  select z.slug, m.dataset_version, m.dem_mean_m, m.slope_mean_degrees,
    m.drainage_index, m.historical_flood_exposure, m.population_estimate,
    m.vulnerability_index, m.provenance,
    case when o.imported then coalesce(f.hospitals, 0) else null end,
    case when o.imported then coalesce(f.schools, 0) else null end,
    case when o.imported then coalesce(f.emergency_services, 0) else null end,
    case when o.imported then coalesce(r.length_km, 0) else null end
  from public.zones z
  cross join (select exists(select 1 from public.osm_import_runs) as imported) o
  left join lateral (
    select d.dataset_version, d.dem_mean_m, d.slope_mean_degrees,
      d.drainage_index, d.historical_flood_exposure, d.population_estimate,
      d.vulnerability_index, d.provenance
    from public.zone_dataset_metrics d where d.zone_id = z.id
    order by d.computed_at desc limit 1
  ) m on true
  left join lateral (
    select count(*) filter (where i.kind = 'hospital')::integer as hospitals,
      count(*) filter (where i.kind = 'school')::integer as schools,
      count(*) filter (where i.kind in ('fire_station','police','ambulance_station','mapped_shelter'))::integer as emergency_services
    from public.infrastructure i
    where z.boundary is not null and st_intersects(i.location, z.boundary)
  ) f on true
  left join lateral (
    select round((sum(st_length(st_collectionextract(st_intersection(road.geometry, z.boundary), 2)::geography)) / 1000)::numeric, 2) as length_km
    from public.osm_roads road
    where z.boundary is not null and st_intersects(road.geometry, z.boundary)
  ) r on true
  where z.metadata->>'kind' = 'analysis_grid'
  order by z.slug
$$;
revoke all on function public.analysis_zone_context_all() from public;
grant execute on function public.analysis_zone_context_all() to anon, authenticated;
