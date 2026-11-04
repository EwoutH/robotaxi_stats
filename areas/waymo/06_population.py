"""Step 6: residents inside each service-area version (2020 Census blocks).

For every metro version and every expansion, sums the 2020 Census population of
the blocks inside the polygon. A block that crosses the boundary counts with the
share of its area inside (areal weighting). Density uses the blocks' land area
(ALAND20), so water drawn inside the service area doesn't dilute it.

Inputs (downloaded once into raw/census/, ~2.6 GB, see README):
  tl_2020_<state>_tabblock20.zip   2020 blocks with POP20, HOUSING20, ALAND20
  tl_2023_us_uac20.zip             2020 Census Urban Areas (polygons)

Outputs:
  data/population_versions.csv     population per metro version (+-150 m band)
  data/population_events.csv       residents and density added per launch/expansion
  data/population_timeseries.csv   residents served per metro per snapshot date
  data/population_density_deciles.csv  share covered per density decile of the urban area
  data/population_stats.json       numbers for report.md
  figures/report/people_*.svg, density_*.svg
"""
import json
import sys
from importlib import import_module
from pathlib import Path

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).parent))
R = import_module("05_report_figures")  # style, colours, helpers
METROS = import_module("02_georeference").METROS

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CENSUS = ROOT / "raw" / "census"
OUT = R.OUT
KM2_PER_MI2 = 2.589988110336
BAND_M = 150  # boundary error used for the low/high band (README: 50-300 m)
UA_MIN_SHARE = 0.10  # an Urban Area counts as "the metro's" if it holds >=10% of residents served now
TIGER = "https://www2.census.gov/geo/tiger"

STATE = {"Phoenix": "04", "San Francisco": "06", "Los Angeles": "06", "San Diego": "06",
         "Austin": "48", "Dallas": "48", "Houston": "48", "San Antonio": "48",
         "Atlanta": "13", "Miami": "12", "Orlando": "12", "Tampa": "12",
         "Denver": "08", "Las Vegas": "32", "Nashville": "47",
         "Washington DC": "11", "Detroit": "26", "New Orleans": "22"}
BLOCK_COLS = ["GEOID20", "POP20", "HOUSING20", "ALAND20", "AWATER20", "INTPTLAT20", "INTPTLON20"]


# ---------------------------------------------------------------- census data

def _need(path, url):
    if not path.exists():
        raise SystemExit(f"Missing {path}. Download it first:\n  curl -o {path} {url}")


def urban_areas():
    f = CENSUS / "tl_2023_us_uac20.zip"
    _need(f, f"{TIGER}/TIGER2023/UAC/tl_2023_us_uac20.zip")
    return gpd.read_file(f, columns=["UACE20", "NAME20"])


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
    """Blocks within the metro's search radius, plus all blocks of its Urban Area(s)."""
    fips = STATE[metro]
    if fips not in cache_states:
        cache_states[fips] = state_blocks(fips, ua)
    sb = cache_states[fips]
    lat, lon, rad_km = METROS[metro]
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
    names = ua.set_index("UACE20").NAME20
    return B, crs, [names.get(u, u) for u in uas]


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


# ---------------------------------------------------------------- tables

