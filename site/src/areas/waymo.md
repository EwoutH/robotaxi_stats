---
title: Waymo service areas
toc: false
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">

```js
import {slug, fmtInt, fmtMillions, fmtResidents, fmtDate, BLUE, UNITS, ageColor, activeOn, lookup, areaMap, popup, bounds, metroPicker, segmented} from "../components/areas.js";

const areas = FileAttachment("../data/waymo_areas.geojson").json();
const waymo = FileAttachment("../data/waymo_stats.json").json();
```

```js
const features = areas.features;
const dates = [...new Set(waymo.timeseries.map((d) => d.date))].sort();
const color = ageColor(dates[0], dates.at(-1));
// Metros in launch order.
const allMetros = d3.groupSort(features, (v) => d3.min(v, (f) => f.properties.valid_from), (f) => f.properties.metro);
const fromHash = location.hash.slice(1).split(",");
const fmtMonth = (d) => d3.utcFormat("%b %Y")(new Date(d));
```

<div class="eyebrow"><a href="../">Robotaxi stats</a></div>

# Waymo service areas

<p class="lede">Where Waymo's robotaxis can take you, ${fmtMonth(dates[0])} to ${fmtMonth(dates.at(-1))}.</p>

```js
const picked = view(metroPicker(allMetros, Object.fromEntries(waymo.metros.map((d) => [d.metro, d.state])), allMetros.filter((m) => fromHash.includes(slug(m)))));
```

```js
const unitInput = segmented({mi: "mi²", km: "km²"}, "mi");
const unit = Generators.input(unitInput);
```

```js
// Nothing selected = all metros. The selection is kept in the URL so it can be shared.
const metros = picked.length ? picked : allMetros;
const inSel = (m) => metros.includes(m);
const selFeatures = features.filter((f) => inSel(f.properties.metro));
const current = selFeatures.filter((f) => !f.properties.valid_to);
const series = waymo.timeseries.filter((d) => inSel(d.metro));
const events = waymo.events.filter((d) => inSel(d.metro)).map((d) => ({...d, date: new Date(d.date)}));
history.replaceState(null, "", picked.length ? `#${picked.map(slug).join(",")}` : location.pathname);
```

```js
// Areas are stored in square miles; convert for display.
const {label: areaLabel, factor: K} = UNITS[unit];
const fmtArea = (mi2) => `${fmtInt(mi2 * K)} ${areaLabel}`;
```

```js
// Slider over snapshot dates, with a play button that steps through them.
const slider = Inputs.range([0, dates.length - 1], {step: 1, value: dates.length - 1});
const playButton = html`<button class="play" title="Play">▶</button>`;
const dateLabel = html`<span class="timeline-date"></span>`;
display(html`<div class="timeline">${playButton}${slider}${dateLabel}</div>`);
const pick = Generators.input(slider);

let timer = null;
const setIndex = (i) => {
  slider.value = i;
  slider.dispatchEvent(new Event("input", {bubbles: true}));
};
const stop = () => {
  clearInterval(timer);
  timer = null;
  playButton.textContent = "▶";
};
playButton.onclick = () => {
  if (timer) return stop();
  if (+slider.value >= dates.length - 1) setIndex(0);
  playButton.textContent = "❚❚";
  timer = setInterval(() => (+slider.value >= dates.length - 1 ? stop() : setIndex(+slider.value + 1)), 150);
};
invalidation.then(stop);
```

```js
const date = dates[pick];
dateLabel.textContent = date;
```

```js
// Stats for the selected metros on the slider date.
const live = selFeatures.filter((f) => activeOn(f, date));
```

<div class="stats">
  <div><div class="stat-label">Service area</div><div class="stat-value">${fmtArea(d3.sum(live, (f) => f.properties.area_mi2))}</div></div>
  <div><div class="stat-label">Residents inside</div><div class="stat-value">${fmtResidents(live.map((f) => f.properties.pop))}</div></div>
  <div><div class="stat-label">Metros</div><div class="stat-value">${live.length}</div></div>
  <div><div class="stat-label">Expansions so far</div><div class="stat-value">${events.filter((d) => d.kind === "expansion" && fmtDate(d.date) <= date).length}</div></div>
  <div class="stats-unit">${unitInput}</div>
</div>

```js
const mapDiv = display(html`<div class="map"></div>`);
const map = await areaMap(mapDiv, dark);
map.on("click", (e) => popup(map, e.lngLat, lookup(features, [e.lngLat.lng, e.lngLat.lat])));
// "My location" also answers whether that spot is served.
map.geolocate.on("geolocate", ({coords: {longitude, latitude}}) =>
  popup(map, [longitude, latitude], lookup(features, [longitude, latitude]))
);
invalidation.then(() => map.remove());
```

```js
map.scale.setUnit(unit === "km" ? "metric" : "imperial");
```

```js
map.fitBounds(bounds(current), {padding: 40, maxZoom: 11});
```

```js
// Every version up to this date. Oldest last, so it draws on top and the rings show how each area grew.
const shown = d3.sort(selFeatures.filter((f) => f.properties.valid_from <= date), (f) => f.properties.valid_from).reverse();
map.getSource("areas").setData({
  type: "FeatureCollection",
  features: shown.map((f) => ({
    ...f,
    properties: {...f.properties, color: color(new Date(f.properties.valid_from)), active: activeOn(f, date)}
  }))
});
map.getSource("dots").setData({
  type: "FeatureCollection",
  features: shown
    .filter((f) => activeOn(f, date))
    .map((f) => ({type: "Feature", geometry: {type: "Point", coordinates: d3.geoCentroid(f)}, properties: {}}))
});
```

<div class="map-footer">

```js
Plot.legend({
  color: {type: "utc", domain: [new Date(dates[0]), new Date(dates.at(-1))], interpolate: color.interpolator()},
  label: "First on the map (darker = served longer)",
  width: 300
})
```

<span class="hint">Click the map to check a spot.</span>

</div>

## Growth

```js
// Without a selection, chart the total; with one, one row per metro.
const rows = picked.length
  ? series.map((d) => ({...d, date: new Date(d.date)}))
  : d3.rollups(series, (v) => ({area_mi2: d3.sum(v, (d) => d.area_mi2), pop: d3.sum(v, (d) => d.pop)}), (d) => d.date)
      .map(([date, t]) => ({date: new Date(date), metro: "All metros", ...t}));
