# CLIMAGUARD AI — project context for Nugen

**Project:** CLIMAGUARD AI  
**Tagline:** Predict Earlier. Decide Faster. Protect More.  
**Setting:** Indradhanu Hackathon 2026; Pune-first climate-risk and emergency-response application.  
**Document purpose:** Give the deployed Nugen model and project agents an accurate description of the product, its available evidence, and its operating limits. See [current project status](PROJECT_STATUS.md) for deployment and persistence details.

## 1. Product description

CLIMAGUARD AI helps citizens and local authorities inspect weather, air quality, exploratory hazard screening, mapped infrastructure, incident reports, and official alerts for Pune. It presents information at the level of nine reproducible geographic **analysis cells**. Citizens can report observed conditions; authorized authorities can review reports and manage alerts. The product distinguishes model estimates, historical reanalysis, mapped assets, verified observations, heuristic scores, and hypothetical simulations.

The application is intended to support awareness and review. It does **not** issue official meteorological warnings, validate flood-inundation boundaries, prove that a building or road is flooded, or automate emergency dispatch.

## 2. Existing implementation

- **Frontend:** React, TypeScript, Vite, React Router, TanStack Query, React Leaflet, and Recharts. It has citizen and authority views, a Pune map, analysis cards, comparison rankings, a what-if simulator, incident screens, alerts, and loading/empty/error states. With Supabase browser configuration present it starts in live mode; the explicit **DEMO** toggle uses illustrative data.
- **Backend:** FastAPI with modular API, schemas, services, repositories, and integrations. Pydantic validates requests and responses. It provides CORS, structured logging, health checks, timeout/retry handling, and centralized errors.
- **Database:** Supabase PostgreSQL with PostGIS. Migrations 001–008 are applied and the project owner reports 009 and 010 applied. A read-only probe confirmed migration 010's new column, while live self-approval is pending. They define profiles, zones, environmental records, infrastructure, waterways, incident reports, alerts, audit logs, sourced metrics and Nugen draft metadata. Row Level Security restricts access. WorldPop, slope, mapped-drain metrics and 213 OSM waterways are persisted. The 1 November 2026 Nugen smoke test stored a new unapproved recommendation draft.
- **Authentication:** Supabase Auth. Roles are `citizen`, `authority`, and `admin`. New accounts are citizens. FastAPI verifies bearer tokens and reads roles from database profiles. Citizens manage their reports; authorities review reports and manage official alerts; admins assign roles. A user cannot grant themselves authority or admin access. Browser code uses publishable credentials; privileged keys remain server-side.
- **Nugen status:** Deployed aligned inference is connected server-side through FastAPI. Citizen and authority guidance use current deterministic analysis, with response validation and explicit unavailable states. The authority route checks the database role. No other LLM provider is used. The existing recommendation API still returns only approved stored recommendations.

## 3. Geographic scope

The current pilot is a deterministic 3×3 Pune grid, `pune-core-grid-v1`, covering approximately 18.45–18.60° N and 73.77–73.96° E. Each cell has a stable ID, polygon, centroid, and source metadata. Cells are **not official municipal wards**. Map colors are screening bins, **not physical flood extents**. Clicking a cell selects the corresponding dashboard context.

The map can show OpenStreetMap hospitals, schools, fire stations, and major roads with layer toggles and source links. Their records are mapped, not independently verified emergency facilities. The facility/road GeoJSON remains a clearly labeled local preview; no `osm_import_runs` record exists. The 213 OSM waterways are in PostGIS.

## 4. Data sources and present coverage

