# Waymo maps before February 12, 2024

Investigated November 4, 2026. **February 12, 2024 is the start of our current
Help-page capture series, not the earliest surviving service-area evidence.**
Seven original operator map assets have been downloaded and visually inspected.
Together they support six metro/date states, five now incorporated into the dataset, reaching back to December
2022. They are catalogued in [early_history_sources.csv](data/early_history_sources.csv)
with source URLs, publication dates, content hashes, dimensions and scope.
Raw HTML, images and extracted animation frames remain in `raw/early_history/`.

## Strongest recovered sources

| Date/state | Metro | Surviving evidence | Treatment |
|---|---|---|---|
| December 16, 2022 | San Francisco | [Waymo announcement](https://waymo.com/blog/2022/12/wheels-up-for-waymo-as-we-expand/), 1920 x 1080 map | Dark blue is public; light blue is employees and guests. Public fill imported separately. Public access still involved invitation/onboarding. |
| December 2022 | Phoenix | Same announcement has a downtown map; the [May 2023 animation](https://waymo.com/blog/2023/05/waymo-one-doubles-service-area-in/) retrospectively shows both downtown and East Valley | Full metro map exists, with two disconnected components. Animation labels only the month; do not invent an exact December date for that union. |
| February 17, 2023 | San Francisco | [Dated Help announcement](https://support.google.com/waymo/answer/13367795?hl=en), 4216 x 4216 map | Explicit expansion effective that afternoon; Mission, Potrero Hill and Dogpatch added. |
| May 4, 2023 | Phoenix | [Dated Help announcement](https://support.google.com/waymo/answer/13559801?hl=en), 8000 x 4281 map; [blog announcement and animation](https://waymo.com/blog/2023/05/waymo-one-doubles-service-area-in/) | Connected downtown and East Valley, adding Scottsdale. Blog states 180 sq mi; use traced area separately from nominal area. |
| July 7, 2023 | Phoenix | [Dated Help announcement](https://support.google.com/waymo/answer/13768098?hl=en), 786 x 787 map | Explicit expanded boundary, visibly extending beyond May coverage. |
| October 9, 2023 | San Francisco | [Dated Help announcement](https://support.google.com/waymo/answer/14249097?hl=en), 393 x 384 map | All existing riders gain access to the whole displayed area. This does not mean the waitlist ended. Low resolution; checked against and aliased to the existing higher-resolution rendition. |

The Phoenix animation is 1920 x 1080 with 168 frames. Frame 0 shows the stable
May 2023 state; frame 84 shows the stable December 2022 state. Interpolated frames
are transitions, not additional historical boundaries. The standalone December
Phoenix map covers downtown only: importing it as the entire metro would wrongly
remove the East Valley service area.

These are live retrievals of dated historical publications, **not verified
Wayback captures from their publication dates**. Explicit image labels, distinct
older boundaries, and agreement between announcements provide useful evidence;
the five explicit announcement dates have been incorporated as `operator_announcement`,
with original image hashes and checked shapes. They are not relabelled as archive
observations. The month-only Phoenix reconstruction remains a candidate.

## What this reveals about our existing history

Our first Phoenix polygon is 174.02 sq mi, labelled February 12, 2024. Visually its
source map resembles the May 2023 connected area, rather than the larger map in
the July 7, 2023 announcement. This is a concrete conflict to audit: either the
general Help page retained an older map, or our legacy capture/image association
is wrong. Re-fetching the February 12 and April 25, 2024 pages confirms they linked the old
image. The archived image at February 14, 2024 is byte-identical to ours: the general
Help page retained a stale map. The four raw observations remain in the index,
but [observation_exclusions.csv](data/observation_exclusions.csv) excludes them from
the operational sequence in favor of the July 2023 announcement.

Our first SF polygon is 44.37 sq mi and visually resembles the whole-area October
2023 map. The independently fitted October rendition has 98.93% IoU and differs by only
0.03 sq mi; visual inspection confirms the same map. We reuse the existing
higher-resolution geometry with the October 9 announcement date. Earlier December and February maps show distinct
public-service boundaries that would add genuinely new shapes.

## AV Map: useful leads, not automatic imports

At the pinned revision `3c94c4f924c69f425a54debe0c594a286bf16d8c`, AV Map already
has six pre-cutoff Waymo boundary files:

| Metro/date label | Recomputed sq mi | Assessment |
|---|---:|---|
| Phoenix 2017-04-25 | 70.88 | Early-rider program; original boundary image not verified here. |
| Phoenix 2020-10-08 | 50.13 | Driverless public launch is confirmed; original boundary image not verified here. |
| Phoenix 2022-11-01 | 93.30 | Date/scope needs audit: operator's airport announcement initially describes Trusted Testers with a driver. |
| SF 2022-12-16 | 34.69 | Compare against the recovered dark-blue public area, excluding light-blue employee area. |
| Phoenix 2023-05-04 | 172.75 | Compare against the recovered high-resolution official map. |
| SF 2023-08-21 | 44.67 | August 21 is confirmed as a fares date, not independently as the whole-city public-boundary date. |

Areas above were recomputed geodesically on WGS84 from the local pinned geometry
files; they are not official advertised areas. The files and event rows are in
[AV Map's pinned repository](https://github.com/path-avmap/av-map-data/tree/3c94c4f924c69f425a54debe0c594a286bf16d8c).

The [2017 operator post](https://waymo.com/blog/2017/04/apply-to-be-part-of-waymos-early-rider/)
is dated April 24 on the migrated blog, while AV Map and contemporary reporting
use April 25. It documents an early-rider trial, not unrestricted driverless
service. The [2018 launch post](https://waymo.com/blog/2018/12/waymo-one-next-step-on-our-self-driving/)
also explicitly says trained drivers initially supervise rides. Keep those
service modes distinct from the [October 2020 driverless launch](https://waymo.com/blog/2020/10/waymo-is-opening-its-fully-driverless-service-in-phoenix/).

For November 2022, [Waymo's original airport announcement](https://waymo.com/blog/2022/11/making-air-travel-more-convenient-at/)
says Trusted Testers initially travel with a specialist; the December announcement
then opens the airport connection to public driverless rides.

For SF, [the August 16 pricing announcement](https://support.google.com/waymo/answer/13878283?hl=en)
explicitly establishes August 21 as the start of fares. The [August 11 blog](https://waymo.com/blog/2023/08/waymos-next-chapter-in-san-francisco/)
describes gradual access to the whole city. The October 9 Help announcement
explicitly establishes whole-area access for all riders. These events should not
be collapsed into one August polygon update without further evidence.

## Shipped extension

| Metro | Effective announcement date | Drawn sq mi | 2020 residents |
|---|---|---:|---:|
| San Francisco | 2022-12-16 | 34.12 | 528,726 |
| San Francisco | 2023-02-17 | 37.51 | 610,291 |
| San Francisco | 2023-10-09 | 44.37 | 837,390 |
| Phoenix | 2023-05-04 | 174.02 | 809,019 |
| Phoenix | 2023-07-07 | 215.04 | 963,725 |

Five explicit dates add three metropolitan shapes; two are checked equivalents
of existing higher-resolution maps. The May Phoenix pairing has 99.35% IoU.
No AV Map geometry was imported. Nominal operator areas (180 and 225 sq mi) are
kept distinct from the areas traced from the displayed maps.

December SF's automatic alignment failed visual QA. Its corrected alignment uses
532 SIFT/RANSAC inliers against the road-checked February SF image, constrained to
the existing north-up scale/translation model. Median image residual is 0.26 px;
road-match quality is 0.611. The correction is in `data/manual_georef.csv`.
The public-only mask excludes light-blue employee/guest coverage and legend dots
outside the circular map. All five overlays were inspected against OSM roads.

The February 2023 SF announcement was also recovered from an actual June 29,
2023 Wayback capture. Other replay requests returned later captures or failed;
those have not been presented as contemporary evidence. Page/image replay URLs,
Memento timestamps and hashes are in
[the archive audit](data/early_history_archive_audit.json).

The dataset now has 48 canonical city/map versions, 52 image renditions and 45
metropolitan boundary versions. Current coverage remains unchanged. Corrected
February 2024 documented coverage is 259 sq mi and about 1.80 million residents,
versus the previous 218 sq mi and 1.65 million. Before May 4, 2023, totals are
incomplete because Phoenix was operating but lacks an imported boundary. The
interactive map and stacked charts flag that gap; growth statistics start from
May 2023 rather than the incomplete SF-only segment.

The December 2022 full Phoenix animation is not imported: its label supplies only
a month, while the dated December 16 map covers downtown alone. Earlier AV Map
2017/2020 geometry and conflicting date assignments also remain unimported.

## Reproduce

```bash
python fetch_history_images.py
python 02_georeference.py --only-cached
python 03_build_dataset.py
python 05_report_figures.py
python 06_population.py
python compare_external.py
```

The source-image restoration checks both original and prepared hashes before
writing. Run `python -m unittest discover -s areas/waymo/tests -v` from the repo
root for archive-provenance and early-dataset regressions.

Validation: all ten regression tests and dataset integration checks pass. All 45
metro geometries are valid, population joins are complete, current shapes are
unchanged, and all histories outside SF/Phoenix are unchanged. The full site build
passes with freshly generated data-loader caches.
