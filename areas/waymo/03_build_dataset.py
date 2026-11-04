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
    snaps["date_basis"] = "legacy_map_observation"
    snaps["date_source_url"] = ""
    exclusions_path = DATA / "observation_exclusions.csv"
    if exclusions_path.exists():
        # Preserve raw observations, but exclude a documented stale map from
        # the operational history when a dated operator map supersedes it.
        for rule in pd.read_csv(exclusions_path).itertuples():
            stale = ((snaps.city == rule.city) & (snaps.image_file == rule.image_file)
                     & snaps.date.between(rule.from_date, rule.through_date))
            snaps = snaps.loc[~stale].copy()
    verified_path = DATA / "snapshot_sources.csv"
    if verified_path.exists():
        verified = pd.read_csv(verified_path, dtype={"page": str, "snapshot": str}).fillna("")
        evidence = {(r.page, r.snapshot, r.city, r.image_file): r.page_url
                    for r in verified.itertuples()}
        for i, row in snaps.iterrows():
            key = (str(row.page), row.snapshot, row.city, row.image_file)
            if key in evidence:
                snaps.loc[i, "date_basis"] = "map_observation"
                snaps.loc[i, "date_source_url"] = evidence[key]
    # Curated dates are explicitly attributed to operator announcements rather
    # than masquerading as captures at synthetic archive timestamps.
    supplements_path = DATA / "history_sources.csv"
    if supplements_path.exists():
        extra = pd.read_csv(supplements_path).rename(columns={"source_url": "date_source_url"})
        extra["snapshot"] = extra.date.str.replace("-", "") + "000000"
        extra["page"] = "operator_announcement"
        extra["note"] = ""
        snaps = pd.concat([snaps, extra], ignore_index=True)
    equivalents_path = DATA / "image_equivalences.csv"
    if equivalents_path.exists():
        eq = pd.read_csv(equivalents_path).set_index("image_file").canonical_image_file.to_dict()
        snaps["observed_image_file"] = snaps.image_file
        snaps["image_file"] = snaps.image_file.replace(eq)
    snaps["date"] = pd.to_datetime(snaps.date)
    snaps = snaps[snaps.image_file.notna()]
    # one observation per (day, city): if several captures on the same day disagree,
    # keep the latest capture of that day
    snaps = (snaps.sort_values("snapshot")
             .drop_duplicates(["date", "city", "image_file"], keep="last"))
    all_dates = sorted(snaps.date.unique())
    obs_dates = sorted(snaps.date.unique())

    polys = gpd.read_file(DATA / "image_polygons.gpkg").set_index("image_file")
    missing = set(snaps.image_file) - set(polys.index)
    if missing:
        raise RuntimeError(f"Maps missing georeferenced polygons; run step 2 first: {sorted(missing)}")

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
            first_records = g[(g.date == first) & (g.image_file == img)].sort_values("snapshot").tail(1)
            basis = first_records.date_basis.iloc[0]
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
                change_window_start=first if basis == "operator_announcement" else
                    runs[i - 1][2] if i > 0 else pd.NaT,
                valid_from=first, last_seen=last, valid_to=valid_to,
                n_snapshots=int((g.image_file == img).sum()),
                note=note.iloc[-1] if len(note) else "",
                date_basis=basis,
                date_source_url=first_records.date_source_url.fillna("").iloc[0]))
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
                               change_window_start=g.change_window_start.max(),
                               date_basis=";".join(sorted(set(g.date_basis))),
                               date_source_url=";".join(sorted(set(g.date_source_url) - {""})),
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
