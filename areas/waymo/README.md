# Waymo service areas over time

Historical, georeferenced polygons of Waymo's robotaxi service areas, traced from
the map images on Waymo's help pages as archived by the Wayback Machine:

- https://support.google.com/waymo/answer/9059119 (service areas, Feb 2024 to now)
- https://support.google.com/waymo/answer/16011725 (Austin & Atlanta on Uber, Jun 2025 to now)

Waymo publishes these areas only as styled PNG maps with no coordinates, and no
existing polygon archive was found. This folder rebuilds them as vector data:
42 map versions across 15 metros, from Feb 2024 to Oct 27 2026.

**Findings:** see [report.md](report.md). The total area grew from 218 to 1,891 sq mi,
10 new metros launched in 2026, and service areas almost never shrink.
[report_population.md](report_population.md) adds residents (2020 Census): 11.3 million
people now live inside a service area, up from 1.65 million in Feb 2024.

## Outputs

| File | What it holds |
|---|---|
| `waymo_service_areas.gpkg`, layer `versions` | One row per city label per map version: `city`, `metro`, `valid_from`, `valid_to`, `change_window_start`, `area_km2`, `area_mi2`, `quality`, `clipped_by_frame`, `note` (e.g. "Gradually adding riders"), `image_file` |
| `waymo_service_areas.gpkg`, layer `metro_versions` | Labels merged per metro (e.g. "San Francisco" + "Silicon Valley" → San Francisco). One row per change in shape |
| `waymo_service_area_*.geojson` | The same two layers as GeoJSON (generated, not in git) |
| `data/area_timeseries.csv` | Area per metro on every snapshot date |
| `data/expansion_events.csv` | Every launch/expansion per metro: area before/after, sq mi added and removed |
| `report.md`, `figures/report/*.svg`, `data/report_stats.json` | Report with statistics and figures |
| `figures/*.png` | Area over time per metro, total area, and a map of all versions per metro (generated, not in git) |
| `data/population_*.csv`, `report_population.md`, `figures/report/people_*.svg`, `density_*.svg` | Residents (2020 Census blocks) per version, per expansion, per snapshot date and per density decile, plus the population report |
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
open (empty) for maps still on the page. The newest versions (2026-10-27) come
from the live pages fetched on that day.

## Method

1. `01_fetch_snapshots.py` lists Wayback snapshots (CDX API), downloads each page,
   pulls out every city heading and its map image, and downloads each distinct image.
2. `02_georeference.py` + `georef.py` fit each image to OpenStreetMap roads. The
   maps are north-up Web Mercator renders, so the fit has three parameters (scale,
   x-offset, y-offset). Road lines are extracted from the image and matched to
   rasterised OSM motorway/trunk/primary/secondary roads. A coarse-to-fine search
   uses template correlation on a distance field. The blue fill is then vectorised.
   OSM roads come from Overpass or, if that's down, Geofabrik extracts in `raw/osm/pbf/`.
3. `03_build_dataset.py` turns the snapshot dates into validity periods and
   computes the area.
4. `04_visualize.py` makes the overview PNG figures.
5. `05_report_figures.py` computes the report statistics and SVG figures.
   `report.md` itself is written by hand from `data/report_stats.json`.
6. `06_population.py` sums 2020 Census block population inside every version and
   expansion (areal weighting, ±150 m band) and relates it to 2020 Urban Areas.
   `report_population.md` is written by hand from `data/population_stats.json`.

## Accuracy and caveats

- All 42 images were checked by eye in `qa/`. Highway shields and OSM roads line
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
- Austin: no archived map between 2025-03-03 (removed from the main page) and
  2025-06-12 (first capture of the Uber page).
- "Gradually adding riders" areas are included as drawn. Use the `note` column to
  filter them.

## Maintaining and extending

### Updating with new snapshots

```bash
python 01_fetch_snapshots.py      # new archive snapshots + today's live pages
python 02_georeference.py         # only new images; ~2-4 min each, 6 in parallel
python 03_build_dataset.py
python 04_visualize.py
python 05_report_figures.py       # then update the numbers in report.md by hand
python 06_population.py           # then update report_population.md by hand
```

Step 6 needs 2020 Census blocks per state and the 2020 Urban Areas in `raw/census/`
(~2.6 GB). It stops with the download URL if a file is missing; a new metro also needs
an entry in `STATE` in `06_population.py`:

```bash
curl -o raw/census/tl_2020_06_tabblock20.zip https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_06_tabblock20.zip
curl -o raw/census/tl_2023_us_uac20.zip https://www2.census.gov/geo/tiger/TIGER2023/UAC/tl_2023_us_uac20.zip
```

Each state is read once (CA/TX take a minute) and cached as `raw/census/blocks_<fips>.parquet`.

After step 2, look at the new `qa/*.jpg` files: the red OSM roads should run along
the grey roads and through the highway shields. If a fit is wrong, add a row to
`data/manual_georef.csv` (`image_file, s, x0, y0`), delete that image's row in
`data/georef_params.csv`, and re-run step 2.

Python packages: `geopandas shapely pyproj opencv-python numpy pandas requests
matplotlib osmium pyogrio pyarrow`.

Git holds only code, docs, the final dataset and the report. Everything else is
regenerated by the scripts (see `.gitignore`): `raw/snapshots/` (page HTML, ~210 MB,
from archive.org), `raw/images/` (source maps, ~37 MB, from Google/archive.org),
`raw/osm/` (road caches and Geofabrik extracts, ~2.7 GB), `qa/`, the PNG figures and
the GeoJSON exports. `data/georef_params.csv` is committed, so polygons can be rebuilt
from re-downloaded images without redoing the slow fit. Keep a local copy of
`raw/images/` if you want to be safe against the source maps disappearing.

### Things learned the hard way

- **Page structure changes.** City headings have been `<h2>` (2024), `<a class="zippy">`
  (2025) and `<h2 class="zippy">` / `<p class="zippy">` (2026, mixed on one page).
  The parser matches any element whose class is exactly `zippy`. Don't match
  `zippy-wrapper`: that once swallowed the next city, so Houston's map was booked
  under Denver. If a snapshot suddenly shows fewer cities, check the parser first.
- **Image hosts.** 2024 maps are on `storage.googleapis.com/support-kms-prod/...`,
  later ones on `lh3.googleusercontent.com/...`. The `=w895` suffix is stripped and
  `=s0` requested to get full resolution (2400 px). The live URL is tried first,
  archive.org is the fallback. Downloaded images are deduplicated by SHA-1, so the
  same map reached through a new URL isn't processed twice.
- **City labels.** "San Francisco" + "Silicon Valley" (Mar–Nov 2025) became
  "San Francisco Bay Area". Austin left the main page in Mar 2025 and lives on the
  Uber page (`answer/16011725`) together with Atlanta. `METROS` / `ALIASES` in
  `02_georeference.py` map labels to metros. A new city needs a `METROS` entry
  (centre and search radius) and, for offline roads, a `PBF` entry.
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
- Run step 1 on a schedule (e.g. a GitHub Action) so changes are captured within a day
  instead of relying on the archive's irregular snapshots.
