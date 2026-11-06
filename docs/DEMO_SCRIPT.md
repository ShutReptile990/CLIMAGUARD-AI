# CLIMAGUARD AI — five-minute judge demo

> **Earlier five-minute outline.** The current Indradhanu walkthrough, including the extreme-rainfall map and verified single-authority flow, is [DEMO_GUIDE.md](DEMO_GUIDE.md). Some status statements below reflect the date of this earlier outline.

**Preflight:** Use the live backend and a known Pune grid cell. Confirm Open-Meteo and Nugen are available immediately before presenting. If the citizen/authority workflow has not been verified, stop at its prepared screen and say so; do not stage a real warning. Any test report or advisory must begin `TEST —` and be withdrawn or archived after the demo.

## 0:00–0:35 — The problem

“Weather, air quality, terrain and citizen reports are often scattered across different tools. CLIMAGUARD AI brings source-labeled screening into one local view, so residents can understand conditions and responders can prioritize follow-up. This is a decision-support prototype, not an official warning system.”

## 0:35–1:25 — Citizen view and location

Open Citizen Overview. Point out the selected scope: **Pune overview** versus **B2 analysis grid cell**. Select B2 using the selector, then click its polygon on the map. Explain that the grid is reproducible and is **not** an official ward or flood boundary. Show current temperature, humidity, rain and US AQI with their timestamps and source labels.

## 1:25–2:15 — Transparent risk evidence

Open Predictions. Show flood, heat and air-quality cards, rainfall forecast, and feature availability. B2 has sourced WorldPop population, Copernicus mean slope and distance to mapped OSM drainage. Explain that distance does not measure drainage capacity, population in a cell is not flood-exposed population, and the flood score is a heuristic index rather than a calibrated probability. Historical flood labels and calibrated model performance remain unavailable.

## 2:15–3:00 — Aligned AI and scenario

Open Safety Center and press **Generate** once. Identify the displayed Nugen model ID and inference time. “Nugen receives our deterministic source context and returns practical actions. The backend validates the response and does not let the model invent measurements or publish alerts.” Then open What-If Simulator, change rainfall or heat inputs, point to **SIMULATION MODE**, and reset to live conditions.

## 3:00–4:25 — Citizen to authority workflow

Using a separate citizen test account, submit a report beginning `TEST —` for B2. Show it in My Reports as unverified. With one authorized Authority account, show the Incident Queue, start review, verify the report and show review history. Follow the verified-incident link to the Response Planner, generate an authority Nugen brief, edit and save a `TEST —` advisory draft, submit it, explicitly approve it, then publish it with a short expiry. Return to the citizen B2 alert screen and show only the active approved TEST alert. **Migration 010 is applied, but run this live sequence before claiming publication verification.**

## 4:25–5:00 — Value and limits

“The prototype combines live model estimates, measured-source metadata, mapped assets, explainable rules and a human approval workflow. Next steps are PostGIS import of the remaining facility/road preview, verified flood-event labels, validated hazard footprints and operational review with authorities. None of those are claimed as complete today.”

## Evidence to keep ready

- `docs/FINAL_TEST_REPORT.md` for exact test results and blockers.
- `backend/scripts/smoke_nugen.py` for a real aligned-model request; the 1 November 2026 B2 check returned HTTP 200, three validated actions and a stored unapproved draft.
- `docs/ARCHITECTURE.md` for the data and security flow.
- `docs/DEPLOYMENT.md` for hosting and environment setup.