def compute(mv):
    ua = urban_areas()
    states, vers, events, deciles, meta = {}, [], [], [], {}
    for metro, g in mv.groupby("metro"):
        g = g.sort_values("valid_from")
        if metro not in STATE:
            raise SystemExit(f"Add {metro} to STATE (state FIPS code) in 06_population.py")
        print(metro, flush=True)
        B, crs, ua_names = metro_blocks(metro, g.geometry.iloc[-1], ua, states)
        ua_pop = B.loc[B.in_metro_ua, "POP20"].sum()
        meta[metro] = dict(urban_areas=ua_names, urban_area_pop=int(ua_pop))
        geoms = g.to_crs(crs).geometry.make_valid().values
        prev = None
        for (_, r), geom in zip(g.iterrows(), geoms):
            s = summarise(cover_shares(geom, B), B)
            lo = summarise(cover_shares(geom.buffer(-BAND_M), B), B)["pop"]
            hi = summarise(cover_shares(geom.buffer(BAND_M), B), B)["pop"]
            vers.append(dict(metro=metro, valid_from=r.valid_from, valid_to=r.valid_to,
                             area_mi2=r.area_mi2, **s, pop_lo=lo, pop_hi=hi,
                             share_of_ua=s["pop_in_metro_ua"] / ua_pop))
            added = geom if prev is None else geom.difference(prev)
            removed = None if prev is None else prev.difference(geom)
            a = summarise(cover_shares(added, B), B)
            events.append(dict(metro=metro, date=r.valid_from,
                               kind="launch" if prev is None else "expansion",
                               area_added_mi2=shapely.area(added) / 1e6 / KM2_PER_MI2,
                               pop_added=a["pop"], land_added_mi2=a["land_mi2"],
                               density_added_mi2=a["density_mi2"],
                               pw_density_added_mi2=a["pw_density_mi2"],
                               pop_removed=summarise(cover_shares(removed, B), B)["pop"]))
            prev = geom
        # coverage by density decile of the metro's Urban Area (current version)
        share = cover_shares(geoms[-1], B)
        U = B[B.in_metro_ua].assign(cov=(B.POP20 * share)[B.in_metro_ua])
        bg = U.groupby("bg").agg(pop=("POP20", "sum"), cov=("cov", "sum"), d=("bg_density_mi2", "first"))
        bg = bg[bg["pop"] > 0].sort_values("d")
        # deciles hold 10% of the Urban Area's residents each, least to most dense
        bg["decile"] = np.minimum((bg["pop"].cumsum() / bg["pop"].sum() * 10 - 1e-9).astype(int) + 1, 10)
        for d, x in bg.groupby("decile"):
            deciles.append(dict(metro=metro, decile=d, pop=x["pop"].sum(), covered=x["cov"].sum(),
                                share_covered=x["cov"].sum() / x["pop"].sum(),
                                density_min=x.d.min(), density_max=x.d.max()))
    return pd.DataFrame(vers), pd.DataFrame(events), pd.DataFrame(deciles), meta


def timeseries(V, ts):
    rows = []
    for _, t in ts.iterrows():
        v = V[(V.metro == t.metro) & (V.valid_from <= t.date)
              & (V.valid_to.isna() | (V.valid_to > t.date))]
        if len(v):
            v = v.iloc[-1]
            rows.append(dict(date=t.date, metro=t.metro, pop=v["pop"], pop_lo=v.pop_lo,
                             pop_hi=v.pop_hi, area_mi2=t.area_mi2, land_mi2=v.land_mi2))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- figures

def fig_people_vs_area(cur):
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    xs = np.array([10, 600])
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(18, 500)
    ax.set_ylim(0.04, 3.5)
    for d, x in ((2000, 260), (5000, 230), (10000, 80)):
        ax.plot(xs, xs * d / 1e6, color=R.GRID, lw=1, zorder=0)
        p0, p1 = ax.transData.transform([(x, x * d / 1e6), (x * 2, x * 2 * d / 1e6)])
        ang = np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0]))
        ax.text(x, x * d / 1e6 * 1.06, f"{d:,} / sq mi", rotation=ang, rotation_mode="anchor",
                ha="center", va="bottom", fontsize=7, color=R.INK2)
    for _, r in cur.iterrows():
        c = R.BLUE if r.metro in R.ORIGINAL else R.ORANGE
        ax.errorbar(r.area_mi2, r["pop"] / 1e6, yerr=[[(r["pop"] - r.pop_lo) / 1e6], [(r.pop_hi - r["pop"]) / 1e6]],
                    fmt="o", color=c, ms=5, elinewidth=0.8, capsize=0)
        ax.annotate(r.metro, (r.area_mi2, r["pop"] / 1e6), textcoords="offset points",
                    xytext=(5, -9) if r.metro == "Dallas" else (5, 2),
                    fontsize=7.5)
    ax.set_xticks([20, 50, 100, 200, 400], ["20", "50", "100", "200", "400"])
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1, 2], ["0.05", "0.1", "0.2", "0.5", "1", "2"])
    ax.minorticks_off()
    ax.set_xlabel("service area (sq mi)")
    ax.set_ylabel("residents (millions, 2020 Census)")
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=R.BLUE, label="Phoenix, SF Bay Area, LA"),
                       Line2D([], [], marker="o", ls="", color=R.ORANGE, label="newer metros")],
              loc="upper left", frameon=False)
    ax.set_title("Residents vs. area of each current service area", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "people_vs_area.svg")
    plt.close(fig)


