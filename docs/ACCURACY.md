# How accurate is it, and how often is it updated?

A short answer for judges and mentors. The detail, with the tests behind every line, is in `docs/VALIDATION.md`.

## How often each input changes

| Input | Refresh | Where it comes from |
|---|---|---|
| Sun position | exact, for any minute | pvlib solar position, checked against 20 golden samples within 0.5° (`backend/tests/test_sun.py`) |
| Shadows | every **10 minutes** of the day (`TIME_STEP_MIN = 10`), on a **2 m** grid | ray-marched from 3D buildings and mapped trees |
| Route timing | every 5 minutes of departure time (`DEPARTURE_STEP_MIN = 5`) | the departure optimiser |
| Weather (UV, cloud, sunlight, temperature) | **hourly** | Open-Meteo; a recorded copy is used offline and labelled "Recorded" |
| Map data (buildings, streets, trees) | **re-baked from OpenStreetMap on demand**: one command per city; a weekly scheduled re-bake is the production plan, not yet running | OpenStreetMap via Overpass. Snapshots: Dubai 2026-10-22, Oslo 2026-10-23 (`meta.json`) |

Adding or refreshing a city is automatic from open data. Oslo took about 29 minutes end to end tonight, most of it
waiting on a busy public Overpass server; the shade bake itself took about 92 seconds for 4 dates.

## How accurate

What is solid:
- **Sun geometry** matches the reference solar model within 0.5°.
- **Shadow geometry** is unit-tested: shadow length and direction for boxes at several sun angles, including Oslo's
  6.6° December sun (shadows about 8.6× the building height, `backend/tests/test_low_sun.py`), night, trees and gaps
  between buildings.
- **Visual checks**: shadows start at building bases and fall away from the sun in the QA stills.

What is approximate (said plainly in the app and the deck):
- **Building heights.** OpenStreetMap has no height for about 79% of Dubai's footprints, so those use typical heights
  by building type. Oslo is better tagged (about half have levels). Shadow length is only as good as the height.
- **Trees, awnings and arcades** are only what is mapped; real shade is usually a little more than we model.
- **Clouds** come from the hourly forecast, not from a sky camera; a passing cloud is not predicted.
- **No field validation yet.** The next step is a field test: walk the hero routes with a light sensor and a camera
  at fixed times and compare measured sun minutes with the model. Results are not in yet, so we make no accuracy
  percentage claim.
