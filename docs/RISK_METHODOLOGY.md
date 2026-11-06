# Climate-risk screening methodology

[Project overview](../README.md) · [Source provenance](DATA_SOURCES.md) · [Training-data audit](../ml/README.md)

## What the scores mean

The backend returns rule versions, contributing factors, source information, timestamps and warnings. Missing inputs are unavailable, not zero. The 3 × 3 Pune polygons are analysis cells, not flood-inundation boundaries. No verified flood-event label set or held-out model evaluation exists, so **no calibrated flood probability, XGBoost performance or SHAP explanation** is produced.

## Flood rainfall index v1

`flood-rainfall-index-v1` is a 0–100 **heuristic**. For each available feature, compute a term in `[0, 1]`, multiply by its weight, sum those products, divide by the sum of *available* weights, and multiply by 100. The service clamps terms and rounds the final score to one decimal place.

| Input | Normalized risk term | Weight | Current availability |
| --- | --- | ---: | --- |
| Forecast next-24-hour rain, mm | `min(max(rain / 100, 0), 1)` | 0.35 | Live forecast or explicitly hypothetical scenario |
| Peak hourly rain, mm/h | `min(max(peak / 30, 0), 1)` | 0.20 | Live forecast or explicitly hypothetical scenario |
| Prior 72-hour model rain, mm | `min(max(rain / 150, 0), 1)` | 0.20 | Only when recent model hours are supplied; absent in isolated demo |
| Flat-terrain indicator, mean slope in degrees | `1 − min(max(slope / 10, 0), 1)` | 0.05 | Sourced DEM for individual grid cells; no Pune-wide aggregate |
| Drainage deficiency, verified 0–1 capacity | `1 − capacity` | 0.10 | Unavailable; mapped distance is **not** capacity |
| Verified historical flood exposure, 0–1 | `exposure` | 0.10 | Unavailable without verified event evidence |

Default category thresholds are **Low <25**, **Moderate 25–<50**, **High 50–<75**, **Severe ≥75**; server environment variables can change them. These are planning assumptions, not locally calibrated event frequencies. If future rain is absent, flood screening is unavailable. When optional terms are absent, the API lists them and renormalizes the available weights. Mean elevation, WorldPop population and mapped-drain distance are context, not substituted flood-score inputs. The Pune overview omits cell-only slope and mapped-distance values rather than claiming a city-wide average.

The extreme-rainfall demo supplies 25 mm/h for six hours, making a hypothetical 150 mm total and 25 mm/h peak. Its 6 November 2026 PostGIS readback yielded cell scores from 89.4 to 92.4; all are Severe under the existing threshold. This is an explainable sensitivity demonstration, not evidence that those cells are currently flooded.

## Heat screening

`heat-index-rules-v1` uses current temperature and humidity where available. The NWS Rothfusz regression is applied only in its supported warm domain; otherwise air temperature is used. The screening value is the larger of that current apparent/air temperature and the next three daily forecast highs. Future humidity is not supplied, so forecast highs are **not** forecast heat indices. Default bands are Low <32°C, Moderate 32–<40°C, High 40–<50°C and Severe ≥50°C. These are project screening bands, **not an official heatwave warning**.

## Air-quality screening

The provider's **US AQI** is reported as a measured index, not a 0–100 probability and not Indian AQI. Categories follow the US AQI breakpoints: Good 0–50, Moderate 51–100, Unhealthy for Sensitive Groups 101–150, Unhealthy 151–200, Very Unhealthy 201–300, Hazardous 301+. PM2.5 and PM10 are shown in µg/m³ with provider timestamps. When US AQI is absent, the backend does not derive a category from partial pollutant values. No AQI simulation override exists.

## Geographic exposure and priority

PostGIS intersects analysis cells with mapped roads and facilities, reporting co-location rather than physical damage. WorldPop estimates people *in a cell*, not people in a hazard footprint. Potential exposed population remains unavailable until a validated hazard geometry and matching population coverage exist.

`emergency-screening-priority-v1` combines maximum normalized hazard (40%), population (30%), mapped critical-facility count (20%) and sourced vulnerability (10%). It discloses missing components and renormalizes the available weights. Ranking is provisional screening, not a dispatch instruction. See the exact normalization and dataset audit in [`ml/README.md`](../ml/README.md).

## Simulation boundary

`POST /api/v1/analysis/simulate` accepts bounded hypothetical rain, temperature, humidity and optional drainage **assumptions** for a selected zone; it preserves a separate live baseline. Demo Mode's `GET /api/v1/analysis/demo/extreme-rainfall` applies one server-owned rainfall preset to all nine cells without fetching live environmental streams or writing observations. Both modes label simulated outputs. Neither can publish an alert, create an incident or claim a validated flood boundary.
