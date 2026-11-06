"""Step 6: residents inside each service-area version (2020 Census blocks).

For every metro version and every expansion, sums the 2020 Census population of
the blocks inside the polygon, with the method in areas/census.py (areal weighting,
shared with the Tesla data).

Only metros whose versions changed since the last run are recomputed, so only
their states' Census blocks are needed (delete data/population_versions.csv to
recompute every metro, ~2.6 GB). Missing Census files are downloaded into
areas/raw/census/ (~100-750 MB per state).

Outputs (used by the site):
  data/population_versions.csv     population per metro version (+-150 m band)
  data/population_events.csv       residents and density added per launch/expansion
  data/population_timeseries.csv   residents served per metro per snapshot date
"""
import sys
from importlib import import_module
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from census import KM2_PER_MI2, cover_shares, metro_blocks, summarise, urban_areas  # noqa: E402
from metros import METROS  # noqa: E402

event_kind = import_module("03_build_dataset").event_kind

ROOT = Path(__file__).parent
DATA = ROOT / "data"
BAND_M = 150  # boundary error used for the low/high band (README: 50-300 m)


# ---------------------------------------------------------------- tables

def compute(mv, only):
    """Population per version and event for the metros in `only`."""
    ua = urban_areas()
    states, vers, events = {}, [], []
    for metro, g in mv.groupby("metro"):
        if metro not in only:
            continue
        g = g.sort_values("valid_from")
        if metro not in METROS:
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
