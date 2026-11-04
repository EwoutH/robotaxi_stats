"""Restore checked announcement-map renditions before running step 2.

Original image URLs and hashes are recorded in data/history_image_sources.csv.
Images are resized proportionally to at most 1600 px for road matching.
"""
import csv
import hashlib
import io
from pathlib import Path

from PIL import Image
import requests

ROOT = Path(__file__).parent
IMAGES = ROOT / "raw" / "images"


def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    with (ROOT / "data" / "history_image_sources.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            target = IMAGES / row["image_file"]
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == row["prepared_sha256"]:
                continue
            response = requests.get(row["image_url"], timeout=60)
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != row["original_sha256"]:
                raise ValueError(f"Source image changed: {row['image_url']}")
            image = Image.open(io.BytesIO(response.content))
            image.seek(int(row.get("frame_index") or 0))
            image = image.convert("RGBA")
            if row.get("crop_box"):
                image = image.crop(tuple(map(int, row["crop_box"].split(","))))
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            prepared = io.BytesIO()
            image.save(prepared, format="PNG")
            payload = prepared.getvalue()
            if hashlib.sha256(payload).hexdigest() != row["prepared_sha256"]:
                raise ValueError(f"Prepared rendition differs; check Pillow version: {target.name}")
            target.write_bytes(payload)
            print(target.name)


if __name__ == "__main__":
    main()
