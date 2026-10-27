# Waymo service areas, Feb 2024 – Oct 2026

*Based on 42 service-area maps traced from Waymo's help pages via archive.org
(see [README.md](README.md) for method and accuracy). All areas are as drawn by
Waymo, in square miles; figures and numbers come from [05_report_figures.py](05_report_figures.py).*

## Key numbers

| | |
|---|---|
| Total service area, Feb 2024 | **218 sq mi** (Phoenix, SF) |
| Total service area, Oct 27 2026 | **1,891 sq mi** across 15 metros |
| Growth | **×8.7** in 2.7 years, about ×2.2 per year (doubling every ~10 months) |
| Total at year end | 2024: 468 · 2025: 952 · 2026 (to date): 1,891 |
| New metros on the page | 2024: 4 · 2025: 1 · 2026: 10 |
| Expansions of existing metros | 2024: 3 · 2025: 8 · 2026: 13 (median 134 days between expansions in a metro) |
| Area added by expansions | 1,027 sq mi, of which **13.5 sq mi** removed elsewhere (1.3%) |
| Share of Phoenix + SF + LA | 100% in early 2024 → **48%** now |

## Growth went from linear to compounding

![Total service area](figures/report/total_area.svg)

Until mid-2025, growth came from expanding the three original markets. From mid-2025,
new cities did most of the work: Austin's big jump (Jun 2025), Atlanta, and then
ten launches in 2026. The newer metros now cover more area together (977 sq mi)
than Phoenix, SF and LA combined (914 sq mi).

## When each metro launched and grew

![Timeline of launches and expansions](figures/report/timeline.svg)

- **2026 is the year of new cities.** Miami, Dallas, Houston, Orlando and San Antonio
  appeared within four weeks (Jan 31 – Feb 28), Nashville in April, and Denver,
  San Diego, Tampa and Las Vegas in September.
- **Expansions are getting more frequent.** There were 13 so far in 2026, against 8 in all
  of 2025. On today's live page alone, five metros have new maps (LA, SF, Orlando,
  Nashville, San Diego).
- Phoenix is the exception: its map stayed the same for over two years (Jul 2024 →
  Sep 2026), then grew 57 sq mi into Gilbert and Chandler.

## Launch small, then grow

![Service area at launch vs now](figures/report/launch_vs_now.svg)

New metros follow a template. The median launch size in 2026 was **49 sq mi**, and every
2026 launch was between 22 and 58 sq mi. Atlanta (112 sq mi, launched via Uber) is the
only recent large launch. The 2024 Phoenix launch (174 sq mi) reflects an older,
already-mature market.

Metros then grow fast. SF grew **×7.8** (44 → 348 sq mi), Austin ×4.2, LA ×3.8 and
Miami ×2.9 in just four months.

![Service area over time per metro](figures/report/growth_grid.svg)

On the same scale, the gap is clear: Phoenix and SF are now about 350 sq mi each, LA
213, and Miami and Austin about 150. Six of the ten 2026 launches are still under
60 sq mi. Five metros still carry the label "Gradually adding riders" (Dallas, Denver, Houston, Las Vegas, Tampa: 224 sq mi, 12% of the total).

## Biggest single expansions

| Date first seen | Metro | Before → after (sq mi) | Added |
|---|---|---|---|
| 2025-11-13 | San Francisco (Peninsula) | 134 → 262 | **+127** |
| 2024-07-12 | Phoenix | 174 → 300 | +126 |
| 2025-06-12 | Austin (move to Uber page) | 35 → 150 | +115 |
| 2026-10-27 | Los Angeles (South Bay to Torrance) | 125 → 213 | +89 |
| 2026-06-06 | San Francisco (to San José/Campbell) | 278 → 339 | +63 |
| 2026-06-06 | Miami (north to Miami Gardens) | 89 → 151 | +62 |
| 2026-09-07 | Phoenix (Gilbert/Chandler) | 300 → 353 | +57 |
| 2025-06-17 | San Francisco (to Burlingame + larger Silicon Valley zone) | 81 → 134 | +53 |

**Service areas almost never shrink.** Across 24 expansions, only 13.5 sq mi
disappeared from earlier maps, against 1,027 sq mi added. The largest removal is
3.7 sq mi (Phoenix, Sep 2026). Some of that removed area is probably just tracing
error between map versions rather than a real cutback.

## Shape and scale

![Current service areas at the same scale](figures/report/same_scale.svg)

- **SF Bay Area** is an 83 km corridor from the Golden Gate to Campbell and is the least
  compact area (Polsby-Popper 0.16; a circle is 1.0). It's shaped by the Peninsula
  between the ocean and the bay.
- **Phoenix** (353 sq mi) is the largest area, a grid-aligned block 54 km tall.
- **Las Vegas** is the smallest (23 sq mi) and most compact (0.52): one rectangle around
  the Strip and downtown.
- Most 2026 launches fit in a 15–25 km box.

## How SF and LA grew

Each panel is one version of the map: orange is new in that version, blue was already
served. All panels for a metro share the same extent. Basemap: Esri World Light Gray Canvas.

![San Francisco versions](figures/report/versions_san_francisco.svg)

San Francisco grew in nine steps: the city (Feb 2024) → Daly City (Aug 2024) →
a separate Silicon Valley zone (Mar 2025) → SF down to Burlingame (Jun 2025) → the
full Peninsula linking both (Nov 2025) → San José and Campbell (2026).

![Los Angeles versions](figures/report/versions_los_angeles.svg)

Los Angeles started as a Santa Monica–DTLA strip, then filled in toward the airport
and Inglewood. The latest map (Oct 27 2026) adds the South Bay down to Torrance.

## Caveats

- Dates are when a new map **first appeared in the archive**, not announcement dates. The
  actual change happened between the previous snapshot and that date. For metros
  that were already running when the archive starts (Phoenix, SF), "launch" means
  "first map on the page".
- Areas are as drawn, including water inside the blue fill (Biscayne Bay, Mission Bay).
  Boundaries are accurate to roughly 50–300 m, so differences under ~2 sq mi between
  versions aren't meaningful.
- The page shows public rider service areas. It doesn't show testing areas, airport
  access or freeway-only extensions.

Data: [waymo_service_areas.gpkg](waymo_service_areas.gpkg) ·
[data/area_timeseries.csv](data/area_timeseries.csv) ·
[data/expansion_events.csv](data/expansion_events.csv) ·
[data/report_stats.json](data/report_stats.json)
