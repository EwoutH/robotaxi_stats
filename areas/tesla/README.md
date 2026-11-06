# Tesla Robotaxi service areas over time

Tesla publishes no service-area maps or polygons outside its Robotaxi app. This folder combines two community datasets into one version history per city, and adds Tesla's own city status ("open" / "soon") from archived copies of tesla.com/robotaxi.

| Script | Reads | Writes |
|---|---|---|
| `01_boundaries.py` | [Robotaxi Tracker](https://github.com/Robotaxi-Tracker/robotaxi-service-areas) (CC BY 4.0), every commit touching `areas/tesla/`; [AV Map](https://github.com/path-avmap/av-map-data) (MIT) at a pinned commit | `data/boundary_versions.csv`, `tesla_service_areas.geojson` |
| `02_city_status.py` | Wayback Machine captures of [tesla.com/robotaxi](https://www.tesla.com/robotaxi), one per day, only new ones on re-runs | `data/page_captures.csv`, `data/page_cities.csv`, `data/status_changes.csv` |

Run both with the system `python` (`ds` environment). Set `GITHUB_TOKEN` (e.g. `GITHUB_TOKEN=$(gh auth token)`) to avoid GitHub API rate limits. Both scripts are safe to re-run daily: script 1 rebuilds from scratch in seconds, and script 2 fetches only captures it has not seen. `.github/workflows/tesla_areas.yml` does this daily on GitHub Actions, commits the results and opens an issue when `boundary_versions.csv` or `status_changes.csv` changes.

## Sources and dates

- **Robotaxi Tracker** polygons come from the Tesla Robotaxi app's fleet areas. Until 2026-08-30 they were hand-drawn copies (files without properties, edges 25–115 m off on average); since then they are Tesla's exact polygons from the app's API. Their date is the commit date (`date_kind = first_seen`), which is when the tracker recorded the shape, not necessarily when Tesla changed it. History starts with the repo's public import on 2026-04-20.
- **AV Map** covers Austin (5 versions, June–October 2025) and the Bay Area (July 2025). Its dates are announcement dates from news reports (`date_kind = announced`); `source_url` links each one. The repo has not changed since May 2026.
- The two agree where they overlap: AV Map's October 2025 Austin shape and the tracker's April 2026 one have an intersection over union of 0.989 (Bay Area: 0.976).
- `iou_prev` is the overlap with the city's previous version. Values around 0.97–0.99 with small area changes are usually re-exports or small edits; lower values are expansions.
- tesla.com/robotaxi has no service-area map. Since October 2026 it embeds a list of cities with a center point and status ("open" / "soon"). Earlier 2026 captures only name the open cities in a footnote ("rides are currently being offered in …"), and 2025 captures name no cities at all. So Austin's first row (2025-12-25) is when the page first named it, not its launch. Later launches match the announced dates: Dallas and Houston (April 17–27, 2026), Miami (July 3–4), Orlando and Tampa (July 21–26). `page_cities.csv` column `form` says which form a row came from (`map` or `text`).
- Some captures (e.g. 2026-07-10) are archived Brotli-compressed. Install the `brotli` package to read them; without it the script skips them and retries on the next run.

Areas are geodesic (WGS84). Geometries are EPSG:4326.

## Known gaps

- Changes after the tracker's last commit (2026-09-10) are missing, e.g. the Houston expansion announced on 2026-10-26.
- No Tesla boundaries between AV Map's last version (2025-10-28) and the tracker's first (2026-04-20). Press reports say Austin did not change in that period, which the 0.989 overlap supports.
- Tesla's announcement maps on X are not used yet. They could fill these gaps and confirm dates.
