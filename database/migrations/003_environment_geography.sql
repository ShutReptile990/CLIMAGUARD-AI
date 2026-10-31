-- Current Open-Meteo values are model estimates, not station observations.
alter table public.climate_observations add column data_kind text not null default 'unknown_legacy'
  check (data_kind in ('unknown_legacy','station_observation','current_model_estimate'));
alter table public.weather_forecasts add column precipitation_probability_percent numeric(5,2)
  check (precipitation_probability_percent between 0 and 100);
alter table public.weather_forecasts add column temperature_max_c numeric(5,2);
alter table public.weather_forecasts add column temperature_min_c numeric(5,2);
alter table public.weather_forecasts add column forecast_kind text not null default 'forecast'
  check (forecast_kind = 'forecast');

create table public.air_quality_observations (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  valid_at timestamptz not null,
  us_aqi integer check (us_aqi >= 0),
  pm2_5 numeric(10,2) check (pm2_5 >= 0),
  pm10 numeric(10,2) check (pm10 >= 0),
  nitrogen_dioxide numeric(10,2) check (nitrogen_dioxide >= 0),
  ozone numeric(10,2) check (ozone >= 0),
  sulphur_dioxide numeric(10,2) check (sulphur_dioxide >= 0),
  carbon_monoxide numeric(10,2) check (carbon_monoxide >= 0),
  source text not null,
  data_kind text not null check (data_kind = 'current_model_estimate'),
  created_at timestamptz not null default now(),
  unique(zone_id, valid_at, source)
);
create index air_quality_zone_time_idx on public.air_quality_observations(zone_id, valid_at desc);
alter table public.air_quality_observations enable row level security;
revoke all on public.air_quality_observations from anon, authenticated;
grant select on public.air_quality_observations to anon, authenticated;
create policy air_quality_public_read on public.air_quality_observations for select to anon, authenticated using (true);

alter table public.zones add column metadata jsonb not null default '{}'::jsonb;
-- This fixed analysis grid is reproducible from the extent and 3x3 specification.
-- It is not an official Pune ward boundary or a flood-inundation polygon.
with cells(id,slug,row_num,col_num) as (
  values
  ('c74abcf0-6b74-5fe2-ab83-4aafd31161c1'::uuid,'pune-grid-r1-c1',1,1),
  ('ab285537-6c72-5cfb-b71a-2a0918691c2a'::uuid,'pune-grid-r1-c2',1,2),
  ('0231fe4a-197b-502c-8225-e174d92b0325'::uuid,'pune-grid-r1-c3',1,3),
  ('dc2699fb-d6b5-5722-91e5-3ee96af48f66'::uuid,'pune-grid-r2-c1',2,1),
  ('e631d13e-ba9d-576d-b97d-d8d31828e1e7'::uuid,'pune-grid-r2-c2',2,2),
  ('f87edca6-1f2d-555d-b35e-5f7a0967258d'::uuid,'pune-grid-r2-c3',2,3),
  ('3b74def4-b2ed-5ae6-af34-9577e29083ef'::uuid,'pune-grid-r3-c1',3,1),
  ('e20aec1f-ba7d-5193-b7c7-6f17eb88323a'::uuid,'pune-grid-r3-c2',3,2),
  ('a750c628-b06a-5e19-8403-e27f0f741b4f'::uuid,'pune-grid-r3-c3',3,3)
)
insert into public.zones(id,slug,name,city,center_lat,center_lng,boundary,metadata)
select id, slug, 'Pune grid ' || chr(64 + row_num) || col_num::text,
  'Pune, Maharashtra',
  18.45 + (row_num - 0.5) * 0.05,
  73.77 + (col_num - 0.5) * ((73.96 - 73.77) / 3),
  st_multi(st_makeenvelope(73.77 + (col_num - 1) * ((73.96 - 73.77) / 3),
                           18.45 + (row_num - 1) * 0.05,
                           73.77 + col_num * ((73.96 - 73.77) / 3),
                           18.45 + row_num * 0.05, 4326)),
  jsonb_build_object('kind','analysis_grid','grid_version','pune-core-grid-v1','official_boundary',false)
from cells on conflict (slug) do nothing;

alter table public.infrastructure add column osm_type text;
alter table public.infrastructure add column osm_id bigint;
alter table public.infrastructure add column osm_tags jsonb not null default '{}'::jsonb;
create unique index infrastructure_osm_unique on public.infrastructure(osm_type,osm_id) where osm_type is not null;
drop policy infrastructure_verified_read on public.infrastructure;
create policy infrastructure_mapped_read on public.infrastructure for select to anon, authenticated
  using (verified_at is not null or source = 'OpenStreetMap');

create table public.osm_roads (
  id uuid primary key default gen_random_uuid(),
  osm_type text not null,
  osm_id bigint not null,
  name text,
  highway_class text not null,
  geometry geometry(LineString,4326) not null,
  osm_tags jsonb not null default '{}'::jsonb,
  source text not null default 'OpenStreetMap',
  imported_at timestamptz not null default now(),
  unique(osm_type,osm_id)
);
create index osm_roads_geometry_gix on public.osm_roads using gist(geometry);
alter table public.osm_roads enable row level security;
revoke all on public.osm_roads from anon, authenticated;
grant select on public.osm_roads to anon, authenticated;
create policy osm_roads_read on public.osm_roads for select to anon, authenticated using (true);

create table public.zone_dataset_metrics (
  id uuid primary key default gen_random_uuid(),
  zone_id uuid not null references public.zones(id),
  dataset_version text not null,
  dem_mean_m numeric(10,2),
  population_estimate bigint check (population_estimate >= 0),
  drainage_index numeric(10,4),
  historical_flood_exposure numeric(10,4),
  provenance jsonb not null,
  computed_at timestamptz not null default now(),
  unique(zone_id,dataset_version)
);
create index zone_dataset_metrics_zone_idx on public.zone_dataset_metrics(zone_id);
alter table public.zone_dataset_metrics enable row level security;
revoke all on public.zone_dataset_metrics from anon, authenticated;
grant select on public.zone_dataset_metrics to anon, authenticated;
create policy zone_dataset_metrics_read on public.zone_dataset_metrics for select to anon, authenticated using (true);

-- Security-invoker functions respect table RLS and expose mapped geometry as simple JSON.
create function public.map_infrastructure()
returns table(id uuid, name text, kind text, lat double precision, lng double precision,
              source text, verified_at timestamptz, osm_type text, osm_id bigint)
language sql stable security invoker set search_path = 'public' as $$
  select i.id, i.name, i.kind, st_y(i.location), st_x(i.location),
         i.source, i.verified_at, i.osm_type, i.osm_id
  from public.infrastructure i
  where i.location && st_makeenvelope(73.77,18.45,73.96,18.60,4326)
  order by i.kind, i.name limit 1000
$$;
revoke all on function public.map_infrastructure() from public;
grant execute on function public.map_infrastructure() to anon, authenticated;

create function public.map_roads()
returns table(id uuid, name text, highway_class text, geometry jsonb, osm_id bigint)
language sql stable security invoker set search_path = 'public' as $$
  select r.id, r.name, r.highway_class, st_asgeojson(r.geometry)::jsonb, r.osm_id
  from public.osm_roads r
  where r.geometry && st_makeenvelope(73.77,18.45,73.96,18.60,4326)
  order by r.highway_class, r.name limit 2000
$$;
revoke all on function public.map_roads() from public;
grant execute on function public.map_roads() to anon, authenticated;
