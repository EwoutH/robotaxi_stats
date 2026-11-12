---
title: Zoox service areas
toc: false
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">
<style>:root { --accent: #139a8a; }</style>

```js
import {slug, fmtMonth, areaUnit, prepare, select, metroPicker, segmented, timeline, statTiles, ageColor, ageLegend, areaMap, bounds, drawAreas, growthCharts, eventsChart, eventsTable} from "../components/areas.js";

const areas = FileAttachment("../data/zoox_areas.geojson").json();
const stats = FileAttachment("../data/zoox_stats.json").json();
```

```js
const data = prepare(areas, stats, {name: "Zoox", color: "#139a8a", colorName: "teal"});
const {dates, allMetros} = data;
const RAMP = ["#9ee0d4", "#8dd0c4", "#7dc0b4", "#6cafa4", "#5b9f94", "#4b8e84", "#3a7e74", "#296d65", "#185d55", "#084c45"];
const color = ageColor(dates[0], dates.at(-1), RAMP);
const fromHash = location.hash.slice(1).split(",");
```

<div class="eyebrow"><a href="../">Robotaxi stats</a></div>

# Zoox service areas

<p class="lede">Where Zoox's robotaxis can take you, ${fmtMonth(dates[0])} to ${fmtMonth(dates.at(-1))}.</p>

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

<p class="small muted">Zoox publishes no boundaries, only map images, so this page combines two community datasets: <a href="https://github.com/path-avmap/av-map-data">AV Map</a> (MIT), dated by announcements, and <a href="https://github.com/Robotaxi-Tracker/robotaxi-service-areas">Robotaxi Tracker</a> (CC BY 4.0), dated when it first recorded a shape, so a change can be older than its date. Both trace Zoox's map images. Missing: the Las Vegas area now reaches downtown on <a href="https://zoox.com/zoox-operating-areas">Zoox's own map</a> (August 2026), which neither dataset has yet. Las Vegas is open to the public, San Francisco to select riders. Residents are from the 2020 Census. Details: <a href="https://github.com/EwoutH/robotaxi_stats/tree/main/areas/zoox">method and data</a>.</p>
