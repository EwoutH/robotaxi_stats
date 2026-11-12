---
title: Tesla Robotaxi service areas
toc: false
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css">
<style>:root { --accent: #d6312b; }</style>

```js
import {slug, fmtInt, fmtMonth, areaUnit, prepare, select, metroPicker, segmented, timeline, statTiles, ageColor, ageLegend, areaMap, bounds, drawAreas, growthCharts, eventsChart, eventsTable} from "../components/areas.js";

const areas = FileAttachment("../data/tesla_areas.geojson").json();
const stats = FileAttachment("../data/tesla_stats.json").json();
const status = FileAttachment("../data/tesla_status.json").json();
```

```js
const RED = "#d6312b";
const PURPLE = "#8a6fd1"; // AV Map in the coverage chart
const AMBER = "#d9902f"; // Tesla's maps (traced) in the coverage chart
// Sequential red ramp, light (recent) to dark (old).
const RAMP = ["#f0a29b", "#ea8c83", "#e3766c", "#dc5f55", "#d6493f", "#c93a31", "#b5322a", "#9e2a23", "#87231d", "#701c17"];
const data = prepare(areas, stats, {name: "Tesla", color: RED, colorName: "red"});
const {dates, allMetros} = data;
const color = ageColor(dates[0], dates.at(-1), RAMP);
const fromHash = location.hash.slice(1).split(",");
```

```js
// What the data covers, derived from the boundary versions and tesla.com.
const versions = d3.sort(data.features.map((f) => f.properties), (p) => p.metro, (p) => p.valid_from);
const lastChange = dates.at(-1);
const lastAnnounced = d3.max(versions.filter((p) => p.source === "av_map"), (p) => p.valid_from);
const lastTracker = d3.max(versions.filter((p) => p.source === "robotaxi_tracker"), (p) => p.valid_from);
const traced = versions.filter((p) => p.source === "tesla_map");
const firstSeen = d3.min(versions.filter((p) => p.date_kind === "first_seen"), (p) => p.valid_from);
// Where AV Map hands over to Robotaxi Tracker: the area change is between sources, not on the ground.
const switches = versions.flatMap((p, i) => {
  const prev = versions[i - 1];
  return prev && prev.metro === p.metro && prev.source === "av_map" && p.source === "robotaxi_tracker" ? [{...p, change: p.area_mi2 - prev.area_mi2}] : [];
});
const cityOf = (metro) => versions.find((p) => p.metro === metro)?.city ?? metro;
const statusRow = (d) => d.metro ?? d.name;
const listed = new Map(status.cities.map((d) => [statusRow(d), d]));
const firstNamed = status.cities.filter((d) => d.since === status.cities_from).map((d) => d.name);
const soon = status.cities.filter((d) => d.status === "soon" && !allMetros.includes(statusRow(d)));
const list = (xs) => new Intl.ListFormat("en").format(xs);
const DATE_IS = {announced: "Announced", first_seen: "First seen", opened: "Listed open"};
```

<div class="eyebrow"><a href="../">Robotaxi stats</a></div>

# Tesla Robotaxi service areas

<p class="lede">Where Tesla's Robotaxi service can take you, ${fmtMonth(dates[0])} to ${fmtMonth(lastChange)}, from boundaries traced by two community projects and from Tesla's own maps.</p>

<p class="small muted">Tesla publishes no service-area polygons, only map images in its app and its announcements, so this record is thinner than the <a href="./waymo">Waymo one</a>: many dates are when a boundary was first recorded, not when it changed; there are no boundaries between ${lastAnnounced} and ${firstSeen}; and the latest recorded change is from ${lastChange}. See <a href="#what-the-data-covers">what the data covers</a>.</p>

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
eventsTable(data, sel.events, unit, {
  columns: {
    "Date is": (d) => DATE_IS[d.date_kind],
    "On tesla.com": (d) => (d.kind === "expansion" ? null : listed.get(d.metro)?.status === "open" ? listed.get(d.metro).since : null),
    Source: (d) => d.source_url
  },
  format: {
    "On tesla.com": (x) => x ?? "–",
    Source: (url) => html`<a href=${url} target="_blank" rel="noopener">${new URL(url).hostname.replace(/^www\./, "")}</a>`
  }
})
```

<p class="small muted">A metro's first boundary counts as a launch when its date is an announcement or the date tesla.com first listed the city open, and as earliest data when it is the date Robotaxi Tracker first recorded it; the service may have started earlier, as the date tesla.com first listed it open shows. Later boundaries count as expansions when they add at least 5% to the area; smaller edits stay in the map and charts.</p>

## What the data covers

```js
// One bar per boundary version, colored by where its date comes from; faded where no source covers it.
const end = d3.max([lastChange, status.last_capture]);
const segments = versions.flatMap((p) => {
  const from = p.valid_from, to = p.valid_to ?? end;
  const cuts = [from, ...[lastAnnounced, firstSeen].filter((d) => d > from && d < to), to];
  return d3.pairs(cuts).map(([a, b]) => ({...p, a: new Date(a), b: new Date(b), carried: a >= lastAnnounced && b <= firstSeen}));
});
const SOURCES = {av_map: "Announced (AV Map)", robotaxi_tracker: "First seen (Robotaxi Tracker)", tesla_map: "Announced (Tesla's maps, traced)"};
const rows = [...allMetros, ...soon.map(statusRow)];
display(Plot.plot({
  title: "Boundary versions per metro, and when tesla.com listed each city",
  width,
  height: 70 + rows.length * 30,
  marginLeft: 90,
  marginTop: 34,
  x: {domain: [new Date(dates[0]), new Date(end)], grid: true, label: null},
  y: {domain: rows, label: null, tickFormat: cityOf},
  color: {domain: Object.values(SOURCES), range: [PURPLE, RED, AMBER], legend: true},
  marks: [
    Plot.rectX([{a: new Date(lastAnnounced), b: new Date(firstSeen)}], {x1: "a", x2: "b", fill: "currentColor", fillOpacity: 0.06}),
    Plot.text([new Date(lastAnnounced)], {x: (d) => d, frameAnchor: "top", dy: -20, dx: 4, textAnchor: "start", text: () => "No boundary source", fill: "currentColor", fillOpacity: 0.7}),
    Plot.barX(segments, {
      x1: "a",
      x2: "b",
      y: "metro",
      fill: (d) => SOURCES[d.source],
      fillOpacity: (d) => (d.carried ? 0.3 : 0.9),
      insetLeft: 1,
      insetRight: 1,
      insetTop: 6,
      insetBottom: 6,
      title: (d) => `${d.city}: ${fmtInt(d.area_mi2)} sq mi\nfrom ${d.valid_from} (${DATE_IS[d.date_kind].toLowerCase()})${d.valid_to ? ` to ${d.valid_to}` : ", latest"}${d.carried ? "\nno source covers this stretch" : ""}`,
      tip: true
    }),
    Plot.ruleX([new Date(lastChange)], {strokeDasharray: "3,3", strokeOpacity: 0.6}),
    Plot.text([new Date(lastChange)], {x: (d) => d, frameAnchor: "top", dy: -6, dx: -4, textAnchor: "end", text: () => "Latest change", fill: "currentColor", fillOpacity: 0.7}),
    Plot.dot(status.cities, {
      x: (d) => new Date(d.since),
      y: statusRow,
      symbol: "diamond2",
      r: 5,
      stroke: "currentColor",
      strokeWidth: 1.5,
      fill: (d) => (d.status === "open" ? "currentColor" : "none"),
      title: (d) => `${d.name} listed as "${d.status}" on tesla.com from ${d.since}${d.since === status.cities_from ? "\n(first capture naming any city)" : d.window_start ? `\n(changed between ${d.window_start} and ${d.since})` : ""}`,
      tip: true
    })
  ]
}));
```

<p class="small muted">Bars are boundary versions; faded where a version is only assumed to stay in force. ◆ listed as open on tesla.com, ◇ listed as coming soon.</p>

<div class="grid grid-cols-2" style="grid-auto-rows: auto;">
<div>

**What it has**

- Boundary shapes for the ${allMetros.length} metros tesla.com lists as open, ${versions.length} versions in all, each from the date tesla.com first listed it open (or earlier, for ${list(firstNamed)}, which it listed before naming any other city). Up to ${lastAnnounced} they come from [AV Map](https://github.com/path-avmap/av-map-data), dated by news reports of Tesla's announcements. From ${firstSeen} on they come from [Robotaxi Tracker](https://github.com/Robotaxi-Tracker/robotaxi-service-areas), which takes them from the Tesla Robotaxi app's fleet areas.${traced.length ? ` Changes since its last update (${lastTracker}) are traced from the maps Tesla posts with its announcements, or from app screenshots, and dated by the announcement: ${list(traced.map((p) => `${p.city} (${p.valid_from})`))}. Their edges are good to about 100–250 m.` : ""}
- Residents inside each version, from 2020 Census blocks, counted the same way as for [Waymo](./waymo). Population growth since 2020 is not included.
- Tesla's own city status ("open" or "coming soon") from archived copies of [tesla.com/robotaxi](https://www.tesla.com/robotaxi), ${status.first_capture} to ${status.last_capture}.

</div>
<div>

**What it lacks**

- **Exact dates.** Robotaxi Tracker dates are when it first recorded a shape, which can be days or weeks after Tesla changed it. Its history starts on ${firstSeen}, so that date is the earliest data for metros already served, not their launch.
- **${lastAnnounced} to ${firstSeen}.** No source has boundaries in this stretch; the last announced ones are assumed to stay in force. Where the sources meet, ${list(switches.map((d) => `${d.city} (${d.change > 0 ? "+" : "−"}${fmtInt(Math.abs(d.change))} sq mi)`))} changed by the difference between the sources, not on the ground.
- **Anything after ${lastChange}**, the latest recorded change. Changes Tesla announced since are missing until they are traced or Robotaxi Tracker records them.
- **Cities tesla.com does not list as open.** It lists ${list(soon.map((d) => d.name))} as coming soon, without boundaries${status.not_shown.length ? html`, and does not list ${list(status.not_shown)}, so ${status.not_shown.length > 1 ? "their" : "its"} boundaries are left out` : ""}. It named no cities before ${status.cities_from}, so ${list(firstNamed)}'s date there is when the page first named ${firstNamed.length > 1 ? "them" : "it"}, not a launch.

</div>
</div>

<p class="small muted">Boundaries from <a href="https://github.com/Robotaxi-Tracker/robotaxi-service-areas">Robotaxi Tracker</a> (CC BY 4.0) and <a href="https://github.com/path-avmap/av-map-data">AV Map</a> (MIT), and traced from Tesla's maps on <a href="https://x.com/robotaxi">X</a> and app screenshots; city status from the <a href="https://web.archive.org/web/*/https://www.tesla.com/robotaxi">Wayback Machine</a>. Tesla calls the San Francisco metro "Bay Area". Areas are geodesic. Details: <a href="https://github.com/EwoutH/robotaxi_stats/tree/main/areas/tesla">method and data</a>.</p>