const xDomain = [new Date(dates[0]), new Date(dates.at(-1))];

function growth(y, title, format) {
  return Plot.plot({
    title,
    width: Math.min(width, 640),
    height: picked.length > 1 ? 30 + 110 * picked.length : 260,
    marginRight: picked.length ? 100 : 20,
    x: {domain: xDomain, label: null},
    y: {grid: true, label: null, ticks: 4, domain: [0, d3.max(rows, y) || 1], nice: true},
    fy: {label: null, axis: picked.length ? "right" : null},
    marks: [
      Plot.areaY(rows, {x: "date", y, fy: "metro", curve: "step-after", fill: BLUE, fillOpacity: 0.15}),
      Plot.lineY(rows, {x: "date", y, fy: "metro", curve: "step-after", stroke: BLUE, strokeWidth: 2}),
      Plot.ruleY([0]),
      // Mark the latest value, so a metro with a single snapshot still shows up.
      Plot.dot(rows, Plot.selectLast({x: "date", y, fy: "metro", fill: BLUE, r: 3})),
      Plot.tip(rows, Plot.pointerX({x: "date", y, fy: "metro", title: (d) => `${d.metro}\n${fmtDate(d.date)}\n${format(d)}`}))
    ]
  });
}
```

<div class="grid grid-cols-2">
  <div class="card">${growth((d) => d.area_mi2 * K, `Service area (${areaLabel})`, (d) => fmtArea(d.area_mi2))}</div>
  <div class="card">${growth((d) => (d.pop == null ? null : d.pop / 1e6), "Residents inside (millions)", (d) => `${fmtInt(d.pop)} residents`)}</div>
</div>

<div class="card">

```js
Plot.plot({
  title: "Earliest data (gray), launches (blue), expansions (open)",
  width,
  height: 40 + metros.length * 28,
  marginLeft: 100,
  x: {domain: xDomain, grid: true, label: null, insetLeft: 16, insetRight: 16},
  y: {domain: metros, label: null},
  r: {domain: [0, d3.max(waymo.events, (d) => d.added)], range: [0, 14]},
  marks: [
    Plot.dot(events, {
      x: "date",
      y: "metro",
      r: "added",
      fill: (d) => (d.kind === "earliest_data" ? "#6b7280" : d.kind === "launch" ? BLUE : "none"),
      stroke: (d) => (d.kind === "earliest_data" ? "#6b7280" : BLUE),
      strokeWidth: 2,
      channels: {
        Kind: "kind_label",
        Added: (d) => fmtArea(d.added),
        "Residents added": (d) => (d.pop_added == null ? "–" : fmtInt(d.pop_added))
      },
      tip: {format: {x: fmtDate, y: true, r: false, fill: false, stroke: false}}
    })
  ]
})
```

</div>

## Earliest data, launches and expansions

```js
Inputs.table(
  d3.sort(events, (d) => d.date).reverse().map((d) => ({
    Date: d.date,
    Metro: d.metro,
    Kind: d.kind_label,
    [`Added (${areaLabel})`]: d.added * K,
    [`Area after (${areaLabel})`]: d.after * K,
    "Residents added": d.pop_added
  })),
  {
    format: {
      Date: fmtDate,
      [`Added (${areaLabel})`]: fmtInt,
      [`Area after (${areaLabel})`]: fmtInt,
      "Residents added": (x) => (x == null ? "–" : fmtInt(x))
    }
  }
)
```

<p class="small muted">Traced from Waymo's published maps. Dates usually record the first verified map observation; early SF/Phoenix and two Austin dates use dated operator announcements. Observed changes can have happened earlier within the documented date window. Austin/Atlanta archive provenance was repaired in November 2026; the early SF/Phoenix extension also excludes a documented stale Help map. Other history retains the earlier reconstruction pending audit. Boundaries are accurate to roughly 50–300 m; residents are from the 2020 Census. Details: <a href="https://github.com/EwoutH/robotaxi_stats/tree/main/areas/waymo">method and data</a>, <a href="https://github.com/EwoutH/robotaxi_stats/releases/tag/waymo-reports-2026-11">reports (Nov 2026)</a>.</p>
