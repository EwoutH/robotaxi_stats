"""Trace Tesla Robotaxi service areas from published map images (Tesla's posts, app screenshots).

For changes that neither community dataset has. Each row of data/traced_maps.csv names an image, how to
georeference it and which pixels to read as the service area. The maps are north-up Web Mercator renders, so
pixel -> mercator is X = x0 + s * col, Y = y0 - s * row; the fit finds (s, x0, y0) in one of two ways:

- fit = roads: the map's light road lines are matched against OpenStreetMap roads (motorway to secondary),
  first over a wide range of scales and shifts around the row's start guess, then finely.
- fit = outline: the map draws a boundary we already have (the previous version, "Old geofence"). Its drawn
  line (white, or white and green) is matched to that polygon's edge; parts that changed are capped so they
  don't pull the fit.

The area is then read from the image (Tesla's blue fill, an app screenshot's grey fill, or the green fill of a
community screenshot), vectorised, simplified to under a pixel and joined with `union_with` if the map shows
the new area on top of the old one. Results:
  data/traced_boundaries.geojson  one feature per row, EPSG:4326, read by 01_boundaries.py
  data/traced_fits.csv            fit, its checks and the traced area per row
QA images go to areas/raw/tesla_maps/qa/ (not in git). Images are downloaded to areas/raw/tesla_maps/ and
must match the row's SHA-256.

Run by hand after adding a row; 01_boundaries.py, 03_population.py and the site then pick it up.
Needs opencv-python-headless and scipy besides the usual packages, and osmium for the first OSM extract.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import requests
import shapely
from pyproj import Geod, Transformer
from scipy.optimize import minimize
from shapely.geometry import Polygon, mapping, shape

ROOT = Path(__file__).parent
AREAS = ROOT.parent
sys.path.insert(0, str(AREAS / "waymo"))
import georef  # noqa: E402  (OSM road caches and Geofabrik extracts, shared with Waymo)

RAW = AREAS / "raw" / "tesla_maps"
QA = RAW / "qa"
TO_M = Transformer.from_crs(4326, 3857, always_xy=True)
TO_W = Transformer.from_crs(3857, 4326, always_xy=True)
GEOD = Geod(ellps="WGS84")
WEIGHT = {"motorway": 3, "trunk": 3, "motorway_link": 1, "primary": 2, "secondary": 1}


def mi2(g):
    return abs(GEOD.geometry_area_perimeter(g)[0]) / 2.589988e6


def to_merc(g):
    return shapely.transform(g, lambda xy: np.c_[TO_M.transform(xy[:, 0], xy[:, 1])])


def to_wgs(g):
    return shapely.transform(g, lambda xy: np.c_[TO_W.transform(xy[:, 0], xy[:, 1])])


def boxes(spec):
    """'c0 r0 c1 r1; ...' -> list of pixel boxes."""
    return [tuple(int(v) for v in b.split()) for b in spec.split(";") if b.strip()]


def blank(arr, bxs, value=0):
    for c0, r0, c1, r1 in bxs:
        arr[r0:r1, c0:c1] = value
    return arr


# ------------------------------------------------------------------ image

def image(row):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{row['image_sha256'][:16]}{Path(row['image_url'].split('?')[0]).suffix or '.jpg'}"
    if not path.exists():
        r = requests.get(row["image_url"], timeout=60, headers={"User-Agent": "robotaxi_stats"})
        r.raise_for_status()
        path.write_bytes(r.content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["image_sha256"]:
        raise RuntimeError(f"{row['city']} {row['valid_from']}: image changed, check {row['image_url']}")
    return cv2.imread(str(path))


def channels(a):
    return [a[..., i].astype(int) for i in (2, 1, 0)]  # r, g, b


def white_line(a):
    r, g, b = channels(a)
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    return ((mx > 165) & (mx - mn < 45)).astype(np.uint8)


def green_line(a):
    r, g, b = channels(a)
    return ((g > 150) & (g - r > 60) & (g - b > 60)).astype(np.uint8)


def region_mask(a, kind):
    r, g, b = channels(a)
    if kind == "blue":      # Tesla's announcement maps: blue tint over a dark map
        return ((b - r > 18) & (b > 25)).astype(np.uint8)
    if kind == "grey":      # Tesla app screenshot: light grey fill with a white edge
        gray = cv2.medianBlur(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), 7)
        return ((gray > 38) | (white_line(a) > 0)).astype(np.uint8)
    if kind == "green":     # community screenshot: added area filled green
        return ((g - r > 40) & (g - b > 40)).astype(np.uint8)
    raise ValueError(kind)


def road_strength(a):
    """Light thin lines on a dark map: white top-hat of the brightest channel."""
    g = a.max(axis=2).astype(np.float32)
    k = max(7, int(round(a.shape[1] / 150)) | 1)
    th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return np.clip(th / 40.0, 0, 1)


def fill_holes(m):
    ff = m.copy()
    cv2.floodFill(ff, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 1)
    return m | (1 - ff)


# ------------------------------------------------------------------ OSM roads

def osm_roads(row):
    lat, lon = float(row["start_lat"]), float(row["start_lon"])
    name, radius = f"tesla_{row['city'].lower().replace(' ', '_')}", 35
    path = georef.osm_cache_path(name, radius)
    if not path.exists():
        georef.roads_from_pbf(georef.download_pbf(row["geofabrik"]), {str(path): georef.osm_bbox(lat, lon, radius)})
    out = []
    for e in json.loads(path.read_text(encoding="utf-8"))["elements"]:
        g = e["geometry"]
        x, y = TO_M.transform([p["lon"] for p in g], [p["lat"] for p in g])
        out.append((np.c_[x, y], e["tags"].get("highway", "")))
    return out


def raster(roads, gx0, gy1, res, shp):
    can = np.zeros(shp, np.float32)
    for xy, cls in roads:
        pts = np.round(np.c_[(xy[:, 0] - gx0) / res, (gy1 - xy[:, 1]) / res] * 4).astype(np.int32)
        cv2.polylines(can, [pts], False, float(WEIGHT.get(cls, 1)), 1, cv2.LINE_AA, shift=2)
    return can


def search(strength, roads, p, res, rel, steps, pad_m):
    """Scale grid x FFT translation search around p = (s, x0, y0)."""
    s0, x0, y0 = p
    H, W = strength.shape
    cx, cy = x0 + s0 * W / 2, y0 - s0 * H / 2
    half = s0 * max(W, H) / 2 * np.exp(rel) + pad_m
    N = int(2 * half / res)
    gx0, gy1 = cx - half, cy + half
    can = raster(roads, gx0, gy1, res, (N, N))
    F = np.exp(-(cv2.distanceTransform((can <= 0).astype(np.uint8), cv2.DIST_L2, 5) / 1.5) ** 2)
    F = (F - F.mean()).astype(np.float32)
    best = None
    for s in s0 * np.exp(np.linspace(-rel, rel, steps)):
        w, h = int(round(W * s / res)), int(round(H * s / res))
        if w >= N or h >= N:
            continue
        t = cv2.resize(strength, (w, h), interpolation=cv2.INTER_AREA)
        t = (t / (np.linalg.norm(t) + 1e-9)).astype(np.float32)
        _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(F, t, cv2.TM_CCORR))
        if best is None or mx > best[0]:
            best = (mx, (s, gx0 + loc[0] * res, gy1 - loc[1] * res))
    return best[1]


def road_checks(strength, roads, p, ignore):
    """road_quality: share of the image's road pixels within 2.5 px of an OSM road;
    motorway_share: share of OSM motorway/trunk points within 2.5 px of a drawn road."""
    s, x0, y0 = p
    H, W = strength.shape
    d = cv2.distanceTransform((raster(roads, x0, y0, s, (H, W)) <= 0).astype(np.uint8), cv2.DIST_L2, 5)
    quality = float(np.mean(d[strength > 0.5] < 2.5))
    near = cv2.distanceTransform((strength <= 0.1).astype(np.uint8), cv2.DIST_L2, 5)
    pts = [xy for xy, cls in roads if cls in ("motorway", "trunk")]
    P = np.vstack([np.c_[np.interp(np.arange(0, len(xy) - 1, 0.1), np.arange(len(xy)), xy[:, 0]),
                         np.interp(np.arange(0, len(xy) - 1, 0.1), np.arange(len(xy)), xy[:, 1])]
                   for xy in pts if len(xy) > 1])
    c, r = (P[:, 0] - x0) / s, (y0 - P[:, 1]) / s
    ok = (c >= 0) & (c < W - 1) & (r >= 0) & (r < H - 1)
    for c0, r0, c1, r1 in ignore:
        ok &= ~((c >= c0) & (c < c1) & (r >= r0) & (r < r1))
    c, r = c[ok].astype(int), r[ok].astype(int)
    return quality, float(np.mean(near[r, c] < 2.5))


def fit_roads(a, roads, p0, ignore):
    st = blank(road_strength(a), ignore)
    s0 = p0[0]
    p = search(st, roads, p0, res=s0 * 4, rel=0.10, steps=41, pad_m=6000)
    p = search(st, roads, p, res=s0 * 1.5, rel=0.015, steps=31, pad_m=s0 * 40)
    q, mw = road_checks(st, roads, p, ignore)
    return p, dict(road_quality=round(q, 3), motorway_share=round(mw, 3))


# ------------------------------------------------------------------ outline fit

def edge_points(geom, step_m=50):
    pts = []
    for ring in [g.exterior for g in getattr(geom, "geoms", [geom])]:
        xy = np.array(ring.coords)
        for i in range(len(xy) - 1):
            n = max(1, int(np.hypot(*(xy[i + 1] - xy[i])) / step_m))
            pts.append(xy[i] + (np.arange(n)[:, None] / n) * (xy[i + 1] - xy[i]))
    return np.vstack(pts)


def fit_outline(a, line_kind, ref, p0, ignore, cap=6.0):
    mask = white_line(a) if line_kind == "white" else white_line(a) | green_line(a)
    mask = blank(mask, ignore)
    dt = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 5)
    H, W = mask.shape
    P = edge_points(to_merc(ref))
    X, Y = P[:, 0], P[:, 1]

    def cost(p):
        c, r = (X - p[1]) / p[0], (p[2] - Y) / p[0]
        ok = (c >= 0) & (c < W - 1) & (r >= 0) & (r < H - 1)
        d = np.full(len(c), cap)
        d[ok] = np.minimum(dt[r[ok].astype(int), c[ok].astype(int)], cap)
        return float(np.mean(d ** 2))

    s0, x0, y0 = p0
    cx, cy = x0 + s0 * W / 2, y0 - s0 * H / 2
    best = None
    for k in np.exp(np.linspace(-0.12, 0.12, 25)):
        s = s0 * k
        for dx in range(-30, 31, 3):
            for dy in range(-30, 31, 3):
                p = (s, cx - s * W / 2 + s0 * dx, cy + s * H / 2 + s0 * dy)
                v = cost(p)
                if best is None or v < best[0]:
                    best = (v, p)
    p = best[1]
    simplex = [p, (p[0] * 1.01, p[1], p[2]), (p[0], p[1] + 2 * p[0], p[2]), (p[0], p[1], p[2] + 2 * p[0])]
    p = minimize(cost, p, method="Nelder-Mead",
                 options=dict(xatol=1e-3, fatol=1e-6, maxiter=4000, initial_simplex=simplex)).x
    c, r = (X - p[1]) / p[0], (p[2] - Y) / p[0]
    ok = (c >= 0) & (c < W - 1) & (r >= 0) & (r < H - 1)
    d = dt[r[ok].astype(int), c[ok].astype(int)]
    return tuple(p), dict(edge_median_px=round(float(np.median(d)), 2),
                          edge_share_2px=round(float(np.mean(d < 2)), 3))


# ------------------------------------------------------------------ area

def rasterize(geom, p, shp):
    s, x0, y0 = p
    m = np.zeros(shp, np.uint8)
    for g in getattr(to_merc(geom), "geoms", [to_merc(geom)]):
        xy = np.array(g.exterior.coords)
        cv2.fillPoly(m, [np.round(np.c_[(xy[:, 0] - x0) / s, (y0 - xy[:, 1]) / s] * 4).astype(np.int32)], 1, shift=2)
    return m


def complete_under(poly_px, box):
    """The area runs under a label box (e.g. the app's title): replace the vertices on the box's edge by the
    point where the two edges entering the box meet."""
    c0, r0, c1, r1 = box
    under = [c0 - 2 <= c <= c1 + 2 and r <= r1 + 3 for c, r in poly_px]
    if not any(under) or all(under):
        return poly_px
    k = under.index(False)  # rotate so the run of vertices under the box doesn't wrap around
    pts = [tuple(v) for v in np.roll(poly_px, -k, axis=0)]
    on = [i for i, u in enumerate(np.roll(under, -k)) if u]
    i0, i1 = on[0], on[-1]
    a0, a1 = np.array(pts[i0 - 1]), np.array(pts[i0])
    b0, b1 = np.array(pts[(i1 + 1) % len(pts)]), np.array(pts[i1])
    d1, d2 = a1 - a0, b1 - b0
    cross = lambda u, v: u[0] * v[1] - u[1] * v[0]
    tip = a0 + cross(b0 - a0, d2) / cross(d1, d2) * d1
    return np.array(pts[:i0] + [tuple(tip)] + pts[i1 + 1:])


def trace_area(a, row, p, ignore, base):
    m = blank(region_mask(a, row["region"]), ignore)
    if base is not None:
        m |= rasterize(base, p, m.shape[:2])
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = fill_holes(cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    m = (lab == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float) + 0.5
    c = cv2.approxPolyDP(c.astype(np.float32), 0.7, True)[:, 0, :].astype(float)
    for box in boxes(row["complete_under"]):
        c = complete_under(c, box)
    s, x0, y0 = p
    # the fill reaches the outer edge of the drawn line; move in by half a line
    poly = Polygon(np.c_[x0 + s * c[:, 0], y0 - s * c[:, 1]]).buffer(-float(row["edge_px"]) * s, join_style="mitre")
    g = shapely.make_valid(to_wgs(poly))
    return shapely.union(g, base) if base is not None else g


# ------------------------------------------------------------------ main

def references():
    out = {}
    for f in json.load(open(ROOT / "tesla_service_areas.geojson", encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr["source"] != "tesla_map":
            out[(pr["city"], pr["valid_from"])] = shape(f["geometry"])
    return out


def main():
    rows = list(csv.DictReader(open(ROOT / "data" / "traced_maps.csv", encoding="utf-8")))
    refs = references()
    QA.mkdir(parents=True, exist_ok=True)
    feats, fits = [], []
    for row in rows:
        key = (row["city"], row["valid_from"])
        a = image(row)
        H, W = a.shape[:2]
        ignore = boxes(row["ignore"])
        s0 = float(row["start_m_per_px"]) / np.cos(np.radians(float(row["start_lat"])))  # mercator m/px
        cx, cy = TO_M.transform(float(row["start_lon"]), float(row["start_lat"]))
        p0 = (s0, cx - s0 * W / 2, cy + s0 * H / 2)
        if row["fit"] == "roads":
            p, checks = fit_roads(a, osm_roads(row), p0, ignore)
        else:
            p, checks = fit_outline(a, row["outline"], refs[(row["city"], row["outline_ref"])], p0, ignore)
        base = refs[(row["city"], row["union_with"])] if row["union_with"] else None
        g = trace_area(a, row, p, ignore, base)
        refs[key] = g
        area = mi2(g)
        lon, lat = TO_W.transform(p[1] + p[0] * W / 2, p[2] - p[0] * H / 2)
        fit = dict(city=row["city"], valid_from=row["valid_from"], fit=row["fit"],
                   m_per_px=round(p[0] * np.cos(np.radians(lat)), 2), centre_lon=round(lon, 5),
                   centre_lat=round(lat, 5), road_quality=None, motorway_share=None, edge_median_px=None,
                   edge_share_2px=None, area_mi2=round(area, 2), geom_type=g.geom_type)
        fit.update(checks)
        fits.append(fit)
        print(fit, flush=True)
        props = {k: row[k] for k in ("city", "valid_from", "image_url", "image_sha256", "image_credit", "post_url",
                                     "article_url", "note")}
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
        vis = (a * 0.7).astype(np.uint8)
        if row["fit"] == "roads":
            vis[raster(osm_roads(row), p[1], p[2], p[0], (H, W)) > 0] = (0, 0, 255)
        for part in getattr(to_merc(g), "geoms", [to_merc(g)]):
            xy = np.array(part.exterior.coords)
            cv2.polylines(vis, [np.c_[(xy[:, 0] - p[1]) / p[0], (p[2] - xy[:, 1]) / p[0]].astype(np.int32)],
                          True, (0, 255, 255), max(1, W // 800))
        cv2.imwrite(str(QA / f"{row['city'].replace(' ', '_')}_{row['valid_from']}.jpg"), vis)
    with open(ROOT / "data" / "traced_boundaries.geojson", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    with open(ROOT / "data" / "traced_fits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(fits[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(fits)


if __name__ == "__main__":
    main()
