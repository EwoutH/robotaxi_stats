"""Waymo area and residents over time, and every launch and expansion (format: contract.py)."""

from pathlib import Path

import pandas as pd

from contract import write_stats

DATA = Path(__file__).resolve().parents[3] / "areas" / "waymo" / "data"

area = pd.read_csv(DATA / "area_timeseries.csv")
pop = pd.read_csv(DATA / "population_timeseries.csv")
ts = area[["date", "metro", "area_mi2"]].merge(pop[["date", "metro", "pop"]], on=["date", "metro"], how="left")

ev = pd.read_csv(DATA / "expansion_events.csv")
pev = pd.read_csv(DATA / "population_events.csv")
ev = ev.merge(pev[["metro", "date", "pop_added"]], on=["metro", "date"], how="left")

write_stats("waymo", ts, ev)
