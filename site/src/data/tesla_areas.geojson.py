"""Tesla Robotaxi service areas per metro and boundary version, as GeoJSON for the site (format: contract.py).

Extra properties: city (Tesla's name, e.g. "Bay Area"), date_kind (announced or first_seen), source, source_url.
"""
import sys
from pathlib import Path

import geopandas as gpd
import shapely

from contract import write_areas

AREAS = Path(__file__).resolve().parents[3] / "areas"
sys.path.insert(0, str(AREAS))
from metros import metro_of  # noqa: E402

v = gpd.read_file(AREAS / "tesla" / "tesla_service_areas.geojson")
v["metro"] = [metro_of(c) or c for c in v.city]
v["geometry"] = shapely.set_precision(v.geometry, 1e-5)
v = v[["metro", "city", "valid_from", "valid_to", "date_kind", "source", "source_url", "area_mi2", "geometry"]]

write_areas(v.sort_values(["metro", "valid_from"]), "tesla")
