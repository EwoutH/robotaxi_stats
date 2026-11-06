"""Metro metadata shared by the Waymo and Tesla scripts, read from metros.csv.

One row per metro:
  metro       name used in every dataset
  state       state name (the site groups metros by it)
  state_fips  2-digit state FIPS code (Census blocks for the population step)
  lat, lon    approximate centre
  radius_km   search radius for the map fit and the population step
  geofabrik   Geofabrik extract with the metro's roads (raw/osm/pbf/<name>-latest.osm.pbf), may be empty
  aliases     other labels for the metro, separated by ";"

Row order matters: metro_of() returns the first metro whose name appears in a label.
Use from a script one folder down (e.g. areas/tesla/):
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from metros import METROS, metro_of
"""
import csv
from pathlib import Path

with open(Path(__file__).with_name("metros.csv"), newline="", encoding="utf-8") as f:
    METROS = {r["metro"]: dict(r, lat=float(r["lat"]), lon=float(r["lon"]), radius_km=int(r["radius_km"]),
                               aliases=[a for a in r["aliases"].split(";") if a])
              for r in csv.DictReader(f)}
ALIASES = {a: m for m, r in METROS.items() for a in r["aliases"]}


def metro_of(label):
    """Metro for a city label (e.g. "Silicon Valley" -> "San Francisco"), or None."""
    c = ALIASES.get(label, label)
    for k in METROS:
        if k.lower() in c.lower():
            return k
    return None
