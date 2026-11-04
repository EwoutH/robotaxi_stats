import * as d3 from "npm:d3";
import maplibregl from "npm:maplibre-gl@5.24.0";

export const slug = (name) => name.toLowerCase().replace(/\s+/g, "-");
export const fmtInt = d3.format(",.0f");
export const fmtMillions = (x) => `${d3.format(".2f")(x / 1e6)}M`;
export const fmtDate = d3.utcFormat("%Y-%m-%d");
export const BLUE = "#2a78d6";

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
