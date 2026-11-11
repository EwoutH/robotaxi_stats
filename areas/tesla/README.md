# Tesla Robotaxi service areas over time

Tesla publishes no service-area maps or polygons outside its Robotaxi app. This folder combines two community datasets into one version history per city, and adds Tesla's own city status ("open" / "soon") from archived copies of tesla.com/robotaxi.

| Script | Reads | Writes |
|---|---|---|
| `01_boundaries.py` | [Robotaxi Tracker](https://github.com/Robotaxi-Tracker/robotaxi-service-areas) (CC BY 4.0), every commit touching `areas/tesla/`; [AV Map](https://github.com/path-avmap/av-map-data) (MIT) at a pinned commit | `data/boundary_versions.csv`, `tesla_service_areas.geojson` |
| `02_city_status.py` | Wayback Machine captures of [tesla.com/robotaxi](https://www.tesla.com/robotaxi), one per day, only new ones on re-runs | `data/page_captures.csv`, `data/page_cities.csv`, `data/status_changes.csv` |
| `03_population.py` | `tesla_service_areas.geojson`; 2020 Census blocks and Urban Areas (downloaded into `areas/raw/census/`) | `data/population_versions.csv` |

Run them with the system `python` (`ds` environment). Set `GITHUB_TOKEN` (e.g. `GITHUB_TOKEN=$(gh auth token)`) to avoid GitHub API rate limits. All are safe to re-run daily: script 1 rebuilds from scratch in seconds, script 3 recomputes only cities whose versions changed, and script 2 fetches only captures it has not seen. `.github/workflows/tesla_areas.yml` does this daily on GitHub Actions, commits the results and opens an issue when `boundary_versions.csv` or `status_changes.csv` changes.

## Sources and dates

- **Robotaxi Tracker** polygons come from the Tesla Robotaxi app's fleet areas. Its Austin and Bay Area files were hand-drawn copies until 2026-08-30 (files without properties, edges 25–115 m off on average); all other files, including Dallas and Houston from the start, are Tesla's exact polygons from the app's API. Column `exact` marks these. When an exact shape overlaps the hand-drawn one before it by 90% or more, it replaces that version's geometry instead of adding a version, and `redrawn` gives its date. This applies to Austin, Bay Area, Miami, Orlando and Tampa on 2026-08-30. Their date is the commit date (`date_kind = first_seen`), which is when the tracker recorded the shape, not necessarily when Tesla changed it. History starts with the repo's public import on 2026-04-20.
- **AV Map** covers Austin (5 versions, June–October 2025) and the Bay Area (July 2025). Its dates are announcement dates from news reports (`date_kind = announced`); `source_url` links each one. The repo has not changed since May 2026.
- The two agree where they overlap: AV Map's October 2025 Austin shape and the tracker's exact one for April 2026 have an intersection over union of 0.992 (Bay Area: 0.979).
- `iou_prev` is the overlap with the city's previous version. Values around 0.98–0.99 mark the switch from AV Map to the tracker; lower values are expansions.
- tesla.com/robotaxi has no service-area map. Since October 2026 it embeds a list of cities with a center point and status ("open" / "soon"). Earlier 2026 captures only name the open cities in a footnote ("rides are currently being offered in …"), and 2025 captures name no cities at all. So Austin's first row (2025-12-25) is when the page first named it, not its launch. Later launches match the announced dates: Dallas and Houston (April 17–27, 2026), Miami (July 3–4), Orlando and Tampa (July 21–26). `page_cities.csv` column `form` says which form a row came from (`map` or `text`).
- Some captures (e.g. 2026-07-10) are archived Brotli-compressed. Install the `brotli` package to read them; without it the script skips them and retries on the next run.

Areas are geodesic (WGS84). Geometries are EPSG:4326.

## Residents

`03_population.py` counts the 2020 Census residents inside every version with the same code as Waymo's step 6 (`areas/census.py`): Census blocks inside the area count fully, blocks crossing the boundary by the share of their area inside. Density uses land area only. Each city uses the blocks of its metro in `areas/metros.csv` (Tesla's "Bay Area" is San Francisco); a city without a row there is skipped until one is added.

`data/population_versions.csv` has one row per boundary version (key: `city`, `valid_from`):

- `pop`, `housing`, `land_mi2`, `density_mi2`: residents, housing units, land area and residents per square mile of land.
- `pw_density_mi2`: the block-group density the average resident lives at.
- `pop_lo`, `pop_hi`: residents with the boundary moved `band_m` in and out. Traced shapes (AV Map, hand-drawn copies) get 150 m, as Waymo's traced maps do; Tesla's own polygons get 0.
- `pop_in_metro_ua`, `pop_urban`, `share_of_ua`: residents in the metro's 2020 Urban Area(s), in any Urban Area, and the share of the metro's Urban Area population served.
- `area_added_mi2`, `pop_added`, `land_added_mi2`, `density_added_mi2`, `pw_density_added_mi2`, `pop_removed`: what the version added to and removed from the city's previous one.

These are 2020 counts on 2025–2026 boundaries, so growth since 2020 is missing. The site shows `pop` and `pop_added` for the cities tesla.com lists as open.

## Known gaps

- Changes after the tracker's last commit (2026-09-10) are missing, e.g. the Houston expansion announced on 2026-10-26, and Fort Worth, which tesla.com lists as open since 2026-11-05 but which has no boundary yet.
- No Tesla boundaries between AV Map's last version (2025-10-28) and the tracker's first (2026-04-20). Press reports say Austin did not change in that period, which the 0.989 overlap supports.
- Tesla's announcement maps on X are not used yet. They could fill these gaps and confirm dates.
