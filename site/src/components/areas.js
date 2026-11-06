// Service-area pages for any operator: data preparation, inputs, map, charts and table.
// Data format: see site/src/data/contract.py. The page adds its own text and the operator's look,
// {name, color, colorName}. Every data row also carries an operator id, for a later page that combines operators.
// Population may be missing (null) for some or all versions; residents are then left out.
import * as d3 from "npm:d3";
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import maplibregl from "npm:maplibre-gl@5.24.0";

export const slug = (name) => name.toLowerCase().replace(/\s+/g, "-");
export const fmtInt = d3.format(",.0f");
export const fmtMillions = (x) => `${d3.format(".2f")(x / 1e6)}M`;
// Sum of residents; "–" if none are known yet, and "+" if some are missing (e.g. a new map before its population is computed).
export function fmtResidents(values) {
  const known = values.filter((v) => v != null);
  if (!known.length) return "–";
  return fmtMillions(d3.sum(known)) + (known.length < values.length ? "+" : "");
}
export const fmtDate = d3.utcFormat("%Y-%m-%d");
export const fmtMonth = (d) => d3.utcFormat("%b %Y")(new Date(d));
const GRAY = "#6b7280";

// Area units. Source data is in square miles.
export const UNITS = {mi: {label: "sq mi", factor: 1}, km: {label: "km²", factor: 2.589988}};
export function areaUnit(key) {
  const {label, factor} = UNITS[key];
  return {key, label, factor, fmt: (mi2) => `${fmtInt(mi2 * factor)} ${label}`};
}

// The loaders' areas (GeoJSON) and stats (JSON), with what every page derives from them.
// operator: {name, color, colorName}, e.g. {name: "Waymo", color: "#2a78d6", colorName: "blue"}.
export function prepare(areas, stats, operator) {
  const features = areas.features;
  return {
    operator,
    features,
    timeseries: stats.timeseries,
    events: stats.events,
    dates: [...new Set(stats.timeseries.map((d) => d.date))].sort(),
    // Metros in launch order.
    allMetros: d3.groupSort(features, (v) => d3.min(v, (f) => f.properties.valid_from), (f) => f.properties.metro),
    states: Object.fromEntries(stats.metros.map((d) => [d.metro, d.state])),
    hasPop: stats.timeseries.some((d) => d.pop != null) || features.some((f) => f.properties.pop != null)
  };
}

// The data for a list of metros.
export function select(data, metros) {
  const inSel = (m) => metros.includes(m);
  const features = data.features.filter((f) => inSel(f.properties.metro));
  return {
    features,
    current: features.filter((f) => !f.properties.valid_to),
    timeseries: data.timeseries.filter((d) => inSel(d.metro)),
    events: data.events.filter((d) => inSel(d.metro)).map((d) => ({...d, date: new Date(d.date)}))
  };
}

function el(tag, className, text, onclick) {
  const node = document.createElement(tag);
  node.className = className;
  if (text != null) node.textContent = text;
  if (onclick) node.onclick = onclick;
  return node;
}

// Metro picker grouped by state (states: {metro: state name}): click a metro to toggle it, or a state name to toggle all its metros.
// Works as an Observable input: .value is the selected metros, and it fires "input" on change.
export function metroPicker(metros, states, initial = []) {
  const root = el("div", "picker");
  // Alphabetical, with metros missing a state ("Other") last.
  const groups = d3.sort(d3.groups(metros, (m) => states[m] ?? "Other"), ([state]) => [state === "Other", state]);
  let value = metros.filter((m) => initial.includes(m));
  const set = (next) => {
    value = metros.filter((m) => next.includes(m));
    render();
    root.dispatchEvent(new Event("input", {bubbles: true}));
  };
  function render() {
    const groupNodes = groups.map(([state, members]) => {
      const all = members.every((m) => value.includes(m));
      const group = el("div", "picker-group");
      group.append(
        el("button", `picker-state${all ? " on" : ""}`, state, () =>
          set(all ? value.filter((m) => !members.includes(m)) : [...value, ...members])
        ),
        ...members.map((m) =>
          el("button", `chip${value.includes(m) ? " on" : ""}`, m, () =>
            set(value.includes(m) ? value.filter((v) => v !== m) : [...value, m])
          )
        )
      );
      return group;
    });
    const clear = value.length ? [el("button", "picker-clear", "Show all", () => set([]))] : [];
    root.replaceChildren(...groupNodes, ...clear);
  }
  Object.defineProperty(root, "value", {get: () => value, set: (v) => ((value = v), render())});
  render();
  return root;
}

