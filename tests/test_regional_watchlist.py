from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mothdash.config import Settings, Station
from mothdash.db import init_db
from mothdash.regional import cached_regional_watchlist, refresh_regional_watchlists


def species_count(taxon_id: int, name: str, common_name: str, count: int) -> dict:
    return {
        "count": count,
        "taxon": {
            "id": taxon_id,
            "rank": "species",
            "name": name,
            "preferred_common_name": common_name,
            "default_photo": {"medium_url": f"https://example.test/{taxon_id}.jpg"},
        },
    }


class RegionalWatchlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            root=root,
            data_dir=root / "data",
            public_dir=root / "public",
            database=root / "data" / "mothdash.db",
            regional_watch_days=14,
            regional_watch_cache_hours=168,
        )
        init_db(self.settings.database)
        self.station = Station(
            id="test-station",
            name="Test Station",
            enabled=True,
            active=True,
            query={},
            regional_watch_lat=42.4,
            regional_watch_lng=-76.4,
        )

    @patch("mothdash.regional.iter_species_counts")
    def test_refreshes_day_counts_and_reuses_overlapping_cache(self, counts_mock) -> None:
        counts_mock.side_effect = (
            [
                [
                    species_count(101, "Mothus commonus", "Common Moth", 4),
                    {"count": 3, "taxon": {"id": 202, "rank": "genus", "name": "Not A Species"}},
                ]
                for _ in range(7)
            ]
            + [
                [
                    species_count(101, "Mothus commonus", "Common Moth", 6),
                    species_count(102, "Mothus later", "Later Moth", 2),
                ]
                for _ in range(7)
            ]
        )

        refresh_regional_watchlists(
            self.settings,
            [self.station],
            today=date(2026, 7, 25),
        )

        cached = cached_regional_watchlist(self.settings, "test-station", date(2026, 7, 25))
        self.assertIsNotNone(cached)
        self.assertEqual(cached["run"]["window_end"], "2026-08-07")
        self.assertEqual(cached["run"]["radius_km"], 100.0)
        self.assertEqual(
            {row["taxon_id"]: row["record_count"] for row in cached["rows"]},
            {101: 70, 102: 14},
        )
        self.assertEqual(counts_mock.call_count, 14)
        first_params = counts_mock.call_args_list[0].args[0]
        second_params = counts_mock.call_args_list[7].args[0]
        self.assertEqual(first_params["month"], 7)
        self.assertEqual(first_params["day"], 25)
        self.assertEqual(second_params["month"], 8)
        self.assertEqual(second_params["day"], 1)
        self.assertEqual(first_params["radius"], 100.0)
        self.assertEqual(first_params["taxon_id"], 47157)
        self.assertEqual(first_params["without_taxon_id"], 47224)

        refresh_regional_watchlists(
            self.settings,
            [self.station],
            today=date(2026, 7, 25),
        )
        self.assertEqual(counts_mock.call_count, 14, "current daily cache avoids duplicate API calls")

        counts_mock.reset_mock()
        counts_mock.side_effect = None
        counts_mock.return_value = [species_count(103, "Mothus incoming", "Incoming Moth", 1)]
        refresh_regional_watchlists(
            self.settings,
            [self.station],
            today=date(2026, 7, 26),
        )
        self.assertEqual(counts_mock.call_count, 1, "only the newly entering calendar day is fetched")
        self.assertEqual(counts_mock.call_args.args[0]["day"], 8)
        next_cached = cached_regional_watchlist(self.settings, "test-station", date(2026, 7, 26))
        self.assertIn(103, {row["taxon_id"] for row in next_cached["rows"]})


if __name__ == "__main__":
    unittest.main()
