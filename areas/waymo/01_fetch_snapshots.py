"""Step 1: download all archive.org snapshots of the Waymo help pages with
service-area maps (the main page, and the Uber page for Austin/Atlanta), plus
today's live version of each, extract the per-city map image URLs, and
download each distinct image.

Outputs
  raw/snapshots/<timestamp>.html   cached page HTML (Uber page: 16011725_<timestamp>.html)
  raw/images/<sha1>.png            each distinct map image (deduplicated by content)
  data/snapshot_images.csv         one row per (snapshot, city, image)
"""
import csv
import argparse
import gzip
import hashlib
import shutil
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import html as html_lib

import requests

ROOT = Path(__file__).parent
SNAP_DIR = ROOT / "raw" / "snapshots"
IMG_DIR = ROOT / "raw" / "images"
DATA_DIR = ROOT / "data"
LIVE_DIR = ROOT / "live"  # committed captures from the daily CI check
for d in (SNAP_DIR, IMG_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

# main service-area page, and the "Waymo on Uber" page with Austin/Atlanta maps
PAGES = {"9059119": "support.google.com/waymo/answer/9059119",
         "16011725": "support.google.com/waymo/answer/16011725"}
MAIN = "9059119"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research; waymo service area history)"


def get(url, tries=5, **kw):
    timeout = kw.pop("timeout", 60)
    for i in range(tries):
        try:
            r = S.get(url, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 403):
                return r
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    return None


def list_snapshots(page):
    url = ("https://web.archive.org/cdx/search/cdx?url=" + PAGES[page] +
           "&matchType=prefix&output=json&fl=timestamp,original,statuscode"
           "&filter=statuscode:200")
    response = get(url, tries=2)
    if response is None or response.status_code != 200:
        raise RuntimeError(f"Could not list archived captures: {url}")
    rows = response.json()[1:]
    # keep English (or default) versions only
    rows = [r for r in rows if "hl=" not in r[1] or "hl=en" in r[1]]
    return sorted(rows)


def snapshot_path(ts, page):
    return SNAP_DIR / (f"{ts}.html" if page == MAIN else f"{page}_{ts}.html")


def replay_timestamp(response):
    """Use the capture actually returned, including closest-capture redirects."""
    match = re.search(r"/web/(\d{14})(?:id_|im_)?/", response.url)
    if not match:
        raise ValueError(f"Archive response escaped replay: {response.url}")
    stamp = match[1]
    memento = response.headers.get("Memento-Datetime")
    if memento:
        actual = parsedate_to_datetime(memento).astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
        if actual != stamp:
            raise ValueError(f"Replay URL and Memento timestamp disagree: {stamp} != {actual}")
    return stamp


