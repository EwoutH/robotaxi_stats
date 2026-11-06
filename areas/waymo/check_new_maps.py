"""Automatic QA for newly georeferenced maps (run after steps 2 and 3).

Replaces looking at qa/ by eye for routine updates. A new map passes if
- its fit is good: `quality` >= MIN_QUALITY (correct fits score 0.5-0.95,
  modern 2400 px maps 0.7+; a wrong fit ~0.2-0.3), and
- for an existing metro, the new area covers most of the previous one
  (>= MIN_KEPT): service areas almost never shrink, while a misaligned fit
  lands kilometres off and overlaps little.

"New" = in data/georef_params.csv but not in the committed version (git HEAD),
or the image files given as arguments. Exits 1 if any map fails; then fix it by
hand as described in the README (data/manual_georef.csv).
"""
import io
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MIN_QUALITY = 0.6
MIN_KEPT = 0.9


def new_images():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    now = pd.read_csv(DATA / "georef_params.csv")
    old = subprocess.run(["git", "show", "HEAD:./data/georef_params.csv"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return sorted(set(now.image_file) - set(pd.read_csv(io.StringIO(old)).image_file))


def main():
    imgs = new_images()
    if not imgs:
        print("no new maps")
        return
    params = pd.read_csv(DATA / "georef_params.csv").set_index("image_file")
    mv = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="metro_versions")
    mv = mv.sort_values(["metro", "valid_from"]).to_crs(6933)  # equal-area
    failed = False
    for img in imgs:
        p = params.loc[img]
        msgs = [f"quality {p.quality:.2f}" + ("" if p.quality >= MIN_QUALITY or p.source == "manual"
                                              else f" < {MIN_QUALITY}: FAIL")]
        bad = p.quality < MIN_QUALITY and p.source != "manual"
        for _, g in mv.groupby("metro"):
            g = g.reset_index(drop=True)
            for i in g.index[g.images.str.split(";").map(lambda x: img in x)]:
                if i == 0:
                    msgs.append(f"first version of {g.metro[i]}")
                    continue
                prev, cur = g.geometry[i - 1], g.geometry[i]
                kept = prev.intersection(cur).area / prev.area
                ok = kept >= MIN_KEPT
                bad |= not ok
                msgs.append(f"{g.metro[i]} {g.valid_from[i]}: {cur.area / 2.59e6:.1f} sq mi "
                            f"(was {prev.area / 2.59e6:.1f}), keeps {kept:.0%} of previous area"
                            + ("" if ok else f" < {MIN_KEPT:.0%}: FAIL"))
        print(f"{'FAIL' if bad else 'ok  '} {img} {p.metro}: " + "; ".join(msgs))
        failed |= bad
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
