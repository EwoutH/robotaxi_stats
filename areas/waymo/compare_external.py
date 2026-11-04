"""Compare Waymo polygons with pinned public datasets; run with --fetch initially.

Inputs are cached under raw/external_comparison/. Existing pins are reused unless
--refresh is passed. Metrics use geodesic WGS84 areas; maps use local UTM.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from pyproj import Geod
import requests
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "raw" / "external_comparison"
OUT = ROOT / "data" / "external_comparison"
GEOD = Geod(ellps="WGS84")
SQMI = 1609.344 ** 2
REPOS = {
    "robotaxi_tracker": "Robotaxi-Tracker/robotaxi-service-areas",
    "av_map": "path-avmap/av-map-data",
}
ALIASES = {
    "San Francisco Bay Area": "San Francisco",
    "Bay Area": "San Francisco",
    "Silicon Valley": "San Francisco",
}


def download(url):
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    return response.content


def fetch(refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = CACHE / "manifest.json"
    if manifest_path.exists() and not refresh:
        return
    pinned_path = OUT / "manifest.json"
    pinned = json.loads(pinned_path.read_text()) if pinned_path.exists() and not refresh else None
    manifest = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "datasets": {}}
    for name, repo in REPOS.items():
        if pinned:
            entry = pinned["datasets"][name]
            sha, committed_at = entry["commit"], entry["committed_at"]
            paths = list(entry["files_sha256"])
        else:
            commit = json.loads(download(f"https://api.github.com/repos/{repo}/commits/main"))
            sha = commit["sha"]
            committed_at = commit["commit"]["committer"]["date"]
            tree = json.loads(download(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1"))
            paths = [entry["path"] for entry in tree["tree"]]
        if not pinned and name == "robotaxi_tracker":
            paths = [p for p in paths if p.startswith("areas/waymo/") and
                     (p.endswith("meta.json") or p.endswith("boundary.geojson"))]
        elif not pinned:
            events = download(f"https://raw.githubusercontent.com/{repo}/{sha}/events.csv")
            rows = list(csv.DictReader(io.StringIO(events.decode("utf-8-sig"))))
            files = {r["geometry_file"] for r in rows if r["company"] == "Waymo"
                     and r["geometry_file"].endswith(".geojson")}
            paths = ["events.csv"] + [f"geometries/{p}" for p in sorted(files)]
        if not pinned:
            paths += ["README.md", "LICENSE"]
        target = CACHE / name / sha

        def save(path):
            payload = download(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}")
            digest = hashlib.sha256(payload).hexdigest()
            if pinned and digest != entry["files_sha256"][path]:
                raise ValueError(f"Downloaded file differs from pin: {name}/{path}")
            local = target / path
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(payload)
            return path, digest

        with ThreadPoolExecutor(max_workers=6) as pool:
            hashes = dict(pool.map(save, paths))
        manifest["datasets"][name] = {
            "repository": repo, "commit": sha,
            "committed_at": committed_at,
            "files_sha256": hashes,
        }
        print(f"Fetched {name}: {sha}, {len(paths)} files")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def polygons(geometry):
    """Repair invalid input and retain polygonal components only."""
    if not geometry.is_valid:
        geometry = make_valid(geometry)
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if isinstance(geometry, GeometryCollection):
        return unary_union([polygons(g) for g in geometry.geoms if
                            isinstance(g, (Polygon, MultiPolygon, GeometryCollection))])
    raise ValueError(f"Expected polygon, got {geometry.geom_type}")


def read_geojson(path):
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    features = obj["features"] if obj["type"] == "FeatureCollection" else [obj]
    return polygons(unary_union([polygons(shape(f["geometry"])) for f in features]))


def area(geometry):
    if geometry.is_empty:
        return 0.0
    if isinstance(geometry, Polygon):
        shell = abs(GEOD.polygon_area_perimeter(*geometry.exterior.coords.xy)[0])
        holes = sum(abs(GEOD.polygon_area_perimeter(*ring.coords.xy)[0])
                    for ring in geometry.interiors)
        return (shell - holes) / SQMI
    return sum(area(part) for part in geometry.geoms)


def metrics(ours, theirs):
    a, b = area(ours), area(theirs)
    inter = area(ours.intersection(theirs))
    return {
        "ours_mi2": a, "external_mi2": b,
        "external_minus_ours_mi2": b - a,
        "external_minus_ours_pct": (b / a - 1) * 100,
        "intersection_mi2": inter,
        "iou_pct": inter / area(ours.union(theirs)) * 100,
        "ours_covered_pct": inter / a * 100,
        "external_covered_pct": inter / b * 100,
        "ours_only_mi2": area(ours.difference(theirs)),
        "external_only_mi2": area(theirs.difference(ours)),
    }


def external_records(manifest):
    records = []
    for name, entry in manifest["datasets"].items():
        folder = CACHE / name / entry["commit"]
        for path, digest in entry["files_sha256"].items():
            assert hashlib.sha256((folder / path).read_bytes()).hexdigest() == digest, path
        if name == "robotaxi_tracker":
            for path in sorted(folder.glob("areas/waymo/*/meta.json")):
                meta = json.loads(path.read_text())
                records.append({
                    "dataset": name, "metro": ALIASES.get(meta["name"], meta["name"]),
                    "external_date": "", "external_city": meta["name"],
                    "file": str(path.parent.relative_to(folder) / "boundary.geojson"),
                    "source_url": "", "geometry": read_geojson(path.parent / "boundary.geojson"),
                })
        else:
            rows = list(csv.DictReader(io.StringIO((folder / "events.csv").read_text(encoding="utf-8-sig"))))
            # Reconstruct separate SF and Silicon Valley series, then union them
            # at each change date to match our metropolitan aggregation.
            events = [r for r in rows if r["company"] == "Waymo" and
                      r["geometry_file"].endswith(".geojson") and
                      r["event_type"] in {"service_created", "geometry_updated"}]
            state = {}
            for date in sorted({r["date"] for r in events}):
                changed = set()
                for row in [r for r in events if r["date"] == date]:
                    metro = ALIASES.get(row["city"], row["city"])
                    state[row["city"]] = {**row, "metro": metro,
                        "geometry": read_geojson(folder / "geometries" / row["geometry_file"])}
                    changed.add(metro)
                for metro in sorted(changed):
                    parts = [r for r in state.values() if r["metro"] == metro]
                    records.append({
                        "dataset": name, "metro": metro, "external_date": date,
                        "external_city": "; ".join(r["city"] for r in parts),
                        "file": "; ".join("geometries/" + r["geometry_file"] for r in parts),
                        "source_url": "; ".join(r["source_url"] for r in parts),
                        "geometry": polygons(unary_union([r["geometry"] for r in parts])),
                    })
    return records


def compare(ours, external):
    latest_rows, best_rows, temporal_rows = [], [], []
    latest_pairs, best_pairs = [], []
    for dataset in REPOS:
        subset = [r for r in external if r["dataset"] == dataset]
        for metro in sorted({r["metro"] for r in subset}):
            history = ours[ours.metro == metro].sort_values("valid_from")
            if history.empty:
                continue
            candidates = [r for r in subset if r["metro"] == metro]
            ext = max(candidates, key=lambda r: r["external_date"])
            current = history.iloc[-1]
            base = {k: v for k, v in ext.items() if k != "geometry"}
            result = {**base, "ours_valid_from": current.valid_from,
                      **metrics(current.geometry, ext["geometry"])}
            latest_rows.append(result)
            latest_pairs.append((result, current.geometry, ext["geometry"]))
            for ext_version in candidates:
                base = {k: v for k, v in ext_version.items() if k != "geometry"}
                all_matches = [(row, metrics(row.geometry, ext_version["geometry"]))
                               for _, row in history.iterrows()]
                best, stat = max(all_matches, key=lambda pair: pair[1]["iou_pct"])
                result = {**base, "ours_valid_from": best.valid_from,
                          "ours_valid_to": best.valid_to, **stat}
                best_rows.append(result)
                if ext_version is ext:
                    best_pairs.append((result, best.geometry, ext_version["geometry"]))
                if dataset == "av_map":
                    date = ext_version["external_date"]
                    active = history[(history.valid_from <= date) &
                                     (history.valid_to.isna() | (history.valid_to > date))]
                    if not active.empty:
                        row = active.iloc[-1]
                        temporal_rows.append({**base, "ours_valid_from": row.valid_from,
                                              **metrics(row.geometry, ext_version["geometry"])})
    return latest_rows, best_rows, temporal_rows, latest_pairs, best_pairs


def atlas(pairs, path, title):
    plt.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "robotaxi_stats"})
    metros = sorted({r[0]["metro"] for r in pairs})
    fig, axes = plt.subplots(int(np.ceil(len(metros) / 3)), 3, figsize=(13, 18))
    for ax, metro in zip(axes.flat, metros):
        selected = [p for p in pairs if p[0]["metro"] == metro]
        series = gpd.GeoSeries([g for _, a, b in selected for g in (a, b)], crs=4326)
        crs = series.estimate_utm_crs()
        for i, (row, a, b) in enumerate(selected):
            # In the historical atlas, each source may match a different version.
            projected = gpd.GeoSeries([a, b], crs=4326).to_crs(crs)
            # Rendering only: 20 m is below a panel pixel and map-source accuracy.
            # All overlap/area calculations above retain the full geometries.
            projected = projected.simplify(20, preserve_topology=True)
            projected.iloc[[0]].boundary.plot(ax=ax, color="#202c39", linewidth=0.9,
                             linestyle="-" if i == 0 else ":")
            projected.iloc[[1]].boundary.plot(ax=ax, color="#d53e73" if row["dataset"] == "robotaxi_tracker" else "#1684be",
                             linewidth=0.7, alpha=0.9)
        ax.set_title(metro + "\n" + " | ".join(
            ("Tracker" if r["dataset"] == "robotaxi_tracker" else "AV Map") +
            f": {r['iou_pct']:.0f}% IoU" for r, _, _ in selected), fontsize=10)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    for ax in list(axes.flat)[len(metros):]:
        ax.set_visible(False)
    fig.suptitle(title, fontsize=16)
    fig.legend(handles=[Line2D([], [], color=c, label=l) for c, l in
                        [("#202c39", "Our Waymo polygons"), ("#d53e73", "Robotaxi Tracker"),
                         ("#1684be", "AV Map")]], loc="upper center", bbox_to_anchor=(0.5, 0.967), ncol=3)
    fig.text(0.5, 0.017, "Boundary overlap is not ground-truth accuracy. No land/water clipping. Local UTM per panel.",
             ha="center", fontsize=8)
    fig.text(0.5, 0.007, "Service areas: robotaxitracker.com (CC BY 4.0); avmap.io (MIT, Jackson Lester); robotaxi_stats. See comparison report for dates.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.025, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, metadata={"Date": None})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Download inputs if not yet pinned")
    parser.add_argument("--refresh", action="store_true", help="Pin and download current upstream revisions")
    args = parser.parse_args()
    if args.fetch or args.refresh:
        fetch(args.refresh)
    manifest = json.loads((CACHE / "manifest.json").read_text())
    ours_path = ROOT / "waymo_service_areas.gpkg"
    ours = gpd.read_file(ours_path, layer="metro_versions")
    ours.geometry = ours.geometry.map(polygons)
    external = external_records(manifest)
    latest, best, temporal, latest_pairs, best_pairs = compare(ours, external)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, entry in manifest["datasets"].items():
        license_path = CACHE / name / entry["commit"] / "LICENSE"
        (OUT / f"LICENSE.{name}.txt").write_bytes(license_path.read_bytes())
    best_latest = [p[0] for p in best_pairs]
    for rows in [latest, best, temporal]:
        for row in rows:
            assert -1e-6 <= row["iou_pct"] <= 100 + 1e-6
            assert abs(row["intersection_mi2"] + row["ours_only_mi2"] - row["ours_mi2"]) < 0.02
            assert abs(row["intersection_mi2"] + row["external_only_mi2"] - row["external_mi2"]) < 0.02
    for name, rows in [("latest", latest), ("best_historical_match", best),
                       ("best_historical_latest", best_latest), ("at_external_date", temporal)]:
        pd.DataFrame(rows).to_csv(OUT / (name + ".csv"), index=False, float_format="%.6f")
    manifest["ours"] = {
        "file": "waymo_service_areas.gpkg", "sha256": hashlib.sha256(ours_path.read_bytes()).hexdigest(),
        "layer": "metro_versions", "versions": len(ours),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {}
    for dataset in REPOS:
        selected = pd.DataFrame([r for r in best_latest if r["dataset"] == dataset])
        available = {r["metro"] for r in external if r["dataset"] == dataset}
        summary[dataset] = {
            "matched_metros": len(selected),
            "missing_our_metros": sorted(set(ours.metro) - available),
            "latest_external_vs_best_historical_median_iou_pct": float(selected.iou_pct.median()),
            "latest_external_vs_best_historical_metros_iou_ge_95": int((selected.iou_pct >= 95).sum()),
            "latest_external_vs_best_historical_median_abs_area_difference_pct":
                float(selected.external_minus_ours_pct.abs().median()),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    atlas(latest_pairs, ROOT / "figures/report/external_comparison_latest.svg",
          "Latest available Waymo boundaries (different observation dates)")
    atlas(best_pairs, ROOT / "figures/report/external_comparison_historical.svg",
          "Each external latest boundary vs. our closest historical shape")
    print("LATEST\n", pd.DataFrame(latest)[["dataset", "metro", "external_date", "ours_valid_from",
          "ours_mi2", "external_mi2", "iou_pct", "external_minus_ours_pct"]].round(2).to_string(index=False))
    print("BEST MATCHES FOR EXTERNAL LATEST\n", pd.DataFrame([p[0] for p in best_pairs])[[
        "dataset", "metro", "external_date", "ours_valid_from", "ours_mi2", "external_mi2", "iou_pct"]]
        .round(2).to_string(index=False))


if __name__ == "__main__":
    main()
