"""Tesla's own city status ("open" / "soon") from archived tesla.com/robotaxi, for the Tesla page's coverage section.

{"first_capture", "last_capture", "cities_from", "cities": [{city_id, name, metro, status, since, window_start}]}
status is the city's status on the latest capture; since is the first capture showing that status (it changed
between window_start and since). cities_from is the first capture naming any city; earlier captures
name none, so a since on that date is when the page first named the city, not a change. Cities that dropped off the page are left out. Dates are YYYY-MM-DD.
"""
import json
import sys
from pathlib import Path

import pandas as pd

AREAS = Path(__file__).resolve().parents[3] / "areas"
sys.path.insert(0, str(AREAS))
from metros import metro_of  # noqa: E402

DATA = AREAS / "tesla" / "data"
day = lambda ts: pd.to_datetime(str(ts), format="%Y%m%d%H%M%S").strftime("%Y-%m-%d")

captures = pd.read_csv(DATA / "page_captures.csv")
cities = pd.read_csv(DATA / "page_cities.csv")
changes = pd.read_csv(DATA / "status_changes.csv")

latest = cities[cities.timestamp == captures.timestamp.max()]
out = []
for r in latest.itertuples():
    ch = changes[(changes.city_id == r.city_id) & (changes.status_to == r.status)].iloc[-1]
    out.append(dict(city_id=r.city_id, name=r.name, metro=metro_of(r.name), status=r.status, since=ch.date,
                    window_start=None if pd.isna(ch.window_start) else ch.window_start))

json.dump({"first_capture": day(captures.timestamp.min()), "last_capture": day(captures.timestamp.max()),
           "cities_from": day(captures[captures.n_cities > 0].timestamp.min()), "cities": out}, sys.stdout)