def launch_vs_later(E):
    """Density at launch vs. all land added by later expansions combined."""
    ex = E[E.kind == "expansion"].groupby("metro")[["pop_added", "land_added_mi2"]].sum()
    la = E[E.kind == "launch"].set_index("metro")
    out = pd.DataFrame({"launch": la.density_added_mi2,
                        "later": ex.pop_added / ex.land_added_mi2,
                        "later_pop": ex.pop_added})
    return out.sort_values("launch")


def fig_density_added(E):
    L = launch_vs_later(E)
    fig, ax = plt.subplots(figsize=(7.5, 0.33 * len(L) + 1.3))
    y = np.arange(len(L))
    for i, (m, r) in enumerate(L.iterrows()):
        c = R.BLUE if m in R.ORIGINAL else R.ORANGE
        if pd.notna(r.later):
            ax.annotate("", (r.later, i), (r.launch, i),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=1.2, shrinkA=4, shrinkB=3))
            ax.plot(r.later, i, "o", color=c, ms=6)
        ax.plot(r.launch, i, "o", mfc=R.SURFACE, mec=c, mew=1.5, ms=7)
    ax.set_yticks(y, [m + (" *" if m in ("Phoenix", "San Francisco") else "") for m in L.index])
    ax.set_xscale("log")
    ax.set_xticks([2000, 5000, 10000, 20000], ["2,000", "5,000", "10,000", "20,000"])
    ax.minorticks_off()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("residents per sq mi of land")
    ax.legend(handles=[Line2D([], [], marker="o", ls="", mfc=R.SURFACE, mec=R.INK2, mew=1.5, label="launch area"),
                       Line2D([], [], marker="o", ls="", color=R.INK2, label="all later expansions combined")],
              loc="lower right", frameon=False, fontsize=8)
    ax.set_title("Launch areas are denser than what gets added later", loc="left", fontsize=11)
    fig.text(0.01, 0.01, "* first map in the archive (Feb 2024), not the actual launch",
             fontsize=7, color=R.INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "density_added.svg")
    plt.close(fig)


def fig_density_over_time(T, end):
    """Residents per sq mi of land, all service areas combined."""
    daily = lambda col: R.daily_total(T.drop(columns="area_mi2").assign(area_mi2=T[col]), end).sum(axis=1)
    d = daily("pop") / daily("land_mi2")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.step(d.index, d.values, where="post", color=R.BLUE, lw=1.8)
    ax.annotate(f"{d.iloc[-1]:,.0f}", (d.index[-1], d.iloc[-1]), xytext=(-2, 6),
                textcoords="offset points", ha="right", fontsize=9, fontweight="bold")
    ax.annotate(f"{d.iloc[0]:,.0f}", (d.index[0], d.iloc[0]), xytext=(2, 6),
                textcoords="offset points", fontsize=9, fontweight="bold")
    ax.set_ylim(0, d.max() * 1.15)
    ax.set_xlim(d.index[0], d.index[-1])
    ax.set_ylabel("residents per sq mi of land")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_title("Average density of all Waymo service areas combined", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "density_over_time.svg")
    plt.close(fig)
    return d


