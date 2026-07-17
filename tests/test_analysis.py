from datetime import date, datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

from mothdash.analysis import (
    current_session_date,
    diversify_by_station,
    flight_season_date,
    session_date,
    station_overlap_similarity,
)


class SessionDateTests(unittest.TestCase):
    def test_morning_observation_belongs_to_previous_evening(self) -> None:
        self.assertEqual(
            session_date("2026-07-15", "2026-07-15T08:30:00-04:00", 12),
            date(2026, 7, 14),
        )

    def test_noon_observation_stays_on_calendar_date(self) -> None:
        self.assertEqual(
            session_date("2026-07-15", "2026-07-15T12:00:00-04:00", 12),
            date(2026, 7, 15),
        )

    def test_missing_timestamp_uses_observed_date(self) -> None:
        self.assertEqual(
            session_date("2026-07-15", None, 12),
            date(2026, 7, 15),
        )


class FlightSeasonTests(unittest.TestCase):
    def test_january_belongs_to_previous_winter(self) -> None:
        season_year, normalized = flight_season_date(date(2026, 1, 8))
        self.assertEqual(season_year, 2025)
        self.assertEqual(normalized, date(2001, 1, 8))


class CurrentSessionDateTests(unittest.TestCase):
    def test_before_noon_belongs_to_previous_event(self) -> None:
        now = datetime(2026, 7, 15, 11, 59, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(
            current_session_date(12, "America/New_York", now),
            date(2026, 7, 14),
        )

    def test_noon_starts_current_calendar_date_event(self) -> None:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(
            current_session_date(12, "America/New_York", now),
            date(2026, 7, 15),
        )

    def test_before_noon_crosses_year_boundary(self) -> None:
        now = datetime(2026, 1, 1, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(
            current_session_date(12, "America/New_York", now),
            date(2025, 12, 31),
        )


class StationOverlapSimilarityTests(unittest.TestCase):
    def test_small_subset_of_large_station_is_fully_similar(self) -> None:
        # 70 shared species, small station has exactly 70, large station has 700:
        # the small station's entire list is contained in the large one's, so
        # this should read as 100% similar, not diluted to 10% (Jaccard would
        # give 70 / (70 + 700 - 70) = 10%).
        self.assertEqual(station_overlap_similarity(70, 70, 700), 1.0)

    def test_identical_stations_are_fully_similar(self) -> None:
        self.assertEqual(station_overlap_similarity(50, 50, 50), 1.0)

    def test_no_shared_species_is_zero(self) -> None:
        self.assertEqual(station_overlap_similarity(0, 40, 60), 0.0)

    def test_partial_overlap_uses_smaller_station_as_denominator(self) -> None:
        self.assertAlmostEqual(station_overlap_similarity(30, 40, 200), 0.75)

    def test_empty_station_is_zero_not_a_division_error(self) -> None:
        self.assertEqual(station_overlap_similarity(0, 0, 100), 0.0)


class DiversifyByStationTests(unittest.TestCase):
    def test_single_station_burst_does_not_crowd_out_other_stations(self) -> None:
        # Station A uploaded 10 observations in one batch (all most recent);
        # station B has 1 older observation. A naive "most recent N" slice
        # would show only station A. Diversification should surface B too.
        rows = [{"station_id": "a", "url": f"a{i}"} for i in range(10)]
        rows.append({"station_id": "b", "url": "b0"})
        result = diversify_by_station(rows, limit=3, dedupe_key="url")
        station_ids = [row["station_id"] for row in result]
        self.assertIn("b", station_ids)
        self.assertEqual(len(result), 3)

    def test_respects_limit_and_order_when_stations_exhausted(self) -> None:
        rows = [{"station_id": "a", "url": "a0"}, {"station_id": "b", "url": "b0"}]
        result = diversify_by_station(rows, limit=5, dedupe_key="url")
        self.assertEqual(len(result), 2)

    def test_dedupes_by_key(self) -> None:
        rows = [
            {"station_id": "a", "url": "shared"},
            {"station_id": "b", "url": "shared"},
            {"station_id": "c", "url": "unique"},
        ]
        result = diversify_by_station(rows, limit=5, dedupe_key="url")
        urls = [row["url"] for row in result]
        self.assertEqual(urls.count("shared"), 1)



class DashboardInsightsRecencyTests(unittest.TestCase):
    """dashboard_insights() should drop date-anchored stories once they're
    old news in real wall-clock time, while durable current-state stories
    (like the network's most widely shared species) keep showing up."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        from mothdash.config import Settings, Station
        from mothdash.db import connect, init_db
        from mothdash.sync import _upsert_station

        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.settings = Settings(
            root=root,
            data_dir=root / "data",
            public_dir=root / "public",
            database=root / "data" / "mothdash.db",
        )
        self.stations = [
            Station(id="alpha", name="Alpha", enabled=True, active=True, query={}),
            Station(id="beta", name="Beta", enabled=True, active=True, query={}),
        ]
        init_db(self.settings.database)
        for station in self.stations:
            _upsert_station(self.settings, station)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _insert_observation(
        self, *, station_id, obs_id, taxon_id, taxon_name, common_name, observed_on
    ) -> None:
        from mothdash.db import connect

        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, uuid, observed_on, observed_at, created_at,
                    updated_at, taxon_id, taxon_name, common_name, rank, quality_grade,
                    observer_login, observer_name, latitude, longitude, url, photo_url,
                    photo_attribution, photo_license, captive
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    station_id, obs_id, f"uuid-{obs_id}", observed_on, f"{observed_on}T21:00:00Z",
                    f"{observed_on}T21:05:00Z", f"{observed_on}T21:05:00Z",
                    taxon_id, taxon_name, common_name, "species", "research",
                    "tester", "Tester", 42.0, -76.0, f"https://example.com/{obs_id}",
                    None, None, None, 0,
                ),
            )

    def test_same_night_connection_disappears_once_stale(self) -> None:
        from mothdash.analysis import dashboard_insights

        # Give the species prior history at both stations so the shared
        # night isn't *also* a network/station first (which would otherwise
        # win the single story slot for this species and mask the story
        # under test). Both stations recorded the same species on the same
        # night, which produces a "Same-night connection" story anchored to
        # that date.
        earlier_date = date(2025, 6, 1)
        event_date = date(2026, 6, 1)
        self._insert_observation(
            station_id="alpha", obs_id=1, taxon_id=100,
            taxon_name="Actias luna", common_name="Luna Moth",
            observed_on=earlier_date.isoformat(),
        )
        self._insert_observation(
            station_id="beta", obs_id=2, taxon_id=100,
            taxon_name="Actias luna", common_name="Luna Moth",
            observed_on=earlier_date.isoformat(),
        )
        self._insert_observation(
            station_id="alpha", obs_id=3, taxon_id=100,
            taxon_name="Actias luna", common_name="Luna Moth",
            observed_on=event_date.isoformat(),
        )
        self._insert_observation(
            station_id="beta", obs_id=4, taxon_id=100,
            taxon_name="Actias luna", common_name="Luna Moth",
            observed_on=event_date.isoformat(),
        )

        fresh = dashboard_insights(self.settings, today=event_date + timedelta(days=1))
        stale = dashboard_insights(self.settings, today=event_date + timedelta(days=30))

        self.assertTrue(
            any(item["category"] == "Same-night connection" for item in fresh),
            "expected a same-night connection story while the event is still recent",
        )
        self.assertFalse(
            any(item["category"] == "Same-night connection" for item in stale),
            "same-night connection story should not persist once it's old news",
        )

    def test_under_documented_find_lists_existing_flight_dates(self) -> None:
        from mothdash.analysis import dashboard_insights

        earlier_date = date(2026, 5, 1)
        event_date = date(2026, 6, 1)
        self._insert_observation(
            station_id="alpha", obs_id=11, taxon_id=110,
            taxon_name="Sparse moth", common_name="Sparse Moth",
            observed_on=earlier_date.isoformat(),
        )
        self._insert_observation(
            station_id="alpha", obs_id=12, taxon_id=110,
            taxon_name="Sparse moth", common_name="Sparse Moth",
            observed_on=event_date.isoformat(),
        )

        insights = dashboard_insights(self.settings, today=event_date + timedelta(days=1))
        insight = next(item for item in insights if item["category"] == "Under-documented find")
        self.assertIn("Known tracked dates so far: 2026-05-01, 2026-06-01.", insight["body"])

    def test_common_two_station_connection_is_not_a_feed_story(self) -> None:
        from mothdash.analysis import dashboard_insights

        earlier_date = date(2026, 5, 1)
        event_date = date(2026, 6, 1)
        for station_id, obs_id, observed_on in [
            ("alpha", 21, earlier_date),
            ("beta", 22, earlier_date),
            ("alpha", 23, event_date),
            ("beta", 24, event_date),
        ]:
            self._insert_observation(
                station_id=station_id, obs_id=obs_id, taxon_id=120,
                taxon_name="Common moth", common_name="Common Moth",
                observed_on=observed_on.isoformat(),
            )

        insights = dashboard_insights(self.settings, today=event_date + timedelta(days=1))
        self.assertFalse(
            any(item["category"] == "Same-night connection" for item in insights),
        )

    def test_shared_fauna_ranking_is_not_date_gated(self) -> None:
        from mothdash.analysis import dashboard_insights

        event_date = date(2026, 6, 1)
        self._insert_observation(
            station_id="alpha", obs_id=1, taxon_id=200,
            taxon_name="Catocala relicta", common_name="White Underwing",
            observed_on=event_date.isoformat(),
        )
        self._insert_observation(
            station_id="beta", obs_id=2, taxon_id=200,
            taxon_name="Catocala relicta", common_name="White Underwing",
            observed_on=event_date.isoformat(),
        )

        # Even long after the observations were made, the current
        # most-widely-shared-species ranking is a standing fact, not news
        # about one specific night, so it should still be reported.
        stale = dashboard_insights(self.settings, today=event_date + timedelta(days=365))
        self.assertTrue(
            any(item["category"] == "Shared fauna" for item in stale),
            "durable ranking insights should not be date-gated",
        )


if __name__ == "__main__":
    unittest.main()
