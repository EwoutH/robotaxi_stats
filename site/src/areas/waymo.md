---
title: Waymo service areas
toc: false
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">

```js
import {slug, fmtMonth, areaUnit, prepare, select, metroPicker, segmented, timeline, statTiles, ageColor, ageLegend, areaMap, bounds, drawAreas, growthCharts, eventsChart, eventsTable} from "../components/areas.js";

const areas = FileAttachment("../data/waymo_areas.geojson").json();
const stats = FileAttachment("../data/waymo_stats.json").json();
```

```js
const data = prepare(areas, stats, {name: "Waymo", color: "#2a78d6", colorName: "blue"});
const {dates, allMetros} = data;
const color = ageColor(dates[0], dates.at(-1));
const fromHash = location.hash.slice(1).split(",");
```

<div class="eyebrow"><a href="../">Robotaxi stats</a></div>

# Waymo service areas

<p class="lede">Where Waymo's robotaxis can take you, ${fmtMonth(dates[0])} to ${fmtMonth(dates.at(-1))}.</p>

```js
const picked = view(metroPicker(allMetros, data.states, allMetros.filter((m) => fromHash.includes(slug(m)))));
```

```js
const unitInput = segmented({mi: "mi²", km: "km²"}, "mi");
const unitKey = Generators.input(unitInput);
```

```js
const unit = areaUnit(unitKey);
```

```js
// Nothing selected = all metros. The selection is kept in the URL so it can be shared.
const metros = picked.length ? picked : allMetros;
const sel = select(data, metros);
history.replaceState(null, "", picked.length ? `#${picked.map(slug).join(",")}` : location.pathname);
```

```js
const pick = view(timeline(dates, invalidation));
```

```js
const date = dates[pick];
```

```js
statTiles(data, sel, date, unit, unitInput)
```

```js
const mapDiv = display(html`<div class="map"></div>`);
const map = await areaMap(mapDiv, dark, data);
invalidation.then(() => map.remove());
```

```js
map.scale.setUnit(unit.key === "km" ? "metric" : "imperial");
```

```js
map.fitBounds(bounds(sel.current), {padding: 40, maxZoom: 11});
```

```js
drawAreas(map, sel.features, date, (f) => color(new Date(f.properties.valid_from)));
```

<div class="map-footer">

```js
ageLegend(color, dates)
```

<span class="hint">Click the map to check a spot.</span>

</div>

## Growth

```js
growthCharts(data, sel.timeseries, {picked, width, unit})
```

<div class="card">

```js
eventsChart(data, sel.events, {metros, width, unit})
```

</div>

## Earliest data, launches and expansions

```js
eventsTable(data, sel.events, unit)
```

<p class="small muted">Traced from Waymo's published maps. Dates usually record the first verified map observation; early SF/Phoenix and two Austin dates use dated operator announcements. Observed changes can have happened earlier within the documented date window. Austin/Atlanta archive provenance was repaired in November 2026; the early SF/Phoenix extension also excludes a documented stale Help map. Other history retains the earlier reconstruction pending audit. Boundaries are accurate to roughly 50–300 m; residents are from the 2020 Census. Details: <a href="https://github.com/EwoutH/robotaxi_stats/tree/main/areas/waymo">method and data</a>, <a href="https://github.com/EwoutH/robotaxi_stats/releases/tag/waymo-reports-2026-11">reports (Nov 2026)</a>.</p>
