# Robotaxi stats

Data and analysis on robotaxi services, built from public sources.

**Site: https://ewouth.github.io/robotaxi_stats/**

## Contents

| Folder | What it holds |
|---|---|
| [`areas/waymo/`](areas/waymo/) | Waymo's service areas over time as georeferenced polygons (Feb 2024 to now), with reports on area and residents served. A daily GitHub Actions check ([`waymo_maps.yml`](.github/workflows/waymo_maps.yml)) archives new service-area maps and opens an issue when one appears. |
| [`site/`](site/) | The public site: interactive map with a time slider, growth charts, and selection by metro or state, built with [Observable Framework](https://observablehq.com/framework/) from the data above. [`site.yml`](.github/workflows/site.yml) publishes it to GitHub Pages on every push to `main`. Run it locally with `npm install` and `npm run dev` in `site/` (needs Python with geopandas). |

Each folder has its own README with sources, outputs and how to rebuild the data.
