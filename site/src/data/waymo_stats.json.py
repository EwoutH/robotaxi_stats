"""Waymo area and residents over time, every launch and expansion, and the state of each metro."""

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
WAYMO = REPO / "areas" / "waymo"
DATA = WAYMO / "data"


def records(df):
    # Missing values (e.g. a new map whose population isn't computed yet) become null.
    return df.round(2).astype(object).where(df.notna(), None).to_dict("records")


area = pd.read_csv(DATA / "area_timeseries.csv")
pop = pd.read_csv(DATA / "population_timeseries.csv")
ts = area[["date", "metro", "area_mi2"]].merge(pop[["date", "metro", "pop"]], on=["date", "metro"], how="left")

ev = pd.read_csv(DATA / "expansion_events.csv")
ev["kind_label"] = ev.kind.map({"earliest_data": "Earliest data", "launch": "Launch", "expansion": "Expansion"})
pev = pd.read_csv(DATA / "population_events.csv")
ev = ev.merge(pev[["metro", "date", "pop_added"]], on=["metro", "date"], how="left")

metros = pd.read_csv(REPO / "areas" / "metros.csv", dtype=str)
states = dict(zip(metros.metro, metros.state))

out = {"timeseries": records(ts), "events": records(ev), "states": states}
sys.stdout.write(json.dumps(out, allow_nan=False))