def fig_deciles(D, order):
    M = D.pivot(index="metro", columns="decile", values="share_covered").loc[order]
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(M) + 1.4))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", ["#f1f0ec"] + R.SEQ)
    ax.imshow(M.values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M.values[i, j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.55 else R.INK)
    ax.set_yticks(range(len(M)), M.index)
    ax.set_xticks(range(10), ["1\nleast\ndense"] + [str(i) for i in range(2, 10)] + ["10\nmost\ndense"])
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("density decile of the metro's Urban Area (each holds 10% of its residents)")
    ax.set_title("Share of each density decile inside the current service area", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "density_deciles.svg")
    plt.close(fig)


# ---------------------------------------------------------------- stats

def stats(V, E, D, T, W, meta):
    cur = V[V.valid_to.isna()].set_index("metro")
    tot = W.iloc[-1].sum()
    first = W.dropna(how="all").iloc[0]
    yr_ago = W.loc[W.index <= T.date.max() - pd.Timedelta(days=365)].iloc[-1].sum()
    orig = cur.index.isin(R.ORIGINAL)
    top = D[D.decile >= 9].groupby("metro").apply(lambda x: x.covered.sum() / x["pop"].sum())
    low = D[D.decile <= 5].groupby("metro").apply(lambda x: x.covered.sum() / x["pop"].sum())
    both = launch_vs_later(E).dropna()
    return {
        "residents_now_m": round(tot / 1e6, 2),
        "residents_now_band_m": [round(T[T.date == T.date.max()].pop_lo.sum() / 1e6, 2),
                                 round(T[T.date == T.date.max()].pop_hi.sum() / 1e6, 2)],
        "residents_first_snapshot_m": round(first.sum() / 1e6, 2),
        "first_snapshot_incomplete": "Phoenix" not in set(T[T.date == T.date.min()].metro),
        "residents_year_ago_m": round(yr_ago / 1e6, 2),
        "housing_units_now_m": round(cur.housing.sum() / 1e6, 2),
        "share_original_three_now": round(cur[orig]["pop"].sum() / cur["pop"].sum(), 3),
        "density_now_mi2": round(cur["pop"].sum() / cur.land_mi2.sum()),
        "land_share_of_drawn_area": round(cur.land_mi2.sum() / cur.area_mi2.sum(), 3),
        "metros_launch_denser_than_later": f"{(both.launch > both.later).sum()} of {len(both)}",
        "launch_vs_later_density": both[["launch", "later"]].round(0).to_dict("index"),
        "current": cur.assign(
            pop_m=cur["pop"] / 1e6, top20_share=top, bottom50_share=low,
            urban_areas=pd.Series({m: "; ".join(meta[m]["urban_areas"]) for m in meta}),
            urban_area_pop_m=pd.Series({m: meta[m]["urban_area_pop"] / 1e6 for m in meta}))
            [["pop_m", "area_mi2", "land_mi2", "density_mi2", "pw_density_mi2", "share_of_ua",
              "urban_area_pop_m", "top20_share", "bottom50_share", "urban_areas"]]
            .sort_values("pop_m", ascending=False).round(3).to_dict("index"),
        "biggest_expansions_by_residents": E.nlargest(8, "pop_added")
            [["metro", "date", "kind", "area_added_mi2", "pop_added", "density_added_mi2"]]
            .round(0).astype({"date": str}).to_dict("records"),
    }


def main():
    mv, _, ts = R.load()
    V, E, D, meta = compute(mv)
    T = timeseries(V, ts)
    W = R.daily_total(T.drop(columns="area_mi2").assign(area_mi2=T["pop"]), ts.date.max())
    R.fig_total(W / 1e6, ylabel="residents (millions, 2020 Census)", total_fmt="{:.1f} M residents",
                fmt="{:.2f}", title="Residents inside Waymo service areas, by metro",
                fname="people_served.svg")
    cur = V[V.valid_to.isna()]
    fig_people_vs_area(cur)
    fig_density_added(E)
    fig_density_over_time(T, ts.date.max())
    fig_deciles(D, cur.sort_values("pw_density_mi2", ascending=False).metro.tolist())
    S = stats(V, E, D, T, W, meta)
    V.round(4).to_csv(DATA / "population_versions.csv", index=False)
    E.round(2).to_csv(DATA / "population_events.csv", index=False)
    T.round(0).to_csv(DATA / "population_timeseries.csv", index=False)
    D.round(4).to_csv(DATA / "population_density_deciles.csv", index=False)
    (DATA / "population_stats.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps(S, indent=1, default=str))


if __name__ == "__main__":
    main()