def fetch_snapshot(ts, original, page, *, live=False):
    path = snapshot_path(ts, page)
    metadata_path = path.with_suffix(".json")
    mode = "ci" if original == "ci" else "live" if live else "archive"
    if path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("version") == 2 and metadata.get("mode") == mode and metadata.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest():
            return path.read_text(encoding="utf-8", errors="replace")
    if mode == "ci":
        raise ValueError("CI capture must be imported from its committed gzip before use")
    url = original if live else f"https://web.archive.org/web/{ts}id_/{original}"
    r = get(url, tries=2)
    if r is None or r.status_code != 200:
        return None
    captured = ts if live else replay_timestamp(r)
    # Old cache files lack proof that historical content was fetched. Preserve
    # them for audit, but never reuse them as an archive observation.
    if path.exists() and not metadata_path.exists():
        backup = SNAP_DIR.parent / "snapshots_legacy" / path.name
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            shutil.copyfile(path, backup)
    path.write_bytes(r.content)
    metadata_path.write_text(json.dumps({
        "version": 2, "mode": mode, "requested_timestamp": ts,
        "captured_at": captured, "response_url": r.url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(r.content).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    return path.read_text(encoding="utf-8", errors="replace")


def clean_img_url(src):
    # strip web.archive.org wrapper and size suffix
    src = re.sub(r"^.*?/web/\d+(im_|id_)?/", "", src)
    if src.startswith("//"):
        src = "https:" + src
    return re.sub(r"=[a-z0-9-]+$", "", src.split("?")[0])


def _text(fragment):
    fragment = re.sub(r"<[^>]*$", " ", re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", html_lib.unescape(fragment)).replace("\xa0", " ").strip()


# any element with class="zippy" (a, h2, p, ... - Waymo mixes them), or a plain h2/h3
HEADING = re.compile(r'<(a|h[1-6]|p|span)\b[^>]*class="zippy(?:\s[^"]*)?"[^>]*>(.*?)</\1>'
                     r'|<(h[23])\b[^>]*>(.*?)</\3>', re.S)


def parse_cities(html):
    """Return list of (city, note, image_url). Cities are headed by either
    <a class="zippy"> (2025+) or <h2>/<h3> (2024); the content runs until the
    next heading."""
    i = html.find("<h1")
    j = html.find('class="sub-article-container', i)
    art = html[i:j] if i >= 0 else html
    heads = list(HEADING.finditer(art))
    out = []
    for k, h in enumerate(heads):
        city = _text(h.group(2) if h.group(1) else h.group(4))
        city = re.sub(r"\s*service area\s*$", "", city, flags=re.I)
        body = art[h.end(): heads[k + 1].start() if k + 1 < len(heads) else len(art)]
        note = _text(body)
        srcs = []
        for tag in re.findall(r"<img[^>]*>", body):
            m = (re.search(r'data-alt-src="([^"]+)"', tag) or re.search(r'\ssrc="([^"]+)"', tag))
            if m and re.search(r"googleusercontent|gstatic|storage\.googleapis", m.group(1)):
                srcs.append(clean_img_url(html_lib.unescape(m.group(1))))
        if not city or (not srcs and not note) or (not srcs and city.endswith("?")):
            continue
        if not srcs:
            out.append((city, note, ""))
        out += [(city, note, s) for s in srcs]
    return out


def download_image_record(url, ts, *, archived=False, known_records=()):
    """Historical images must come from a replay no later than the page capture."""
    cands = ([f"https://web.archive.org/web/{ts}im_/{url}",
              f"https://web.archive.org/web/{ts}im_/{url}=w895",
              f"https://web.archive.org/web/{ts}im_/{url}=s0"] if archived else
             [url + "=s0", url])
    for c in cands:
        r = get(c, tries=2, timeout=30)
        if r is not None and r.status_code == 200 and (
                r.content[:4] == b"\x89PNG" or r.content[:3] == b"\xff\xd8\xff"):
            capture = replay_timestamp(r) if archived else ts
            if archived and capture > ts:
                # A closest-capture redirect can go forward. It is usable only
                # when its bytes are identical to a verified earlier capture of
                # this URL; retain that earlier capture as the image evidence.
                digest = hashlib.sha256(r.content).hexdigest()
                earlier = [x for x in known_records if x.get("mode") == "archive"
                           and x["captured_at"] <= ts and x["sha256"] == digest]
                if earlier:
                    record = max(earlier, key=lambda x: x["captured_at"])
                    (IMG_DIR / record["image_file"]).write_bytes(r.content)
                    return {**record,
                            "confirmed_identical_at": r.url}
                continue
            h = hashlib.sha1(r.content).hexdigest()[:16]
            ext = ".png" if r.content[:4] == b"\x89PNG" else ".jpg"
            p = IMG_DIR / f"{h}{ext}"
            if not p.exists():
                p.write_bytes(r.content)
            return {"image_file": p.name, "response_url": r.url,
                    "captured_at": capture, "mode": "archive" if archived else "live",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(r.content).hexdigest()}
    return {}


def download_image(url, ts):
    """Compatibility entry point for the live watcher."""
    record = download_image_record(url, ts)
    return record.get("image_file", ""), record.get("response_url", "")


def import_live_captures():
    """Pages and maps saved by the daily CI check (07_watch_live.py) in live/.
    Copied into raw/ and returned as extra snapshots."""
    out = []
    for p in sorted((LIVE_DIR / "pages").glob("*.html.gz")):
        page, ts = p.name.removesuffix(".html.gz").split("_")
        dst = SNAP_DIR / (f"{ts}.html" if page == MAIN else f"{page}_{ts}.html")
        with gzip.open(p, "rb") as f:
            payload = f.read()
        dst.write_bytes(payload)
        dst.with_suffix(".json").write_text(json.dumps({
            "version": 2, "mode": "ci", "captured_at": ts,
            "response_url": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }, indent=2) + "\n", encoding="utf-8")
        out.append((ts, "ci", page))
    for p in (LIVE_DIR / "images").glob("*"):
        if not (IMG_DIR / p.name).exists():
            shutil.copy(p, IMG_DIR / p.name)
    if out:
        print(len(out), "pages from live/")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", choices=list(PAGES), help="Refresh only this page, retaining other rows")
    parser.add_argument("--existing-index", action="store_true", help="Replay timestamps already in the CSV if CDX is unavailable")
    parser.add_argument("--archive-only", action="store_true", help="Do not fetch today's live page")
    args = parser.parse_args()
    existing_path = DATA_DIR / "snapshot_images.csv"
    previous = list(csv.DictReader(existing_path.open(encoding="utf-8"))) if existing_path.exists() else []
    snaps = []
    today = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    for page, addr in PAGES.items():
        if args.page and page != args.page:
            continue
        if args.existing_index:
            rows = [(ts, f"https://{addr}?hl=en", "200") for ts in sorted({
                r["snapshot"] for r in previous if r["page"] == page})]
        else:
            rows = list_snapshots(page)
        # also take the live page once per day (stored like a snapshot)
        live = [today, f"https://{addr}?hl=en", "live"]
        if not args.archive_only:
            rows.append(live)
        snaps += [(ts, orig, page, status == "live") for ts, orig, status in rows]
        print(page, len(rows), "snapshots")
    snaps += [(ts, orig, page, False) for ts, orig, page in import_live_captures()
              if not args.page or page == args.page]
    cache_path = DATA_DIR / "image_capture_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    changes_file = LIVE_DIR / "changes.csv"
    committed_images = list(csv.DictReader(changes_file.open(encoding="utf-8"))) if changes_file.exists() else []
    rows = [r for r in previous if args.page and r["page"] != args.page]
    sources_path = DATA_DIR / "snapshot_sources.csv"
    sources = list(csv.DictReader(sources_path.open(encoding="utf-8"))) if sources_path.exists() else []
    sources = [r for r in sources if args.page and r["page"] != args.page]
    seen_captures = set()
    for ts, original, page, live in snaps:
        html = fetch_snapshot(ts, original, page, live=live)
        if not html:
            print("  failed", ts)
            continue
        page_meta = json.loads(snapshot_path(ts, page).with_suffix(".json").read_text(encoding="utf-8"))
        capture = page_meta["captured_at"]
        if (page, capture) in seen_captures:
            continue
        seen_captures.add((page, capture))
        cities = parse_cities(html)
        print(ts, "=>", capture, len(cities), "cities", flush=True)
        for city, note, url in cities:
            key = f"{page_meta['mode']}|{capture}|{url}"
            existing_image = cache.get(key, {})
            local_image = IMG_DIR / existing_image.get("image_file", "missing")
            image_valid = existing_image and local_image.is_file() and hashlib.sha256(local_image.read_bytes()).hexdigest() == existing_image.get("sha256")
            if url and not image_valid:
                if page_meta["mode"] == "ci":
                    matches = [r for r in committed_images if r["page"] == page
                        and r["city"] == city and r["image_url"] == url
                        and r["snapshot"] <= capture and r["image_file"]
                        and (IMG_DIR / r["image_file"]).exists()]
                    if not matches:
                        raise RuntimeError(f"No committed image evidence for {city} at {capture}")
                    saved = max(matches, key=lambda r: r["snapshot"])
                    cache[key] = {"image_file": saved["image_file"], "mode": "ci",
                        "captured_at": saved["snapshot"], "response_url": f"live/images/{saved['image_file']}",
                        "sha256": hashlib.sha256((IMG_DIR / saved["image_file"]).read_bytes()).hexdigest()}
                else:
                    known = [v for k, v in cache.items() if k.split("|", 2)[-1] == url and v]
                    cache[key] = download_image_record(url, capture,
                        archived=page_meta["mode"] == "archive", known_records=known)
                cache_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            image = cache.get(key, {}) if url else {}
            fname = image.get("image_file", "")
            if url and not fname:
                raise RuntimeError(f"No verified image for {city} at {capture}; existing CSV left untouched")
            rows.append(dict(page=page, snapshot=capture, date=f"{capture[:4]}-{capture[4:6]}-{capture[6:8]}",
                             city=city, note=note, image_url=url, image_file=fname))
            sources.append(dict(page=page, snapshot=capture, city=city, image_file=fname,
                page_mode=page_meta["mode"], page_url=page_meta["response_url"], page_sha256=page_meta["sha256"],
                image_url=image.get("response_url", ""), image_capture=image.get("captured_at", ""),
                image_sha256=image.get("sha256", ""), retrieved_at=image.get("retrieved_at", "")))
    if not seen_captures or not rows or not sources:
        raise RuntimeError("No verified map observations recovered; existing CSV left untouched")
    # Recovery is reversible; keep original index bytes locally before replacing.
    backup = SNAP_DIR.parent / "history_repair" / "snapshot_images.before.csv"
    backup.parent.mkdir(exist_ok=True)
    if existing_path.exists() and not backup.exists():
        shutil.copyfile(existing_path, backup)
    with open(DATA_DIR / "snapshot_images.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with sources_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sources[0]))
        w.writeheader()
        w.writerows(sources)
    print("distinct images:", len({r["image_file"] for r in rows if r["image_file"]}))
    print("missing images:", sorted({r["image_url"] for r in rows if r["image_url"] and not r["image_file"]}))


if __name__ == "__main__":
    main()
