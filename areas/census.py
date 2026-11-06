"""2020 Census residents inside service areas, shared by the Waymo and Tesla population scripts.

Sums the 2020 Census population of the blocks inside a polygon. A block that crosses the boundary counts with the
share of its area inside (areal weighting). Density uses the blocks' land area (ALAND20), so water drawn inside the
service area doesn't dilute it.

Missing Census files are downloaded into areas/raw/census/ (~100-750 MB per state); each state is read once and
cached there as blocks_<fips>.parquet.

Use from a script one folder down (e.g. areas/tesla/):
    sys.path.insert(0, str(Path(__file__).parents[1]))
    import census
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

from metros import METROS

CENSUS = Path(__file__).parent / "raw" / "census"
KM2_PER_MI2 = 2.589988110336
UA_MIN_SHARE = 0.10  # an Urban Area counts as "the metro's" if it holds >=10% of residents served now
TIGER = "https://www2.census.gov/geo/tiger"

BLOCK_COLS = ["GEOID20", "POP20", "HOUSING20", "ALAND20", "AWATER20", "INTPTLAT20", "INTPTLON20"]


# ---------------------------------------------------------------- census data

def _need(path, url):
    """Download a Census file into raw/census/ if it isn't there yet."""
    if path.exists():
        return
    print(f"  downloading {url}", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)


def urban_areas():
    f = CENSUS / "tl_2023_us_uac20.zip"
    _need(f, f"{TIGER}/TIGER2023/UAC/tl_2023_us_uac20.zip")
    return gpd.read_file(f, columns=["UACE20"])


def state_blocks(fips, ua):
    """All blocks of a state with their 2020 Urban Area code, cached as GeoParquet."""
    cache = CENSUS / f"blocks_{fips}.parquet"
    if cache.exists():
        return gpd.read_parquet(cache)
    f = CENSUS / f"tl_2020_{fips}_tabblock20.zip"
    _need(f, f"{TIGER}/TIGER2020/TABBLOCK20/tl_2020_{fips}_tabblock20.zip")
    print(f"  reading {f.name}", flush=True)
    b = gpd.read_file(f, columns=BLOCK_COLS, engine="pyogrio")
    for c in ("POP20", "HOUSING20", "ALAND20", "AWATER20"):
        b[c] = pd.to_numeric(b[c])
    # Urban Areas are built from 2020 blocks, so the internal point decides membership
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(b.INTPTLON20.astype(float),
                                                       b.INTPTLAT20.astype(float)), crs=4326)
    j = gpd.sjoin(pts, ua.to_crs(4326)[["UACE20", "geometry"]], how="left", predicate="within")
    b["UACE20"] = j[~j.index.duplicated()].reindex(pts.index).UACE20.values
    b = b.drop(columns=["INTPTLAT20", "INTPTLON20"]).to_crs(4326)
    b.to_parquet(cache)
    return b


def metro_blocks(metro, current_geom, ua, cache_states):
    """Blocks within the metro's search radius, plus all blocks of its Urban Area(s).

    current_geom (EPSG:4326) is the area served now; it picks the metro's Urban Areas. cache_states holds the states
    read so far ({fips: blocks}) and is filled as needed. Returns the blocks and the projected CRS they are in.
    """
    m = METROS[metro]
    fips, lat, lon, rad_km = m["state_fips"], m["lat"], m["lon"], m["radius_km"]
    if fips not in cache_states:
        cache_states[fips] = state_blocks(fips, ua)
    sb = cache_states[fips]
    crs = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).estimate_utm_crs()
    centre = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).to_crs(crs).iloc[0]
    sbp = sb.to_crs(crs)
    near = sbp[sbp.intersects(centre.buffer(rad_km * 1000))]
    # which Urban Areas does the current service area mostly serve?
    cur = gpd.GeoSeries([current_geom], crs=4326).to_crs(crs).iloc[0]
    sh = cover_shares(cur, near)
    by_ua = (near.POP20 * sh).groupby(near.UACE20).sum()
    uas = by_ua[by_ua >= UA_MIN_SHARE * by_ua.sum()].index.tolist()
    B = pd.concat([near, sbp[sbp.UACE20.isin(uas) & ~sbp.index.isin(near.index)]])
    B["in_metro_ua"] = B.UACE20.isin(uas)
    # block-group density, for the "how urban is it" measures
    B["bg"] = B.GEOID20.str[:12]
    g = B.groupby("bg")[["POP20", "ALAND20"]].transform("sum")
    B["bg_density_mi2"] = g.POP20 / (g.ALAND20 / 1e6 / KM2_PER_MI2).where(g.ALAND20 > 0)
    return B, crs


# ---------------------------------------------------------------- overlay

def cover_shares(geom, B):
    """Share of each block's area inside `geom` (both in the same projected CRS)."""
    share = np.zeros(len(B))
    if geom is None or geom.is_empty:
        return share
    idx = B.sindex.query(geom, predicate="intersects")
    if len(idx) == 0:
        return share
    shapely.prepare(geom)
    garr = np.asarray(B.geometry.values)
    g = garr[idx]
    inside = shapely.contains(geom, g)
    share[idx[inside]] = 1.0
    part = idx[~inside]
    if len(part):
        gp = garr[part]
        a = shapely.area(gp)
        share[part] = np.where(a > 0, shapely.area(shapely.intersection(gp, geom)) / a, 0.0)
    return np.clip(share, 0, 1)


def summarise(share, B):
    pop = B.POP20.values * share
    land_km2 = (B.ALAND20.values * share).sum() / 1e6
    p = pop.sum()
    dens = B.bg_density_mi2.fillna(0).values
    return dict(
        pop=p,
        housing=(B.HOUSING20.values * share).sum(),
        land_mi2=land_km2 / KM2_PER_MI2,
        density_mi2=p / (land_km2 / KM2_PER_MI2) if land_km2 > 0 else np.nan,
        # density the average resident lives at (block-group level); less sensitive
        # to empty land (parks, industrial, airports) inside the area
        pw_density_mi2=(pop * dens).sum() / p if p > 0 else np.nan,
        pop_in_metro_ua=pop[B.in_metro_ua.values].sum(),
        pop_urban=pop[B.UACE20.notna().values].sum(),
    )


def block_cover(share, B):
    """Census area (land and water, km²) of the blocks inside, to check a polygon lies within the loaded blocks."""
    return ((B.ALAND20.values + B.AWATER20.values) * share).sum() / 1e6
