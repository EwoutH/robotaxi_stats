"""Step 2: georeference every distinct map image and turn the blue service
area into polygons.

Input : data/snapshot_images.csv, raw/images/*
Output: data/georef_params.csv     (scale/offset + match score per image)
        data/image_polygons.gpkg   (one polygon per image, EPSG:4326)
        qa/<city>_<image>.jpg      (OSM roads drawn over the map, for checking)

Re-running only processes images not yet in georef_params.csv. To redo one,
delete its row. Manual fixes can go in data/manual_georef.csv
(columns: image_file, s, x0, y0), which take precedence.
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).parent))
import georef as G  # noqa: E402

ROOT = Path(__file__).parent
DATA, IMG, QA = ROOT / "data", ROOT / "raw" / "images", ROOT / "qa"
QA.mkdir(exist_ok=True)

# Approximate centre and search radius per metro (lat, lon, radius_km)
METROS = {
    "Phoenix": (33.45, -111.90, 75),
    "San Francisco": (37.60, -122.25, 85),
    "Los Angeles": (34.03, -118.35, 70),
    "Austin": (30.30, -97.74, 55),
    "Atlanta": (33.76, -84.39, 55),
    "Miami": (25.80, -80.25, 60),
    "Dallas": (32.80, -96.80, 60),
    "Houston": (29.76, -95.40, 60),
    "Denver": (39.74, -104.95, 55),
    "Las Vegas": (36.15, -115.17, 50),
    "Nashville": (36.16, -86.78, 55),
    "Orlando": (28.50, -81.38, 55),
    "San Antonio": (29.45, -98.50, 55),
    "San Diego": (32.80, -117.15, 55),
    "Tampa": (27.95, -82.46, 55),
    "Washington DC": (38.90, -77.03, 50),
    "Detroit": (42.35, -83.10, 55),
    "New Orleans": (29.95, -90.07, 45),
}
# Geofabrik extract (raw/osm/pbf/<name>-latest.osm.pbf) per metro, used when
# Overpass is unavailable. Download from https://download.geofabrik.de/north-america/us.html
PBF = {"Miami": "florida", "Orlando": "florida", "Tampa": "florida",
       "Nashville": "tennessee", "San Antonio": "texas", "Austin": "texas",
       "Dallas": "texas", "Houston": "texas", "San Diego": "socal",
       "Los Angeles": "socal", "Atlanta": "georgia", "Phoenix": "arizona",
       "Denver": "colorado", "Las Vegas": "nevada", "San Francisco": "norcal"}
ALIASES = {"San Francisco Bay Area": "San Francisco", "Silicon Valley": "San Francisco",
           "Peninsula": "San Francisco", "Washington, D.C.": "Washington DC",
           "Metro Phoenix": "Phoenix", "Miami-Dade": "Miami"}


def metro_of(city):
    c = ALIASES.get(city, city)
    for k in METROS:
        if k.lower() in c.lower():
            return k
    return None


def georeference(rgba, metro):
    lat, lon, rad = METROS[metro]
    roads = G.osm_roads(metro.replace(" ", "_").lower(), lat, lon, rad)
    c = G.TO_MERC.transform(lon, lat)
    H, W = rgba.shape[:2]
    # search over map extents from 6 km to 2*radius*1.15 (mercator metres)
    ext = np.exp(np.linspace(np.log(8000), np.log(2 * rad * 1000 * 1.15), 70))
    half = rad * 1000 * 1.25
    # search resolution adapts to the map extent so the template stays ~250-400 px
    top = []
    for lo, hi, res in [(0, 25000, 50.0), (25000, 60000, 90.0), (60000, 1e9, 150.0)]:
        sel = ext[(ext >= lo) & (ext < hi)]
        if len(sel):
            t, _ = G.match(rgba, roads, c, half, sel / W, res, sigma_px=1.5, top=3)
            # normalise score per band using a quick fixed-resolution quality check
            top += [(quality(rgba, roads, r[1:], sample=500), *r[1:]) for r in t]
    top.sort(reverse=True)
    best = None
    for cand in top[:4]:  # refine the 4 best coarse candidates, keep the best
        r1 = G.refine(rgba, roads, cand[1], cand[2], cand[3], max(cand[1] * W / 600, 15),
                      rel=0.12, steps=25, sigma_px=1.5)
        r2 = G.refine(rgba, roads, r1[1], r1[2], r1[3], max(r1[1] * W / 1500, 6),
                      rel=0.03, steps=17, sigma_px=1.5)
        # comparable score: correlation at a fixed resolution relative to the image
        q = quality(rgba, roads, r2[1:])
        if best is None or q > best[0]:
            best = (q, *r2[1:])
    return best, roads


def quality(rgba, roads, params, sample=900):
    """Fraction of image road pixels within ~2 px of an OSM road, at a fixed
    working resolution. 1 = perfect; random alignment gives ~0.2-0.3."""
    s, x0, y0 = params
    H, W = rgba.shape[:2]
    f = sample / max(H, W)
    rs = cv2.resize(G.road_strength(rgba), (int(W * f), int(H * f)), interpolation=cv2.INTER_AREA)
    can = G.rasterize_roads(roads, x0, y0, s / f, rs.shape)
    d = cv2.distanceTransform((can == 0).astype(np.uint8), cv2.DIST_L2, 5)
    m = rs > 0.35
    return float((d[m] <= 2.0).mean()) if m.any() else 0.0


def mask_to_polygon(mask):
    """Binary mask -> shapely (Multi)Polygon in pixel coordinates."""
    cnts, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return None
    hier = hier[0]
    polys = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:  # hole; handled by its parent
            continue
        c = cv2.approxPolyDP(c, 0.8, True)
        if len(c) < 3:
            continue
        holes = []
        j = hier[i][2]
        while j != -1:
            h = cv2.approxPolyDP(cnts[j], 0.8, True)
            # small holes are map markers/labels (white dots, shields), not exclusions
            if len(h) >= 3 and cv2.contourArea(h) > 4e-4 * mask.shape[0] * mask.shape[1]:
                holes.append(h[:, 0, :].astype(float) + 0.5)
            j = hier[j][0]
        p = Polygon(c[:, 0, :].astype(float) + 0.5, holes).buffer(0)
        if not p.is_empty:
            polys.append(p)
    if not polys:
        return None
    return MultiPolygon([g for p in polys for g in getattr(p, "geoms", [p])])


def save_qa(rgba, roads, params, mask, path):
    s, x0, y0 = params
    H, W = rgba.shape[:2]
    f = min(1.0, 1100 / max(H, W))
    img = cv2.resize(rgba[..., :3], (int(W * f), int(H * f)), interpolation=cv2.INTER_AREA)
    can = G.rasterize_roads([r for r in roads if r[1] in ("motorway", "trunk", "primary")],
                            x0, y0, s / f, img.shape[:2])
    out = img.copy()
    out[can > 0] = (255, 0, 0)
    m = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, cnts, -1, (255, 200, 0), 2)
    both = np.concatenate([img, out], axis=1)
    cv2.imwrite(str(path), cv2.cvtColor(both, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])


WORKERS = max(1, min(6, (os.cpu_count() or 2) - 2))


def service_mask(rgba, image_file):
    """Some historical legends distinguish public from employee-only blue."""
    settings = DATA / "image_mask_settings.csv"
    if settings.exists():
        rows = pd.read_csv(settings).set_index("image_file")
        if image_file in rows.index:
            row = rows.loc[image_file]
            mask = G.blue_mask(rgba, min_blue_red=int(row.min_blue_red))
            if row.clip_circle:
                h, w = mask.shape
                yy, xx = np.ogrid[:h, :w]
                mask[(xx - w / 2) ** 2 + (yy - h / 2) ** 2 > (h / 2) ** 2] = 0
            return mask
    return G.blue_mask(rgba)


def process_one(image_file, metro, first_seen, use_manual):
    rgba = G.load_rgba(IMG / image_file)
    lat, lon, rad = METROS[metro]
    if use_manual:
        m = pd.read_csv(DATA / "manual_georef.csv").set_index("image_file").loc[image_file]
        roads = G.osm_roads(metro.replace(" ", "_").lower(), lat, lon, rad)
        params, src = (m.s, m.x0, m.y0), "manual"
        q = quality(rgba, roads, params)
    else:
        (q, *params), roads = georeference(rgba, metro)
        src = "auto"
    save_qa(rgba, roads, params, service_mask(rgba, image_file),
            QA / f"{metro.replace(' ', '_')}_{first_seen}_{image_file[:8]}.jpg")
    return dict(image_file=image_file, metro=metro, s=params[0], x0=params[1], y0=params[2],
                quality=round(q, 4), source=src, first_seen=first_seen)


def main():
    snaps = pd.read_csv(DATA / "snapshot_images.csv")
    history = DATA / "history_sources.csv"
    if history.exists():
        snaps = pd.concat([snaps, pd.read_csv(history)], ignore_index=True)
    snaps = snaps[snaps.image_file.notna() & (snaps.image_file != "")]
    imgs = snaps.groupby("image_file").agg(city=("city", "first"),
                                           first_seen=("date", "min")).reset_index()
    pfile = DATA / "georef_params.csv"
    done = pd.read_csv(pfile) if pfile.exists() else pd.DataFrame(
        columns=["image_file", "metro", "s", "x0", "y0", "quality", "source"])
    manual = pd.read_csv(DATA / "manual_georef.csv") if (DATA / "manual_georef.csv").exists() else None

    rows = done.to_dict("records")
    todo = []
    for _, r in imgs.sort_values("first_seen").iterrows():
        if r.image_file in set(done.image_file):
            continue
        metro = metro_of(r.city)
        if metro is None:
            print("!! no metro config for", r.city)
            continue
        todo.append((r.image_file, metro, r.first_seen))

    if "--only-cached" in sys.argv:  # skip metros whose road data isn't downloaded yet
        todo = [t for t in todo if G.osm_cache_path(
            t[1].replace(" ", "_").lower(), METROS[t[1]][2]).exists()]

    # OSM roads: read from Geofabrik extracts where available (one pass per file),
    # otherwise fall back to Overpass, one metro at a time.
    need = {}
    for metro in sorted({t[1] for t in todo}):
        lat, lon, rad = METROS[metro]
        cache = G.osm_cache_path(metro.replace(" ", "_").lower(), rad)
        pbf = G.PBF_DIR / f"{PBF.get(metro, '')}-latest.osm.pbf"
        if not cache.exists() and metro in PBF and pbf.exists():
            need.setdefault(pbf, {})[cache] = G.osm_bbox(lat, lon, rad)
    for pbf, targets in need.items():
        G.roads_from_pbf(pbf, targets)
    for metro in sorted({t[1] for t in todo}):
        lat, lon, rad = METROS[metro]
        G.osm_roads(metro.replace(" ", "_").lower(), lat, lon, rad)

    manual_files = set(manual.image_file) if manual is not None else set()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process_one, f, m, fs, f in manual_files): f for f, m, fs in todo}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception as e:  # keep going; report at the end
                print("!! failed", futs[fut], repr(e), flush=True)
                continue
            print(f"{row.pop('first_seen')} {row['metro']:14s} {row['image_file']} "
                  f"s={row['s']:.2f} q={row['quality']:.3f}", flush=True)
            rows.append(row)
            pd.DataFrame(rows).to_csv(pfile, index=False)

    # polygons for all images
    P = pd.read_csv(pfile)
    if manual is not None:  # manual rows override
        for _, m in manual.iterrows():
            P.loc[P.image_file == m.image_file, ["s", "x0", "y0", "source"]] = [m.s, m.x0, m.y0, "manual"]
        P.to_csv(pfile, index=False)
    recs = []
    for _, p in P.iterrows():
        rgba = G.load_rgba(IMG / p.image_file)
        mask = service_mask(rgba, p.image_file)
        poly = mask_to_polygon(mask)
        if poly is None:
            continue
        H, W = mask.shape
        # does the blue area touch the edge of the circular map? (=> possibly cut off)
        edge = cv2.dilate(1 - G.valid_mask(rgba), np.ones((7, 7), np.uint8))
        touches = bool((edge.astype(bool) & mask.astype(bool)).sum() > 20)
        geom = shp_transform(lambda x, y, z=None: G.TO_WGS.transform(p.x0 + p.s * np.asarray(x),
                                                                      p.y0 - p.s * np.asarray(y)), poly)
        recs.append(dict(image_file=p.image_file, metro=p.metro, quality=p.quality,
                         source=p.source, m_per_px_merc=p.s, clipped_by_frame=touches, geometry=geom))
    gdf = gpd.GeoDataFrame(recs, crs=4326)
    gdf.to_file(DATA / "image_polygons.gpkg", driver="GPKG")
    print(gdf.drop(columns="geometry").to_string())


if __name__ == "__main__":
    main()
