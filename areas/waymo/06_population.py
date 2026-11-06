"""Step 6: residents inside each service-area version (2020 Census blocks).

For every metro version and every expansion, sums the 2020 Census population of
the blocks inside the polygon. A block that crosses the boundary counts with the
share of its area inside (areal weighting). Density uses the blocks' land area
(ALAND20), so water drawn inside the service area doesn't dilute it.

Only metros whose versions changed since the last run are recomputed, so only
their states' Census blocks are needed (delete data/population_versions.csv to
recompute every metro, ~2.6 GB). Missing Census files are downloaded into
raw/census/ (~100-750 MB per state).

Outputs (used by the site):
  data/population_versions.csv     population per metro version (+-150 m band)
  data/population_events.csv       residents and density added per launch/expansion
  data/population_timeseries.csv   residents served per metro per snapshot date
"""
import sys
from importlib import import_module
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

sys.path.insert(0, str(Path(__file__).parent))
step2 = import_module("02_georeference")
METROS, STATE = step2.METROS, step2.STATE
event_kind = import_module("03_build_dataset").event_kind

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CENSUS = ROOT / "raw" / "census"
KM2_PER_MI2 = 2.589988110336
BAND_M = 150  # boundary error used for the low/high band (README: 50-300 m)
UA_MIN_SHARE = 0.10  # an Urban Area counts as "the metro's" if it holds >=10% of residents served now
TIGER = "https://www2.census.gov/geo/tiger"

BLOCK_COLS = ["GEOID20", "POP20", "HOUSING20", "ALAND20", "AWATER20", "INTPTLAT20", "INTPTLON20"]


# ---------------------------------------------------------------- census data

def _need(path, url):
    """Download a Census file into raw/census/ if it isn't there yet."""
    if path.exists():
        return
    print(f"  downloading {url}", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)


def urban_areas():
    f = CENSUS / "tl_2023_us_uac20.zip"
    _need(f, f"{TIGER}/TIGER2023/UAC/tl_2023_us_uac20.zip")
    return gpd.read_file(f, columns=["UACE20"])


def state_blocks(fips, ua):
    """All blocks of a state with their 2020 Urban Area code, cached as GeoParquet."""
    cache = CENSUS / f"blocks_{fips}.parquet"
    if cache.exists():
        return gpd.read_parquet(cache)
    f = CENSUS / f"tl_2020_{fips}_tabblock20.zip"
    _need(f, f"{TIGER}/TIGER2020/TABBLOCK20/tl_2020_{fips}_tabblock20.zip")
    print(f"  reading {f.name}", flush=True)
    b = gpd.read_file(f, columns=BLOCK_COLS, engine="pyogrio")
    for c in ("POP20", "HOUSING20", "ALAND20", "AWATER20"):
        b[c] = pd.to_numeric(b[c])
    # Urban Areas are built from 2020 blocks, so the internal point decides membership
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(b.INTPTLON20.astype(float),
                                                       b.INTPTLAT20.astype(float)), crs=4326)
    j = gpd.sjoin(pts, ua.to_crs(4326)[["UACE20", "geometry"]], how="left", predicate="within")
    b["UACE20"] = j[~j.index.duplicated()].reindex(pts.index).UACE20.values
    b = b.drop(columns=["INTPTLAT20", "INTPTLON20"]).to_crs(4326)
    b.to_parquet(cache)
    return b


def metro_blocks(metro, current_geom, ua, cache_states):
    """Blocks within the metro's search radius, plus all blocks of its Urban Area(s)."""
    fips = STATE[metro]
    if fips not in cache_states:
        cache_states[fips] = state_blocks(fips, ua)
    sb = cache_states[fips]
    lat, lon, rad_km = METROS[metro]
    crs = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).estimate_utm_crs()
    centre = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).to_crs(crs).iloc[0]
    sbp = sb.to_crs(crs)
    near = sbp[sbp.intersects(centre.buffer(rad_km * 1000))]
    # which Urban Areas does the current service area mostly serve?
    cur = gpd.GeoSeries([current_geom], crs=4326).to_crs(crs).iloc[0]
    sh = cover_shares(cur, near)
    by_ua = (near.POP20 * sh).groupby(near.UACE20).sum()
    uas = by_ua[by_ua >= UA_MIN_SHARE * by_ua.sum()].index.tolist()
    B = pd.concat([near, sbp[sbp.UACE20.isin(uas) & ~sbp.index.isin(near.index)]])
    B["in_metro_ua"] = B.UACE20.isin(uas)
    # block-group density, for the "how urban is it" measures
    B["bg"] = B.GEOID20.str[:12]
    g = B.groupby("bg")[["POP20", "ALAND20"]].transform("sum")
    B["bg_density_mi2"] = g.POP20 / (g.ALAND20 / 1e6 / KM2_PER_MI2).where(g.ALAND20 > 0)
    return B, crs


# ---------------------------------------------------------------- overlay

def cover_shares(geom, B):
    """Share of each block's area inside `geom` (both in the same projected CRS)."""
    share = np.zeros(len(B))
    if geom is None or geom.is_empty:
        return share
    idx = B.sindex.query(geom, predicate="intersects")
    if len(idx) == 0:
        return share
    shapely.prepare(geom)
    garr = np.asarray(B.geometry.values)
    g = garr[idx]
    inside = shapely.contains(geom, g)
    share[idx[inside]] = 1.0
    part = idx[~inside]
    if len(part):
        gp = garr[part]
        a = shapely.area(gp)
        share[part] = np.where(a > 0, shapely.area(shapely.intersection(gp, geom)) / a, 0.0)
    return np.clip(share, 0, 1)


