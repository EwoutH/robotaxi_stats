# Waymo service areas over time

Historical, georeferenced polygons of Waymo's robotaxi service areas, traced from
dated operator announcements and the map images on Waymo's help pages archived
by the Wayback Machine:

- https://support.google.com/waymo/answer/9059119 (service areas, Feb 2024 to now)
- https://support.google.com/waymo/answer/16011725 (Austin & Atlanta on Uber, Jun 2025 to now)

Waymo publishes these areas as styled PNG maps with no coordinates.
This folder rebuilds them as vector data from Dec 16 2022 onwards, and a daily
GitHub Action adds new maps. The site shows it at https://ewouth.github.io/robotaxi_stats/areas/waymo.

**History repaired (2026-11-04):** Austin/Atlanta now use verified archive
captures and actual replay timestamps. Austin's July 2025 and January 2026 dates
are corroborated operator-announcement additions identified through AV Map.
Other metros retain the prior reconstruction and still need a separate
archive-provenance audit.

**Earlier history added (2026-11-04):** six SF/Phoenix announcement maps
extend the series to December 2022. Stale early-2024 Phoenix maps are excluded
from operational history while retained in the raw index. Both metros share the
December 16, 2022 comparison baseline, labelled "Earliest data", not "Launch".
Phoenix combines downtown and East Valley; the full map's month-only label is
explicitly attributed to the dated December 16 announcement.

## Reports (Nov 2026)

