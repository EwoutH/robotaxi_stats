"""Zoox robotaxi service areas over time, with 2020 Census residents, from two community datasets.

- AV Map (github.com/path-avmap/av-map-data, MIT): dated Zoox boundaries from 2025, read at the same pinned commit as
  the Tesla script. Date = the event date in its events.csv (date_kind "announced").
- Robotaxi Tracker (github.com/Robotaxi-Tracker/robotaxi-service-areas, CC BY 4.0): every commit that touched
  areas/zoox/. Date = commit date, i.e. when the tracker first recorded the shape (date_kind "first_seen").

A version that overlaps the metro's previous one by 99.9% or more (intersection over union) is the same shape and is
dropped. Residents (areas/census.py) are recomputed only when the versions changed since the last run.

Writes:
  data/boundary_versions.csv  one row per version: metro, valid_from, valid_to, date_kind, source, source_url,
                              area_mi2, pop (residents), pop_added (residents of the area added to the previous version)
  zoox_service_areas.geojson  the same rows with geometry (EPSG:4326)
"""
import csv
import io
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import shapely
from pyproj import Geod
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parents[1]))
from census import cover_shares, metro_blocks, urban_areas  # noqa: E402
from metros import metro_of  # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "boundary_versions.csv"
TRACKER = "Robotaxi-Tracker/robotaxi-service-areas"
AVMAP, AVMAP_SHA = "path-avmap/av-map-data", "3c94c4f924c69f425a54debe0c594a286bf16d8c"
GEOD = Geod(ellps="WGS84")
COLUMNS = ["metro", "valid_from", "valid_to", "date_kind", "source", "source_url", "area_mi2", "pop", "pop_added"]

session = requests.Session()
session.headers["User-Agent"] = "robotaxi_stats research script"
if os.environ.get("GITHUB_TOKEN"):
    session.headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"


def get(url):
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r


def to_geometry(geojson):
    feats = geojson["features"] if geojson["type"] == "FeatureCollection" else [geojson]
    return shapely.make_valid(shapely.union_all([shape(f["geometry"]) for f in feats]))


def avmap_versions():
    base = f"https://raw.githubusercontent.com/{AVMAP}/{AVMAP_SHA}"
    for e in csv.DictReader(io.StringIO(get(f"{base}/events.csv").text)):
        if e["company"] == "Zoox" and e["geometry_file"].endswith(".geojson"):
            yield dict(metro=metro_of(e["city"]), valid_from=e["date"], date_kind="announced", source="av_map",
                       source_url=e["source_url"],
                       geometry=to_geometry(get(f"{base}/geometries/{e['geometry_file']}").json()))


def tracker_versions():
    api = f"https://api.github.com/repos/{TRACKER}"
    for c in reversed(get(f"{api}/commits?path=areas/zoox&per_page=100").json()):  # oldest first
        sha, date = c["sha"], c["commit"]["committer"]["date"][:10]
        for item in get(f"{api}/git/trees/{sha}?recursive=1").json()["tree"]:
            parts = item["path"].split("/")
            if parts[:2] == ["areas", "zoox"] and parts[-1] == "boundary.geojson":
                label = parts[2].removesuffix("-zoox").replace("-", " ").title()  # bay-area-zoox -> Bay Area
                yield dict(metro=metro_of(label), valid_from=date, date_kind="first_seen", source="robotaxi_tracker",
                           source_url=f"https://github.com/{TRACKER}/blob/{sha}/{item['path']}",
                           geometry=to_geometry(get(f"https://raw.githubusercontent.com/{TRACKER}/{sha}/{item['path']}").json()))


def iou(a, b):
    return a.intersection(b).area / a.union(b).area


def versions():
    rows = sorted([*avmap_versions(), *tracker_versions()], key=lambda r: (r["metro"], r["valid_from"], r["source"]))
    if any(r["metro"] is None for r in rows):
        raise SystemExit("a Zoox city has no row in areas/metros.csv; add one")
    out = []
    for r in rows:
        prev = out[-1] if out and out[-1]["metro"] == r["metro"] else None
        if prev and iou(r["geometry"], prev["geometry"]) >= 0.999:
            continue  # same shape, recorded again
        if prev:
            prev["valid_to"] = r["valid_from"]
        r["area_mi2"] = round(abs(GEOD.geometry_area_perimeter(r["geometry"])[0]) / 1e6 / 2.589988, 2)
        out.append(r)
    return gpd.GeoDataFrame(out, crs=4326).reindex(columns=[*COLUMNS, "geometry"])


def residents(v):
    """Residents of each version and of the area it added, by areal weighting of 2020 Census blocks."""
    ua, states = urban_areas(), {}
    for metro, g in v.groupby("metro"):
        print(f"residents: {metro}", flush=True)
        B, crs = metro_blocks(metro, g.geometry.iloc[-1], ua, states)
        prev = None
        for i, geom in zip(g.index, g.to_crs(crs).geometry):
            v.loc[i, "pop"] = (B.POP20 * cover_shares(geom, B)).sum()
            added = geom if prev is None else geom.difference(prev)
            v.loc[i, "pop_added"] = (B.POP20 * cover_shares(added, B)).sum()
            prev = geom


def main():
    v = versions()
    key = ["metro", "valid_from", "valid_to", "area_mi2"]
    old = pd.read_csv(OUT, dtype=str) if OUT.exists() else None
    if old is not None and old[key].fillna("").values.tolist() == v[key].fillna("").astype(str).values.tolist():
        v[["pop", "pop_added"]] = old[["pop", "pop_added"]].astype(float).values
    else:
        residents(v)
    v[["pop", "pop_added"]] = v[["pop", "pop_added"]].astype(float).round().astype("Int64")
    OUT.parent.mkdir(exist_ok=True)
    v[COLUMNS].to_csv(OUT, index=False, lineterminator="\n")
    with open(ROOT / "zoox_service_areas.geojson", "w", encoding="utf-8", newline="\n") as f:
        f.write(v.to_json(drop_id=True, na="null"))
    print(f"{len(v)} versions across {v.metro.nunique()} metros")


if __name__ == "__main__":
    main()
