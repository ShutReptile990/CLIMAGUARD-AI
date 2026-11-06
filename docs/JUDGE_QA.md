# CLIMAGUARD AI — judge Q&A

**What problem does this solve?** It puts live weather and air-quality estimates, sourced geographic context, cautious risk screening, citizen reports and a human-approved alert workflow in one Pune-focused product.

**Why Nugen?** The hackathon requires an aligned model. The deployed Nugen model is the application's only LLM integration. FastAPI sends it validated, source-backed analysis and asks for practical citizen or authority guidance; it never computes the risk index or publishes an alert.

**What exactly was aligned?** The project owner reports a deployed climate-response Qwen model, ID `model_01m66gqc3qk10zdy`. This repository proves the configured deployed endpoint, prompt contract, response validation and successful inference. It does **not** contain the alignment training set, procedure or held-out alignment evaluation, so we do not claim specific training metrics.

**How does flood screening work?** A documented deterministic heuristic combines available rainfall forecast intensity and accumulation, recent rainfall context, and optional sourced terrain/other indicators. Missing inputs are disclosed and weights are adjusted by the rule. The current score is a screening index from 0 to 100.

**Why is it not a flood probability?** There are no verified positive/negative flood-event labels and no held-out calibrated model evaluation. The grid colors are not physically validated inundation boundaries.

**How are heat and air quality handled?** Heat uses temperature, humidity and valid heat-index rules with configurable bands; it is not an official heatwave warning. Air quality displays Open-Meteo's **US AQI** standard plus pollutant values and units. It is never relabeled as Indian AQI.

**How is WorldPop used?** The 2025 modeled population estimates cover all nine grid cells at the supplied dataset resolution. They describe population in each cell, not residents exposed to a flood. Exposed population remains unavailable without a validated hazard footprint and matching population coverage.

**How are geographic impacts estimated?** The impact engine can intersect mapped assets and roads with analysis cells when database records are present. An intersection signals possible co-location for follow-up, not physical damage or service disruption. Drainage distance signals proximity to mapped lines, not verified capacity or performance. Facility/road map layers currently use a validated local OSM preview until their PostGIS import is completed.

**How are incident reports verified?** Citizens submit reports as unverified. An authenticated authority can start review and resolve or reject with a recorded reviewer, time and audit history. A reviewed citizen report is not automatically a validated historical flood label.

**How is one-authority publication kept accountable?** An authenticated authority must save, submit, explicitly approve and separately publish an advisory with an expiry. The backend and database validate every transition, bind the reviewer to the signed-in user and audit status and content changes. Nugen cannot perform those actions. Migration 010 enables the same authority to complete the workflow; an authenticated live publication test is pending.

**How is user data secured?** Supabase Auth issues sessions. FastAPI verifies each protected bearer token and reads the role from the database. Row Level Security enforces citizen ownership and authority-only operations. Evidence images use a private bucket and short-lived signed access. The browser receives only a publishable Supabase key; Nugen and Supabase secret credentials stay server-side.

**How can this expand beyond Pune?** Add reproducible or authoritative zones for a new city, ingest matching terrain, population and infrastructure with provenance, configure geographic bounds, and validate hazard rules against local verified events. Do not transfer Pune's grid or heuristic thresholds as an operational warning model without local validation.

**What is proven today?** On 1 November 2026, public FastAPI smoke checks reached Open-Meteo forecast, archive and air-quality sources, nine GeoJSON cells, sourced B2 metrics and real Nugen inference (HTTP 200 with a stored unapproved draft). A TEST citizen report completed both authority review transitions with persisted audit history. Migration 010's column was verified on 2 November; single-authority alert publication still awaits a live signed-in test. Public deployment remains unverified. See [FINAL_TEST_REPORT.md](FINAL_TEST_REPORT.md).
