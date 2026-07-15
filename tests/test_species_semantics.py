from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mothdash.analysis import (
    first_of_season,
    latest_session_taxa,
    recent_days_taxa,
    record_highlights,
    station_profile,
    station_summaries,
    station_taxa,
    trend_summary,
    unique_station_taxa,
)
from mothdash.config import Settings
from mothdash.db import connect, init_db


class SpeciesSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            root=root,
            data_dir=root / "data",
            public_dir=root / "public",
            database=root / "data" / "mothdash.db",
        )
        init_db(self.settings.database)
        with connect(self.settings.database) as conn:
            conn.executemany(
                "INSERT INTO stations (id, name, enabled) VALUES (?, ?, 1)",
                [("station-a", "Station A"), ("station-b", "Station B")],
            )
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("station-a", 1, "2026-07-10", "2026-07-10T22:00:00-04:00", 101, "Species alpha", "Alpha", "species", "https://example.test/1"),
                    ("station-a", 2, "2026-07-10", "2026-07-10T22:10:00-04:00", 101, "Species alpha", "Alpha", "species", "https://example.test/2"),
                    ("station-a", 3, "2026-07-10", "2026-07-10T22:20:00-04:00", 102, "Species beta", "Beta", "species", "https://example.test/3"),
                    ("station-a", 4, "2026-07-10", "2026-07-10T22:30:00-04:00", 201, "Genus gamma", None, "genus", "https://example.test/4"),
                    ("station-a", 5, "2026-07-10", "2026-07-10T22:40:00-04:00", 301, "Family delta", None, "family", "https://example.test/5"),
                    ("station-b", 6, "2026-07-10", "2026-07-10T22:50:00-04:00", 101, "Species alpha", "Alpha", "species", "https://example.test/6"),
                    ("station-b", 7, "2026-07-10", "2026-07-10T23:00:00-04:00", 201, "Genus gamma", None, "genus", "https://example.test/7"),
                ],
            )
            conn.executemany(
                """
                INSERT INTO station_taxon_stats (
                    station_id, taxon_id, station_first_date,
                    is_county_first, is_state_first
                ) VALUES (?, ?, '2026-07-10', 1, 0)
                """,
                [("station-a", 102), ("station-a", 201)],
            )

    def test_station_totals_count_observations_but_only_species_richness(self) -> None:
        summaries = {row["station_id"]: row for row in station_summaries(self.settings)}

        self.assertEqual(summaries["station-a"]["observations"], 5)
        self.assertEqual(summaries["station-a"]["species"], 2)
        self.assertEqual(summaries["station-b"]["observations"], 2)
        self.assertEqual(summaries["station-b"]["species"], 1)

    def test_species_dashboards_exclude_broader_ranks(self) -> None:
        taxa = station_taxa(self.settings)
        latest = latest_session_taxa(self.settings)
        recent = recent_days_taxa(self.settings)

        self.assertEqual({row["taxon_id"] for row in taxa}, {101, 102})
        self.assertEqual({row["taxon_id"] for row in latest["taxa"]}, {101, 102})
        self.assertEqual({row["taxon_id"] for row in recent["taxa"]}, {101, 102})
        self.assertEqual(latest["observations"], 4)
        self.assertEqual(recent["observations"], 4)

    def test_firsts_uniques_and_pulses_exclude_broader_ranks(self) -> None:
        pulses = first_of_season(self.settings, 2026)
        records = record_highlights(self.settings)
        uniques = unique_station_taxa(self.settings)

        self.assertEqual([row["taxon_id"] for row in pulses], [101])
        self.assertNotIn(201, {row["taxon_id"] for row in records})
        self.assertEqual({row["taxon_id"] for row in uniques}, {102})

    def test_profiles_and_trends_remain_species_only(self) -> None:
        profile = station_profile(self.settings, "station-a")
        trends = trend_summary(self.settings)

        self.assertEqual(profile["species"], 2)
        self.assertEqual(profile["observations"], 5)
        self.assertEqual(trends["network_accumulation"][-1]["species"], 2)
        self.assertNotIn(201, {row["taxon_id"] for row in trends["phenology"]})


if __name__ == "__main__":
    unittest.main()
