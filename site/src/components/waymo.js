import * as d3 from "npm:d3";
import maplibregl from "npm:maplibre-gl@5.24.0";

export const slug = (name) => name.toLowerCase().replace(/\s+/g, "-");
export const fmtInt = d3.format(",.0f");
export const fmtMillions = (x) => `${d3.format(".2f")(x / 1e6)}M`;
// Sum of residents; "–" if none are known yet, and "+" if some are missing (a new map before step 6 ran).
export function fmtResidents(values) {
  const known = values.filter((v) => v != null);
  if (!known.length) return "–";
  return fmtMillions(d3.sum(known)) + (known.length < values.length ? "+" : "");
}
export const fmtDate = d3.utcFormat("%Y-%m-%d");
export const BLUE = "#2a78d6";

// Area units. Source data is in square miles.
export const UNITS = {mi: {label: "sq mi", factor: 1}, km: {label: "km²", factor: 2.589988}};

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

// Sequential blue ramp, light (recent) to dark (old): darker = served longer.
const RAMP = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];
export const ageColor = (start, end) =>
  d3.scaleSequential([new Date(start), new Date(end)], d3.piecewise(d3.interpolateRgb, [...RAMP].reverse()));

// Is this metro version in force on a date? (ISO date strings compare correctly.)
export const activeOn = (f, date) =>
  f.properties.valid_from <= date && (!f.properties.valid_to || f.properties.valid_to > date);

// Planar point-in-polygon, fine at city scale. point = [lon, lat].
function containsPoint(geometry, point) {
  const polys = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polys.some(([outer, ...holes]) => d3.polygonContains(outer, point) && !holes.some((h) => d3.polygonContains(h, point)));
}

// Plain-language answer to "is this spot served, and since when?"
export function lookup(features, point) {
  const hits = features.filter((f) => containsPoint(f.geometry, point));
  if (!hits.length) return "Not inside any Waymo service area.";
  const metro = hits[0].properties.metro;
  const first = d3.min(hits, (f) => f.properties.valid_from);
  return hits.some((f) => !f.properties.valid_to)
    ? `Inside Waymo's <b>${metro}</b> service area, since the map of <b>${first}</b>.`
    : `Was inside Waymo's <b>${metro}</b> service area from ${first} to ${d3.max(hits, (f) => f.properties.valid_to)}, but not anymore.`;
}

const empty = {type: "FeatureCollection", features: []};

// Vector base map (OpenFreeMap, no key needed) with one GeoJSON source "areas".
// Features need a `color` property. Later features draw on top.
export async function areaMap(container, dark) {
  const map = new maplibregl.Map({
    container,
    style: `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`,
    center: [-98, 37],
    zoom: 3,
    cooperativeGestures: true,
    attributionControl: {compact: true}
  });
  map.addControl(new maplibregl.NavigationControl({showCompass: false}), "top-right");
  // Exposed on the map so the page can switch units and react to the located position.
  map.geolocate = new maplibregl.GeolocateControl({fitBoundsOptions: {maxZoom: 12}});
  map.addControl(map.geolocate, "top-right");
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
    paint: {"circle-color": BLUE, "circle-radius": 6, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5}
  });
  return map;
}

export function popup(map, lngLat, html) {
  new maplibregl.Popup({closeButton: false, maxWidth: "280px"}).setLngLat(lngLat).setHTML(html).addTo(map);
}

// [[west, south], [east, north]] of a list of GeoJSON features.
export const bounds = (features) => d3.geoBounds({type: "FeatureCollection", features});
