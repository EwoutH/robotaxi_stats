"""Step 3: combine snapshot dates and georeferenced polygons into a
time-aware dataset.

Output: waymo_service_areas.gpkg with layers
  versions      one row per city label per map version (valid_from / valid_to)
  metro_versions  city labels merged per metro (e.g. "San Francisco" +
                  "Silicon Valley" -> San Francisco Bay Area), one row per change
and the same as GeoJSON, plus data/area_timeseries.csv (area per metro per snapshot).

Dates: the archive is sampled irregularly, so a change happened somewhere
between `change_window_start` (last snapshot showing the previous state) and
`valid_from` (first snapshot showing the new state).
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module  # noqa: E402

ROOT = Path(__file__).parent
DATA = ROOT / "data"
metro_of = import_module("02_georeference").metro_of
GEOD = Geod(ellps="WGS84")
KM2_PER_MI2 = 2.589988110336


def geod_area_km2(geom):
    if geom is None or geom.is_empty:
        return 0.0
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def main():
    snaps = pd.read_csv(DATA / "snapshot_images.csv", dtype={"snapshot": str})
    snaps["date"] = pd.to_datetime(snaps.date)
    snaps = snaps[snaps.image_file.notna()]
    # one observation per (day, city): if several captures on the same day disagree,
    # keep the latest capture of that day
    snaps = (snaps.sort_values("snapshot")
             .drop_duplicates(["date", "city", "image_file"], keep="last"))
    all_dates = sorted(pd.read_csv(DATA / "snapshot_images.csv").date.map(pd.Timestamp).unique())
    obs_dates = sorted(snaps.date.unique())

    polys = gpd.read_file(DATA / "image_polygons.gpkg").set_index("image_file")

    # ---- versions per city label ------------------------------------------
    recs = []
    for city, g in snaps.groupby("city"):
        # sequence of image per observation date (last one of the day)
        seq = g.sort_values(["date", "snapshot"]).groupby("date").image_file.last()
        runs, prev = [], None
        for d, img in seq.items():
            if img != prev:
                runs.append([img, d, d])
                prev = img
            else:
                runs[-1][2] = d
        for i, (img, first, last) in enumerate(runs):
            before = [x for x in obs_dates if x < first]
            nxt_run = runs[i + 1][1] if i + 1 < len(runs) else None
            if nxt_run is not None:
                valid_to = nxt_run
            else:
                # city disappeared from the page? first snapshot after `last` without it
                later = [x for x in all_dates if x > last]
                valid_to = later[0] if later and last < max(obs_dates) - pd.Timedelta(days=45) else pd.NaT
            note = g[g.image_file == img].note.dropna()
            recs.append(dict(
                city=city, metro=metro_of(city), image_file=img,
                change_window_start=before[-1] if before else pd.NaT,
                valid_from=first, last_seen=last, valid_to=valid_to,
                n_snapshots=int((g.image_file == img).sum()),
                note=note.iloc[-1] if len(note) else ""))
    V = pd.DataFrame(recs)
    V = V.join(polys[["quality", "source", "clipped_by_frame", "geometry"]], on="image_file")
    V = gpd.GeoDataFrame(V, geometry="geometry", crs=4326)
    V["area_km2"] = V.geometry.map(geod_area_km2).round(2)
    V["area_mi2"] = (V.area_km2 / KM2_PER_MI2).round(2)
    V = V.sort_values(["metro", "valid_from", "city"]).reset_index(drop=True)

    # ---- per metro, per snapshot ------------------------------------------
    def active(d):
        vt = V.valid_to.fillna(pd.Timestamp.max)
        return V[(V.valid_from <= d) & (vt > d)]

    ts, mv = [], []
    last_key = {}
    for d in obs_dates:
        A = active(d)
        for metro, g in A.groupby("metro"):
            key = tuple(sorted(g.image_file))
            geom = unary_union(list(g.geometry))
            area = geod_area_km2(geom)
            ts.append(dict(date=d, metro=metro, area_km2=round(area, 2),
                           area_mi2=round(area / KM2_PER_MI2, 2), images=";".join(key)))
            if last_key.get(metro) != key:
                mv.append(dict(metro=metro, valid_from=d, images=";".join(key),
                               city_labels=";".join(sorted(g.city)),
                               min_quality=g.quality.min(), geometry=geom,
                               area_km2=round(area, 2), area_mi2=round(area / KM2_PER_MI2, 2)))
                last_key[metro] = key
    TS = pd.DataFrame(ts)
    MV = gpd.GeoDataFrame(mv, geometry="geometry", crs=4326).sort_values(["metro", "valid_from"])
    # drop versions whose shape is unchanged from the previous one (image re-uploads):
    # differing area < 0.5% of the area
    keep, prev = [], {}
    for i, r in MV.iterrows():
        p = prev.get(r.metro)
        if p is not None and geod_area_km2(r.geometry.symmetric_difference(p.geometry)) \
                < 0.005 * max(r.area_km2, 1e-9):
            continue
        keep.append(i)
        prev[r.metro] = r
    MV = MV.loc[keep]
    MV["valid_to"] = MV.groupby("metro").valid_from.shift(-1)
    # metros that vanished from the page (e.g. Austin moved to the Uber-only page)
    for i, r in MV[MV.valid_to.isna()].iterrows():
        vt = V[V.metro == r.metro].valid_to
        if vt.notna().all():
            MV.loc[i, "valid_to"] = vt.max()

    for df in (V, MV):
        for c in ("change_window_start", "valid_from", "last_seen", "valid_to"):
            if c in df:
                df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d")
    TS["date"] = pd.to_datetime(TS.date).dt.strftime("%Y-%m-%d")

    out = ROOT / "waymo_service_areas.gpkg"
    out.unlink(missing_ok=True)
    V.to_file(out, layer="versions", driver="GPKG")
    MV.to_file(out, layer="metro_versions", driver="GPKG")
    V.to_file(ROOT / "waymo_service_area_versions.geojson", driver="GeoJSON")
    MV.to_file(ROOT / "waymo_service_area_metro_versions.geojson", driver="GeoJSON")
    TS.to_csv(DATA / "area_timeseries.csv", index=False)
    pd.set_option("display.width", 220)
    print(V.drop(columns="geometry").to_string())
    print(MV.drop(columns="geometry").to_string())


if __name__ == "__main__":
    main()
