"""Tesla Robotaxi area over time, launches and expansions, derived from its boundary versions (format: contract.py).

Tesla has no snapshots of its own, so the timeseries has a row for every date a boundary version starts, with the
version in force in each metro on that date. Events:
- a metro's first version is a launch if its date is an announcement (AV Map), and earliest data if it is the date
  Robotaxi Tracker first recorded the shape (the service may have started before);
- a later version is an expansion if it adds at least MIN_GROWTH of the previous area. Smaller changes are mostly
  re-exports, small edits or a switch of source, and stay in the timeseries only.
No population figures.
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Geod

from contract import write_stats

AREAS = Path(__file__).resolve().parents[3] / "areas"
sys.path.insert(0, str(AREAS))
from metros import metro_of  # noqa: E402

MIN_GROWTH = 0.05
GEOD = Geod(ellps="WGS84")
mi2 = lambda g: abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6 / 2.589988

v = gpd.read_file(AREAS / "tesla" / "tesla_service_areas.geojson")
v["metro"] = [metro_of(c) or c for c in v.city]
v["valid_from"] = v.valid_from.dt.strftime("%Y-%m-%d")
v["valid_to"] = v.valid_to.dt.strftime("%Y-%m-%d")
v = v.sort_values(["metro", "valid_from"])

ts = pd.DataFrame([
    dict(date=d, metro=r.metro, area_mi2=r.area_mi2)
    for d in sorted(v.valid_from.unique())
    for r in v.itertuples()
    if r.valid_from <= d and (pd.isna(r.valid_to) or d < r.valid_to)
])

events = []
for metro, g in v.groupby("metro"):
    prev = None
    for r in g.itertuples():
        extra = dict(metro=metro, date=r.valid_from, after=r.area_mi2, city=r.city, date_kind=r.date_kind,
                     source=r.source, source_url=r.source_url)
        if prev is None:
            kind = "launch" if r.date_kind == "announced" else "earliest_data"
            events.append(dict(kind=kind, added=r.area_mi2, **extra))
        else:
            added = mi2(r.geometry.difference(prev.geometry))
            if added >= MIN_GROWTH * prev.area_mi2:
                events.append(dict(kind="expansion", added=added, **extra))
        prev = r

write_stats("tesla", ts, pd.DataFrame(events))
