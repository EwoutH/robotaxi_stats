import * as d3 from "npm:d3";
import * as L from "npm:leaflet";

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

export function basemap(div, dark) {
  const map = L.map(div, {scrollWheelZoom: false});
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19
  }).addTo(map);
  // Muted tiles so the service areas stand out; inverted in dark mode.
  map.getPane("tilePane").style.filter = dark
    ? "invert(1) hue-rotate(180deg) grayscale(0.6) brightness(0.8)"
    : "grayscale(0.6) opacity(0.8)";
  return map;
}