def summarise(share, B):
    pop = B.POP20.values * share
    land_km2 = (B.ALAND20.values * share).sum() / 1e6
    p = pop.sum()
    dens = B.bg_density_mi2.fillna(0).values
    return dict(
        pop=p,
        housing=(B.HOUSING20.values * share).sum(),
        land_mi2=land_km2 / KM2_PER_MI2,
        density_mi2=p / (land_km2 / KM2_PER_MI2) if land_km2 > 0 else np.nan,
        # density the average resident lives at (block-group level); less sensitive
        # to empty land (parks, industrial, airports) inside the area
        pw_density_mi2=(pop * dens).sum() / p if p > 0 else np.nan,
        pop_in_metro_ua=pop[B.in_metro_ua.values].sum(),
        pop_urban=pop[B.UACE20.notna().values].sum(),
    )


# ---------------------------------------------------------------- tables

def compute(mv, only):
    """Population per version and event for the metros in `only`."""
    ua = urban_areas()
    states, vers, events = {}, [], []
    for metro, g in mv.groupby("metro"):
        if metro not in only:
            continue
        g = g.sort_values("valid_from")
        if metro not in STATE:
            raise SystemExit(f"Add {metro} to areas/metros.csv")
        print(metro, flush=True)
        B, crs = metro_blocks(metro, g.geometry.iloc[-1], ua, states)
        ua_pop = B.loc[B.in_metro_ua, "POP20"].sum()
        geoms = g.to_crs(crs).geometry.make_valid().values
        prev = None
        for (_, r), geom in zip(g.iterrows(), geoms):
            s = summarise(cover_shares(geom, B), B)
            lo = summarise(cover_shares(geom.buffer(-BAND_M), B), B)["pop"]
            hi = summarise(cover_shares(geom.buffer(BAND_M), B), B)["pop"]
            vers.append(dict(metro=metro, valid_from=r.valid_from, valid_to=r.valid_to,
                             area_mi2=r.area_mi2, **s, pop_lo=lo, pop_hi=hi,
                             share_of_ua=s["pop_in_metro_ua"] / ua_pop))
            added = geom if prev is None else geom.difference(prev)
            removed = None if prev is None else prev.difference(geom)
            a = summarise(cover_shares(added, B), B)
            events.append(dict(metro=metro, date=r.valid_from,
                               kind=event_kind(metro, r.valid_from, prev is None),
                               area_added_mi2=shapely.area(added) / 1e6 / KM2_PER_MI2,
                               pop_added=a["pop"], land_added_mi2=a["land_mi2"],
                               density_added_mi2=a["density_mi2"],
                               pw_density_added_mi2=a["pw_density_mi2"],
                               pop_removed=summarise(cover_shares(removed, B), B)["pop"]))
            prev = geom
    return pd.DataFrame(vers), pd.DataFrame(events)


def timeseries(V, ts):
    rows = []
    for _, t in ts.iterrows():
        v = V[(V.metro == t.metro) & (V.valid_from <= t.date)
              & (V.valid_to.isna() | (V.valid_to > t.date))]
        if len(v):
            v = v.iloc[-1]
            rows.append(dict(date=t.date, metro=t.metro, pop=v["pop"], pop_lo=v.pop_lo,
                             pop_hi=v.pop_hi, area_mi2=t.area_mi2, land_mi2=v.land_mi2))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- update

def version_key(df):
    """Per metro: its versions as (valid_from, valid_to, area), to spot changed metros."""
    d = lambda c: pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d").fillna("")
    k = pd.DataFrame({"metro": df.metro, "f": d("valid_from"), "t": d("valid_to"),
                      "a": df.area_mi2.astype(float).round(2)})
    return {m: list(map(tuple, g[["f", "t", "a"]].values)) for m, g in k.groupby("metro")}


def update(mv, ts):
    """Recompute only metros whose versions changed; keep the other rows as they are."""
    vf, ef = DATA / "population_versions.csv", DATA / "population_events.csv"
    if vf.exists():
        V0 = pd.read_csv(vf, parse_dates=["valid_from", "valid_to"])
        E0 = pd.read_csv(ef, parse_dates=["date"])
    else:  # first run: every metro
        V0 = pd.DataFrame(columns=["metro", "valid_from", "valid_to", "area_mi2"])
        E0 = pd.DataFrame(columns=["metro"])
    new, old = version_key(mv), version_key(V0)
    changed = sorted(m for m in new if new[m] != old.get(m))
    print("changed metros:", ", ".join(changed) or "none")
    if changed:
        V1, E1 = compute(mv, set(changed))
        V = pd.concat([V0[V0.metro.isin(new) & ~V0.metro.isin(changed)], V1])
        E = pd.concat([E0[E0.metro.isin(new) & ~E0.metro.isin(changed)], E1])
    else:
        V, E = V0, E0
    V = V.sort_values(["metro", "valid_from"]).reset_index(drop=True)
    E = E.sort_values(["metro", "date"]).reset_index(drop=True)
    for df, cols in ((V, ["valid_from", "valid_to"]), (E, ["date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    return V, E, timeseries(V, ts)


def write(V, E, T):
    fmt = lambda df, cols: df.assign(**{c: pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d") for c in cols})
    fmt(V.round(4), ["valid_from", "valid_to"]).to_csv(DATA / "population_versions.csv", index=False)
    fmt(E.round(2), ["date"]).to_csv(DATA / "population_events.csv", index=False)
    fmt(T.round(0), ["date"]).to_csv(DATA / "population_timeseries.csv", index=False)


def main():
    mv = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="metro_versions")
    for c in ("valid_from", "valid_to"):
        mv[c] = pd.to_datetime(mv[c])
    ts = pd.read_csv(DATA / "area_timeseries.csv", parse_dates=["date"])
    write(*update(mv.sort_values(["metro", "valid_from"]), ts))


if __name__ == "__main__":
    main()
