"""Zoox area over time, launches and expansions, derived from its boundary versions (format: contract.py).

The timeseries has a row for every date a boundary version starts, with the version in force in each metro on that
date. A metro's first version is a launch if its date is an announcement (AV Map), earliest data if it is the date
Robotaxi Tracker first recorded the shape; every later version that grew the area is an expansion.
"""
from pathlib import Path

import pandas as pd

from contract import write_stats

v = pd.read_csv(Path(__file__).resolve().parents[3] / "areas" / "zoox" / "data" / "boundary_versions.csv")
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
        extra = dict(metro=metro, date=r.valid_from, after=r.area_mi2, date_kind=r.date_kind, source_url=r.source_url)
        if prev is None:
            kind = "earliest_data" if r.date_kind == "first_seen" else "launch"
            events.append(dict(kind=kind, added=r.area_mi2, pop_added=r.pop, **extra))
        elif r.area_mi2 > prev.area_mi2:
            events.append(dict(kind="expansion", added=r.area_mi2 - prev.area_mi2, pop_added=r.pop_added, **extra))
        prev = r

write_stats("zoox", ts, pd.DataFrame(events))
