"""Tesla Robotaxi service-area boundaries over time, from two community datasets.

- Robotaxi Tracker (github.com/Robotaxi-Tracker/robotaxi-service-areas, CC BY 4.0):
  polygons taken from the Tesla Robotaxi app's fleet areas. Every commit that
  touched areas/tesla/ is read, so the repo's git history is the version history.
  Date = commit date, i.e. when the tracker first recorded the shape.
- AV Map (github.com/path-avmap/av-map-data, MIT): dated Tesla boundaries from
  2025, read at a pinned commit (the repo has not changed since May 2026).
  Date = the event date in its events.csv.

A version that overlaps the previous one by 99.9% or more (intersection over
union) is treated as unchanged and dropped. Writes:
  data/boundary_versions.csv   one row per version, without geometry
  tesla_service_areas.geojson  the same rows with geometry (EPSG:4326)
"""
import csv
import io
import json
import os
from pathlib import Path

import requests
import shapely
from pyproj import Geod
from shapely.geometry import mapping, shape

ROOT = Path(__file__).parent
TRACKER = "Robotaxi-Tracker/robotaxi-service-areas"
AVMAP, AVMAP_SHA = "path-avmap/av-map-data", "3c94c4f924c69f425a54debe0c594a286bf16d8c"
GEOD = Geod(ellps="WGS84")
FIELDS = ["city", "valid_from", "valid_to", "date_kind", "source", "source_ref",
          "source_url", "area_km2", "area_mi2", "iou_prev"]

session = requests.Session()
session.headers["User-Agent"] = "robotaxi_stats research script"


def api(path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    r = session.get(f"https://api.github.com/repos/{path}", headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def raw(repo, sha, path):
    r = session.get(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}", timeout=60)
    r.raise_for_status()
    return r.text


def to_geometry(geojson):
    feats = geojson["features"] if geojson["type"] == "FeatureCollection" else [geojson]
    return shapely.make_valid(shapely.union_all([shape(f["geometry"]) for f in feats]))


def tracker_versions():
    commits = api(f"{TRACKER}/commits?path=areas/tesla&per_page=100")
    for c in reversed(commits):  # oldest first
        sha, date = c["sha"], c["commit"]["committer"]["date"][:10]
        tree = api(f"{TRACKER}/git/trees/{sha}?recursive=1")["tree"]
        for item in tree:
            parts = item["path"].split("/")
            if parts[:2] == ["areas", "tesla"] and parts[-1] == "boundary.geojson":
                yield {"city": parts[2].replace("_", " ").title(), "valid_from": date,
                       "date_kind": "first_seen", "source": "robotaxi_tracker",
                       "source_ref": sha[:12],
                       "source_url": f"https://github.com/{TRACKER}/blob/{sha}/{item['path']}",
                       "geometry": to_geometry(json.loads(raw(TRACKER, sha, item["path"])))}


def avmap_versions():
    events = csv.DictReader(io.StringIO(raw(AVMAP, AVMAP_SHA, "events.csv")))
    for e in events:
        file = e["geometry_file"]
        if e["company"] == "Tesla" and file.endswith(".geojson"):
            yield {"city": e["city"], "valid_from": e["date"], "date_kind": "announced",
                   "source": "av_map", "source_ref": AVMAP_SHA[:12], "source_url": e["source_url"],
                   "geometry": to_geometry(json.loads(raw(AVMAP, AVMAP_SHA, f"geometries/{file}")))}


def main():
    rows = sorted([*avmap_versions(), *tracker_versions()],
                  key=lambda r: (r["city"], r["valid_from"], r["source"]))
    versions = []
    for r in rows:
        prev = versions[-1] if versions and versions[-1]["city"] == r["city"] else None
        g = r["geometry"]
        if prev:
            p = prev["geometry"]
            iou = g.intersection(p).area / g.union(p).area
            if iou >= 0.999:
                continue  # same shape, only re-exported
            prev["valid_to"] = r["valid_from"]
            r["iou_prev"] = round(iou, 3)
        km2 = abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6
        r.update(area_km2=round(km2, 2), area_mi2=round(km2 / 2.589988, 2))
        versions.append(r)

    (ROOT / "data").mkdir(exist_ok=True)
    with open(ROOT / "data" / "boundary_versions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(versions)
    features = [{"type": "Feature", "properties": {k: v.get(k) for k in FIELDS},
                 "geometry": mapping(v["geometry"])} for v in versions]
    with open(ROOT / "tesla_service_areas.geojson", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    print(f"{len(versions)} versions across {len({v['city'] for v in versions})} cities")


if __name__ == "__main__":
    main()
