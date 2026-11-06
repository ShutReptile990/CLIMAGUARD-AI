# Indradhanu 2026: seven-minute prototype demonstration

[Project overview](../README.md) · [Test evidence](FINAL_TEST_REPORT.md) · [AI safeguards](AI_INTEGRATION.md)

**Before recording:** Use the current local build or a genuinely verified deployment. Check `/api/health`, live Open-Meteo responses, the selected Supabase grid context and `/api/v1/nugen/status`. Sign in to dedicated citizen and authority test accounts if showing protected workflow actions. Prepare a report beginning `TEST —` and an advisory beginning `TEST —`; do not create a misleading public emergency alert. If the protected workflow or Nugen is unavailable, show the honest unavailable state and explain it.

| Time | Screen and action | Narration/evidence |
| --- | --- | --- |
| 0:00–0:45 | Title and Citizen Overview | “Fragmented weather, air quality and reports are hard to interpret together. CLIMAGUARD AI makes evidence and uncertainty visible for a Pune pilot.” No unsupported impact statistic. |
| 0:45–1:40 | Live overview, then select grid B2 | Point to timestamped Open-Meteo model estimates, flood/heat/US AQI cards, the distinction between Pune overview and B2, and the fact that B2 is an **analysis cell, not an official ward**. |
| 1:40–2:30 | Predictions and full Risk Map | Show DEM mean slope, WorldPop population and mapped-drain distance in B2. Explain that drain distance is not capacity, population is not a count exposed to flooding, and colored polygons are screening cells rather than inundation. Toggle mapped OSM features if PostGIS responds. |
| 2:30–3:35 | Activate **Run extreme rainfall demo** | Highlight *SIMULATED — NOT CURRENT CONDITIONS*, **25 mm/h for six hours**, B2's calculated flood index and the matching map popup. Select another cell to show its own score. All nine cells may share the Severe color under the current threshold; the numeric values still differ by sourced slope. Return to Live Mode and show the original result. |
| 3:35–4:30 | Citizen Safety Center | Reactivate Demo Mode, select the extreme-rainfall preset and press **Generate safety guidance**. Wait for a real Nugen result; show its model/time, three numbered actions, source analysis and official-alert disclaimer. State that the model explains deterministic screening and does not calculate the flood score. |
| 4:30–5:50 | Citizen report, then Authority Incident Queue | **Return to Live Mode first** and use an authenticated citizen account. Submit or show a **TEST-labeled** persisted report in My Reports. With the authority account, start review and verify or reject it; display the saved status and audit history. Demo-only reports stay local and cannot enter authority review. A citizen report is not a verified flood-event training label. |
| 5:50–6:35 | Authority Response Planner and Alerts | Show an authority Nugen brief and **unpublished** advisory draft. If using a safe, clearly TEST-labeled advisory, explicitly submit, approve, publish with a short expiry, verify citizen visibility, then withdraw it after recording. Never imply AI publishes automatically. |
| 6:35–7:00 | Closing limitations and impact | “The prototype connects localized evidence, simulated sensitivity, contextual AI guidance and human review. Operational validation, flood-event calibration, drainage capacity and hazard footprints are future work.” |

## Recording evidence

- Use genuine application screens; [screenshot checklist](screenshots/README.md) names the planned stills.
- Keep the selected area, mode, timestamps and source labels visible. Cut or blur private incident text, contact information and browser/account identifiers.
- If a real official alert is already published, present it as such only with the authority owner's consent. Do not withdraw or alter it for the demo.
- A live Nugen inference was locally verified on 6 November 2026. A new recording should capture its **own** successful request or clearly describe an unavailable response.
- Replace “Coming soon” URL placeholders in the README only after verifying a hosted prototype and video link.
