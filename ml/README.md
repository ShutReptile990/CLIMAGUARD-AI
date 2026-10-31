# Climate analysis method and evidence

## Dataset audit

The repository contains no timestamped, zone-linked labeled flood events and no defensible negative examples. Citizen incident reports are unverified and are not training labels. The machine-readable audit is [dataset_audit.json](dataset_audit.json). No XGBoost model was trained, no precision/recall/F1/PR-AUC/calibration metrics exist, and no SHAP values are generated. `app/services/model_registry.py` refuses to load an absent or unevaluated XGBoost artifact. No synthetic model artifact is supplied.

A future training set must include event/non-event labels with source provenance, issue-time feature snapshots, spatial identifiers, observation windows, and enough events for independent temporal holdouts. Train/validation/test periods must be ordered by issue time, and all rolling rainfall and exposure features must be computed using only data available before each prediction time. An eventual XGBoost release must report precision, recall, F1, PR-AUC, reliability/calibration, splits, feature schema and version before activation. SHAP applies only to that trained model.

## Flood rainfall index v1

`flood-rainfall-index-v1` is a **heuristic screening index**, 0–100 points, not a calibrated probability or mapped inundation. For each available feature, calculate the normalized risk term below, multiply by its weight, divide the sum by the sum of available weights, then multiply by 100. Values are clamped to 0–1 before weighting. Missing features are listed and remaining weights are renormalized.

| Feature | Normalized term | Weight |
| --- | --- | ---: |
| Next 24-hour forecast rain (mm) | `min(rain / 100, 1)` | 0.35 |
| Peak forecast hourly rain (mm/h) | `min(peak / 30, 1)` | 0.20 |
| Prior 72-hour model rain (mm) | `min(rain / 150, 1)` | 0.20 |
| Mean terrain slope (degrees) | `1 - min(slope / 10, 1)` | 0.05 |
| Drainage capacity (0–1) | `1 - capacity` | 0.10 |
| Historical flood exposure (0–1) | `exposure` | 0.10 |

The rainfall denominators and index bands (<25 low, 25–49.9 moderate, 50–74.9 high, ≥75 severe) are **transparent planning assumptions**, not local hydrologic calibration. Temperature and elevation alone are not used as flood predictors. DEM mean elevation is retained as provenance context; relative elevation needs a validated hydrologic model before scoring. Open-Meteo `past_days` rain is model-derived, not a station observation. The separate archive ends three days back and is not used as a recent-rainfall surrogate. No flood polygon is produced.

## Heat rules v1

The NWS Rothfusz heat-index equation is calculated for current air temperature ≥26.7°C when the regression's initial check reaches 80°F and humidity is valid. Outside this domain the current air temperature is used. The screening temperature is the greater of current apparent temperature and the next three daily forecast high temperatures; future humidity is unavailable, so forecast highs are **not** future heat indices. Bands are <32°C low, 32–39.9 moderate, 40–49.9 high, ≥50 severe. These project thresholds are configurable with `HEAT_MODERATE_C`, `HEAT_HIGH_C`, `HEAT_SEVERE_C`. They are **not** an official heatwave warning. Equation background: https://www.weather.gov/tbw/heatindex

## Air-quality rules v1

The provider's **US AQI** is categorized using US EPA/AirNow cutoffs: 0–50 Good, 51–100 Moderate, 101–150 Unhealthy for Sensitive Groups, 151–200 Unhealthy, 201–300 Very Unhealthy, ≥301 Hazardous. The displayed numeric score is US AQI itself, not a 0–100 probability. The API does not derive Indian AQI from PM. PM2.5 and PM10 trends show model estimates in μg/m³, with hourly timestamps. Source: https://www.airnow.gov/aqi/aqi-basics/

## Geographic co-location and priority v1

PostGIS migration 004 intersects each grid cell with imported OSM point and road geometries (`ST_Intersects`, clipped `ST_Intersection`). A GeoPandas/Shapely offline check implements the same conceptual intersection and measures road length in UTM zone 43N. Facility counts are **mapped assets in a cell**, not flooded or damaged assets. Population is an imported zone estimate, not the number harmed. Until a validated hazard footprint exists, physical exposure is unavailable.

`emergency-screening-priority-v1` uses 40% maximum normalized hazard screening, 30% population (`min(people / 100000, 1)`), 20% critical facility count (`min(count / 10, 1)`), and 10% sourced vulnerability (0–1). Heat is normalized as `clamp((screening_temperature_c - 25) / 30, 0, 1)` and US AQI as `min(AQI / 300, 1)`; flood uses its 0–100 index divided by 100. Missing components are disclosed and available weights renormalized. A hazard signal is mandatory to rank. Ranks are provisional analysis-cell comparisons, not dispatch instructions.

## Simulation

The simulator substitutes hypothetical hourly rain intensity for a chosen duration (up to 24 h), current temperature, humidity, and/or drainage capacity. It recalculates supported rules and the selected cell's provisional rank, retaining the live baseline separately. It never writes a forecast, alert, trained prediction, or incident. `SIMULATION MODE` is shown on output; reset discards the hypothetical inputs.
