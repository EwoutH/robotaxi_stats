"""Georeferencing helpers: align a Waymo service-area map image with
OpenStreetMap roads in Web Mercator (EPSG:3857).

Model: the map images are north-up Web Mercator renders, so pixel -> mercator
is   X = x0 + s * col,   Y = y0 - s * row   (s = metres per pixel, uniform).
We find (s, x0, y0) by matching road lines in the image against OSM roads.
"""
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from pyproj import Transformer

ROOT = Path(__file__).parent
OSM_DIR = ROOT / "raw" / "osm"
OSM_DIR.mkdir(parents=True, exist_ok=True)
TO_MERC = Transformer.from_crs(4326, 3857, always_xy=True)
TO_WGS = Transformer.from_crs(3857, 4326, always_xy=True)
cv2.setNumThreads(3)  # several worker processes run in parallel

# ---------------------------------------------------------------- image side

def load_rgba(path):
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)


def blue_mask(rgba, close_px=None, min_blue_red=90):
    """Service-area mask: the saturated blue fill, with roads/labels drawn on
    top of it closed over."""
    a = rgba.astype(int)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    # blue-ish: strong blue, blue clearly above red; covers fill + lighter road lines
    m = (b > 200) & (b - r > min_blue_red) & (b - g > 40) & (al > 128)
    m = m.astype(np.uint8)
    h = max(rgba.shape[:2])
    k = close_px or max(3, int(round(h / 180)))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    # drop specks
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] > (h * h) * 2e-5
    m = keep[lab].astype(np.uint8)
    # fill holes caused by black label text
    inv = (1 - m).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, 4)
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        touches = x == 0 or y == 0 or x + w >= m.shape[1] or y + hh >= m.shape[0]
        if not touches and area < (h * h) * 1.5e-4:
            m[lab == i] = 1
    return m


def valid_mask(rgba):
    """Pixels that belong to the map (inside the circle / not transparent)."""
    v = (rgba[..., 3] > 200).astype(np.uint8)
    return cv2.erode(v, np.ones((9, 9), np.uint8))


def road_strength(rgba):
    """0..1 'is this a road line' score from the styled basemap.
    Outside blue: roads are darker than the light grey land.
    Inside blue: roads are lighter (whiter) than the blue fill."""
    a = rgba[..., :3].astype(np.float32)
    gray = a.mean(axis=2)
    inblue = blue_mask(rgba, close_px=1).astype(bool) | (
        (a[..., 2] > 200) & (a[..., 2] - a[..., 0] > 60))
    bg = cv2.medianBlur(gray.astype(np.uint8), 15).astype(np.float32)
    dark = np.clip((bg - gray) / 40.0, 0, 1)            # outside
    red = a[..., 0]
    redbg = cv2.medianBlur(red.astype(np.uint8), 15).astype(np.float32)
    light = np.clip((red - redbg) / 50.0, 0, 1)        # inside blue
    s = np.where(inblue, light, dark)
    # black label text is very dark: suppress
    s[gray < 90] = 0
    s *= valid_mask(rgba)
    return s


# ------------------------------------------------------------------ OSM side

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]


