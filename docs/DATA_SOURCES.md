# Environmental and geographic data

## Connected services

- Open-Meteo Forecast API: current **model estimates** for temperature, relative humidity and precipitation; hourly precipitation and probability; daily high/low temperature and precipitation. Times use `Asia/Kolkata`, temperature °C, rain mm, probability %.
- Open-Meteo Air Quality API: current CAMS model estimates for **US AQI**, PM2.5, PM10, NO₂, O₃, SO₂ and CO when supplied. Pollutants use μg/m³; US AQI is never represented as Indian AQI.
- Open-Meteo Historical Archive: daily precipitation totals and mean 2 m temperature for a 30-day window ending three days before the request. These are **reanalysis**, not direct station observations.
- OpenStreetMap base tiles and the user-supplied `data/raw/pune_infrastructure.geojson` snapshot are available. OSM features are mapped records, not independently verified emergency facilities. The supplied file is validated locally and can be previewed on the map while PostGIS credentials are unavailable; no database import has occurred.

Open-Meteo responses are cached in process. Current/model estimate rows can be upserted into `climate_observations` and `air_quality_observations` when the Supabase secret key and migration 003 are present. Provider failures return explicit unavailable states. There is no substitute provider or fabricated reading.

## Pune analysis grid

The `pune-core-grid-v1` 3×3 WGS84 grid covers a declared pilot box (south 18.45, north 18.60, west 73.77, east 73.96). Cells are 0.05° latitude by approximately 0.0633° longitude. IDs are deterministic UUIDv5 values; slugs are stable. This box was selected to cover the existing Pune pilot localities. It is **not** an official city or ward boundary. Map display bins for 24-hour forecast rainfall, next-two-day maximum temperature and US AQI are exploratory screening only. They are not physical flood-inundation or impact boundaries.

## OSM ingestion

The supplied GeoJSON was downloaded from OSM through overpass-turbo (file timestamp `2026-10-29T09:39:21Z`, source copyright ODbL). It contains 6,542 features. The importer accepts valid WGS84 point/polygon hospital, school and fire-station features with an actual source name, plus LineString major roads. Polygon facilities retain their original footprint in `osm_geometry` and receive an interior point marker in `location`; all geometry is stored with SRID 4326. It retains OSM type/ID and original tags. It ignores unclassified features and records malformed or unsupported classified features as failures in the report. Existing OSM records are skipped by the database unique keys, never updated or deleted.

From `backend`, install `requirements-geo.txt` and run `python scripts/import_pune_infrastructure.py` to validate without writes. Inspect `data/processed/pune_infrastructure_validation.json`. Apply migrations 001–005, provide a server-side `DATABASE_URL` for the Supabase PostgreSQL connection, then run `python scripts/import_pune_infrastructure.py --import-db`. The report then records actual inserted and already-existing row counts. Repeating the import is safe. Do not put `DATABASE_URL` in frontend environment variables. The previous `scripts/ingest_osm.py --fetch` remains available for a deliberate future Overpass refresh and also skips existing rows. Map interactions use bounded PostGIS RPCs, or the labeled local preview, and never query Overpass.

Current validation: 1,030 facility candidates (692 hospitals, 318 schools, 20 fire stations), 5,438 major-road candidates (1,570 primary, 1,201 secondary, 2,667 tertiary), zero duplicate OSM IDs, and 74 rejected records (73 facilities without source names and one polygon incorrectly tagged as a road). Database inserted count is zero because no `DATABASE_URL` is configured. Map feature counts apply to the current viewport and can be capped; zoom in when the map reports truncation.

## Elevation, population and optional attributes

`scripts/import_zone_datasets.py` requires actual licensed raster files and a metadata JSON containing `dataset_version`, `sources`, acquisition dates, licence, CRS, units, processing steps and limitations. DEM values must be meters. Optional slope rasters must be in degrees and declare `slope_unit: "degrees"`. Population raster cells must represent **people per pixel**; density grids need conversion before import. The utility uses each zone polygon to compute DEM and slope means and population sums, ignoring NoData pixels. Partial pixel intersection is approximate (`all_touched=False`). Optional CSV columns are `zone_slug,drainage_index,historical_flood_exposure,vulnerability_index`, with indices defined on 0–1 and provenance in metadata. Run `--dry-run` before writing. Do not fill missing cells with zero.

