"""Step 4: figures from waymo_service_areas.gpkg.

figures/area_over_time.png   service area (sq mi) per metro, small multiples
figures/total_area.png       summed area of all metros on the page
figures/maps_<metro>.png     every version of a metro's service area overlaid
"""
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

ROOT = Path(__file__).parent
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = "#2a78d6"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def step_series(ts, end):
    ts = ts.sort_values("date")
    x = list(ts.date) + [end]
    y = list(ts.area_mi2) + [ts.area_mi2.iloc[-1]]
    return x, y


def area_small_multiples(TS, end):
    metros = (TS.groupby("metro").date.min().sort_values().index.tolist())
    n = len(metros)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(12, 2.3 * rows + 0.6), sharex=True)
    ymax = TS.area_mi2.max() * 1.15
    for ax, m in zip(axes.flat, metros):
        t = TS[TS.metro == m]
        # break the line where a metro is absent from the page (e.g. Austin gap)
        x, y = step_series(t, t.date.max())
        ax.step(x, y, where="post", color=SERIES, lw=2)
        ch = t[t.area_mi2.diff().fillna(1) != 0]
        ax.plot(ch.date, ch.area_mi2, "o", ms=4, color=SERIES, mec=SURFACE, mew=1.5)
        last = t.iloc[-1]
        ax.annotate(f"{last.area_mi2:,.0f}", (last.date, last.area_mi2), xytext=(4, 4),
                    textcoords="offset points", fontsize=8, color=INK)
        ax.set_title(m, loc="left", fontsize=10, color=INK)
        ax.set_ylim(0, ymax)
        ax.set_xlim(TS.date.min(), end)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("sq mi")
    for ax in axes.flat:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.suptitle("Waymo service area by metro (traced from support.google.com/waymo/answer/9059119, "
                 "via archive.org)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "area_over_time.png", dpi=150)
    plt.close(fig)


def total_area(TS):
    tot = TS.groupby("date").area_mi2.sum().reset_index()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.step(tot.date, tot.area_mi2, where="post", color=SERIES, lw=2)
    last = tot.iloc[-1]
    ax.annotate(f"{last.area_mi2:,.0f} sq mi", (last.date, last.area_mi2),
                xytext=(-4, 6), textcoords="offset points", ha="right", fontsize=9)
    ax.set_ylabel("sq mi")
    ax.set_ylim(0, tot.area_mi2.max() * 1.12)
    ax.set_title("Total Waymo service area across all metros on the help pages",
                 loc="left", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout()
    fig.savefig(FIG / "total_area.png", dpi=150)
    plt.close(fig)


def metro_maps(MV):
    import georef as G
    from importlib import import_module
    METROS = import_module("02_georeference").METROS
    for metro, g in MV.groupby("metro"):
        g = g.sort_values("valid_from").to_crs(3857)
        k = len(g)
        idx = np.linspace(0, len(SEQ) - 1, k).round().astype(int) if k > 1 else [4]
        cols = [SEQ[i] for i in idx]
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.grid(False)
        # roads for context
        lat, lon, rad = METROS[metro]
        f = G.OSM_DIR / f"{metro.replace(' ', '_').lower()}_{rad}km.json"
        if f.exists():
            for xy, cls in G.osm_roads(metro.replace(" ", "_").lower(), lat, lon, rad):
                if cls in ("motorway", "trunk"):
                    ax.plot(xy[:, 0], xy[:, 1], color="#c9c8c3", lw=0.5, zorder=1)
        # newest at the bottom, oldest on top -> growth reads as rings
        for (_, r), c in reversed(list(zip(g.iterrows(), cols))):
            gpd.GeoSeries([r.geometry], crs=3857).plot(ax=ax, color=c, edgecolor=SURFACE,
                                                       linewidth=0.8, zorder=2)
        b = g.total_bounds
        pad = 0.08 * max(b[2] - b[0], b[3] - b[1])
        ax.set_xlim(b[0] - pad, b[2] + pad)
        ax.set_ylim(b[1] - pad, b[3] + pad)
        ax.set_axis_off()
        handles = [Patch(facecolor=c, edgecolor="none",
                         label=f"{r.valid_from}  ({r.area_mi2:,.0f} sq mi)")
                   for (_, r), c in zip(g.iterrows(), cols)]
        ax.legend(handles=handles, title="first seen", loc="lower left", fontsize=8,
                  title_fontsize=8, frameon=True, facecolor=SURFACE, edgecolor=GRID)
        ax.set_title(f"{metro}: Waymo service area versions", loc="left", fontsize=11)
        fig.tight_layout()
        fig.savefig(FIG / f"maps_{metro.replace(' ', '_')}.png", dpi=130)
        plt.close(fig)


def main():
    TS = pd.read_csv(ROOT / "data" / "area_timeseries.csv", parse_dates=["date"])
    MV = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="metro_versions")
    end = TS.date.max()
    area_small_multiples(TS, end)
    total_area(TS)
    metro_maps(MV)
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
