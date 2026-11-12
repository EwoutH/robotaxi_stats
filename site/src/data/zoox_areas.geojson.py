"""Zoox service areas per metro and boundary version, as GeoJSON for the site (format: contract.py).

Extra properties: date_kind (announced or first_seen), source, source_url.
"""
from pathlib import Path

import geopandas as gpd
import shapely

from contract import write_areas

v = gpd.read_file(Path(__file__).resolve().parents[3] / "areas" / "zoox" / "zoox_service_areas.geojson")
v["geometry"] = shapely.set_precision(v.geometry, 1e-5)
v["pop"] = v["pop"].round(-2)
v = v[["metro", "valid_from", "valid_to", "date_kind", "source", "source_url", "area_mi2", "pop", "geometry"]]

write_areas(v.sort_values(["metro", "valid_from"]), "zoox")