// Small segmented control, e.g. for units. Same input contract as metroPicker.
export function segmented(options, initial) {
  const root = el("div", "segmented");
  let value = initial;
  const render = () =>
    root.replaceChildren(
      ...Object.entries(options).map(([key, label]) =>
        el("button", key === value ? "on" : "", label, () => {
          value = key;
          render();
          root.dispatchEvent(new Event("input", {bubbles: true}));
        })
      )
    );
  Object.defineProperty(root, "value", {get: () => value, set: (v) => ((value = v), render())});
  render();
  return root;
}

// Slider over snapshot dates (index into dates), with a play button that steps through them and the date shown.
// Works as an Observable input whose value is the index. Playback stops on invalidation.
export function timeline(dates, invalidation) {
  const slider = Inputs.range([0, dates.length - 1], {step: 1, value: dates.length - 1});
  const playButton = html`<button class="play" title="Play">▶</button>`;
  const dateLabel = html`<span class="timeline-date"></span>`;
  const node = html`<div class="timeline">${playButton}${slider}${dateLabel}</div>`;
  Object.defineProperty(node, "value", {get: () => +slider.value});
  const showDate = () => (dateLabel.textContent = dates[slider.value]);
  slider.addEventListener("input", showDate);
  showDate();

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
  return node;
}

// Is this metro version in force on a date? (ISO date strings compare correctly.)
export const activeOn = (f, date) =>
  f.properties.valid_from <= date && (!f.properties.valid_to || f.properties.valid_to > date);

// Headline numbers for the selection on a date, with the unit switch on the right.
export function statTiles(data, sel, date, unit, unitInput) {
  const live = sel.features.filter((f) => activeOn(f, date));
  const tile = (label, value) => html`<div><div class="stat-label">${label}</div><div class="stat-value">${value}</div></div>`;
  return html`<div class="stats">
    ${tile("Service area", unit.fmt(d3.sum(live, (f) => f.properties.area_mi2)))}
    ${data.hasPop ? tile("Residents inside", fmtResidents(live.map((f) => f.properties.pop))) : null}
    ${tile("Metros", new Set(live.map((f) => f.properties.metro)).size)}
    ${tile("Expansions so far", sel.events.filter((d) => d.kind === "expansion" && fmtDate(d.date) <= date).length)}
    <div class="stats-unit">${unitInput}</div>
  </div>`;
}

// Sequential blue ramp, light (recent) to dark (old): darker = served longer.
const RAMP = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
export const ageColor = (start, end, ramp = RAMP) =>
  d3.scaleSequential([new Date(start), new Date(end)], d3.piecewise(d3.interpolateRgb, [...ramp].reverse()));

export function ageLegend(color, dates) {
  return Plot.legend({
    color: {type: "utc", domain: [new Date(dates[0]), new Date(dates.at(-1))], interpolate: color.interpolator()},
    label: "First on the map (darker = served longer)",
    width: 300
  });
}

// Planar point-in-polygon, fine at city scale. point = [lon, lat].
function containsPoint(geometry, point) {
  const polys = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polys.some(([outer, ...holes]) => d3.polygonContains(outer, point) && !holes.some((h) => d3.polygonContains(h, point)));
}

