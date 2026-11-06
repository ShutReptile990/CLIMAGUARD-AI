# Data sources, coverage and attribution

[Project overview](../README.md) · [Risk methodology](RISK_METHODOLOGY.md) · [Flood geography](FLOOD_GEOGRAPHY.md)

The grid is a declared Pune **pilot analysis box**, not the Pune municipal boundary. Data availability is reported for the nine cells, not automatically for the whole city. The latest readbacks below are dated local checks; a new deployment must verify its own database and providers.

## Environmental services

| Service | Application use | Time/units and limitation |
| --- | --- | --- |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Current temperature, relative humidity and precipitation; hourly rain/probability; daily temperature and rain forecasts | Asia/Kolkata timestamps; °C, %, mm and mm/h. Provider **model estimates**, not on-site observations |
| [Open-Meteo Historical Archive](https://open-meteo.com/en/docs/historical-weather-api) | Daily rain totals and mean temperature history | Historical **reanalysis**, not local station observations; not substituted for the flood rule's prior-72-hour forecast-model term |
| [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) | Provider US AQI and supported PM2.5, PM10, NO₂, O₃, SO₂, CO | Timestamps and provider units in API response; pollutants usually µg/m³. **US AQI is not Indian AQI** |

The backend uses async httpx, validation, retries/timeouts and an in-process cache. Failed provider streams return explicit unavailable states; no fabricated live reading replaces them. Selected current model records can be persisted in Supabase when its server configuration is present.

Air-quality provider attribution: **Open-Meteo Air Quality API; Copernicus Atmosphere Monitoring Service (CAMS) global model data where supplied.** Open-Meteo's [air-quality documentation](https://open-meteo.com/en/docs/air-quality-api) asks users to credit the underlying CAMS provider as well as Open-Meteo. This source attribution does not turn modeled concentrations into ground-station measurements.

## Pune grid and geographic context

[`pune-core-grid-v1`](../backend/app/services/zones.py) divides 18.45–18.60°N and 73.77–73.96°E into a reproducible 3 × 3 grid in EPSG:4326. Cell slugs A1–C3 map to deterministic UUIDs. The cells are **not official wards or flood boundaries**. Spatial calculations use cell geometry or centroid as documented by each endpoint. Overlapping non-grid localities must not be summed with the disjoint grid population estimates.

| Dataset | Verified local coverage | What it supports and does not support |
| --- | --- | --- |
| [Copernicus DEM GLO-30 via OpenTopography](https://opentopography.org/) | 9/9 cells with persisted mean elevation and mean slope | Cell terrain context and the flood rule's flat-terrain term; no drainage-flow or inundation model |
| [WorldPop Global2 API v2](https://api.worldpop.org/v2/) | 9/9 disjoint cells, 2025 model estimates at 100 m in the validated cache and Supabase | Estimated people **in a cell**, not people exposed to a hazard |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) waterways | 213 source lines stored in PostGIS; 9/9 cell mapped-distance indicators | Proximity to mapped waterway/drain lines, **not** verified capacity, condition or effectiveness |
| OpenStreetMap infrastructure/roads | 1,030 classified facilities and 5,438 major roads imported in the 5 November 2026 project readback | Mapped hospital/school/fire-station markers and road geometry; not verified access, safety or physical damage |

### Terrain provenance

The supplied [`pune_elevation.tif`](../data/raw/pune_elevation.tif) was validated as an EPSG:4326, single-band GeoTIFF with 684 × 540 finite pixels covering all nine cells. It has no embedded vertical-unit or NoData tag; the supplied [verified metadata](../backend/examples/terrain_population_metadata_verified.json) declares metres and names the product. The recorded citation is: **European Space Agency (2024), Copernicus Global Digital Elevation Model, distributed by OpenTopography, DOI 10.5069/G9028PQB**. The metadata retains this rights notice: “Copyright DLR e.V. 2010-2014 and Airbus Defence and Space GmbH 2014-2018; provided under COPERNICUS by the European Union and ESA; all rights reserved.” Check the source terms before redistributing raster assets. The [validation report](../data/processed/pune_zone_metrics_validation.json) records the source hash, CRS, pixel coverage, masks, resolution and cell metrics. The file named [`pune_population.tif`](../data/raw/pune_population.tif) is **not** a usable population GeoTIFF in this repository.

The DEM is currently tracked under `data/raw`. The repository's MIT license covers project code; it does **not** grant separate redistribution rights for third-party raster or OSM data. Confirm the DEM's applicable redistribution terms with its source before making the repository public or bundling the raster into a release.

### WorldPop provenance

The [WorldPop validation report](../data/processed/pune_worldpop_validation.json) records each polygon, dataset year, `100m` resolution, retrieval time, API task identifier and source URL. A 29 October 2026 API readback yielded nine nonoverlapping cell estimates summing to **2,975,502 people across this analysis grid**. That is a provider model estimate, not a Pune city census total or flood-exposed count. The same estimates were persisted without overwriting existing terrain fields. Do not create a Pune-wide total from a mixture of overlapping grid/locality polygons.

### OpenStreetMap attribution and ingestion

**© OpenStreetMap contributors.** OSM data are available under the [Open Database License (ODbL)](https://www.openstreetmap.org/copyright). The map retains OSM tile attribution and per-feature OSM record links. The supplied `pune_infrastructure.geojson` has 6,542 features; [validation](../data/processed/pune_infrastructure_validation.json) accepted 1,030 named facility candidates (692 hospitals, 318 schools, 20 fire stations) and 5,438 major-road candidates, with 74 rejected classified records. Source type/ID, tags, geometry and attribution are preserved in the insert-only importer. Map requests use bounded PostGIS spatial RPCs; they do **not** query public Overpass on every interaction. When database integration is absent, the API can return a labeled validated local preview rather than claiming PostGIS storage.

The waterway [validation report](../data/processed/pune_waterways_validation.json) covers 213 OSM lines and their mapped-distance metrics. See [FLOOD_GEOGRAPHY.md](FLOOD_GEOGRAPHY.md) for its import commands and optional municipal-data format. Any future municipal drainage dataset needs provenance and independent hydraulic attributes before it can be used as a capacity score.

## Reproducible import checks

From `backend`, the following **validate without writing**:

```powershell
.\.venv\Scripts\python.exe scripts\import_pune_infrastructure.py
.\.venv\Scripts\python.exe scripts\import_pune_waterways.py
.\.venv\Scripts\python.exe scripts\import_pune_terrain_population.py --metadata examples/terrain_population_metadata_verified.json --dem-only
.\.venv\Scripts\python.exe scripts\audit_osm_postgis.py
```

The last command is a database readback and requires configured Supabase access. Insert modes (`--import-supabase` or `--import-db`, depending on the script) are deliberate, server-side operations and are unnecessary for the already-populated project. See [database setup](../database/README.md) before applying migrations or imports.

## Missing evidence

No verified drainage-capacity value, historical flood-event exposure series, calibrated flood model or validated hazard footprint is available. A mapped road or hospital intersecting a cell is **co-located**, not flooded or damaged. Potential population exposure remains unavailable. The [dataset audit](../ml/README.md) explains why supervised flood training is disabled.
