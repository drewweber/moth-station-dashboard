from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from mothdash.analysis import recent_days_taxa
from mothdash.config import Settings, Station, active_stations, historical_stations
from mothdash.db import init_db
from mothdash.render import _snapshot_payload
from mothdash.sync import sync_all


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


if __name__ == "__main__":
    unittest.main()
