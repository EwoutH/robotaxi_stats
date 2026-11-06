"""Official city status ("open" / "soon") over time, from tesla.com/robotaxi.

The page has no service-area map, but embeds a "cities" list with a center point
and a status per city. This reads every Wayback Machine capture (one per day),
and only fetches captures not yet in data/page_captures.csv, so re-runs are cheap.

Writes:
  data/page_captures.csv   every capture read: timestamp, number of cities listed
  data/page_cities.csv     every city on every capture: status and center point
  data/status_changes.csv  first capture showing each city's status; the change
                           happened between window_start and date
"""
import csv
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PAGE = "https://www.tesla.com/robotaxi"
CAPTURES, CITIES, CHANGES = DATA / "page_captures.csv", DATA / "page_cities.csv", DATA / "status_changes.csv"

session = requests.Session()
session.headers["User-Agent"] = "robotaxi_stats research script"


def get(url):
    for attempt in range(4):
        try:
            r = session.get(url, timeout=120)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


OFFERED = re.compile(r"rides are currently being offered[^.<]*?\b(?:in|including) ([^.<]+)")


def parse_cities(html):
    """Cities from the page's map data (Oct 2026 on) or, before that, from the
    footnote "rides are currently being offered in A, B and C" (2026 only;
    2025 pages name no cities)."""
    i = html.find('"cities":')
    cities = json.JSONDecoder().raw_decode(html, i + len('"cities":'))[0] if i >= 0 else []
    if cities:
        return [{"city_id": c["id"], "name": c.get("t_name", ""), "status": c["type"],
                 "lon": c["coordinates"][0], "lat": c["coordinates"][1], "form": "map"}
                for c in cities]
    m = OFFERED.search(html.replace("U.S.", "US"))
    if not m:
        return []
    text = re.sub(r",? (Texas|Florida|Arizona|Nevada|California)\b", "", m.group(1))
    names = re.split(r",\s*(?:and\s+)?|\s+and\s+", text)
    return [{"city_id": n.strip().lower().replace(" ", "-"), "name": n.strip(), "status": "open",
             "lon": "", "lat": "", "form": "text"} for n in names if n.strip()]


def main():
    DATA.mkdir(exist_ok=True)
    captures, cities = read_csv(CAPTURES), read_csv(CITIES)
    done = {c["timestamp"] for c in captures}
    cdx = get(f"http://web.archive.org/cdx/search/cdx?url={PAGE}&output=json"
              "&filter=statuscode:200&collapse=timestamp:8&fl=timestamp").json()[1:]
    new = [ts for (ts,) in cdx if ts not in done]
    print(f"{len(cdx)} captures, {len(new)} new")
    for ts in new:
        r = get(f"https://web.archive.org/web/{ts}id_/{PAGE}")
        if r.headers.get("content-encoding") == "br" and not r.content.lstrip().startswith(b"<"):
            print(ts, "skipped: Brotli-compressed capture (pip install brotli to read it)")
            continue
        found = parse_cities(r.text)
        captures.append({"timestamp": ts, "n_cities": len(found)})
        cities += [{"timestamp": ts, **c} for c in found]
        print(ts, len(found), "cities")
        time.sleep(1)

    captures.sort(key=lambda c: c["timestamp"])
    cities.sort(key=lambda c: (c["timestamp"], c["city_id"]))
    write_csv(CAPTURES, captures, ["timestamp", "n_cities"])
    write_csv(CITIES, cities, ["timestamp", "city_id", "name", "status", "lon", "lat", "form"])

    # Status per city per capture ("" = not listed), then keep the changes.
    status = {}
    for c in cities:
        status.setdefault(c["timestamp"], {})[c["city_id"]] = c["status"]
    names = {c["city_id"]: c["name"] for c in cities}
    listed = [c["timestamp"] for c in captures if int(c["n_cities"]) > 0]
    changes, last, prev_ts = [], {}, ""
    for ts in listed:
        for cid in sorted(set(last) | set(status[ts])):
            now = status[ts].get(cid, "")
            if now != last.get(cid, ""):
                changes.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "window_start": prev_ts,
                                "city_id": cid, "name": names[cid],
                                "status_from": last.get(cid, ""), "status_to": now})
            last[cid] = now
        prev_ts = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    write_csv(CHANGES, changes, ["date", "window_start", "city_id", "name", "status_from", "status_to"])
    print(f"{len(changes)} status changes")


if __name__ == "__main__":
    main()
