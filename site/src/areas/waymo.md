---
title: Waymo service areas
toc: false
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">

```js
import {slug, fmtInt, fmtMillions, fmtDate, BLUE, ageColor, activeOn, lookup, areaMap, popup, bounds} from "../components/waymo.js";

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
```

<div class="eyebrow"><a href="../">Robotaxi stats</a></div>

# Waymo service areas

<p class="lede">Where Waymo's robotaxis can take you, from February 2024 to ${dates.at(-1)}. Traced from the maps on Waymo's help pages.</p>

```js
const chips = Inputs.checkbox(allMetros, {value: allMetros.filter((m) => fromHash.includes(slug(m)))});
chips.classList.add("chips");
const picked = view(chips);
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

<div class="grid grid-cols-4">
  <div class="card"><h2>Service area</h2><span class="big">${fmtInt(d3.sum(current, (f) => f.properties.area_mi2))} sq mi</span></div>
  <div class="card"><h2>Residents inside</h2><span class="big">${fmtMillions(d3.sum(current, (f) => f.properties.pop))}</span></div>
  <div class="card"><h2>${picked.length ? "First launch" : "Metros"}</h2><span class="big">${picked.length ? d3.min(selFeatures, (f) => f.properties.valid_from) : allMetros.length}</span></div>
  <div class="card"><h2>Expansions</h2><span class="big">${events.filter((d) => d.kind === "expansion").length}</span></div>
</div>

## Map

<p class="muted">Press play or drag the slider to watch the areas grow. Darker means served longer. Click anywhere on the map to check whether that spot is served, and since when.</p>

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
const mapDiv = display(html`<div class="map"></div>`);
const map = await areaMap(mapDiv, dark);
map.on("click", (e) => popup(map, e.lngLat, lookup(features, [e.lngLat.lng, e.lngLat.lat])));
invalidation.then(() => map.remove());
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

```js
Plot.legend({
  color: {type: "utc", domain: [new Date(dates[0]), new Date(dates.at(-1))], interpolate: color.interpolator()},
  label: "First on the map",
  width: 320
})
```

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
    y: {grid: true, label: null, ticks: 4},
    fy: {label: null, axis: picked.length ? "right" : null},
    marks: [
      Plot.areaY(rows, {x: "date", y, fy: "metro", curve: "step-after", fill: BLUE, fillOpacity: 0.15}),
      Plot.lineY(rows, {x: "date", y, fy: "metro", curve: "step-after", stroke: BLUE, strokeWidth: 2}),
      Plot.ruleY([0]),
      Plot.tip(rows, Plot.pointerX({x: "date", y, fy: "metro", title: (d) => `${d.metro}\n${fmtDate(d.date)}\n${format(d)}`}))
    ]
  });
}
```

<div class="grid grid-cols-2">
  <div class="card">${growth("area_mi2", "Service area (sq mi)", (d) => `${fmtInt(d.area_mi2)} sq mi`)}</div>
  <div class="card">${growth((d) => d.pop / 1e6, "Residents inside (millions)", (d) => `${fmtInt(d.pop)} residents`)}</div>
</div>

<div class="card">

```js
Plot.plot({
  title: "Launches (filled) and expansions (open), sized by area added",
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
      fill: (d) => (d.kind === "launch" ? BLUE : "none"),
      stroke: BLUE,
      strokeWidth: 2,
      channels: {
        Kind: "kind",
        "Added (sq mi)": (d) => fmtInt(d.added),
        "Residents added": (d) => (d.pop_added == null ? "–" : fmtInt(d.pop_added))
      },
      tip: {format: {x: fmtDate, y: true, r: false, fill: false, stroke: false}}
    })
  ]
})
```

</div>

## Launches and expansions

```js
Inputs.table(
  d3.sort(events, (d) => d.date).reverse().map((d) => ({
    Date: d.date,
    Metro: d.metro,
    Kind: d.kind,
    "Added (sq mi)": d.added,
    "Area after (sq mi)": d.after,
    "Residents added": d.pop_added
  })),
  {
    format: {
      Date: fmtDate,
      "Added (sq mi)": fmtInt,
      "Area after (sq mi)": fmtInt,
      "Residents added": (x) => (x == null ? "–" : fmtInt(x))
    }
  }
)
```

<p class="muted">Dates are when a new map first shows up in the Wayback Machine archive; the change itself can be days to weeks earlier. Boundaries are accurate to roughly 50–300 m, and residents count everyone living inside the drawn area. Method and caveats: <a href="https://github.com/EwoutH/robotaxi_stats/blob/main/areas/waymo/report.md">area report</a>, <a href="https://github.com/EwoutH/robotaxi_stats/blob/main/areas/waymo/report_population.md">population report</a>.</p>