// Plain-language answer to "is this spot served, and since when?"
export function lookup(data, point) {
  const {name} = data.operator;
  const hits = data.features.filter((f) => containsPoint(f.geometry, point));
  if (!hits.length) return `Not inside any ${name} service area.`;
  const metro = hits[0].properties.metro;
  const first = d3.min(hits, (f) => f.properties.valid_from);
  return hits.some((f) => !f.properties.valid_to)
    ? `Inside ${name}'s <b>${metro}</b> service area, since the map of <b>${first}</b>.`
    : `Was inside ${name}'s <b>${metro}</b> service area from ${first} to ${d3.max(hits, (f) => f.properties.valid_to)}, but not anymore.`;
}

const empty = {type: "FeatureCollection", features: []};

// Vector base map (OpenFreeMap, no key needed) with GeoJSON sources "areas" and "dots"; see drawAreas.
// Clicking the map, or "my location", answers whether that spot is served.
export async function areaMap(container, dark, data) {
  const map = new maplibregl.Map({
    container,
    style: `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`,
    center: [-98, 37],
    zoom: 3,
    cooperativeGestures: true,
    attributionControl: {compact: true}
  });
  map.addControl(new maplibregl.NavigationControl({showCompass: false}), "top-right");
  const geolocate = new maplibregl.GeolocateControl({fitBoundsOptions: {maxZoom: 12}});
  map.addControl(geolocate, "top-right");
  // Exposed on the map so the page can switch units.
  map.scale = new maplibregl.ScaleControl({maxWidth: 120, unit: "imperial"});
  map.addControl(map.scale, "bottom-left");
  await map.once("load");
  map.resize();
  map.addSource("areas", {type: "geojson", data: empty});
  map.addLayer({id: "areas-fill", type: "fill", source: "areas", paint: {"fill-color": ["get", "color"], "fill-opacity": 0.45}});
  map.addLayer({
    id: "areas-line",
    type: "line",
    source: "areas",
    paint: {"line-color": ["get", "color"], "line-width": ["case", ["get", "active"], 1.5, 0.75]}
  });
  // One dot per metro when zoomed out, where the areas themselves are too small to see.
  map.addSource("dots", {type: "geojson", data: empty});
  map.addLayer({
    id: "dots",
    type: "circle",
    source: "dots",
    maxzoom: 7,
    paint: {"circle-color": data.operator.color, "circle-radius": 6, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5}
  });
  map.on("click", (e) => popup(map, e.lngLat, lookup(data, [e.lngLat.lng, e.lngLat.lat])));
  geolocate.on("geolocate", ({coords: {longitude, latitude}}) =>
    popup(map, [longitude, latitude], lookup(data, [longitude, latitude]))
  );
  return map;
}

function popup(map, lngLat, html) {
  new maplibregl.Popup({closeButton: false, maxWidth: "280px"}).setLngLat(lngLat).setHTML(html).addTo(map);
}

// [[west, south], [east, north]] of a list of GeoJSON features.
export const bounds = (features) => d3.geoBounds({type: "FeatureCollection", features});

// Draw every version up to date, colored by fill(feature), and a dot per area in force.
export function drawAreas(map, features, date, fill) {
  // Oldest last, so it draws on top and the rings show how each area grew.
  const shown = d3.sort(features.filter((f) => f.properties.valid_from <= date), (f) => f.properties.valid_from).reverse();
  map.getSource("areas").setData({
    type: "FeatureCollection",
    features: shown.map((f) => ({...f, properties: {...f.properties, color: fill(f), active: activeOn(f, date)}}))
  });
  map.getSource("dots").setData({
    type: "FeatureCollection",
    features: shown
      .filter((f) => activeOn(f, date))
      .map((f) => ({type: "Feature", geometry: {type: "Point", coordinates: d3.geoCentroid(f)}, properties: {}}))
  });
}