| Source | Used for | Current status and limitation |
| --- | --- | --- |
| Open-Meteo Forecast API | Temperature, humidity, precipitation, hourly rain/probability, daily forecasts | Connected. Values are provider **model estimates**, with timestamps and units; not rain-gauge observations. |
| Open-Meteo Historical Archive | Earlier daily rainfall and temperature | Connected. Historical **reanalysis**, not direct station observations. |
| Open-Meteo Air Quality API | US AQI, PM2.5, PM10 and supported gases | Connected. Pollutants carry units/timestamps. **US AQI must never be called Indian AQI.** |
| WorldPop Global2 API v2 | Population within the nine analysis polygons | A 2025, 100 m request succeeded for 9/9 cells, is cached locally, and all nine validated estimates are persisted in Supabase. This is modeled population **in a cell**, not flood-exposed population. |
| OpenStreetMap infrastructure GeoJSON | Mapped facilities and roads | Validated: 1,030 named facility candidates and 5,438 major-road candidates; 74 source records rejected, with reasons in the validation report. Local preview available; PostGIS import pending. |
| OpenStreetMap waterways GeoJSON | Rivers, streams, canals, drains, ditches, culvert tags | Validated and persisted: 213/213 lines; mapped drain proximity for 9/9 cells. **No capacity, condition, or effectiveness is known.** |
| Copernicus DEM | Elevation and slope | A valid GeoTIFF and supplied source metadata produced persisted mean slope for 9/9 cells. A slope statistic is not a flood-depth prediction. |
| Local population raster | Raster-based population coverage | **Unavailable.** `data/raw/pune_population.tif` currently contains GeoJSON, not a GeoTIFF. WorldPop API estimates are the available population source. |
| Verified historical flood events | Historical exposure and supervised training labels | **Unavailable.** Zero verified positive and zero verified negative labels. Citizen incident reports are not training labels. |
| Municipal drainage or validated hazard footprints | Hydraulic capacity, inundation/exposure assessment | **Unavailable.** Import formats exist, but no authoritative dataset or validated hazard geometry has been supplied. |

Source availability can change. A Nugen response must use the source, timestamp, coverage, and missing-data status included in the **current API payload**, rather than assuming this document is a live feed.

## 5. Risk and impact methods

### Flood

The active `flood-rainfall-index-v1` is a deterministic **0–100 heuristic screening index**, not a calibrated flood probability. Available forecast 24-hour rainfall, peak hourly rainfall, prior 72-hour model rainfall, and optional sourced mean slope, verified drainage capacity, and historical flood exposure contribute with documented weights. Missing terms are disclosed and the available weights are renormalized. Mapped drain proximity and culvert counts **do not** fill the drainage-capacity term or change the index.

No valid labeled flood-event dataset exists. No XGBoost model was trained; no precision, recall, F1, PR-AUC, calibration score, or SHAP explanation exists. The loader refuses absent or unevaluated artifacts. Nugen must not imply that these capabilities exist.

### Heat and air quality

Heat screening uses current temperature, humidity, the NWS heat-index equation only in its valid domain, and relevant forecast highs. Configurable thresholds categorize the screening result. This is **not an officially issued heatwave warning**. Air quality uses the provider's **US AQI** category and pollutant values; it does not infer Indian AQI from US AQI.

### Geographic impact and priority

PostGIS/GeoPandas intersections can count mapped hospitals, schools, emergency services, and road length within an analysis cell. Intersection means **co-location**, not physical damage. WorldPop provides cell population; potential exposed population remains **unavailable** without both a validated hazard footprint and matching population coverage.

`emergency-screening-priority-v1` ranks cells provisionally using hazard screening (40%), zone population (30%), mapped critical assets (20%), and sourced vulnerability (10%), renormalizing for missing inputs. It is **not an operational dispatch order**. `vulnerability-screening-v1` is itself provisional and requires population plus two more independent sourced domains; current data do not meet that gate.

### What-if simulation

Users can enter hypothetical rain intensity/duration, temperature, humidity, and drainage assumptions. Outputs are labeled **SIMULATION MODE**, remain separate from live data, and reset to current inputs. They are not forecasts, alerts, or observed conditions.

## 6. Main API surfaces

The frontend calls `/api/v1`; unversioned `/api` routes also exist. Relevant routes include:

