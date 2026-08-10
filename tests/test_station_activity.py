from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from mothdash.analysis import recent_days_taxa
from mothdash.config import Settings, Station, active_stations, historical_stations
from mothdash.db import connect, init_db
from mothdash.render import _snapshot_payload
from mothdash.sync import pending_station_updates, refresh_station_stats, sync_all


def station(station_id: str, *, enabled: bool = True, active: bool = True) -> Station:
    return Station(
        id=station_id,
        name=station_id.title(),
        enabled=enabled,
        active=active,
        query={"project_id": station_id},
        county_place_id=1082,
        state_place_id=48,
    )


class StationActivityTests(unittest.TestCase):
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
        self.active = station("active")
        self.inactive = station("inactive", active=False)
        self.disabled = station("disabled", enabled=False)
        self.stations = [self.active, self.inactive, self.disabled]

    def test_station_selectors_separate_history_from_current_work(self) -> None:
        self.assertEqual(
            [item.id for item in historical_stations(self.stations)],
            ["active", "inactive"],
        )
        self.assertEqual(
            [item.id for item in active_stations(self.stations)],
            ["active"],
        )

    def test_station_queries_get_site_moth_scope(self) -> None:
        self.assertEqual(self.settings.taxon_scope, "moths")
        self.assertEqual(
            self.active.api_params(self.settings),
            {
                "project_id": "active",
                "taxon_id": 47157,
                "without_taxon_id": 47224,
            },
        )

    def test_live_snapshot_contains_only_active_stations(self) -> None:
        payload = _snapshot_payload(self.settings, self.stations, [])
        self.assertEqual(
            [item["id"] for item in payload["stations"]],
            ["active"],
        )

    def test_empty_database_still_reports_current_week_range(self) -> None:
        payload = recent_days_taxa(
            self.settings,
            now=datetime(2026, 7, 15, 20, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertEqual(payload["period_label"], "2026-07-09 to 2026-07-15")
        self.assertIsNone(payload["latest_session"])
        self.assertEqual(payload["taxa"], [])

    @patch("mothdash.sync.refresh_station_stats")
    @patch("mothdash.sync.sync_station", return_value=(1, 1))
    def test_sync_and_stats_receive_only_active_station(
        self,
        sync_station_mock,
        refresh_station_stats_mock,
    ) -> None:
        sync_all(self.settings, self.stations)

        sync_station_mock.assert_called_once_with(
            self.settings,
            self.active,
            full=False,
        )
        refresh_station_stats_mock.assert_called_once_with(
            self.settings,
            [self.active],
        )

    @patch("mothdash.sync.latest_observation_id")
    def test_pending_updates_compare_remote_id_with_sync_cursor(self, latest_mock) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO sync_log (
                    station_id, full_sync, observations_added, observations_seen,
                    max_inat_obs_id
                ) VALUES ('active', 0, 1, 1, 100)
                """
            )

        latest_mock.return_value = 100
        self.assertEqual(pending_station_updates(self.settings, self.stations), [])

        latest_mock.return_value = 101
        self.assertEqual(
            [station.id for station in pending_station_updates(self.settings, self.stations)],
            ["active"],
        )
        latest_mock.assert_called_with(
            self.settings.user_agent,
            **self.active.api_params(self.settings),
        )

    @patch("mothdash.sync.first_observed_date")
    def test_first_record_refresh_keeps_ordered_budget_and_cached_values(
        self, first_date_mock
    ) -> None:
        with connect(self.settings.database) as conn:
            conn.executemany(
                """
                INSERT INTO observations (
                    station_id, inat_obs_id, observed_on, taxon_id, taxon_name, rank
                ) VALUES (?, ?, ?, ?, ?, 'species')
                """,
                [
                    ("active", 1, "2026-06-01", 101, "First species"),
                    ("active", 2, "2026-06-02", 102, "Second species"),
                    ("active", 3, "2026-06-03", 103, "Outside budget"),
                ],
            )

        def first_date(_user_agent, *, taxon_id, place_id):
            return {
                (101, 1082): "2026-06-01",
                (101, 48): "2026-05-30",
                (102, 1082): "2026-06-10",
                (102, 48): "2026-06-02",
                (103, 1082): "2026-06-03",
                (103, 48): "2026-06-03",
            }[(taxon_id, place_id)]

        first_date_mock.side_effect = first_date
        limited_settings = Settings(
            root=self.settings.root,
            data_dir=self.settings.data_dir,
            public_dir=self.settings.public_dir,
            database=self.settings.database,
            stats_refresh_limit=2,
        )

        refresh_station_stats(limited_settings, [self.active])

        with connect(self.settings.database) as conn:
            rows = conn.execute(
                """
                SELECT taxon_id, county_first_date, state_first_date,
                       is_county_first, is_state_first
                FROM station_taxon_stats
                ORDER BY taxon_id
                """
            ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [
                (101, "2026-06-01", "2026-05-30", 1, 0),
                (102, "2026-06-10", "2026-06-02", 1, 1),
            ],
        )
        self.assertEqual(first_date_mock.call_count, 4)

        refresh_station_stats(limited_settings, [self.active])
        self.assertEqual(
            first_date_mock.call_count,
            6,
            "the next run refreshes only the taxon outside the first budget",
        )
        refresh_station_stats(limited_settings, [self.active])
        self.assertEqual(first_date_mock.call_count, 6, "fresh cached values are reused")


if __name__ == "__main__":
    unittest.main()
