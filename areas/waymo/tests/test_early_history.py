"""Dataset regressions for recovered announcements and stale-page handling."""
from pathlib import Path
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]


class EarlyHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.versions = gpd.read_file(ROOT / "waymo_service_areas.gpkg", layer="metro_versions")

    def test_december_sf_excludes_employee_downtown(self):
        first = self.versions[self.versions.metro == "San Francisco"].sort_values("valid_from").iloc[0]
        self.assertEqual(first.valid_from, "2022-12-16")
        self.assertTrue(first.geometry.covers(Point(-122.49, 37.75)))
        self.assertFalse(first.geometry.covers(Point(-122.403, 37.793)))
        self.assertLess(first.area_mi2, 36)

    def test_early_sf_expansions_are_announced_dates(self):
        rows = self.versions[self.versions.metro == "San Francisco"].sort_values("valid_from").head(3)
        self.assertEqual(rows.valid_from.tolist(), ["2022-12-16", "2023-02-17", "2023-10-09"])
        self.assertTrue((rows.date_basis == "operator_announcement").all())
        self.assertEqual(rows.area_mi2.tolist(), sorted(rows.area_mi2))

    def test_phoenix_does_not_revert_to_stale_2024_map(self):
        rows = self.versions[self.versions.metro == "Phoenix"].sort_values("valid_from")
        self.assertEqual(rows.head(3).valid_from.tolist(), ["2023-05-04", "2023-07-07", "2024-07-12"])
        self.assertGreater(rows.iloc[1].area_mi2, rows.iloc[0].area_mi2 + 35)
        raw = pd.read_csv(ROOT / "data" / "snapshot_images.csv")
        stale = raw[(raw.city == "Phoenix") & (raw.image_file == "c4ae70c4e9335b83.png")]
        self.assertEqual(len(stale), 4, "Raw stale-page evidence must remain available")

    def test_versions_remain_valid_and_non_overlapping(self):
        self.assertTrue(self.versions.geometry.is_valid.all())
        for _, rows in self.versions.groupby("metro"):
            rows = rows.sort_values("valid_from")
            self.assertFalse(rows.valid_from.duplicated().any())
            self.assertEqual(rows.valid_to.iloc[:-1].tolist(), rows.valid_from.iloc[1:].tolist())


if __name__ == "__main__":
    unittest.main()