- `GET /api/health` — service/configuration status.
- `GET /api/zones/geojson`, `/api/map/screening`, `/api/map/infrastructure`, `/api/map/roads` — analysis grid and map layers.
- `GET /api/environment/{zone_id}` and related environmental routes — sourced weather, air, and history with unavailable states.
- `GET /api/analysis/{zone_id}` — hazard assessments, factors, warnings, source freshness, rules version, feature availability, and provenance.
- `GET /api/analysis/{zone_id}/exposure` — mapped co-location and cell population; potential exposed population is unavailable without a validated footprint.
- `GET /api/analysis/compare`, `POST /api/analysis/simulate` — provisional ranking and explicitly hypothetical scenarios.
- `GET /api/nugen/status`, `POST /api/nugen/citizen/{zone_id}`, `POST /api/nugen/authority/{zone_id}` — real inference status and guidance; authority route requires authority/admin identity.
- `/api/profile`, `/api/incidents`, `/api/alerts` — protected identity, citizen reports, authority review, and official alerts.
- `GET /api/recommendations?zone_id=...` — approved stored Nugen recommendations only; currently unavailable without approved records.

Use the actual typed FastAPI schemas and OpenAPI document for implementation details. Do not infer a Nugen API request/response format from this project description.

## 7. Nugen alignment instructions

The following behavior brief describes how to ground Nugen guidance. The FastAPI integration uses the deployed chat-completions request shape verified by `backend/scripts/smoke_nugen.py`.

> You are the CLIMAGUARD AI explanation and preparedness assistant for the Pune pilot. Use only current, explicitly supplied application data. Identify each value as observed, model-estimated, historical reanalysis, mapped, heuristic, simulated, or unavailable. Include zone name, source, timestamp, units, forecast horizon, and missing-data limitations when relevant. Explain the documented flood, heat, US AQI, geographic co-location, and priority rules in plain language. Give cautious, general preparedness actions and direct users to current official authority advisories for urgent decisions. Never invent a sensor reading, facility, flood extent, verified incident, model metric, probability, SHAP contribution, municipal boundary, or official warning. Never convert US AQI to Indian AQI by relabeling. Never treat a citizen report as a verified training label. Do not claim that mapped drains work or that intersecting assets are damaged. Treat SIMULATION MODE inputs as hypothetical. If the needed evidence is missing or stale, say what is unavailable and why. Do not publish an alert, approve a recommendation, assign a role, or claim authority review occurred; those actions require the existing authenticated backend workflow.

**Implemented boundary:** FastAPI sends source-attributed live analysis for the selected locality to Nugen server-side, validates its response and stores an unapproved draft with model ID, inference time and source-analysis JSON. The 1 November 2026 B2 smoke test returned HTTP 200 and Supabase stored the draft. Official alerts require explicit authenticated authority approval and publication; migration 010 permits one authority to perform both. Nugen and privileged database credentials stay server-side.

## 8. Truthfulness and privacy rules for generated text

1. Separate **observations**, provider estimates, historical reanalysis, derived indices, mapped features, and simulations in wording.
2. State whether a flood score is a heuristic index or an evaluated model output. Today it is only a heuristic.
3. Do not turn cell population into an exposed, injured, or displaced population estimate.
4. Do not use OSM facility or waterway presence as proof of operational readiness, drainage capacity, or safety.
5. Do not portray grid cells as official wards or risk colors as inundation boundaries.
6. Respect citizen/authority/admin roles and do not expose private reports, contact details, credentials, or raw privileged records in generated public text.
7. If an external provider fails, report an unavailable state; do not fill gaps with plausible numbers.
8. Prefer short, actionable, citizen-friendly explanations while preserving source and uncertainty labels.

## 9. Repository references

- [Architecture](ARCHITECTURE.md)
- [Current project status](PROJECT_STATUS.md)
- [Environmental data sources](DATA_SOURCES.md)
- [Flood geography and label pipeline](FLOOD_GEOGRAPHY.md)
- [Risk methods and evidence](../ml/README.md)
- [Dataset training audit](../ml/dataset_audit.json)

**Last checked against repository:** 1 November 2026. This file is a project handoff, not a live status endpoint.
