# Robotaxi stats

Data and analysis on robotaxi services, built from public sources.

## Contents

| Folder | What it holds |
|---|---|
| [`areas/waymo/`](areas/waymo/) | Waymo's service areas over time as georeferenced polygons (Feb 2024 to now), with reports on area and residents served. A daily GitHub Actions check ([`waymo_maps.yml`](.github/workflows/waymo_maps.yml)) archives new service-area maps and opens an issue when one appears. |

Each folder has its own README with sources, outputs and how to rebuild the data.
