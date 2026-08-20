from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch

from mothdash.config import Settings, Station
from mothdash.db import connect, init_db
from mothdash.inat_api import (
    ObservationResultLimitExceeded,
    iter_updated_observations,
)
from mothdash.sync import (
    OBS_INSERT,
    _observation_matches_taxon_scope,
    _observation_row,
    pending_station_updates,
    sync_station,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def observation(
    observation_id: int,
    taxon_id: int,
    name: str,
    *,
    rank: str = "species",
    ancestor_ids: list[int] | None = None,
    ancestry: str | None = None,
) -> dict:
    taxon = {
        "id": taxon_id,
        "name": name,
        "preferred_common_name": name,
        "rank": rank,
    }
    if ancestor_ids is not None:
        taxon["ancestor_ids"] = ancestor_ids
    if ancestry is not None:
        taxon["ancestry"] = ancestry
    return {
        "id": observation_id,
        "uuid": f"uuid-{observation_id}",
        "observed_on": "2026-07-19",
        "time_observed_at": "2026-07-19T22:00:00-04:00",
        "created_at": "2026-07-19T22:10:00-04:00",
        "updated_at": "2026-08-20T07:00:00-04:00",
        "taxon": taxon,
        "quality_grade": "needs_id",
        "user": {"login": "observer", "name": "Observer"},
        "location": "42.27,-76.49",
        "uri": f"https://www.inaturalist.org/observations/{observation_id}",
        "photos": [],
        "captive": False,
    }


class SyncReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            root=root,
            data_dir=root / "data",
            public_dir=root / "public",
            database=root / "data" / "mothdash.db",
            full_sync_interval_days=30,
        )
        self.station = Station(
            id="kingfisher",
            name="Kingfisher Hollow",
            enabled=True,
            active=True,
            query={"project_id": 249580},
        )
        init_db(self.settings.database)

    def seed_observation(self, item: dict) -> None:
        row = _observation_row(self.station.id, item)
        self.assertIsNotNone(row)
        with connect(self.settings.database) as conn:
            conn.execute(OBS_INSERT, row)

    def seed_sync(
        self,
        *,
        max_id: int,
        full: bool = True,
        synced_at: str = "2026-08-01 12:00:00",
        updates_through: str | None = "2026-08-19T12:00:00Z",
    ) -> None:
        with connect(self.settings.database) as conn:
            conn.execute(
                """
                INSERT INTO sync_log (
                    station_id, synced_at, full_sync, observations_added,
                    observations_seen, max_inat_obs_id, updates_through
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    self.station.id,
                    synced_at,
                    int(full),
                    0,
                    0,
                    max_id,
                    updates_through,
                ),
            )

    def cached_rows(self) -> list[dict]:
        with connect(self.settings.database) as conn:
            rows = conn.execute(
                "SELECT * FROM observations WHERE station_id = ? ORDER BY inat_obs_id",
                (self.station.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_reidentification_replaces_cached_taxon_without_advancing_id_cursor(
        self,
        new_observations_mock,
        updated_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Cameraria ohridella", ancestor_ids=[47157])
        )
        self.seed_sync(max_id=200)
        updated_observations_mock.return_value = [
            observation(
                100,
                417061,
                "Aethes interruptofasciata",
                ancestor_ids=[47157],
            )
        ]

        added, seen = sync_station(self.settings, self.station)

        self.assertEqual((added, seen), (0, 1))
        row = self.cached_rows()[0]
        self.assertEqual(row["taxon_id"], 417061)
        self.assertEqual(row["taxon_name"], "Aethes interruptofasciata")
        new_observations_mock.assert_called_once_with(
            {
                "project_id": 249580,
                "taxon_id": 47157,
                "without_taxon_id": 47224,
            },
            user_agent=self.settings.user_agent,
            id_above=200,
        )
        updated_observations_mock.assert_called_once_with(
            {"project_id": 249580},
            user_agent=self.settings.user_agent,
            updated_since="2026-08-19T11:55:00Z",
        )
        with connect(self.settings.database) as conn:
            log = conn.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(log["max_inat_obs_id"], 200)
        self.assertEqual(log["observations_reconciled"], 1)
        self.assertEqual(log["observations_removed"], 0)
        self.assertEqual(log["updates_through"], "2026-08-20T12:00:00Z")

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_reconciliation_removes_broader_butterfly_and_non_moth_ids(
        self,
        _new_observations_mock,
        updated_observations_mock,
        _now_mock,
    ) -> None:
        for observation_id in (100, 101, 102):
            self.seed_observation(
                observation(
                    observation_id,
                    200000 + observation_id,
                    f"Old moth {observation_id}",
                    ancestor_ids=[47157],
                )
            )
        self.seed_sync(max_id=200)
        updated_observations_mock.return_value = [
            observation(100, 146626, "Aethes", rank="genus", ancestor_ids=[47157]),
            observation(
                101,
                48662,
                "Danaus plexippus",
                ancestor_ids=[47157, 47224],
            ),
            observation(102, 47158, "Bird", ancestor_ids=[1, 3]),
        ]

        sync_station(self.settings, self.station)

        self.assertEqual(self.cached_rows(), [])
        with connect(self.settings.database) as conn:
            log = conn.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(log["observations_reconciled"], 3)
        self.assertEqual(log["observations_removed"], 3)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_old_observation_updated_into_scope_is_inserted_below_id_cursor(
        self,
        _new_observations_mock,
        updated_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_sync(max_id=200)
        updated_observations_mock.return_value = [
            observation(100, 417061, "Aethes interruptofasciata", ancestor_ids=[47157])
        ]

        added, _seen = sync_station(self.settings, self.station)

        self.assertEqual(added, 1)
        self.assertEqual(self.cached_rows()[0]["inat_obs_id"], 100)
        with connect(self.settings.database) as conn:
            log = conn.execute(
                "SELECT max_inat_obs_id FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(log["max_inat_obs_id"], 200)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations")
    def test_first_sync_is_full_and_skips_update_crawl(
        self,
        new_observations_mock,
        updated_observations_mock,
        _now_mock,
    ) -> None:
        new_observations_mock.return_value = [
            observation(100, 417061, "Aethes interruptofasciata", ancestor_ids=[47157])
        ]

        sync_station(self.settings, self.station)

        updated_observations_mock.assert_not_called()
        with connect(self.settings.database) as conn:
            log = conn.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(log["full_sync"], 1)
        self.assertEqual(log["max_inat_obs_id"], 100)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations", return_value=[])
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_latest_full_log_can_reset_cursor_below_historical_max(
        self,
        new_observations_mock,
        _updated_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_sync(max_id=500, full=False, synced_at="2026-07-31 12:00:00")
        self.seed_sync(max_id=400, full=True, synced_at="2026-08-01 12:00:00")

        sync_station(self.settings, self.station)

        self.assertEqual(new_observations_mock.call_args.kwargs["id_above"], 400)

        with patch("mothdash.sync.latest_observation_id", return_value=401):
            pending = pending_station_updates(self.settings, [self.station])
        self.assertEqual([item.id for item in pending], [self.station.id])

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.latest_observation_id", return_value=0)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_overdue_full_sync_removes_rows_absent_from_current_query(
        self,
        _new_observations_mock,
        updated_observations_mock,
        _latest_observation_id_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Cameraria ohridella", ancestor_ids=[47157])
        )
        self.seed_sync(
            max_id=100,
            synced_at="2026-07-01 12:00:00",
            updates_through="2026-07-01T12:00:00Z",
        )

        sync_station(self.settings, self.station)

        self.assertEqual(self.cached_rows(), [])
        updated_observations_mock.assert_not_called()
        with connect(self.settings.database) as conn:
            log = conn.execute(
                "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(log["full_sync"], 1)
        self.assertEqual(log["observations_removed"], 1)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.latest_observation_id", return_value=101)
    @patch("mothdash.sync.iter_observations", return_value=[])
    def test_unexpected_empty_full_sync_preserves_populated_cache(
        self,
        _new_observations_mock,
        _latest_observation_id_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Cameraria ohridella", ancestor_ids=[47157])
        )
        self.seed_sync(max_id=100)

        with self.assertRaisesRegex(RuntimeError, "source query still contains"):
            sync_station(self.settings, self.station, full=True)

        self.assertEqual(
            [row["inat_obs_id"] for row in self.cached_rows()],
            [100],
        )
        with connect(self.settings.database) as conn:
            log_count = conn.execute("SELECT COUNT(*) AS c FROM sync_log").fetchone()["c"]
        self.assertEqual(log_count, 1)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_observations")
    def test_failed_full_sync_rolls_back_delete_and_partial_inserts(
        self,
        new_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Cameraria ohridella", ancestor_ids=[47157])
        )
        self.seed_sync(max_id=100)

        def failing_results():
            yield observation(200, 417061, "New moth", ancestor_ids=[47157])
            raise RuntimeError("iNaturalist failed")

        new_observations_mock.return_value = failing_results()

        with self.assertRaisesRegex(RuntimeError, "iNaturalist failed"):
            sync_station(self.settings, self.station, full=True)

        rows = self.cached_rows()
        self.assertEqual([row["inat_obs_id"] for row in rows], [100])
        with connect(self.settings.database) as conn:
            log_count = conn.execute("SELECT COUNT(*) AS c FROM sync_log").fetchone()["c"]
        self.assertEqual(log_count, 1)

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch("mothdash.sync.iter_updated_observations")
    @patch("mothdash.sync.iter_observations")
    def test_failed_incremental_sync_rolls_back_and_keeps_watermark(
        self,
        new_observations_mock,
        updated_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Cameraria ohridella", ancestor_ids=[47157])
        )
        self.seed_sync(max_id=200)

        def failing_results():
            yield observation(201, 417061, "New moth", ancestor_ids=[47157])
            raise RuntimeError("iNaturalist failed")

        new_observations_mock.return_value = failing_results()

        with self.assertRaisesRegex(RuntimeError, "iNaturalist failed"):
            sync_station(self.settings, self.station)

        self.assertEqual(
            [row["inat_obs_id"] for row in self.cached_rows()],
            [100],
        )
        updated_observations_mock.assert_not_called()
        with connect(self.settings.database) as conn:
            logs = conn.execute(
                "SELECT max_inat_obs_id, updates_through FROM sync_log ORDER BY id"
            ).fetchall()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["max_inat_obs_id"], 200)
        self.assertEqual(logs[0]["updates_through"], "2026-08-19T12:00:00Z")

    def test_taxon_scope_uses_ancestry_and_exclusion_wins(self) -> None:
        moth = observation(1, 417061, "Moth", ancestor_ids=None, ancestry="1/47157")
        butterfly = observation(
            2,
            48662,
            "Butterfly",
            ancestor_ids=[1, 47157, 47224],
        )
        order_itself = observation(3, 47157, "Lepidoptera", ancestor_ids=[])

        self.assertTrue(_observation_matches_taxon_scope(self.settings, moth))
        self.assertFalse(_observation_matches_taxon_scope(self.settings, butterfly))
        self.assertTrue(_observation_matches_taxon_scope(self.settings, order_itself))

    @patch("mothdash.sync._utc_now", return_value=NOW)
    @patch(
        "mothdash.sync.iter_updated_observations",
        side_effect=ObservationResultLimitExceeded("too many updates"),
    )
    @patch("mothdash.sync.iter_observations")
    def test_oversized_update_window_falls_back_to_full_reconciliation(
        self,
        observations_mock,
        _updated_observations_mock,
        _now_mock,
    ) -> None:
        self.seed_observation(
            observation(100, 126088, "Old moth", ancestor_ids=[47157])
        )
        self.seed_sync(max_id=200)
        replacement = observation(150, 417061, "Current moth", ancestor_ids=[47157])
        observations_mock.side_effect = [[], [replacement]]

        sync_station(self.settings, self.station)

        self.assertEqual(
            [row["taxon_name"] for row in self.cached_rows()],
            ["Current moth"],
        )
        self.assertEqual(
            [item.kwargs["id_above"] for item in observations_mock.call_args_list],
            [200, 0],
        )
        with connect(self.settings.database) as conn:
            latest = conn.execute(
                "SELECT full_sync, max_inat_obs_id FROM sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(latest["full_sync"], 1)
        self.assertEqual(latest["max_inat_obs_id"], 150)


class SyncLogMigrationTests(unittest.TestCase):
    def test_init_db_adds_reconciliation_columns_to_legacy_sync_log(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "legacy.db"
            with closing(sqlite3.connect(database)) as conn:
                conn.execute(
                    """
                    CREATE TABLE sync_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        station_id TEXT NOT NULL,
                        synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        full_sync INTEGER NOT NULL,
                        observations_added INTEGER NOT NULL,
                        observations_seen INTEGER NOT NULL,
                        max_inat_obs_id INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO sync_log (
                        station_id, full_sync, observations_added,
                        observations_seen, max_inat_obs_id
                    ) VALUES ('kingfisher', 1, 10, 10, 200)
                    """
                )
                conn.commit()

            init_db(database)

            with connect(database) as conn:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(sync_log)")
                }
                legacy_row = conn.execute("SELECT * FROM sync_log").fetchone()
            self.assertTrue(
                {"observations_reconciled", "observations_removed", "updates_through"}
                <= columns
            )
            self.assertEqual(legacy_row["observations_reconciled"], 0)
            self.assertEqual(legacy_row["observations_removed"], 0)
            self.assertIsNone(legacy_row["updates_through"])


class UpdatedObservationApiTests(unittest.TestCase):
    @patch("mothdash.inat_api.PER_PAGE", 2)
    @patch("mothdash.inat_api.get_json")
    def test_updated_crawl_uses_id_cursor_not_deep_pages(self, get_json_mock) -> None:
        get_json_mock.side_effect = [
            {"total_results": 3, "results": [{"id": 1}, {"id": 2}]},
            {"total_results": 1, "results": [{"id": 9}]},
        ]

        rows = list(
            iter_updated_observations(
                {"project_id": 249580},
                user_agent="test-agent",
                updated_since="2026-08-19T00:00:00Z",
                max_results=10,
            )
        )

        self.assertEqual([row["id"] for row in rows], [1, 2, 9])
        self.assertEqual(
            get_json_mock.call_args_list,
            [
                call(
                    "observations",
                    user_agent="test-agent",
                    per_page=2,
                    order_by="id",
                    order="asc",
                    id_above=0,
                    project_id=249580,
                    updated_since="2026-08-19T00:00:00Z",
                ),
                call(
                    "observations",
                    user_agent="test-agent",
                    per_page=2,
                    order_by="id",
                    order="asc",
                    id_above=2,
                    project_id=249580,
                    updated_since="2026-08-19T00:00:00Z",
                ),
            ],
        )
        self.assertNotIn("page", get_json_mock.call_args_list[0].kwargs)

    @patch("mothdash.inat_api.get_json")
    def test_oversized_update_window_fails_before_yielding(self, get_json_mock) -> None:
        get_json_mock.return_value = {"total_results": 11, "results": [{"id": 1}]}

        with self.assertRaises(ObservationResultLimitExceeded):
            list(
                iter_updated_observations(
                    {"project_id": 249580},
                    user_agent="test-agent",
                    updated_since="2026-01-01T00:00:00Z",
                    max_results=10,
                )
            )

    @patch("mothdash.inat_api.PER_PAGE", 2)
    @patch("mothdash.inat_api.get_json")
    def test_growing_update_window_is_bounded_cumulatively(self, get_json_mock) -> None:
        get_json_mock.side_effect = [
            {"total_results": 2, "results": [{"id": 1}, {"id": 2}]},
            {"total_results": 1, "results": [{"id": 3}]},
        ]

        iterator = iter_updated_observations(
            {"project_id": 249580},
            user_agent="test-agent",
            updated_since="2026-01-01T00:00:00Z",
            max_results=2,
        )
        self.assertEqual(next(iterator)["id"], 1)
        self.assertEqual(next(iterator)["id"], 2)
        with self.assertRaises(ObservationResultLimitExceeded):
            next(iterator)


if __name__ == "__main__":
    unittest.main()