A one-time analysis of the dataset as of 2026-11-04 (49 map versions across 15 metros) is archived in the release [`waymo-reports-2026-11`](https://github.com/EwoutH/robotaxi_stats/releases/tag/waymo-reports-2026-11): area over time, residents served (2020 Census), the Austin/Atlanta history repair, the early SF/Phoenix history, and a comparison with Robotaxi Tracker and AV Map. Comparable total area grew from 123 to 1,891 sq mi, 10 new metros launched in 2026, service areas almost never shrink, and 11.3 million people lived inside a service area, up from 0.97 million in December 2022. The reports aren't updated; the release's tag holds the code that built them.

## Outputs

| File | What it holds |
|---|---|
| `waymo_service_areas.gpkg`, layer `versions` | One row per city label per map version: `city`, `metro`, `valid_from`, `valid_to`, `change_window_start`, `area_km2`, `area_mi2`, `quality`, `clipped_by_frame`, `note` (e.g. "Gradually adding riders"), `image_file` |
| `waymo_service_areas.gpkg`, layer `metro_versions` | Labels merged per metro (e.g. "San Francisco" + "Silicon Valley" → San Francisco). One row per change in shape |
| `waymo_service_area_*.geojson` | The same two layers as GeoJSON (generated, not in git) |
| `data/area_timeseries.csv` | Area per metro on every snapshot date |
| `data/expansion_events.csv` | Every launch/expansion per metro: area before/after, sq mi added and removed |
| `data/image_polygons.gpkg`, `data/georef_params.csv` | Polygon and georeference per source map image |
| `data/population_*.csv` | Residents (2020 Census blocks) per version, per expansion and per snapshot date |
| `qa/` | Each source map next to OSM roads drawn with the fitted georeference, for checking (generated, not in git) |

Geometries are EPSG:4326. Areas are geodesic (WGS84 ellipsoid). For your own
area calculations, either use `pyproj.Geod` or reproject to an equal-area CRS
(e.g. `gdf.to_crs(6933)` or a local UTM zone). Don't compute area in EPSG:4326 or 3857.

```python
import geopandas as gpd
mv = gpd.read_file("waymo_service_areas.gpkg", layer="metro_versions")
current = mv[mv.valid_to.isna()]                  # areas in force now
on = lambda d: mv[(mv.valid_from <= d) & (mv.valid_to.isna() | (mv.valid_to > d))]
on("2025-06-30").to_crs(6933).area.sum() / 2.59e6  # total sq mi on a date
```

## Dates

The archive is sampled irregularly (125 snapshots of the main page). A change
happened somewhere between `change_window_start` (the last snapshot showing the old
map) and `valid_from` (the first snapshot showing the new one). `valid_to` is
open (empty) for maps still on the page. The current full-page map set was fetched on 2026-10-27; Austin/Atlanta were
rechecked on 2026-11-04. `date_basis` and `date_source_url` distinguish
operator-announcement dates from first verified map observations.
`change_window_start` now uses the last old observation of the same city, not an
unrelated metro snapshot date.

## Method

- Step 1, `01_fetch_snapshots.py`, lists Wayback snapshots (CDX API), downloads each page,
  pulls out every city heading and its map image, and downloads each distinct image.
- Step 2, `02_georeference.py` + `georef.py`, fits each image to OpenStreetMap roads. The
  maps are north-up Web Mercator renders, so the fit has three parameters (scale,
  x-offset, y-offset). Road lines are extracted from the image and matched to
  rasterised OSM motorway/trunk/primary/secondary roads. A coarse-to-fine search
  uses template correlation on a distance field. The blue fill is then vectorised.
  OSM roads come from Overpass or, if that's down, Geofabrik extracts in `raw/osm/pbf/`.
- Step 3, `03_build_dataset.py`, turns the snapshot dates into validity periods and
  computes the area and the expansion events.
- Step 6, `06_population.py`, sums 2020 Census block population inside every version and
  expansion (areal weighting, ±150 m band). It recomputes only metros whose versions
  changed; delete `data/population_versions.csv` to recompute all of them.

`check_new_maps.py` checks newly fitted maps automatically and `07_watch_live.py` captures the live pages (see below). Steps 4 and 5 made the report figures and are only in the [release](https://github.com/EwoutH/robotaxi_stats/releases/tag/waymo-reports-2026-11).

## Accuracy and caveats

- The original 42 images and eleven recovered renditions were checked by eye in `qa/`. Highway shields and OSM roads line
  up everywhere. Expect boundary errors of roughly 50–300 m, larger on older,
  coarser maps (2024 SF/Austin).
- Checks against reported figures: Phoenix 300 sq mi in Jul 2024 (reported
  315), +53 sq mi in Aug 2026 (reported +55); SF 53 sq mi and LA 79 sq mi in
  Aug 2024 (reported 55 and 79).
- Areas are as drawn. Where Waymo's fill covers water (Biscayne Bay in Miami,
  Mission Bay in San Diego), that water is included. Clip with a land polygon if you
  need land area only.
- Small map markers inside the area (white POI dots, highway shields) are filled in.
  A shield sitting exactly on the boundary can still leave a small notch.
- `clipped_by_frame` marks maps whose blue area touches the circular map edge,
  where the real area may extend past the image.
- Austin: the first recovered Uber-page map is 2025-07-29. The July 17, 2025
  and January 13, 2026 expansion dates are separately supported by operator
  announcements. Atlanta first appears in verified captures on 2025-07-29; its
  June 24 launch is known, but that exact launch polygon has not been imported.
- "Gradually adding riders" areas are included as drawn. Use the `note` column to
  filter them.

## Maintaining and extending

### Updating with new snapshots

New maps on the live pages are picked up and published by the daily GitHub Action
(next section). A full local rebuild, including the Wayback Machine history:

```bash
python 01_fetch_snapshots.py      # new archive snapshots + today's live pages
python 02_georeference.py         # only new images; ~1-4 min each, 6 in parallel
python 03_build_dataset.py
python check_new_maps.py          # automatic check of maps fitted since the last commit
python 06_population.py           # only metros that changed
```

Missing inputs are downloaded: Geofabrik road extracts into `raw/osm/pbf/` (step 2)
and 2020 Census blocks per state plus the 2020 Urban Areas into `raw/census/`
(step 6, ~100-750 MB per state). Each state is read once and cached as
`raw/census/blocks_<fips>.parquet`. A new metro needs one row in [`areas/metros.csv`](../metros.csv): centre, search radius, state and state FIPS code, and ideally a Geofabrik extract.

Commit and push `waymo_service_areas.gpkg`, `data/` and (for a new metro) `metros.csv`.
The site (`site/`, published by `.github/workflows/site.yml`) then rebuilds by itself: new
metros, dates and expansions appear automatically, grouped by the state in `metros.csv`.

### Daily check (GitHub Action)

`.github/workflows/waymo_maps.yml` runs every day at 06:17 UTC (or by hand via
*Run workflow*) in two stages.

**1. check** runs `07_watch_live.py`. It fetches both live pages and compares the cities,
notes and map images with `live/state.json`. On a change it commits:

- `live/pages/<page>_<timestamp>.html.gz`: the page as fetched
- `live/images/<sha1>.png`: each map not seen before
- `live/changes.csv`: one row per city added, removed, given a new map or changed text
- the capture's rows in `data/snapshot_images.csv` and `data/snapshot_sources.csv`

It also asks the Wayback Machine to capture the page and the new maps. This uses the
anonymous Save Page Now endpoint, or the authenticated API if the repo secrets
`IA_ACCESS_KEY` / `IA_SECRET_KEY` are set (keys from https://archive.org/account/s3.php).
The job fails (and GitHub emails you) if a page can't be fetched or parsed.

**2. update** runs only after a change (or when started by hand). It runs steps 2, 3,
`check_new_maps.py` and 6 on the runner, without the archived pages or old images:
step 2 takes new maps from `live/images/` and keeps the committed polygons of the
others; the road extract and Census blocks for the changed metro are downloaded.
If all passes, it commits the dataset and starts the site workflow (pushes made with
the workflow's own token don't trigger other workflows). It opens an issue for new
maps with the check results; the QA images are in the run's `qa` artifact.

`check_new_maps.py` replaces looking at `qa/` by eye. A new map passes if its fit
`quality` is at least 0.6 and, for an existing metro, the new area keeps at least 90%
of the previous version. Service areas almost never shrink, and a misaligned fit
lands kilometres off (the Nov 2026 Las Vegas map shifted by 5 km keeps only 45%).

If stage 2 fails (bad fit, a real shrinkage, a new city without a row in `metros.csv`), the
capture is already committed and the issue says so. Fix it locally: `git pull`, run the
steps above and look at the new `qa/*.jpg`. If a fit is wrong, add a row to
`data/manual_georef.csv` (`image_file, s, x0, y0`), delete that image's row in
`data/georef_params.csv`, and re-run step 2. Then push the result.
`01_fetch_snapshots.py` reads `live/` as extra snapshots, so a full rebuild keeps the
CI captures, even if Google has since removed the map.

Python packages: `geopandas shapely pyproj opencv-python numpy pandas requests
osmium pyogrio pyarrow`.

Git holds only code, docs, the final dataset and the live captures. Everything else is
regenerated by the scripts (see `.gitignore`): `raw/snapshots/` (page HTML, ~210 MB,
from archive.org), `raw/images/` (source maps, ~37 MB, from Google/archive.org),
`raw/osm/` (road caches and Geofabrik extracts, ~2.7 GB), `qa/` and
the GeoJSON exports. `data/georef_params.csv` and `data/image_polygons.gpkg` are
committed, so the dataset can be rebuilt without the images or the slow fit. Keep a local copy of
`raw/images/` if you want to be safe against the source maps disappearing.

### Things learned the hard way

- **Page structure changes.** City headings have been `<h2>` (2024), `<a class="zippy">`
  (2025) and `<h2 class="zippy">` / `<p class="zippy">` (2026, mixed on one page).
  The parser matches any element whose class is exactly `zippy`. Don't match
  `zippy-wrapper`: that once swallowed the next city, so Houston's map was booked
  under Denver. If a snapshot suddenly shows fewer cities, check the parser first.
- **Image hosts.** 2024 maps are on `storage.googleapis.com/support-kms-prod/...`,
  later ones on `lh3.googleusercontent.com/...`. The `=w895` suffix is stripped and
  `=s0` requested to get full resolution (2400 px). Historical images are fetched from archive.org. A later image replay is accepted
  only if its bytes match an already verified earlier capture of that image URL.
  Live captures fetch live images. Neither path reuses the old URL-only cache. Downloaded images are deduplicated by SHA-1, so the
  same map reached through a new URL isn't processed twice.
- **City labels.** "San Francisco" + "Silicon Valley" (Mar–Nov 2025) became
  "San Francisco Bay Area". Austin left the main page in Mar 2025 and lives on the
  Uber page (`answer/16011725`) together with Atlanta. The `aliases` column in
  `metros.csv` and `metro_of()` in `areas/metros.py` map labels to metros: an alias is matched
  exactly, otherwise a label belongs to the first metro (in file order) whose name it contains.
  A new city needs a row there (centre and search radius) and, for offline roads, a
  `geofabrik` extract.
- **Overpass is unreliable for this.** On 2026-10-27 every public instance returned
  502/504 for hours. A batch of 15 metros × several tiles also exceeds the fair-use
  policy. The working route is Geofabrik state extracts
  (`raw/osm/pbf/<state>-latest.osm.pbf`, e.g. florida, tennessee, texas, socal)
  read with pyosmium. Each state takes 10–50 s. `georef.osm_roads` still falls back to
  tiled Overpass queries if no cache or extract exists. osmnx doesn't help: it also
  uses Overpass.
- **Quality score.** `quality` is the share of image road pixels within 2 px of an
  OSM road. Correct fits score 0.5–0.95. Sparse, older maps (2024 SF, 2024 Austin)
  score ~0.5 and are still correct. Always judge by the QA image, not the score.
- **Map style.** The blue fill is RGB (0, 119, 255). Roads inside it are lighter,
  water inside it is darker (still counted), and white POI dots, labels and shields
  are filled. The fit assumes north-up Web Mercator without rotation, which held for
  every map so far.
- **Same map, new file.** Waymo sometimes re-uploads an identical map (Dallas
  Apr 2026, Denver Sep 2026). `03_build_dataset.py` drops metro versions whose
  shape changed by less than 0.5% of their area.
- **Timing.** About 2–4 minutes of CPU per image for georeferencing.
  `02_georeference.py --only-cached` processes only metros whose roads are already
  cached, which is useful while extracts are still downloading.

### Ideas for further work

- Jobs (LEHD LODES) and points of interest covered over time, building on the
  block overlay in `06_population.py`. Commute flows with both ends inside the area.
- Who is served: income, car ownership and race/ethnicity (ACS, block groups),
  covered vs. not covered.
- A model of which block groups get added next (density, income, distance to the boundary).
- Land-only areas (clip with a coastline/water layer).
- Airports and freeways: these are announced separately and not drawn on these maps.
- Other sources with dated maps, e.g. `waymo.com` city pages, press releases, or
  the CPUC/CA DMV ODD maps, to tighten change dates or go back before Feb 2024.

### Repair inputs and archive provenance

- `data/snapshot_sources.csv` records the verified Austin/Atlanta page and image
  replay URLs, actual capture times, retrieval times and SHA-256 hashes.
- `data/history_sources.csv` holds the two curated operator-announcement dates;
  step 3 uses these without inventing archive captures on those dates.
- `data/image_equivalences.csv` identifies two lower-resolution renditions of
  unchanged maps, preventing resampling from creating spurious expansions.
- Old HTML without a version-2 provenance sidecar is not trusted as archived
  content. On recovery it is retained locally in `raw/snapshots_legacy/`.

If CDX is unavailable, replay the existing index for the Uber page with:

```bash
python 01_fetch_snapshots.py --page 16011725 --existing-index
```

Other page rows are retained. Replay redirects use the returned capture date,
not the requested timestamp. A missing verified image aborts before replacing
the index. To run the provenance regression checks from the repository root:

```bash
python -m unittest discover -s areas/waymo/tests -p "test_*.py" -v
```

### Restoring early announcement maps

Run `python fetch_history_images.py` before step 2 to restore the six checked
announcement renditions from `data/history_image_sources.csv`. Both original and
prepared hashes must match. `data/image_mask_settings.csv` selects the public-only
December 2022 SF fill; `data/manual_georef.csv` fixes its checked alignment.
`data/observation_exclusions.csv` documents stale observations retained in the raw
index but omitted from the operational history.
