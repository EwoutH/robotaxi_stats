"""Daily check of the live Waymo help pages (run by .github/workflows/waymo_maps.yml).

Fetches today's live pages, parses them with the step 1 parser, and compares the
(city, note, map image) list with the last known state. On a change it saves:

  live/pages/<page>_<timestamp>.html.gz   the page as fetched
  live/images/<sha1>.png                  each map image not seen before
  live/changes.csv                        one row per added/changed/removed city
  live/state.json                         the current state, for the next check

and adds the capture to data/snapshot_images.csv and data/snapshot_sources.csv,
so steps 2-6 can run on the CI runner without the archived pages in raw/.
It also asks the Wayback Machine to capture the page and the new images.
01_fetch_snapshots.py reads live/ too, so a full local rebuild gives the same rows.

Unlike raw/, live/ is committed: the CI runner has no other place to keep files.
"""
import csv
import datetime
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
LIVE = ROOT / "live"
PAGES_DIR, IMAGES_DIR = LIVE / "pages", LIVE / "images"
STATE, CHANGES = LIVE / "state.json", LIVE / "changes.csv"

spec = importlib.util.spec_from_file_location("fetch", ROOT / "01_fetch_snapshots.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def initial_state():
    """Latest snapshot per page from data/snapshot_images.csv."""
    rows = list(csv.DictReader(open(ROOT / "data" / "snapshot_images.csv", encoding="utf-8")))
    state = {}
    for page in fetch.PAGES:
        prow = [r for r in rows if r["page"] == page]
        last = max(r["snapshot"] for r in prow)
        state[page] = sorted([r["city"], r["note"], r["image_file"]]
                             for r in prow if r["snapshot"] == last)
    return state


def known_images():
    rows = csv.DictReader(open(ROOT / "data" / "snapshot_images.csv", encoding="utf-8"))
    return {r["image_file"] for r in rows} | {p.name for p in IMAGES_DIR.glob("*")}


def wayback_save(url):
    """Ask the Wayback Machine to capture url. Uses SPN2 with keys if set
    (IA_ACCESS_KEY / IA_SECRET_KEY), otherwise the anonymous endpoint.
    Never raises: archiving is a bonus, not the point of the job."""
    key, secret = os.environ.get("IA_ACCESS_KEY"), os.environ.get("IA_SECRET_KEY")
    try:
        if key and secret:
            r = fetch.S.post("https://web.archive.org/save",
                             headers={"Accept": "application/json",
                                      "Authorization": f"LOW {key}:{secret}"},
                             data={"url": url, "skip_first_archive": "1"}, timeout=120)
            msg = r.json().get("job_id") or r.json().get("message", "") if r.ok else r.text[:200]
        else:
            r = fetch.S.get("https://web.archive.org/save/" + url, timeout=180)
            msg = r.headers.get("Content-Location", "")
        print(f"  wayback {r.status_code} {url} {msg}")
        return r.ok
    except Exception as e:  # noqa: BLE001
        print(f"  wayback failed {url}: {e}")
        return False


def record_capture(page, ts, cities, html):
    """Add one CI capture (cities: [city, note, image_file, image_url]) to the
    snapshot index and its sources, in the same form 01_fetch_snapshots.py writes."""
    date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    page_sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    index, sources = [], []
    for city, note, fname, url in cities:
        index.append(dict(page=page, snapshot=ts, date=date, city=city, note=note,
                          image_url=url, image_file=fname))
        img = fetch.IMG_DIR / fname if fname else None
        sources.append(dict(page=page, snapshot=ts, city=city, image_file=fname, page_mode="ci",
                            page_url=f"live/pages/{page}_{ts}.html.gz", page_sha256=page_sha,
                            image_url=url, image_capture=ts if fname else "",
                            image_sha256=hashlib.sha256(img.read_bytes()).hexdigest() if img else "",
                            retrieved_at=now if fname else ""))
    for name, rows in (("snapshot_images.csv", index), ("snapshot_sources.csv", sources)):
        path = ROOT / "data" / name
        with open(path, encoding="utf-8") as f:
            fields = next(csv.reader(f))
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writerows(rows)


def diff(old, new):
    """Rows (city, change, image_file) between two lists of [city, note, image_file]."""
    o, n = {}, {}
    for c, note, img in old:
        o.setdefault(c, set()).add((note, img))
    for c, note, img in new:
        n.setdefault(c, set()).add((note, img))
    out = []
    for c in sorted(o.keys() | n.keys()):
        if c not in o:
            out += [(c, "added", img) for _, img in n[c]]
        elif c not in n:
            out += [(c, "removed", img) for _, img in o[c]]
        elif {i for _, i in o[c]} != {i for _, i in n[c]}:
            out += [(c, "new map", img) for _, img in n[c] - o[c]]
        elif o[c] != n[c]:
            out.append((c, "text changed", ""))
    return out


def main():
    for d in (PAGES_DIR, IMAGES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else initial_state()
    seen = known_images()
    ts = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    changes, new_maps, to_archive = [], [], []

    for page, addr in fetch.PAGES.items():
        url = f"https://{addr}?hl=en"
        r = fetch.get(url)
        if r is None or r.status_code != 200:
            sys.exit(f"could not fetch {url}")
        cities = fetch.parse_cities(r.text)
        if not cities:
            sys.exit(f"no cities parsed from {url}: page layout changed? see README")
        current = []
        for city, note, img_url in cities:
            fname = ""
            if img_url:
                fname, _ = fetch.download_image(img_url, ts)
                if not fname:
                    sys.exit(f"could not download map for {city}: {img_url}")
                if fname not in seen:
                    shutil.copy(fetch.IMG_DIR / fname, IMAGES_DIR / fname)
                    seen.add(fname)
                    new_maps.append((city, fname))
                    to_archive.append(img_url + "=s0")
            current.append([city, note, fname, img_url])
        print(page, len(current), "cities")

        page_state = sorted(c[:3] for c in current)
        rows = diff(state.get(page, []), page_state)
        if not rows:
            continue
        with gzip.open(PAGES_DIR / f"{page}_{ts}.html.gz", "wt", encoding="utf-8") as f:
            f.write(r.text)
        record_capture(page, ts, current, r.text)
        urls = {c[2]: c[3] for c in current}
        changes += [dict(date=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", snapshot=ts, page=page,
                         city=c, change=kind, image_file=img, image_url=urls.get(img, ""))
                    for c, kind, img in rows]
        state[page] = page_state
        to_archive.insert(0, f"https://{addr}")

    if changes:
        new_file = not CHANGES.exists()
        with open(CHANGES, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(changes[0]))
            if new_file:
                w.writeheader()
            w.writerows(changes)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False))

    if os.environ.get("NO_WAYBACK") != "1":
        for u in to_archive:
            wayback_save(u)
    else:
        print("skipping wayback:", to_archive)

    lines = [f"- **{c['city']}**: {c['change']} {c['image_file']}" for c in changes]
    summary = "\n".join(lines) or "No changes."
    print(summary)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changes else 'false'}\n")
            f.write(f"new_maps={len(new_maps)}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("## Waymo service-area maps\n\n" + summary + "\n")
    if os.environ.get("SUMMARY_FILE"):  # body for the GitHub issue
        Path(os.environ["SUMMARY_FILE"]).write_text(summary + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
