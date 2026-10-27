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
import hashlib
import json
import re
import time
from pathlib import Path

import html as html_lib

import requests

ROOT = Path(__file__).parent
SNAP_DIR = ROOT / "raw" / "snapshots"
IMG_DIR = ROOT / "raw" / "images"
DATA_DIR = ROOT / "data"
for d in (SNAP_DIR, IMG_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

# main service-area page, and the "Waymo on Uber" page with Austin/Atlanta maps
PAGES = {"9059119": "support.google.com/waymo/answer/9059119",
         "16011725": "support.google.com/waymo/answer/16011725"}
MAIN = "9059119"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research; waymo service area history)"


def get(url, tries=5, **kw):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60, **kw)
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
    rows = get(url).json()[1:]
    # keep English (or default) versions only
    rows = [r for r in rows if "hl=" not in r[1] or "hl=en" in r[1]]
    return sorted(rows)


def fetch_snapshot(ts, original, page):
    path = SNAP_DIR / (f"{ts}.html" if page == MAIN else f"{page}_{ts}.html")
    if path.exists() and path.stat().st_size > 1000:
        return path.read_text(encoding="utf-8", errors="replace")
    url = original if original.startswith("https://support") else         f"https://web.archive.org/web/{ts}id_/{original}"
    r = get(url)
    if r is None or r.status_code != 200:
        return None
    path.write_text(r.text, encoding="utf-8")
    time.sleep(1)
    return r.text


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


def download_image(url, ts):
    """Try the live URL first (Google keeps these), then archive.org."""
    cands = [url + "=s0", url, f"https://web.archive.org/web/{ts}im_/{url}=w895",
             f"https://web.archive.org/web/{ts}im_/{url}"]
    for c in cands:
        r = get(c, tries=2)
        if r is not None and r.status_code == 200 and (
                r.content[:4] == b"\x89PNG" or r.content[:3] == b"\xff\xd8\xff"):
            h = hashlib.sha1(r.content).hexdigest()[:16]
            ext = ".png" if r.content[:4] == b"\x89PNG" else ".jpg"
            p = IMG_DIR / f"{h}{ext}"
            if not p.exists():
                p.write_bytes(r.content)
            return p.name, c
    return "", ""


def main():
    snaps = []
    today = time.strftime("%Y%m%d%H%M%S")
    for page, addr in PAGES.items():
        rows = list_snapshots(page)
        # also take the live page once per day (stored like a snapshot)
        live = [today, f"https://{addr}?hl=en", "live"]
        if not any(r[0][:8] == today[:8] for r in rows):
            rows.append(live)
        snaps += [(ts, orig, page) for ts, orig, _ in rows]
        print(page, len(rows), "snapshots")
    cache_path = DATA_DIR / "image_url_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = []
    for ts, original, page in snaps:
        html = fetch_snapshot(ts, original, page)
        if not html:
            print("  failed", ts)
            continue
        cities = parse_cities(html)
        print(ts, len(cities), "cities")
        for city, note, url in cities:
            if url and url not in cache:
                cache[url] = download_image(url, ts)
                cache_path.write_text(json.dumps(cache, indent=1))
            fname = cache.get(url, ("", ""))[0] if url else ""
            rows.append(dict(page=page, snapshot=ts, date=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                             city=city, note=note, image_url=url, image_file=fname))
    with open(DATA_DIR / "snapshot_images.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("distinct images:", len({r["image_file"] for r in rows if r["image_file"]}))
    print("missing images:", sorted({r["image_url"] for r in rows if r["image_url"] and not r["image_file"]}))


if __name__ == "__main__":
    main()
