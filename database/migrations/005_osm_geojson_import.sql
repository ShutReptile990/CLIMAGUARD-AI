-- Preserve OSM facility footprints while keeping the existing Point marker location.
-- No existing rows are modified. New imports use ON CONFLICT DO NOTHING.
alter table public.infrastructure
  add column osm_geometry geometry(Geometry,4326);
alter table public.infrastructure
  add constraint infrastructure_osm_geometry_valid
  check (osm_geometry is null or st_isvalid(osm_geometry));

-- Bounded map reads from PostGIS. Security invoker keeps table RLS in effect.
create function public.map_infrastructure_bbox(
  p_west double precision, p_south double precision,
  p_east double precision, p_north double precision
)
returns table (
  id uuid, name text, kind text, lat double precision, lng double precision,
  source text, verified_at timestamptz, osm_type text, osm_id bigint,
  total_count bigint
)
language sql stable security invoker set search_path = 'public' as $$
  select i.id, i.name, i.kind, st_y(i.location), st_x(i.location),
    i.source, i.verified_at, i.osm_type, i.osm_id, count(*) over()
  from public.infrastructure i
  where i.kind in ('hospital','school','fire_station')
    and i.location && st_makeenvelope(p_west,p_south,p_east,p_north,4326)
  order by i.kind, i.name, i.osm_type, i.osm_id
  limit 1000
$$;
revoke all on function public.map_infrastructure_bbox(double precision,double precision,double precision,double precision) from public;
grant execute on function public.map_infrastructure_bbox(double precision,double precision,double precision,double precision) to anon, authenticated;

create function public.map_roads_bbox(
  p_west double precision, p_south double precision,
  p_east double precision, p_north double precision
)
returns table (
  id uuid, name text, highway_class text, geometry jsonb,
  osm_type text, osm_id bigint, total_count bigint
)
language sql stable security invoker set search_path = 'public' as $$
  select r.id, r.name, r.highway_class, st_asgeojson(r.geometry,6)::jsonb,
    r.osm_type, r.osm_id, count(*) over()
  from public.osm_roads r
  where r.geometry && st_makeenvelope(p_west,p_south,p_east,p_north,4326)
  order by r.highway_class, r.name, r.osm_id
  limit 2500
$$;
revoke all on function public.map_roads_bbox(double precision,double precision,double precision,double precision) from public;
grant execute on function public.map_roads_bbox(double precision,double precision,double precision,double precision) to anon, authenticated;
