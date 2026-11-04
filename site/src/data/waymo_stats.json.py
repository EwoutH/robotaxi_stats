"""Waymo area and residents over time, every launch and expansion, and the state of each metro."""

import ast
import json
import sys
from pathlib import Path

import pandas as pd

WAYMO = Path(__file__).resolve().parents[3] / "areas" / "waymo"
DATA = WAYMO / "data"

STATE_NAMES = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware", "11": "District of Columbia", "12": "Florida", "13": "Georgia",
    "15": "Hawaii", "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa", "20": "Kansas",
    "21": "Kentucky", "22": "Louisiana", "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi", "29": "Missouri", "30": "Montana",
    "31": "Nebraska", "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio", "40": "Oklahoma",
    "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island", "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}


def metro_states():
    """Metro -> state name, read from the STATE dict in 06_population.py (one list to maintain)."""
    tree = ast.parse((WAYMO / "06_population.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "STATE" for t in node.targets):
            return {metro: STATE_NAMES.get(fips, fips) for metro, fips in ast.literal_eval(node.value).items()}
    return {}


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

out = {"timeseries": records(ts), "events": records(ev), "states": metro_states()}
sys.stdout.write(json.dumps(out, allow_nan=False))
