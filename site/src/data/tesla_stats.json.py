"""Tesla Robotaxi area over time, launches and expansions, derived from its boundary versions (format: contract.py).

Only cities tesla.com lists as open, from the date it first listed them (tesla_open.py).
Tesla has no snapshots of its own, so the timeseries has a row for every date a boundary version starts, with the
version in force in each metro on that date. Events:
- a metro's first version is a launch if its date is an announcement (AV Map) or the date tesla.com first listed
  the city open, and earliest data if it is the date
  Robotaxi Tracker first recorded the shape (the service may have started before);
- a later version is an expansion if it adds at least MIN_GROWTH of the previous area. Smaller changes are mostly
  re-exports, small edits or a switch of source, and stay in the timeseries only.
Residents come from areas/tesla/03_population.py: a launch or earliest data adds all residents of its version, an
expansion those of the area it added.
"""
import pandas as pd
from pyproj import Geod

from contract import write_stats
from tesla_open import open_versions

MIN_GROWTH = 0.05
GEOD = Geod(ellps="WGS84")
mi2 = lambda g: abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6 / 2.589988

v, _ = open_versions()
v["valid_from"] = v.valid_from.dt.strftime("%Y-%m-%d")
v["valid_to"] = v.valid_to.dt.strftime("%Y-%m-%d")
v = v.sort_values(["metro", "valid_from"])

ts = pd.DataFrame([
    dict(date=d, metro=r.metro, area_mi2=r.area_mi2, pop=r.pop)
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
            kind = "earliest_data" if r.date_kind == "first_seen" else "launch"
            events.append(dict(kind=kind, added=r.area_mi2, pop_added=r.pop, **extra))
        else:
            added = mi2(r.geometry.difference(prev.geometry))
            if added >= MIN_GROWTH * prev.area_mi2:
                events.append(dict(kind="expansion", added=added, pop_added=r.pop_added, **extra))
        prev = r

write_stats("tesla", ts, pd.DataFrame(events))