// Area and residents over time: the total, or with metros picked, one row per metro.
export function growthCharts(data, timeseries, {picked, width, unit}) {
  const rows = picked.length
    ? timeseries.map((d) => ({...d, date: new Date(d.date)}))
    : d3.rollups(timeseries, (v) => ({area_mi2: d3.sum(v, (d) => d.area_mi2), pop: d3.sum(v, (d) => d.pop)}), (d) => d.date)
        .map(([date, t]) => ({date: new Date(date), metro: "All metros", ...t}));
  const xDomain = [new Date(data.dates[0]), new Date(data.dates.at(-1))];
  const c = data.operator.color;

  function growth(y, title, format) {
    const opts = {x: "date", y, fy: "metro", curve: "step-after"};
    return Plot.plot({
      title,
      width: Math.min(width, 640),
      height: picked.length > 1 ? 30 + 110 * picked.length : 260,
      marginRight: picked.length ? 100 : 20,
      x: {domain: xDomain, label: null},
      y: {grid: true, label: null, ticks: 4, domain: [0, d3.max(rows, y) || 1], nice: true},
      fy: {label: null, axis: picked.length ? "right" : null},
      marks: [
        Plot.areaY(rows, {...opts, fill: c, fillOpacity: 0.15}),
        Plot.lineY(rows, {...opts, stroke: c, strokeWidth: 2}),
        Plot.ruleY([0]),
        // Mark the latest value, so a metro with a single snapshot still shows up.
        Plot.dot(rows, Plot.selectLast({x: "date", y, fy: "metro", fill: c, r: 3})),
        Plot.tip(rows, Plot.pointerX({x: "date", y, fy: "metro", title: (d) => `${d.metro}\n${fmtDate(d.date)}\n${format(d)}`}))
      ]
    });
  }

  const area = html`<div class="card">${growth((d) => d.area_mi2 * unit.factor, `Service area (${unit.label})`, (d) => unit.fmt(d.area_mi2))}</div>`;
  if (!data.hasPop) return area;
  const pop = html`<div class="card">${growth((d) => (d.pop == null ? null : d.pop / 1e6), "Residents inside (millions)", (d) => `${fmtInt(d.pop)} residents`)}</div>`;
  return html`<div class="grid grid-cols-2">${area}${pop}</div>`;
}

// One row per metro, a dot per event sized by the area added.
export function eventsChart(data, events, {metros, width, unit}) {
  const {color, colorName} = data.operator;
  return Plot.plot({
    title: `Earliest data (gray), launches (${colorName}), expansions (open)`,
    width,
    height: 40 + metros.length * 28,
    marginLeft: 100,
    x: {domain: [new Date(data.dates[0]), new Date(data.dates.at(-1))], grid: true, label: null, insetLeft: 16, insetRight: 16},
    y: {domain: metros, label: null},
    r: {domain: [0, d3.max(data.events, (d) => d.added)], range: [0, 14]},
    marks: [
      Plot.dot(events, {
        x: "date",
        y: "metro",
        r: "added",
        fill: (d) => (d.kind === "earliest_data" ? GRAY : d.kind === "launch" ? color : "none"),
        stroke: (d) => (d.kind === "earliest_data" ? GRAY : color),
        strokeWidth: 2,
        channels: {
          Kind: "kind_label",
          Added: (d) => unit.fmt(d.added),
          ...(data.hasPop ? {"Residents added": (d) => (d.pop_added == null ? "–" : fmtInt(d.pop_added))} : {})
        },
        tip: {format: {x: fmtDate, y: true, r: false, fill: false, stroke: false}}
      })
    ]
  });
}

// Every event, newest first.
export function eventsTable(data, events, unit) {
  const added = `Added (${unit.label})`;
  const after = `Area after (${unit.label})`;
  return Inputs.table(
    d3.sort(events, (d) => d.date).reverse().map((d) => ({
      Date: d.date,
      Metro: d.metro,
      Kind: d.kind_label,
      [added]: d.added * unit.factor,
      [after]: d.after * unit.factor,
      ...(data.hasPop ? {"Residents added": d.pop_added} : {})
    })),
    {
      format: {
        Date: fmtDate,
        [added]: fmtInt,
        [after]: fmtInt,
        "Residents added": (x) => (x == null ? "–" : fmtInt(x))
      }
    }
  );
}