A structurally valid DEM and its supplied verified product metadata are now present. Mean slope is persisted for all nine cells. No valid population raster, verified drainage-capacity dataset, vulnerability index or historical flood-exposure dataset has been supplied. The [OSM waterway pipeline](FLOOD_GEOGRAPHY.md) supplies persisted mapped proximity only. WorldPop API population is persisted for all nine cells. Potential flood-exposed population remains unavailable without a validated hazard footprint. See [analysis methods](../ml/README.md) for the current rainfall index and exposure assumptions.

### Pune terrain and WorldPop integration (updated 31 October 2026)

`data/raw/pune_elevation.tif` is a single-band GeoTIFF: EPSG:4326, 684×540 pixels, approximately 1 arcsecond resolution, 9/9 analysis cells covered and all pixels finite. It lacks an embedded vertical unit and NoData marker; the full finite-pixel check records this limitation. The supplied `backend/examples/terrain_population_metadata_verified.json` identifies Copernicus DEM GLO-30 via OpenTopography, declares metres, and supplies citation, access terms and retrieval time. The validation report is `validated`, with 9/9 calculated slopes. All nine slopes are now persisted in the existing Supabase zone metric rows; source SHA256 and metadata are retained. `data/raw/pune_population.tif` remains an invalid placeholder; use the persisted WorldPop API estimates rather than this file.

For a repeat import of the same DEM, use the supplied verified metadata and confirm the raster SHA256 `e25842b9fe6e7f561124e0e1957edd571cbef826f4002ddc39b44ab60a84df2f`. From `backend`:

```text
python scripts/import_pune_terrain_population.py --metadata examples/terrain_population_metadata_verified.json --dem-only
python scripts/import_pune_terrain_population.py --metadata examples/terrain_population_metadata_verified.json --dem-only --import-supabase
```

The first command validates without writes; require report status `validated`. The second uses the configured server-side Supabase secret key and verifies readback. It patches only DEM mean, slope and DEM provenance in the existing WorldPop metric rows, and skips identical source hashes on repeat. The JSON report is `data/processed/pune_zone_metrics_validation.json`; it includes source tags, SHA256, CRS, resolution, NoData/mask validation, covered pixels, mean/min/max elevation and UTM 43N mean slope per cell. The existing `--import-db` route remains available if `DATABASE_URL` is configured. Migration 004 is already present in the current database; do not rerun it. Slope is a screening input, not hydrologic flow modeling.

Alternatively, `python scripts/import_worldpop.py --year YEAR --resolution 100m` requests the nine disjoint GeoJSON grid polygons through the [WorldPop Global2 API v2](https://api.worldpop.org/v2/) and caches successful results by polygon/year/resolution. Inspect `data/processed/pune_worldpop_validation.json`; add `--import-db` and `DATABASE_URL` to persist estimates. Optional `WORLDPOP_API_KEY` stays server-side. The script records source, year, resolution, retrieval time and API task ID. Use the same `dataset_version` (`pune-terrain-population-v1`) as a DEM import so both attributes merge in one row. API polygon totals estimate **people within an analysis cell**, not people exposed to flood or heat. A potential-exposure number remains unavailable until a validated hazard footprint and matching population coverage exist.

A live WorldPop v2 request for dataset year 2025 at 100 m resolution succeeded for all nine nonoverlapping grid cells on 29 October 2026. The cached cell estimates sum to 2,975,502 people across this analysis grid. This is a sourced model estimate, not a census or exposed population count. On 30 October, nine validated estimates were inserted into Supabase through `python scripts/persist_worldpop_supabase.py --import-db` from `backend`; repeat runs skip matching records and do not replace conflicts. The live analysis RPC now reports Supabase provenance. A broader locality such as `pune` does not inherit one grid cell's population.
