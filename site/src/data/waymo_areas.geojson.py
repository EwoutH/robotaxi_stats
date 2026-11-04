"""Waymo service areas per metro and map version, as GeoJSON for the site."""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

WAYMO = Path(__file__).resolve().parents[3] / "areas" / "waymo"

mv = gpd.read_file(WAYMO / "waymo_service_areas.gpkg", layer="metro_versions")
pop = pd.read_csv(WAYMO / "data" / "population_versions.csv")
mv = mv.merge(pop[["metro", "valid_from", "pop"]], on=["metro", "valid_from"], how="left")

# Boundaries are accurate to roughly 50-300 m, so ~10 m simplification loses nothing.
mv["geometry"] = shapely.set_precision(mv.geometry.simplify(0.0001), 1e-5)
mv["pop"] = mv["pop"].round(-2)
mv = mv[["metro", "valid_from", "valid_to", "area_mi2", "pop", "geometry"]].sort_values(["metro", "valid_from"])

sys.stdout.write(mv.to_json(drop_id=True, na="null"))
