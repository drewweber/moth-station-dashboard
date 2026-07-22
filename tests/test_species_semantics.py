from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from mothdash.analysis import (
    _forecast_station_context,
    _historical_target_backtest,
    _published_forecast_validation,
    first_of_season,
    last_completed_session_taxa,
    load_rows,
    latest_session_taxa,
    recent_days_taxa,
    record_highlights,
    station_profile,
    station_summaries,
    station_taxa,
    store_forecast_snapshot,
    trend_summary,
    unique_station_taxa,
    weekly_recap,
)
from mothdash.config import Settings
from mothdash.db import connect, init_db
from mothdash.render import _recent_week_dashboard


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
        recent = recent_days_taxa(
            self.settings,
            now=datetime(2026, 7, 11, 10, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertEqual({row["taxon_id"] for row in taxa}, {101, 102})
        self.assertEqual({row["taxon_id"] for row in latest["taxa"]}, {101, 102})
        self.assertEqual({row["taxon_id"] for row in recent["taxa"]}, {101, 102})
        self.assertEqual(latest["observations"], 4)
        self.assertEqual(recent["observations"], 4)

    def test_last_night_uses_the_last_completed_session_not_the_active_one(self) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "station-a",
                    8,
                    "2026-07-11",
                    "2026-07-11T22:00:00-04:00",
                    999,
                    "Current session species",
                    "Current",
                    "species",
                    "https://example.test/8",
                ),
            )

        last_night = last_completed_session_taxa(
            self.settings,
            now=datetime(2026, 7, 11, 21, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertEqual(last_night["session_date"].isoformat(), "2026-07-10")
        self.assertEqual(last_night["latest_session"].isoformat(), "2026-07-11")
        self.assertEqual({row["taxon_id"] for row in last_night["taxa"]}, {101, 102})

    def test_current_week_does_not_slide_back_to_stale_data(self) -> None:
        recent = recent_days_taxa(
            self.settings,
            now=datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertEqual(recent["period_label"], "2026-07-13 to 2026-07-19")
        self.assertEqual(recent["latest_session"].isoformat(), "2026-07-10")
        self.assertTrue(recent["is_stale"])
        self.assertEqual(recent["taxa"], [])
        rendered = _recent_week_dashboard(recent, [])
        self.assertIn("2026-07-13 to 2026-07-19", rendered)
        self.assertIn("Latest synced session: 2026-07-10", rendered)

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

    def test_station_profile_adds_nearby_seasonal_targets_not_seen_at_station(self) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                "UPDATE stations SET county_place_id = 1082, state_place_id = 48, public_location = 'Tompkins County, NY'"
            )
            conn.execute(
                """
                INSERT INTO stations (id, name, enabled, county_place_id, state_place_id)
                VALUES ('station-c', 'State Station', 1, 9999, 48)
                """
            )
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url, photo_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "station-b", 800, "2024-07-26", "2024-07-26T22:00:00-04:00",
                        404, "Targetus localis", "Local Target", "species",
                        "https://example.test/800", "https://example.test/800.jpg",
                    ),
                    (
                        "station-b", 801, "2026-07-20", "2026-07-20T22:00:00-04:00",
                        404, "Targetus localis", "Local Target", "species",
                        "https://example.test/801", "https://example.test/801.jpg",
                    ),
                    (
                        "station-b", 802, "2026-09-01", "2026-09-01T22:00:00-04:00",
                        405, "Targetus later", "Later Target", "species",
                        "https://example.test/802", None,
                    ),
                    (
                        "station-c", 803, "2026-07-21", "2026-07-21T22:00:00-04:00",
                        404, "Targetus localis", "Local Target", "species",
                        "https://example.test/803", None,
                    ),
                ],
            )

        profile = station_profile(self.settings, "station-a", today=date(2026, 7, 22))
        targets = profile["seasonal_targets"]
        target_ids = {item["taxon_id"] for item in targets["items"]}
        local_target = next(item for item in targets["items"] if item["taxon_id"] == 404)

        self.assertIn(404, target_ids)
        self.assertNotIn(405, target_ids)
        self.assertNotIn(101, target_ids, "already-recorded species are not new targets")
        self.assertEqual(local_target["scope"], "county")
        self.assertEqual(local_target["current_year_records"], 1)
        self.assertEqual(local_target["years"], 2)
        self.assertEqual(local_target["records"], 2, "state evidence is not mixed into county evidence")
        self.assertEqual(local_target["stations"], ["Station B"])
        self.assertEqual(local_target["window"], "Jul 20 to Jul 26")

    def test_station_profile_prefers_cached_nearby_inaturalist_targets(self) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO regional_watch_runs (
                    station_id, window_start, window_end, latitude, longitude, radius_km
                ) VALUES ('station-a', '2026-07-22', '2026-08-04', 42.4, -76.4, 100)
                """
            )
            conn.executemany(
                """
                INSERT INTO regional_watch_taxa (
                    station_id, window_start, taxon_id, taxon_name, common_name,
                    photo_url, record_count
                ) VALUES (?, '2026-07-22', ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "station-a", 101, "Species alpha", "Alpha",
                        "https://example.test/alpha.jpg", 99,
                    ),
                    (
                        "station-a", 404, "Targetus regionalis", "Regional Target",
                        "https://example.test/regional.jpg", 12,
                    ),
                ],
            )

        profile = station_profile(self.settings, "station-a", today=date(2026, 7, 22))
        targets = profile["seasonal_targets"]

        self.assertEqual(targets["source"], "nearby-inaturalist")
        self.assertEqual(targets["window"], "Jul 22 to Aug 4")
        self.assertEqual(targets["radius_km"], 100.0)
        self.assertEqual([item["taxon_id"] for item in targets["items"]], [404])
        self.assertEqual(targets["items"][0]["records"], 12)

    def test_station_profile_targets_use_weekly_timing_and_host_overlap(self) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO regional_watch_runs (
                    station_id, window_start, window_end, latitude, longitude, radius_km
                ) VALUES ('station-a', '2026-07-22', '2026-08-04', 42.4, -76.4, 100)
                """
            )
            conn.executemany(
                """
                INSERT INTO regional_watch_taxa (
                    station_id, window_start, taxon_id, taxon_name, common_name,
                    photo_url, record_count
                ) VALUES ('station-a', '2026-07-22', ?, ?, ?, ?, ?)
                """,
                [
                    (404, "Targetus regionalis", "Regional Target", None, 12),
                    (405, "Targetus later", "Later Target", None, 11),
                ],
            )
            conn.executemany(
                """
                INSERT INTO regional_watch_day_taxa (
                    station_id, calendar_day, taxon_id, taxon_name, common_name,
                    photo_url, record_count
                ) VALUES ('station-a', ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("2026-07-23", 404, "Targetus regionalis", "Regional Target", None, 7),
                    ("2026-07-30", 404, "Targetus regionalis", "Regional Target", None, 5),
                    ("2026-07-31", 405, "Targetus later", "Later Target", None, 11),
                ],
            )

        host_data = {
            "species": {
                "Species alpha": [{"family": "Fagaceae", "genus": "Quercus", "species": "alba"}],
                "Targetus regionalis": [{"family": "Fagaceae", "genus": "Quercus", "species": "rubra"}],
                "Targetus later": [{"family": "Rosaceae", "genus": "Prunus", "species": "serotina"}],
            },
            "match_level": {
                "Species alpha": "species",
                "Targetus regionalis": "species",
                "Targetus later": "species",
            },
        }
        with mock.patch("mothdash.analysis._load_host_plants", return_value=host_data):
            profile = station_profile(self.settings, "station-a", today=date(2026, 7, 22))

        targets = {item["taxon_id"]: item for item in profile["seasonal_targets"]["items"]}
        regional = targets[404]
        later = targets[405]

        self.assertEqual(regional["time_buckets"], ["this-week", "next-week"])
        self.assertEqual(regional["peak_buckets"], ["this-week"])
        self.assertEqual(regional["this_week_records"], 7)
        self.assertEqual(regional["next_week_records"], 5)
        self.assertEqual(regional["seasonal_score"], 10.75)
        self.assertEqual(later["time_buckets"], ["next-week"])
        self.assertEqual(later["peak_buckets"], ["next-week"])
        self.assertEqual(regional["host_matches"][0]["genus"], "Quercus")
        self.assertEqual(
            regional["host_matches"][0]["matching_species"],
            ["Alpha (Species alpha)"],
        )
        self.assertGreater(regional["prediction_score"], regional["records"])
        self.assertFalse(later["host_matches"])

    def test_distinctive_records_combine_firsts_and_network_rarity(self) -> None:
        # Taxon 102 already qualifies via the setUp fixture's county-first
        # flag and has exactly one tracked observation network-wide, so it
        # should land in "uniques". Build three more scenarios: a rare
        # (2-10 network records) non-first species, a common (>=10) species
        # with no flags that should be excluded entirely, and a common
        # (>=10) species that still qualifies because it carries a first
        # flag, to confirm flagged species aren't dropped just for being
        # common.
        # All three synthetic taxa are recorded at station-a only (never
        # station-b), so station_count stays at 1 and "first among tracked"
        # (which only applies once a taxon is shared by 2+ stations) can't
        # accidentally kick in and confound the network-count-only cases.
        with connect(self.settings.database) as conn:
            rows = []
            obs_id = 100
            # taxon 500: 5 network records at station-a, no flags.
            for _ in range(5):
                obs_id += 1
                rows.append(
                    ("station-a", obs_id, "2026-07-12", "2026-07-12T21:00:00-04:00",
                     500, "Species epsilon", "Epsilon", "species", f"https://example.test/{obs_id}")
                )
            # taxon 600: 12 network records at station-a, no flags.
            for _ in range(12):
                obs_id += 1
                rows.append(
                    ("station-a", obs_id, "2026-07-12", "2026-07-12T21:00:00-04:00",
                     600, "Species zeta", "Zeta", "species", f"https://example.test/{obs_id}")
                )
            # taxon 700: 11 network records at station-a, but with a
            # state-first flag, so it should still qualify despite being
            # common.
            for _ in range(11):
                obs_id += 1
                rows.append(
                    ("station-a", obs_id, "2026-07-12", "2026-07-12T21:00:00-04:00",
                     700, "Species eta", "Eta", "species", f"https://example.test/{obs_id}")
                )
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.execute(
                """
                INSERT INTO station_taxon_stats (
                    station_id, taxon_id, station_first_date,
                    is_county_first, is_state_first
                ) VALUES ('station-a', 700, '2026-07-12', 0, 1)
                """
            )

        profile = station_profile(self.settings, "station-a")
        distinctive = profile["distinctive_records"]

        unique_ids = {item["taxon_id"] for item in distinctive["uniques"]}
        rare_ids = {item["taxon_id"] for item in distinctive["rare"]}

        self.assertIn(102, unique_ids, "county-first species with 1 network record should be a unique")
        self.assertIn(500, rare_ids, "non-flagged species with 2-10 network records should qualify as rare")
        self.assertNotIn(600, unique_ids | rare_ids, "non-flagged species with >=10 network records should be excluded")
        self.assertIn(700, rare_ids, "a flagged first should qualify even with >=10 network records")

    def test_weekly_recap_reports_no_data_for_a_quiet_week(self) -> None:
        recap = weekly_recap(self.settings, "station-a", today=date(2026, 8, 12))

        self.assertFalse(recap["has_data"])
        self.assertEqual(recap["week_start"].isoformat(), "2026-08-03")
        self.assertEqual(recap["week_end"].isoformat(), "2026-08-09")

    def test_weekly_recap_summarizes_the_most_recently_completed_week(self) -> None:
        # Target week: Mon 2026-08-03 through Sun 2026-08-09. Previous week:
        # Mon 2026-07-27 through Sun 2026-08-02. Both are chosen well clear
        # of setUp's fixed 2026-07-10 fixture data so this test is
        # self-contained.
        with connect(self.settings.database) as conn:
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url, photo_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    # Returning species: also present the week before, so it
                    # should NOT show up in "new in town" this time.
                    ("station-a", 900, "2026-07-27", "2026-07-27T21:00:00-04:00",
                     801, "Species returning", "Returning", "species",
                     "https://example.test/900", "https://example.test/900.jpg"),
                    ("station-a", 901, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     801, "Species returning", "Returning", "species",
                     "https://example.test/901", "https://example.test/901.jpg"),
                    # Frequent flyer: 4 observations on 2 nights this week.
                    ("station-a", 902, "2026-08-04", "2026-08-04T21:00:00-04:00",
                     802, "Species frequent", "Frequent", "species",
                     "https://example.test/902", "https://example.test/902.jpg"),
                    ("station-a", 903, "2026-08-04", "2026-08-04T21:05:00-04:00",
                     802, "Species frequent", "Frequent", "species",
                     "https://example.test/903", "https://example.test/903.jpg"),
                    ("station-a", 904, "2026-08-06", "2026-08-06T21:00:00-04:00",
                     802, "Species frequent", "Frequent", "species",
                     "https://example.test/904", "https://example.test/904.jpg"),
                    # Brand-new-here species, first ever at station-a this week.
                    ("station-a", 905, "2026-08-07", "2026-08-07T21:00:00-04:00",
                     803, "Species newcomer", "Newcomer", "species",
                     "https://example.test/905", "https://example.test/905.jpg"),
                    # Also seen at station-b this week -> shared species.
                    ("station-b", 906, "2026-08-04", "2026-08-04T21:00:00-04:00",
                     802, "Species frequent", "Frequent", "species",
                     "https://example.test/906", "https://example.test/906.jpg"),
                ],
            )

        recap = weekly_recap(self.settings, "station-a", today=date(2026, 8, 12))

        self.assertTrue(recap["has_data"])
        self.assertEqual(recap["week_start"].isoformat(), "2026-08-03")
        self.assertEqual(recap["week_end"].isoformat(), "2026-08-09")
        self.assertEqual(recap["total_species"], 3)
        self.assertEqual(recap["previous_total_species"], 1)
        self.assertEqual(recap["trend"], 2)
        self.assertEqual(recap["nights_active"], 4)  # 08-03, 08-04, 08-06, 08-07
        self.assertEqual(recap["nights_total"], 7)

        new_in_town_ids = {item["taxon_id"] for item in recap["new_in_town"]}
        self.assertIn(803, new_in_town_ids, "brand-new species should appear in New in Town")
        self.assertNotIn(801, new_in_town_ids, "returning species should not appear in New in Town")

        self.assertEqual(recap["frequent_flyer"]["taxon_id"], 802)
        self.assertEqual(recap["frequent_flyer"]["count"], 3)

        self.assertEqual(recap["total_shared_species"], 1)
        self.assertEqual(recap["top_shared_station_name"], "Station B")
        self.assertEqual(recap["top_shared_count"], 1)

        # Only 3 species were seen this week, so all 3 surface as "moths of
        # the week", ordered rarest-first by network record count: 803 (1
        # network record), 801 (2), 802 (5, plus the station-b sighting).
        moth_ids = [item["taxon_id"] for item in recap["moths_of_the_week"]]
        self.assertEqual(moth_ids, [803, 801, 802])
        self.assertEqual(recap["new_in_town_count"], len(recap["new_in_town"]))

    def test_weekly_recap_caps_moths_of_the_week_at_three(self) -> None:
        with connect(self.settings.database) as conn:
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("station-a", 950, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     811, "Species one", "One", "species", "https://example.test/950"),
                    ("station-a", 951, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     812, "Species two", "Two", "species", "https://example.test/951"),
                    ("station-a", 952, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     813, "Species three", "Three", "species", "https://example.test/952"),
                    ("station-a", 953, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     814, "Species four", "Four", "species", "https://example.test/953"),
                    ("station-a", 954, "2026-08-03", "2026-08-03T21:00:00-04:00",
                     815, "Species five", "Five", "species", "https://example.test/954"),
                ],
            )

        recap = weekly_recap(self.settings, "station-a", today=date(2026, 8, 12))

        self.assertTrue(recap["has_data"])
        self.assertEqual(len(recap["moths_of_the_week"]), 3)

    def test_station_profile_exposes_night_coverage_and_upload_lag(self) -> None:
        with connect(self.settings.database) as conn:
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at, created_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "station-a", 8, "2026-07-11", "2026-07-11T20:00:00-04:00",
                        "2026-07-12T02:00:00Z", 103, "Species gamma", "Gamma", "species",
                        "https://example.test/8",
                    ),
                    (
                        "station-a", 9, "2026-07-12", "2026-07-12T20:00:00-04:00",
                        "2026-07-13T04:00:00Z", 104, "Species delta", "Delta", "species",
                        "https://example.test/9",
                    ),
                ],
            )

        profile = station_profile(self.settings, "station-a")

        self.assertEqual(profile["active_sessions"], 3)
        self.assertEqual(profile["seasonal_richness"][6]["nights"], 3)
        self.assertEqual(
            profile["yearly_coverage"],
            [{"year": 2026, "nights": 3, "species": 4}],
        )
        self.assertEqual(profile["upload_timing"]["timestamped_records"], 2)
        self.assertEqual(profile["upload_timing"]["median_lag_minutes"], 180)
        self.assertEqual(profile["accumulation"][-1]["nights"], 3)

    def test_historical_target_backtest_excludes_records_uploaded_after_checkpoint(self) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                "UPDATE stations SET county_place_id = 1082, state_place_id = 48"
            )
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at, created_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "station-a", 1000, "2026-06-01", "2026-06-01T22:00:00-04:00",
                        "2026-06-02T02:00:00Z", 101, "Species alpha", "Alpha", "species",
                        "https://example.test/1000",
                    ),
                    (
                        "station-b", 1001, "2025-07-10", "2025-07-10T22:00:00-04:00",
                        "2025-07-11T02:00:00Z", 404, "Targetus historicalis", "Historical Target", "species",
                        "https://example.test/1001",
                    ),
                    # This evidence appears after the Jul 6 checkpoint and must
                    # not become a retroactive target.
                    (
                        "station-b", 1002, "2026-07-10", "2026-07-10T22:00:00-04:00",
                        "2026-07-10T02:00:00Z", 405, "Targetus futureus", "Future Target", "species",
                        "https://example.test/1002",
                    ),
                    (
                        "station-a", 1003, "2026-07-12", "2026-07-12T22:00:00-04:00",
                        "2026-07-13T02:00:00Z", 404, "Targetus historicalis", "Historical Target", "species",
                        "https://example.test/1003",
                    ),
                    (
                        "station-a", 1004, "2026-07-12", "2026-07-12T22:00:00-04:00",
                        "2026-07-13T02:00:00Z", 405, "Targetus futureus", "Future Target", "species",
                        "https://example.test/1004",
                    ),
                ],
            )

        backtest = _historical_target_backtest(
            load_rows(self.settings),
            "station-a",
            _forecast_station_context(self.settings),
            date(2026, 7, 21),
            cutoff_hour=12,
            timezone="America/New_York",
            weeks=1,
        )

        self.assertEqual(backtest["checked_windows"], 1)
        self.assertEqual(backtest["target_count"], 1)
        self.assertEqual(backtest["target_hits"], 1)
        self.assertEqual(backtest["caught_new_species"], 1)
        self.assertEqual(backtest["median_hit_rank"], 1)

    def test_published_forecast_validation_uses_first_snapshot_per_day(self) -> None:
        with connect(self.settings.database) as conn:
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, observed_at, created_at,
                    taxon_id, taxon_name, common_name, rank, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "station-a", 1100, "2026-06-01", "2026-06-01T22:00:00-04:00",
                        "2026-06-02T02:00:00Z", 101, "Species alpha", "Alpha", "species",
                        "https://example.test/1100",
                    ),
                    (
                        "station-a", 1101, "2026-07-12", "2026-07-12T22:00:00-04:00",
                        "2026-07-13T02:00:00Z", 404, "Targetus published", "Published Target", "species",
                        "https://example.test/1101",
                    ),
                    (
                        "station-a", 1102, "2026-07-12", "2026-07-12T22:00:00-04:00",
                        "2026-07-13T02:00:00Z", 405, "Targetus later", "Later Target", "species",
                        "https://example.test/1102",
                    ),
                ],
            )

        first_targets = {
            "reference_day": date(2026, 7, 6),
            "source": "nearby-inaturalist",
            "items": [{"taxon_id": 404, "label": "Published Target"}],
        }
        later_targets = {
            "reference_day": date(2026, 7, 6),
            "source": "nearby-inaturalist",
            "items": [{"taxon_id": 405, "label": "Later Target"}],
        }
        store_forecast_snapshot(
            self.settings,
            "station-a",
            first_targets,
            snapshot_at=datetime(2026, 7, 6, 12, tzinfo=ZoneInfo("America/New_York")),
        )
        store_forecast_snapshot(
            self.settings,
            "station-a",
            later_targets,
            snapshot_at=datetime(2026, 7, 6, 18, tzinfo=ZoneInfo("America/New_York")),
        )

        validation = _published_forecast_validation(
            self.settings,
            load_rows(self.settings),
            "station-a",
            date(2026, 7, 22),
        )

        self.assertEqual(validation["available_snapshots"], 1)
        self.assertEqual(validation["checked_windows"], 1)
        self.assertEqual(validation["target_count"], 1)
        self.assertEqual(validation["target_hits"], 1)
        self.assertEqual(validation["caught_new_species"], 1)


if __name__ == "__main__":
    unittest.main()
