# Austin and Atlanta history repair

Completed 2026-11-04. The GeoPackage, area/population tables, report statistics,
figures and site data now use the recovered history.

## Corrected sequence

| Metro | Date used | Area, sq mi | Basis |
|---|---|---:|---|
| Austin | 2024-11-03 | 35.49 | Existing first map observation; legacy provenance |
| Austin | 2025-07-17 | 89.38 | Operator-announced expansion; recovered historical map |
| Austin | 2026-01-13 | 132.29 | Operator-announced expansion; recovered historical map |
| Austin | 2026-09-16 | 150.13 | First verified capture of larger map; change after 2026-07-08 |
| Atlanta | 2025-07-29 | 58.33 | First recovered capture of smaller map |
| Atlanta | 2026-09-16 | 111.56 | First verified capture of larger map; change after 2026-07-08 |

The September dates are observation dates, not claims that the expansions happened
on that day. The source images still show the smaller areas on July 8. A tracker
reports July 14 for both expansions, but a broad operator statement saying they
were coming soon does not independently establish that exact day. Their recorded
change window remains **(2026-07-08, 2026-09-16]**.

Atlanta's public launch on June 24, 2025 is confirmed by
[Uber's announcement](https://www.uber.com/us/en/newsroom/waymo-on-uber-atl/).
Its stated 65 sq mi and AV Map's 68.55 sq mi reconstruction differ from the
58.33 sq mi traced from the recovered map. That is a reason to keep the first
polygon observation at July 29, rather than assert an undisputed June 24 polygon.
Areas in this dataset measure the fill as drawn; they are not the operator's
nominal service-area figures.

## What was fixed

The old fetcher treated an HTTPS Google Support original URL as a live request,
even when it came from a historical archive listing. It then saved that live
HTML under the historical timestamp. The old image cache also keyed only by URL.

The fetcher now distinguishes live requests explicitly. Historical HTML must be
fetched through Wayback and have a versioned provenance sidecar with a matching
content hash before it can be reused. Unverified old HTML is retained locally in
`raw/snapshots_legacy/` for audit. It is not used as historical evidence.

Replay redirects use the **returned** capture time, checked against the Memento
header when present. For example, a request for June 12 returned July 29. The
result is recorded as July 29, not June 12. The recovery used the existing index
because CDX was returning HTTP 503; some requested dates collapsed onto the same
actual replay. Failed/unavailable dates were not replaced with live content.

Historical image requests also use Wayback. A forward redirect is accepted only
when the returned bytes match an already verified earlier capture of that image
URL; that earlier capture remains the image evidence. A later image with different
bytes is rejected. Live and committed CI captures retain separate handling.

Tracked [snapshot_sources.csv](data/snapshot_sources.csv) records actual page and
image replay URLs, capture dates, retrieval dates and SHA-256 hashes. The original
page/image bytes and request metadata remain in gitignored `raw/`. A missing
verified image aborts before the observation index is replaced.

The five newly georeferenced renditions were checked visually against OSM roads.
Two are lower-resolution renditions of unchanged current maps; their equivalences
are explicit in [image_equivalences.csv](data/image_equivalences.csv). They reuse
the higher-resolution geometry, avoiding false November expansions.

## Conservative additions identified through AV Map

[history_sources.csv](data/history_sources.csv) adds two effective dates identified
in AV Map at revision `3c94c4f924c69f425a54debe0c594a286bf16d8c`:

- **Austin, July 17, 2025:** Waymo's
  [dated expansion map](https://waymo.com/blog/shorts/north-to-south-were-covering-more-ground-in-austin-starting-today-safe-and/)
  confirms the expansion. The independently recovered map traces to 89.38 sq mi
  and has 98.34% IoU with AV Map's July 17 polygon.
- **Austin, January 13, 2026:** Uber's
  [expansion announcement](https://www.uber.com/us/en/blog/waymo-on-uber/)
  explicitly describes January 13 and 133 sq mi from North Austin to Manchaca;
  AV Map and contemporaneous reports corroborate the year/date. The recovered
  map traces to 132.29 sq mi. The article's original masthead date is not used as
  the expansion date.

These are announcement-based attributions of the recovered shapes, **not** invented
archive captures on those dates. `date_basis`, `date_source_url`, and
`change_window_start` record the distinction in both GeoPackage layers.
We retain our checked geometry rather than replace it with AV Map's larger
January reconstruction. Other conflicting AV Map date/shape pairings and the
unmerged Tracker updates have not been imported.

## Effect on the analysis

Current coverage remains approximately **1,891 sq mi and 11.33 million residents**.
Historical totals change: year-end 2025 coverage is now **838 sq mi**, versus
952 before repair; residents are about **5.8 million**, versus 6.2 million before.
This repair added three metropolitan boundary versions: 42 instead of 39.
The subsequent [early-history extension](report_early_history.md) brings the count to 46.

All derived area/population tables and history-dependent figures were regenerated.
The unchanged SF/LA version maps and current-only graphics retain their previous
renderings. The external comparison has also been rerun against the repaired
dataset, with upstream revisions still pinned.

The date-window lower bound now comes from the last observation of the old map
for the same city, rather than an unrelated snapshot of another metro. First
observations without a lower bound remain unknown. Other metros' historical
shapes/dates were retained and are labelled `legacy_map_observation` pending a
separate provenance audit; this repair does not certify their full history.

## Reproduce

```bash
python 01_fetch_snapshots.py --page 16011725 --existing-index
python 02_georeference.py --only-cached
python 03_build_dataset.py
python 04_visualize.py
python 05_report_figures.py
python 06_population.py
python compare_external.py
```

Use the documented Python dependencies and existing local road/Census caches.
The capture recovery leaves `raw/history_repair/snapshot_images.before.csv` and
the old GeoPackage/tables under `raw/history_repair/before/` for comparison.
Source pages can move or disappear; the stored replay URLs and hashes make such
changes visible rather than silently substituting today's content.

## Validation

Six archive-provenance regression tests pass (`python -m unittest discover -s
areas/waymo/tests -v`, from the repository root). Integration checks confirm all
then-current 42 metropolitan geometries are valid, population records join one-to-one,
current areas and other-page observations are unchanged, and recorded image
hashes and the external-comparison input hash match the local files.
Both site data loaders also run successfully; the GeoJSON contained all 42
versions and the corrected dates, uncertainty windows and source attribution.

A full site build passes after clearing the two generated data-loader caches.
Both built data files were compared with fresh loader output and match exactly,
including the final provenance labels. The build also validates both page links.
