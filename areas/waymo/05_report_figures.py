"""Step 5: exploratory statistics and SVG figures for report.md.

Writes figures/report/*.svg and data/report_stats.json.
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pyproj import Geod

ROOT = Path(__file__).parent
OUT = ROOT / "figures" / "report"
OUT.mkdir(parents=True, exist_ok=True)
GEOD = Geod(ellps="WGS84")
MI2 = 2.589988110336e6  # m2 per sq mi

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ORIGINAL = ["Phoenix", "San Francisco", "Los Angeles"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "svg.fonttype": "none", "font.family": "DejaVu Sans",
})


def mi2(g):
    return 0.0 if g is None or g.is_empty else abs(GEOD.geometry_area_perimeter(g)[0]) / MI2


def load():
    mv = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="metro_versions")
    v = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="versions")
    for df in (mv, v):
        for c in ("valid_from", "valid_to"):
            df[c] = pd.to_datetime(df[c])
    ts = pd.read_csv(ROOT / "data" / "area_timeseries.csv", parse_dates=["date"])
    return mv.sort_values(["metro", "valid_from"]), v, ts


def expansion_events(mv):
    rows = []
    for m, g in mv.groupby("metro"):
        prev = None
        for _, r in g.iterrows():
            if prev is None:
                rows.append(dict(metro=m, date=r.valid_from, kind="launch", added=r.area_mi2,
                                 removed=0.0, before=0.0, after=r.area_mi2))
            else:
                rows.append(dict(metro=m, date=r.valid_from, kind="expansion",
                                 added=mi2(r.geometry.difference(prev.geometry)),
                                 removed=mi2(prev.geometry.difference(r.geometry)),
                                 before=prev.area_mi2, after=r.area_mi2))
            prev = r
    return pd.DataFrame(rows)


def daily_total(ts, end):
    """Total area per day (carry each metro's last known area forward)."""
    w = ts.pivot_table(index="date", columns="metro", values="area_mi2", aggfunc="last")
    # run a few days past the last snapshot so a step plot shows the last change
    w = w.reindex(pd.date_range(w.index.min(), end + pd.Timedelta(days=30), freq="D")).ffill()
    return w


# ---------------------------------------------------------------- figures

def _shades(c_light, c_dark, n):
    """n colours from light to dark, interleaved so neighbouring bands differ."""
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("r", [c_light, c_dark])
    ramp = [cm(t) for t in (np.linspace(0, 1, n) if n > 1 else [0.6])]
    half = (n + 1) // 2  # alternate light half / dark half
    return [ramp[i // 2] if i % 2 == 0 else ramp[half + i // 2] for i in range(n)]


def fig_total(W, ylabel="sq mi", total_fmt="{:,.0f} sq mi total", fmt="{:,.0f}",
              title="Total Waymo service area, by metro", fname="total_area.svg"):
    """Stacked area per metro: original three in blues, newer metros in oranges."""
    first = {m: W[m].first_valid_index() for m in W.columns}
    newer = sorted((m for m in W.columns if m not in ORIGINAL), key=lambda m: first[m])
    orig = sorted(ORIGINAL, key=lambda m: first[m])
    order = orig + newer
    colors = _shades("#9ec5f4", "#0d366b", len(orig)) + _shades("#fbd0b9", "#a83a10", len(newer))
    D = W[order].fillna(0)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.stackplot(D.index, *[D[m] for m in order], colors=colors, step="post",
                 edgecolor=SURFACE, linewidth=0.5)
    end = D.index[-1]
    total = D.iloc[-1].sum()
    ax.annotate(total_fmt.format(total), (end, total), xytext=(-4, 6),
                textcoords="offset points", ha="right", fontsize=9, fontweight="bold")
    # direct labels at the right edge, nudged apart so they don't overlap
    tops = D.iloc[-1].cumsum()
    mids = (tops - D.iloc[-1] / 2)[order].values
    gap = total * 0.032
    ys = mids.copy()
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + gap)
    over = ys[-1] - (total - gap / 2)
    if over > 0:  # push back down, keeping spacing
        ys -= over
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - gap)
    for m, y_mid, y_lab, c in zip(order, mids, ys, colors):
        ax.annotate(f"{m}  {fmt.format(D[m].iloc[-1])}", (end, y_mid), xytext=(end + pd.Timedelta(days=40), y_lab),
                    textcoords="data", va="center", fontsize=7.5, color=INK, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.5, shrinkA=0, shrinkB=0))
    ax.set_ylabel(ylabel)
    ax.set_xlim(D.index[0], end)
    ax.set_ylim(0, total * 1.08)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(handles=[Patch(color=colors[1], label="Phoenix, SF Bay Area, LA"),
                       Patch(color=colors[len(orig) + 3], label="12 newer metros")],
              loc="upper left", frameon=False)
    ax.set_title(title, loc="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 0.83, 1))
    fig.savefig(OUT / fname)
    plt.close(fig)


def fig_timeline(E, end):
    order = E[E.kind == "launch"].sort_values("date", ascending=False).metro.tolist()
    y = {m: i for i, m in enumerate(order)}
    fig, ax = plt.subplots(figsize=(8, 5.2))
    for m in order:
        e = E[E.metro == m]
        ax.plot([e.date.min(), end], [y[m]] * 2, color=GRID, lw=2, solid_capstyle="round", zorder=1)
    s = lambda a: 12 + a * 2.2  # marker area ~ sq mi
    la = E[E.kind == "launch"]; ex = E[E.kind == "expansion"]
    ax.scatter(la.date, la.metro.map(y), s=s(la.added), color=ORANGE, edgecolor=SURFACE,
               linewidth=1.5, zorder=3)
    ax.scatter(ex.date, ex.metro.map(y), s=s(ex.added), color=BLUE, edgecolor=SURFACE,
               linewidth=1.5, zorder=3)
    for m in order:
        cur = E[E.metro == m].after.iloc[-1]
        ax.annotate(f"{cur:,.0f}", (end, y[m]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(order)), order)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(pd.Timestamp("2024-01-01"), end + pd.Timedelta(days=10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    leg = [Line2D([], [], marker="o", ls="", color=ORANGE, ms=8, label="first map (launch on page)"),
           Line2D([], [], marker="o", ls="", color=BLUE, ms=8, label="expansion")]
    leg += [Line2D([], [], marker="o", ls="", color=INK2, ms=np.sqrt(s(a)), label=f"{a} sq mi added")
            for a in (25, 100)]
    ax.legend(handles=leg, loc="lower left", frameon=False, fontsize=8)
    ax.set_title("Launches and expansions (right: current sq mi)", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "timeline.svg")
    plt.close(fig)


def fig_launch_vs_now(E):
    la = E[E.kind == "launch"].set_index("metro")
    now = E.groupby("metro").after.last()
    d = la.assign(now=now).sort_values("date")
    fig, ax = plt.subplots(figsize=(8, 4.6))
    yy = np.arange(len(d))[::-1]
    for yi, (_, r) in zip(yy, d.iterrows()):
        ax.plot([r.added, r.now], [yi, yi], color=GRID, lw=3, zorder=1, solid_capstyle="round")
    ax.scatter(d.added, yy, color=ORANGE, s=50, zorder=3, edgecolor=SURFACE, linewidth=1.5,
               label="at launch")
    ax.scatter(d.now, yy, color=BLUE, s=50, zorder=3, edgecolor=SURFACE, linewidth=1.5, label="now")
    for yi, (m, r) in zip(yy, d.iterrows()):
        if r.now / r.added >= 1.5:
            ax.annotate(f"×{r.now / r.added:.1f}", (r.now, yi), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=8, color=INK2)
    ax.set_yticks(yy, [f"{m}  ({r.date:%b %Y})" for m, r in d.iterrows()])
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("sq mi")
    ax.set_xlim(0, d.now.max() * 1.12)
    ax.legend(loc="lower right", frameon=False)
    ax.set_title("Service area at launch vs now (metros in order of launch)", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "launch_vs_now.svg")
    plt.close(fig)


def fig_same_scale(mv):
    """All current service areas, drawn at the same scale."""
    cur = mv[mv.valid_to.isna()].copy()
    cur = cur.sort_values("area_mi2", ascending=False)
    n, cols = len(cur), 5
    rows = int(np.ceil(n / cols))
    half = 46_000  # metres; fixed window so all panels share one scale
    fig, axes = plt.subplots(rows, cols, figsize=(10, 2.25 * rows))
    for ax, (_, r) in zip(axes.flat, cur.iterrows()):
        g = gpd.GeoSeries([r.geometry], crs=4326)
        c = g.to_crs(4326).centroid.iloc[0]
        lcc = f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +units=m"  # local, true-scale
        gl = g.to_crs(lcc).simplify(30)
        gl.plot(ax=ax, color=BLUE, edgecolor="none")
        ax.set_xlim(-half, half); ax.set_ylim(-half, half)
        ax.set_aspect("equal"); ax.set_axis_off()
        ax.set_title(f"{r.metro}\n{r.area_mi2:,.0f} sq mi", fontsize=8.5, loc="left")
    for ax in axes.flat[n:]:
        ax.set_axis_off()
    # scale bar on the last used panel
    ax = axes.flat[n - 1]
    ax.plot([-half * 0.9, -half * 0.9 + 20000], [-half * 0.9] * 2, color=INK, lw=2)
    ax.text(-half * 0.9, -half * 0.8, "20 km", fontsize=8)
    fig.suptitle("Current service areas at the same scale", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "same_scale.svg")
    plt.close(fig)


def fig_growth_grid(mv, end):
    """Service area over time per metro, every panel on the same axes."""
    end = end + pd.Timedelta(days=30)  # room to see the latest jump
    steps = {}
    for m, g in mv.sort_values("valid_from").groupby("metro"):
        x = list(g.valid_from) + [end]
        y = list(g.area_mi2) + [g.area_mi2.iloc[-1]]
        steps[m] = (x, y)
    order = sorted(steps, key=lambda m: -steps[m][1][-1])
    ncols = 5
    nrows = int(np.ceil(len(order) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(10, 2.0 * nrows + 0.6),
                             sharex=True, sharey=True)
    x0 = pd.Timestamp("2024-01-01")
    ymax = max(y[-1] for _, y in steps.values()) * 1.18
    for ax, m in zip(axes.flat, order):
        for o in order:  # all other metros as faint context
            if o != m:
                ax.step(*steps[o], where="post", color=GRID, lw=0.9, zorder=1)
        x, y = steps[m]
        ax.fill_between(x, y, step="post", color=BLUE, alpha=0.18, lw=0, zorder=2)
        ax.step(x, y, where="post", color=BLUE, lw=1.8, zorder=3)
        ax.plot(x[0], y[0], "o", color=ORANGE, ms=4.5, mec=SURFACE, mew=1, zorder=4)
        ax.annotate(f"{y[-1]:,.0f}", (x[-1], y[-1]), xytext=(-2, 4), textcoords="offset points",
                    ha="right", va="bottom", fontsize=8, color=INK, fontweight="bold")
        ax.set_title(m, loc="left", fontsize=9)
        ax.grid(axis="x", visible=False)
        ax.set_xlim(x0, end); ax.set_ylim(0, ymax)
        ax.set_yticks([0, 100, 200, 300])
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.tick_params(length=0, labelsize=8)
    for ax in axes.flat[len(order):]:
        ax.set_axis_off()
    for ax in axes[:, 0]:
        ax.set_ylabel("sq mi")
    fig.legend(handles=[Line2D([], [], color=BLUE, lw=1.8, label="service area"),
                        Line2D([], [], marker="o", ls="", color=ORANGE, ms=5, label="first map"),
                        Line2D([], [], color=GRID, lw=1.2, label="other metros")],
               loc="upper right", ncols=3, frameon=False, fontsize=8)
    fig.suptitle("Service area over time, all metros on the same scale",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "growth_grid.svg")
    plt.close(fig)


# a few reference places (lon, lat) so readers can orient themselves
PLACES = {
    "San Francisco": {"San Francisco": (-122.44, 37.76), "San Mateo": (-122.31, 37.56),
                      "Palo Alto": (-122.14, 37.44), "San José": (-121.89, 37.335)},
    "Los Angeles": {"Santa Monica": (-118.49, 34.02), "Downtown": (-118.25, 34.05),
                    "LAX": (-118.41, 33.94), "Torrance": (-118.34, 33.835)},
}


def add_basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, crs=3857, source=cx.providers.Esri.WorldGrayCanvas,
                       attribution=False, zorder=0)
    except Exception as e:  # offline: draw without basemap
        print(f"basemap skipped: {e}")


def fig_versions_map(mv, metro, fname, ncols=3):
    """One panel per service-area version: earlier area in blue, newly added area in orange."""
    g = mv[mv.metro == metro].sort_values("valid_from").to_crs(3857).reset_index(drop=True)
    g["geometry"] = g.geometry.simplify(25)
    x0, y0, x1, y1 = g.total_bounds
    pad = 0.06 * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    n = len(g)
    nrows = int(np.ceil(n / ncols))
    w = 10 / ncols
    h = w * (y1 - y0) / (x1 - x0) + 0.45  # room for the panel title
    fig, axes = plt.subplots(nrows, ncols, figsize=(10, h * nrows + 0.5))
    places = gpd.GeoSeries(gpd.points_from_xy(*zip(*PLACES[metro].values())), crs=4326).to_crs(3857)
    for i, (ax, (_, r)) in enumerate(zip(axes.flat, g.iterrows())):
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        add_basemap(ax)
        prev = g.geometry.iloc[i - 1] if i else None
        if prev is not None:
            kept = r.geometry.intersection(prev)
            added = r.geometry.difference(prev)
            gpd.GeoSeries([kept], crs=3857).plot(ax=ax, color=BLUE, alpha=0.55, zorder=2)
        else:
            added = r.geometry
        gpd.GeoSeries([added], crs=3857).plot(ax=ax, color=ORANGE, zorder=3)
        if prev is not None:  # anything dropped from the previous version
            lost = prev.difference(r.geometry)
            if mi2(gpd.GeoSeries([lost], crs=3857).to_crs(4326).iloc[0]) > 0.5:
                gpd.GeoSeries([lost], crs=3857).plot(ax=ax, facecolor="none", edgecolor=INK2,
                                                     linewidth=0.6, linestyle=(0, (2, 1.5)), zorder=3)
        gpd.GeoSeries([r.geometry], crs=3857).boundary.plot(ax=ax, color=INK, linewidth=0.4, zorder=4)
        if i == n - 1:  # orientation labels on the latest map
            for (name, _), pt in zip(PLACES[metro].items(), places):
                ax.plot(pt.x, pt.y, "o", ms=2.5, color=INK, zorder=5)
                ax.annotate(name, (pt.x, pt.y), xytext=(4, 2), textcoords="offset points",
                            fontsize=7, color=INK, zorder=5,
                            bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec="none", alpha=0.75))
        delta = "" if prev is None else f"  +{r.area_mi2 - g.area_mi2.iloc[i - 1]:,.0f}"
        ax.set_title(f"{r.valid_from:%b} {r.valid_from.day} {r.valid_from.year}", loc="left", fontsize=9, fontweight="bold")
        ax.set_title(f"{r.area_mi2:,.0f} sq mi{delta}", loc="right", fontsize=8, color=INK2)
        ax.set_aspect("equal"); ax.set_axis_off()
    for ax in axes.flat[n:]:
        ax.set_axis_off()
    fig.legend(handles=[Patch(color=ORANGE, label="new in this version"),
                        Patch(color=BLUE, alpha=0.55, label="already served")],
               loc="upper right", ncols=2, frameon=False, fontsize=8)
    fig.suptitle(f"{metro}: how the service area grew", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / fname, dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------ stats

def stats(mv, v, ts, E, W):
    W = W[W.index <= ts.date.max()]  # drop the plotting padding
    tot = W.sum(axis=1)
    t0, t1 = tot.index[0], tot.index[-1]
    yrs = (t1 - t0).days / 365.25
    growth = (tot.iloc[-1] / tot.iloc[0]) ** (1 / yrs)
    by_year = {str(y): int(tot[tot.index.year == y].iloc[-1]) for y in sorted(set(tot.index.year))}
    ex = E[E.kind == "expansion"]
    la = E[E.kind == "launch"]
    cur = mv[mv.valid_to.isna()].copy()
    cur_l = cur.to_crs(6933)
    cur["compactness"] = (4 * np.pi * cur_l.area / cur_l.length ** 2).values
    gradual = v[v.valid_to.isna() & v.note.str.contains("radually", na=False)]
    orig_share = (W[ORIGINAL].sum(axis=1) / tot)
    return {
        "first_date": str(t0.date()), "last_date": str(t1.date()),
        "total_first": round(tot.iloc[0]), "total_now": round(tot.iloc[-1]),
        "growth_factor": round(tot.iloc[-1] / tot.iloc[0], 1),
        "annual_growth_factor": round(growth, 2),
        "doubling_months": round(12 * np.log(2) / np.log(growth), 1),
        "total_end_of_year": by_year,
        "launches_per_year": la.groupby(la.date.dt.year).size().to_dict(),
        "expansions_per_year": ex.groupby(ex.date.dt.year).size().to_dict(),
        "n_expansions": len(ex),
        "added_by_expansions": round(ex.added.sum()), "removed_by_expansions": round(ex.removed.sum(), 1),
        "max_removed_single": ex.loc[ex.removed.idxmax(), ["metro", "removed"]].to_dict(),
        "top_expansions": ex.nlargest(8, "added")[["metro", "date", "before", "after", "added"]]
            .assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).round(1).to_dict("records"),
        "launch_size_median_2026": round(la[la.date.dt.year == 2026].added.median(), 1),
        "launch_sizes": la.set_index("metro").added.round(1).to_dict(),
        "share_original_three_first": round(orig_share.iloc[0], 3),
        "share_original_three_now": round(orig_share.iloc[-1], 3),
        "current": cur.set_index("metro")[["area_mi2", "area_km2", "compactness"]]
            .sort_values("area_mi2", ascending=False).round(3).to_dict("index"),
        "gradual_now": gradual[["city", "area_mi2"]].round(1).to_dict("records"),
        "median_days_between_expansions": float(ex.sort_values("date").groupby("metro").date.diff()
                                                .dt.days.median()),
    }


def main():
    mv, v, ts, = load()
    end = ts.date.max()
    E = expansion_events(mv)
    W = daily_total(ts, end)
    fig_total(W)
    fig_timeline(E, end)
    fig_launch_vs_now(E)
    fig_same_scale(mv)
    fig_growth_grid(mv, end)
    fig_versions_map(mv, "San Francisco", "versions_san_francisco.svg")
    fig_versions_map(mv, "Los Angeles", "versions_los_angeles.svg")
    S = stats(mv, v, ts, E, W)
    (ROOT / "data" / "report_stats.json").write_text(json.dumps(S, indent=1, default=str))
    E.round(2).to_csv(ROOT / "data" / "expansion_events.csv", index=False)
    print(json.dumps(S, indent=1, default=str))


if __name__ == "__main__":
    main()
