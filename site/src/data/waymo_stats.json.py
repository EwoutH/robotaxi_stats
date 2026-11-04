"""Waymo area and residents over time, plus every launch and expansion."""

import json
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[3] / "areas" / "waymo" / "data"

area = pd.read_csv(DATA / "area_timeseries.csv")
pop = pd.read_csv(DATA / "population_timeseries.csv")
ts = area[["date", "metro", "area_mi2"]].merge(pop[["date", "metro", "pop"]], on=["date", "metro"], how="left")

ev = pd.read_csv(DATA / "expansion_events.csv")
pev = pd.read_csv(DATA / "population_events.csv")
ev = ev.merge(pev[["metro", "date", "pop_added"]], on=["metro", "date"], how="left")

out = {
    "timeseries": ts.round(2).to_dict("records"),
    "events": ev.round(2).to_dict("records"),
}
sys.stdout.write(json.dumps(out, allow_nan=False))
