"""Tesla boundary versions limited to cities tesla.com/robotaxi lists as open, from the date it first listed them.

Shared by the Tesla loaders. A city's open date is the first capture showing it open. When that is the first capture
naming any city (Austin), the page only started naming cities then, so the city's earlier versions are kept.
A version straddling the open date starts on it instead, with date_kind "opened", unless it is an announcement
dated after the last capture showing the city not open: then the announcement is the better date and is kept.
Adds the residents of each version (pop) and those it added to the previous version (pop_added) from
areas/tesla/data/population_versions.csv, or nulls where they are not computed yet.
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

AREAS = Path(__file__).resolve().parents[3] / "areas"
sys.path.insert(0, str(AREAS))
from metros import metro_of  # noqa: E402

DATA = AREAS / "tesla" / "data"


def open_since(windows=False):
    """{metro: open date (YYYY-MM-DD) or None for no cut} for cities open on the latest capture.
    With windows=True, {metro: (window_start, open date)}: the city changed to open after window_start."""
    captures = pd.read_csv(DATA / "page_captures.csv")
    cities = pd.read_csv(DATA / "page_cities.csv")
    changes = pd.read_csv(DATA / "status_changes.csv")
    cities_from = pd.to_datetime(str(captures[captures.n_cities > 0].timestamp.min()), format="%Y%m%d%H%M%S")
    latest = cities[(cities.timestamp == captures.timestamp.max()) & (cities.status == "open")]
    out = {}
    for r in latest.itertuples():
        ch = changes[(changes.city_id == r.city_id) & (changes.status_to == "open")].iloc[-1]
        since = None if ch.date == cities_from.strftime("%Y-%m-%d") else ch.date
        start = ch.window_start if isinstance(ch.window_start, str) else None
        out[metro_of(r.name) or r.name] = (start, since) if windows else since
    return out


def open_versions():
    """(versions, dropped): open versions with a metro column, and the cities left out as not listed open."""
    v = gpd.read_file(AREAS / "tesla" / "tesla_service_areas.geojson")
    f = DATA / "population_versions.csv"
    pop = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["city", "valid_from", "pop", "pop_added"])
    pop["valid_from"] = pd.to_datetime(pop.valid_from).astype(v.valid_from.dtype)
    v = v.merge(pop[["city", "valid_from", "pop", "pop_added"]], on=["city", "valid_from"], how="left")
    v["metro"] = [metro_of(c) or c for c in v.city]
    windows = open_since(windows=True)
    since = {m: w[1] for m, w in windows.items()}
    dropped = sorted(set(v.city[~v.metro.isin(since)]))
    v = v[v.metro.isin(since)].copy()
    cut = pd.to_datetime(v.metro.map(since))
    v = v[cut.isna() | v.valid_to.isna() | (v.valid_to > cut)].copy()
    cut = cut[v.index]
    start = pd.to_datetime(v.metro.map(lambda m: windows[m][0]))
    announced_in_window = (v.date_kind == "announced") & start.notna() & (v.valid_from > start)
    moved = cut.notna() & (v.valid_from < cut) & ~announced_in_window
    v.loc[moved, "valid_from"] = cut[moved]
    v.loc[moved, "date_kind"] = "opened"
    return v, dropped