def _overpass_bbox(s, w, n, e, classes, tries=3, depth=0):
    """Fetch one bbox (cached as its own tile). If it keeps failing, split it
    into 4 quarters and fetch those instead (up to 3 levels deep)."""
    tdir = OSM_DIR / "tiles"
    tdir.mkdir(exist_ok=True)
    key = f"{s:.4f}_{w:.4f}_{n:.4f}_{e:.4f}_{abs(hash(classes)) % 10**6}"
    f = tdir / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["elements"]
    q = (f'[out:json][timeout:120];way["highway"~"^({classes})$"]({s},{w},{n},{e});'
         "out tags geom;")
    for attempt in range(tries):
        url = OVERPASS[(attempt + depth) % len(OVERPASS)]
        try:
            r = requests.post(url, data={"data": q}, timeout=200,
                              headers={"User-Agent": "waymo-area-research"})
            if r.ok and r.text.lstrip().startswith("{") and '"elements"' in r.text                     and "runtime error" not in r.text[-2000:]:
                f.write_text(r.text, encoding="utf-8")
                return json.loads(r.text)["elements"]
            print(f"  overpass d{depth} {url.split('/')[2]} -> {r.status_code}", flush=True)
        except requests.RequestException as ex:
            print(f"  overpass d{depth} {url.split('/')[2]} -> {type(ex).__name__}", flush=True)
        time.sleep(10 * (attempt + 1))
    if depth >= 3:
        raise RuntimeError(f"Overpass failed for bbox {s},{w},{n},{e}")
    ms, mw = (s + n) / 2, (w + e) / 2
    out = []
    for bb in ((s, w, ms, mw), (s, mw, ms, e), (ms, w, n, mw), (ms, mw, n, e)):
        out += _overpass_bbox(*bb, classes, tries=tries, depth=depth + 1)
    return out


PBF_DIR = OSM_DIR / "pbf"
GEOFABRIK = "https://download.geofabrik.de/north-america/us/"


def download_pbf(name):
    """Fetch a Geofabrik extract (e.g. "nevada", "socal") into raw/osm/pbf/."""
    path = PBF_DIR / f"{name}-latest.osm.pbf"
    if path.exists():
        return path
    sub = "california/" if name in ("socal", "norcal") else ""
    url = f"{GEOFABRIK}{sub}{name}-latest.osm.pbf"
    print(f"  downloading {url}", flush=True)
    PBF_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120,
                      headers={"User-Agent": "robotaxi_stats"}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)
    return path


def roads_from_pbf(pbf, targets, classes="motorway|trunk|primary|secondary|motorway_link"):
    """Read a Geofabrik .osm.pbf once and write the road cache JSON for every
    target. targets: {cache_path: (south, west, north, east)}. Same format as
    the Overpass output, so osm_roads() can read either."""
    import osmium  # pip install osmium
    keep = set(classes.split("|"))
    found = {p: [] for p in targets}
    fp = (osmium.FileProcessor(str(pbf))
          .with_locations()
          .with_filter(osmium.filter.KeyFilter("highway")))
    for obj in fp:
        if not obj.is_way() or obj.tags.get("highway") not in keep:
            continue
        try:
            g = [(n.lon, n.lat) for n in obj.nodes]
        except osmium.InvalidLocationError:
            g = [(n.lon, n.lat) for n in obj.nodes if n.location.valid()]
        if len(g) < 2:
            continue
        lons = [c[0] for c in g]; lats = [c[1] for c in g]
        for p, (s, w, n, e) in targets.items():
            if max(lats) >= s and min(lats) <= n and max(lons) >= w and min(lons) <= e:
                found[p].append({"type": "way", "id": obj.id,
                                 "tags": {"highway": obj.tags.get("highway")},
                                 "geometry": [{"lat": la, "lon": lo} for lo, la in g]})
    for p, els in found.items():
        Path(p).write_text(json.dumps({"elements": els}), encoding="utf-8")
        print(f"  osm {Path(p).name}: {len(els)} ways from {Path(pbf).name}", flush=True)


def osm_bbox(lat, lon, radius_km):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def osm_cache_path(name, radius_km):
    return OSM_DIR / f"{name}_{radius_km}km.json"


