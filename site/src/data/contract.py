"""The data a loader hands to an area page, the same for every operator.

Each operator has its own two loaders in this folder, which read its sources and write with the functions below.
The page adds the operator's name and colors.

<operator>_areas.geojson.py: a FeatureCollection with one feature per metro and boundary version.
  operator     operator id, e.g. "waymo"
  metro        metro name, as in areas/metros.csv
  valid_from   first date (YYYY-MM-DD) the version was in force
  valid_to     date it was replaced, or null while still in force
  area_mi2     area in square miles
  pop          residents inside, or null if unknown
  Other properties pass through untouched. Outer rings are written clockwise, which d3's spherical
  geometry (bounds, centroids) needs; the other way round it reads a ring as everything outside it.

<operator>_stats.json.py: {"metros", "timeseries", "events"}.
  metros       [{"metro", "state"}], every row of areas/metros.csv, in its order
  timeseries   one row per snapshot date and metro in service: operator, date, metro, area_mi2, pop
  events       one row per change: operator, date, metro, kind (earliest_data, launch or expansion),
               kind_label, added and after (sq mi), pop_added. Other columns pass through.

pop and pop_added may be null anywhere, or everywhere for an operator without population figures; the page then
leaves residents out.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import shapely

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "areas"))
from metros import METROS  # noqa: E402

KIND_LABELS = {"earliest_data": "Earliest data", "launch": "Launch", "expansion": "Expansion"}

AREA_COLUMNS = ["metro", "valid_from", "valid_to", "area_mi2", "pop"]
TIMESERIES_COLUMNS = ["date", "metro", "area_mi2", "pop"]
EVENT_COLUMNS = ["date", "metro", "kind", "added", "after", "pop_added"]


def _check(df, columns, what, operator):
    df = df.copy()
    # Population is optional: an operator without figures gets an all-null column.
    for col in ("pop", "pop_added"):
        if col in columns and col not in df:
            df[col] = None
    missing = [c for c in columns if c not in df]
    if missing:
        raise ValueError(f"{what} is missing columns {missing}")
    # Dates as YYYY-MM-DD strings, also when read as timestamps (geopandas does that for GeoJSON).
    for col in ("date", "valid_from", "valid_to"):
        if col in df and pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d").astype(object).where(df[col].notna(), None)
    unknown = sorted(set(df.metro) - set(METROS))
    if unknown:
        print(f"{what}: metros not in areas/metros.csv (shown under 'Other'): {unknown}", file=sys.stderr)
    df.insert(0, "operator", operator)
    return df


def _records(df):
    # Missing values (e.g. a new map whose population isn't computed yet) become null.
    return df.round(2).astype(object).where(df.notna(), None).to_dict("records")


def write_areas(gdf, operator):
    """Write a GeoDataFrame of boundary versions (columns AREA_COLUMNS plus geometry) to stdout as GeoJSON."""
    gdf = _check(gdf, AREA_COLUMNS, "areas", operator)
    gdf["geometry"] = shapely.orient_polygons(gdf.geometry.values, exterior_cw=True)
    sys.stdout.write(gdf.to_json(drop_id=True, na="null"))


def write_stats(operator, timeseries, events):
    """Write the stats for one operator to stdout as JSON."""
    timeseries = _check(timeseries, TIMESERIES_COLUMNS, "timeseries", operator)
    events = _check(events, EVENT_COLUMNS, "events", operator)
    events["kind_label"] = events.kind.map(KIND_LABELS)
    out = {
        "metros": [{"metro": m, "state": r["state"]} for m, r in METROS.items()],
        "timeseries": _records(timeseries),
        "events": _records(events),
    }
    sys.stdout.write(json.dumps(out, allow_nan=False))
