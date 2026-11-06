"""Tesla Robotaxi service areas per metro and boundary version, as GeoJSON for the site (format: contract.py).

Only cities tesla.com lists as open, from the date it first listed them (tesla_open.py).

Extra properties: city (Tesla's name, e.g. "Bay Area"), date_kind (announced, first_seen, or opened when cut to the open date), source, source_url.
"""
import shapely

from contract import write_areas
from tesla_open import open_versions

v, _ = open_versions()
v["geometry"] = shapely.set_precision(v.geometry, 1e-5)
v = v[["metro", "city", "valid_from", "valid_to", "date_kind", "source", "source_url", "area_mi2", "geometry"]]

write_areas(v.sort_values(["metro", "valid_from"]), "tesla")
