"""Regression checks for archive/live provenance and closest-capture redirects."""

import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("waymo_fetch", Path(__file__).parents[1] / "01_fetch_snapshots.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def response(url, content=b"archived page", memento=None):
    return SimpleNamespace(url=url, content=content, text=content.decode("utf-8", errors="replace"),
                           headers={"Memento-Datetime": memento} if memento else {}, status_code=200)


class ArchiveCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ["snapshots", "images"]:
            (root / name).mkdir()
        for name, value in [("SNAP_DIR", root / "snapshots"), ("IMG_DIR", root / "images")]:
            patcher = patch.object(fetch, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_https_original_is_replayed_unless_explicitly_live(self):
        original = "https://support.google.com/waymo/answer/16011725?hl=en"
        url = "https://web.archive.org/web/20250729215009id_/" + original
        with patch.object(fetch, "get", return_value=response(url)) as request:
            fetch.fetch_snapshot("20250729215009", original, "16011725")
        self.assertEqual(request.call_args.args[0], url)

    def test_unverified_legacy_cache_is_not_reused(self):
        path = fetch.snapshot_path("20250729215009", "16011725")
        path.write_text("wrong live page" * 100)
        url = "https://web.archive.org/web/20250729215009id_/https://support.google.com/waymo/answer/16011725"
        with patch.object(fetch, "get", return_value=response(url)):
            self.assertEqual(fetch.fetch_snapshot("20250729215009", "https://support.google.com/waymo/answer/16011725", "16011725"), "archived page")
        self.assertTrue((fetch.SNAP_DIR.parent / "snapshots_legacy" / path.name).exists())

    def test_redirect_uses_actual_capture_and_verified_cache(self):
        url = "https://web.archive.org/web/20250729215009id_/https://support.google.com/waymo/answer/16011725"
        with patch.object(fetch, "get", return_value=response(url, memento="Tue, 29 Jul 2025 21:50:09 GMT")) as request:
            for _ in range(2):
                fetch.fetch_snapshot("20250612165522", "https://support.google.com/waymo/answer/16011725", "16011725")
        self.assertEqual(request.call_count, 1)
        meta = json.loads(fetch.snapshot_path("20250612165522", "16011725").with_suffix(".json").read_text())
        self.assertEqual(meta["captured_at"], "20250729215009")
        self.assertEqual(meta["requested_timestamp"], "20250612165522")

    def test_live_mode_is_explicit(self):
        url = "https://support.google.com/waymo/answer/16011725?hl=en"
        with patch.object(fetch, "get", return_value=response(url)) as request:
            fetch.fetch_snapshot("20261104090000", url, "16011725", live=True)
        self.assertEqual(request.call_args.args[0], url)

    def test_archive_response_cannot_escape_to_live(self):
        with self.assertRaisesRegex(ValueError, "escaped replay"):
            fetch.replay_timestamp(response("https://support.google.com/waymo/answer/16011725"))

    def test_future_image_needs_identical_verified_earlier_bytes(self):
        url = "https://storage.googleapis.com/example-map"
        future = "https://web.archive.org/web/20251114092722im_/" + url
        payload = b"\x89PNGsynthetic image"
        with patch.object(fetch, "get", return_value=response(future, payload)):
            self.assertEqual(fetch.download_image_record(url, "20251105134342", archived=True), {})
            known = {"mode": "archive", "captured_at": "20250729215009", "image_file": "old.png",
                     "sha256": hashlib.sha256(payload).hexdigest(), "response_url": "earlier archive"}
            result = fetch.download_image_record(url, "20251105134342", archived=True, known_records=[known])
        self.assertEqual(result["captured_at"], "20250729215009")
        self.assertEqual(result["confirmed_identical_at"], future)


if __name__ == "__main__":
    unittest.main()
