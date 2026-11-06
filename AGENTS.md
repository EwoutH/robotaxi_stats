# robotaxi_stats

Public repo with data and analysis on robotaxi services, one folder per topic under `areas/` (and later possibly other top-level folders, e.g. `safety/`).

- `areas/metros.csv` (read through `areas/metros.py`, which also has `metro_of()` for mapping labels): one row per metro with state, state FIPS code, centre, search radius, Geofabrik extract and aliases (e.g. Tesla's "Bay Area"). Used by the Waymo scripts and the site, and meant for the Tesla scripts; a new metro needs only a row here. Row order matters for `metro_of()`.
- `areas/waymo/`: Waymo service areas over time. Numbered scripts `01_`-`03_`, `06_` and `07_` build the dataset; see its README. Run with the system `python` (`ds` environment). Regenerable inputs (`raw/`, `qa/`) are gitignored and stay local.
- `areas/tesla/`: Tesla Robotaxi service areas over time, combined from community datasets (Robotaxi Tracker, AV Map) plus city status from archived tesla.com/robotaxi. Two re-runnable scripts; see its README.
- `site/`: public Observable Framework site (GitHub Pages), one page per topic (`src/areas/waymo.md`) plus a landing page. Python data loaders in `site/src/data/` read straight from the topic folders. Service-area pages share `src/components/areas.js` and take the same data from every operator, defined and written by `src/data/contract.py`; a page adds only its text and the operator's name and colour. Add new pages to `pages` in `observablehq.config.js`. Local: `npm install`, `npm run dev` (or `npm run build`) in `site/`.
- CI: `.github/workflows/site.yml` builds and deploys the site on pushes to `main`. `.github/workflows/waymo_maps.yml` runs daily in two stages: `areas/waymo/07_watch_live.py` commits new captures (`live/` plus the snapshot index); then, after a change, steps 2, 3, `check_new_maps.py` and 6 update the dataset, commit it, start the site workflow and open an issue. Hand work is only needed when that check fails. The one-time Waymo reports (Nov 2026, with steps 4-5 and `compare_external.py`) live only in the release `waymo-reports-2026-11` (tag at the commit that built them), not in the repo. Optional secrets: `IA_ACCESS_KEY`, `IA_SECRET_KEY`. `.github/workflows/tesla_areas.yml` re-runs both Tesla scripts daily, commits `areas/tesla/`, starts the site workflow and opens an issue when a boundary version or city status changes.

## Status

Moved from `EwoutH/sandbox1/waymo_area` on 2026-11-03 with full history. Nothing in progress.
