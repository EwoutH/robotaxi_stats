# Zoox service areas over time

Zoox publishes no service-area polygons, only map images ([zoox.com/zoox-operating-areas](https://zoox.com/zoox-operating-areas)). `zoox_areas.py` combines the two community datasets that trace them, as the Tesla scripts do:

- [AV Map](https://github.com/path-avmap/av-map-data) (MIT), at the commit the Tesla script pins: Las Vegas (2025-09-10) and San Francisco (2025-09-16, 2025-11-18). Dates are announcement dates from news reports (`date_kind = announced`); `source_url` links each one.
- [Robotaxi Tracker](https://github.com/Robotaxi-Tracker/robotaxi-service-areas) (CC BY 4.0), every commit touching `areas/zoox/`. Its first commit (2026-04-20) repeats AV Map's latest shapes, so it adds nothing. The 2026-05-11 (San Francisco) and 2026-05-14 (Las Vegas) shapes were traced from Zoox's map images. Dates are commit dates (`date_kind = first_seen`), when the tracker recorded the shape, not necessarily when Zoox changed it.

A shape that overlaps the metro's previous version by 99.9% or more is dropped as a repeat.

Run it with the system `python` (`ds` environment); set `GITHUB_TOKEN` to avoid API rate limits. It writes `data/boundary_versions.csv` (one row per version) and `zoox_service_areas.geojson` (the same with geometry, EPSG:4326). `pop` is the 2020 Census residents inside a version and `pop_added` those of the area it added, by areal weighting of Census blocks (`areas/census.py`). Residents are recomputed only when the versions change, which downloads the states' Census blocks (Nevada, California) the first time.

## Known gaps

- Zoox's own Las Vegas map (August 2026) reaches downtown, beyond the tracker's latest shape. That expansion is missing.
- Zoox's maps for Austin, Miami and Foster City show where Zoox drives, "including areas where we're testing", not rider service areas, so they are left out. Las Vegas is open to the public, San Francisco to select riders (zoox.com/community, November 2026).
- Not run on a schedule: re-run the script by hand to pick up tracker changes.