def osm_roads(name, lat, lon, radius_km,
              classes="motorway|trunk|primary|secondary|motorway_link", grid=3):
    """Download (cached) OSM road geometries around a point, return list of
    (Nx2 mercator array, class). The area is fetched as grid x grid tiles to
    keep each Overpass query small."""
    p = OSM_DIR / f"{name}_{radius_km}km.json"
    if not p.exists():
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
        S, W, N, E = lat - dlat, lon - dlon, lat + dlat, lon + dlon
        els = {}
        for i in range(grid):
            for j in range(grid):
                s_ = S + (N - S) * i / grid; n_ = S + (N - S) * (i + 1) / grid
                w_ = W + (E - W) * j / grid; e_ = W + (E - W) * (j + 1) / grid
                for el in _overpass_bbox(s_, w_, n_, e_, classes):
                    els[el["id"]] = el  # ways crossing tile borders appear twice
        p.write_text(json.dumps({"elements": list(els.values())}), encoding="utf-8")
        print(f"  osm {name}: {len(els)} ways", flush=True)
    d = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for e in d["elements"]:
        g = e.get("geometry")
        if not g:
            continue
        lo = np.array([pt["lon"] for pt in g]); la = np.array([pt["lat"] for pt in g])
        x, y = TO_MERC.transform(lo, la)
        out.append((np.c_[x, y], e["tags"].get("highway", "")))
    return out


WEIGHT = {"motorway": 3, "trunk": 3, "motorway_link": 1, "primary": 2, "secondary": 1}


def rasterize_roads(roads, x0, y1, res, shape):
    """Draw roads to a canvas whose top-left is (x0, y1) in mercator, res m/px."""
    can = np.zeros(shape, np.float32)
    for xy, cls in roads:
        px = np.c_[(xy[:, 0] - x0) / res, (y1 - xy[:, 1]) / res]
        pts = np.round(px * 4).astype(np.int32)  # 2 bits subpixel
        w = WEIGHT.get(cls, 1)
        cv2.polylines(can, [pts], False, float(w), thickness=1, lineType=cv2.LINE_AA, shift=2)
    return can


# --------------------------------------------------------------- matching

def _field(can, sigma_px):
    """Smooth 'closeness to a road' field from a road raster."""
    binm = (can > 0).astype(np.uint8)
    d = cv2.distanceTransform(1 - binm, cv2.DIST_L2, 5)
    return np.exp(-(d / sigma_px) ** 2)


def match(rgba, roads, center_xy, search_m, scales, res, sigma_px=1.5, top=3):
    """Brute-force scale search with FFT translation search.

    center_xy: approximate mercator centre of the map; search_m: half width of
    the reference canvas. Returns list of best (score, s, x0, y0)."""
    rs = road_strength(rgba)
    H, W = rs.shape
    N = int(2 * search_m / res)
    cx, cy = center_xy
    gx0, gy1 = cx - search_m, cy + search_m
    can = rasterize_roads(roads, gx0, gy1, res, (N, N))
    F = _field(can, sigma_px)
    F = F - F.mean()
    results = []
    for s in scales:
        f = s / res  # image px -> canvas px
        w, h = max(8, int(round(W * f))), max(8, int(round(H * f)))
        if w >= N or h >= N:
            continue
        t = cv2.resize(rs, (w, h), interpolation=cv2.INTER_AREA)
        t = t / (np.linalg.norm(t) + 1e-9)
        cc = cv2.matchTemplate(F.astype(np.float32), t.astype(np.float32), cv2.TM_CCORR)
        _, mx, _, loc = cv2.minMaxLoc(cc)
        x0 = gx0 + loc[0] * res
        y0 = gy1 - loc[1] * res
        results.append((mx, s, x0, y0))
    results.sort(reverse=True)
    return results[:top], results


def refine(rgba, roads, s, x0, y0, res, rel=0.06, steps=25, pad_px=60, sigma_px=1.2):
    """Finer search around an initial solution."""
    H, W = rgba.shape[:2]
    cx, cy = x0 + s * W / 2, y0 - s * H / 2
    half = s * max(W, H) / 2 + pad_px * res
    scales = s * np.exp(np.linspace(-rel, rel, steps))
    best, _ = match(rgba, roads, (cx, cy), half, scales, res, sigma_px=sigma_px, top=1)
    return best[0]


def pixel_to_merc(params, cols, rows):
    s, x0, y0 = params
    return x0 + s * np.asarray(cols), y0 - s * np.asarray(rows)
