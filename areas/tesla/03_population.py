"""Residents (2020 Census) inside each Tesla boundary version, and those added or removed by each change.

Same method as Waymo's step 6 (areas/census.py): areal weighting of 2020 Census blocks, with the blocks of the
city's metro (areas/metros.csv). The low/high band moves the boundary in and out by BAND_M for traced shapes (AV Map,
the tracker's hand-drawn copies); Tesla's own polygons (`exact`) get no band.

Only cities whose versions changed since the last run are recomputed, so on most days nothing is read. A changed
city needs its state's Census blocks, downloaded into areas/raw/census/ when missing (~100-750 MB per state). Delete
data/population_versions.csv to recompute every city. A city without a row in areas/metros.csv is skipped (its
figures stay empty) until one is added.

Writes data/population_versions.csv: one row per row of data/boundary_versions.csv (city, valid_from).
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).parents[1]))
from census import KM2_PER_MI2, block_cover, cover_shares, metro_blocks, summarise, urban_areas  # noqa: E402
from metros import metro_of  # noqa: E402

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "population_versions.csv"
BAND_M = 150  # boundary error of traced shapes, as for Waymo's maps (hand-drawn edges are 25-115 m off on average)
MIN_COVER = 0.98  # a version must lie (almost) entirely within the loaded Census blocks


def load():
    v = gpd.read_file(ROOT / "tesla_service_areas.geojson")
    for c in ("valid_from", "valid_to", "redrawn"):
        v[c] = pd.to_datetime(v[c]).dt.strftime("%Y-%m-%d")
    v["exact"] = v.exact.astype(str).str.lower() == "true"
    v["metro"] = [metro_of(c) for c in v.city]
    return v.sort_values(["city", "valid_from"]).reset_index(drop=True)


def compute(v, only):
    ua, states, rows = urban_areas(), {}, []
    for city, g in v[v.city.isin(only)].groupby("city"):
        metro = g.metro.iloc[0]
        print(f"{city} ({metro})", flush=True)
        B, crs = metro_blocks(metro, g.geometry.iloc[-1], ua, states)
        ua_pop = B.loc[B.in_metro_ua, "POP20"].sum()
        geoms = g.to_crs(crs).geometry.make_valid().values
        prev = None
        for r, geom in zip(g.itertuples(), geoms):
            share = cover_shares(geom, B)
            cover = block_cover(share, B) / (shapely.area(geom) / 1e6)
            if cover < MIN_COVER:
                raise SystemExit(f"{city} {r.valid_from}: only {cover:.1%} of the area lies within the Census blocks "
                                 f"loaded for {metro}; raise its radius_km in areas/metros.csv")
            s = summarise(share, B)
            band = 0 if r.exact else BAND_M
            lo = summarise(cover_shares(geom.buffer(-band), B), B)["pop"] if band else s["pop"]
            hi = summarise(cover_shares(geom.buffer(band), B), B)["pop"] if band else s["pop"]
            added = geom if prev is None else geom.difference(prev)
            removed = None if prev is None else prev.difference(geom)
            a = summarise(cover_shares(added, B), B)
            rows.append(dict(
                city=city, metro=metro, valid_from=r.valid_from, valid_to=r.valid_to, exact=r.exact,
                area_mi2=r.area_mi2, **s, band_m=band, pop_lo=lo, pop_hi=hi, share_of_ua=s["pop_in_metro_ua"] / ua_pop,
                area_added_mi2=shapely.area(added) / 1e6 / KM2_PER_MI2, pop_added=a["pop"],
                land_added_mi2=a["land_mi2"], density_added_mi2=a["density_mi2"],
                pw_density_added_mi2=a["pw_density_mi2"], pop_removed=summarise(cover_shares(removed, B), B)["pop"]))
            prev = geom
    return pd.DataFrame(rows)


def version_key(df):
    """Per city: its versions as (valid_from, valid_to, area, exact), to spot changed cities."""
    k = df[["city", "valid_from", "valid_to", "area_mi2", "exact"]].copy()
    k["valid_to"] = k.valid_to.fillna("")
    k["area_mi2"] = k.area_mi2.astype(float).round(2)
    k["exact"] = k.exact.astype(str).str.lower() == "true"
    return {c: list(map(tuple, g.drop(columns="city").values)) for c, g in k.groupby("city")}


def main():
    v = load()
    old = pd.read_csv(OUT, dtype={"valid_to": str}) if OUT.exists() else pd.DataFrame(
        columns=["city", "valid_from", "valid_to", "area_mi2", "exact"])
    new, before = version_key(v), version_key(old)
    changed = {c for c in new if new[c] != before.get(c)}
    unmapped = sorted(c for c in changed if v.metro[v.city == c].isna().any())
    if unmapped:
        print("no row in areas/metros.csv, skipped:", ", ".join(unmapped))
    changed -= set(unmapped)
    print("changed cities:", ", ".join(sorted(changed)) or "none")
    if not changed and set(old.city) <= set(new):
        return
    keep = old[old.city.isin(new) & ~old.city.isin(changed)]
    out = pd.concat([keep, compute(v, changed)]) if changed else keep
    out = out.sort_values(["city", "valid_from"])
    out.round(4).to_csv(OUT, index=False, lineterminator="\n")


if __name__ == "__main__":
    main()
