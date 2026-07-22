from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import copy
import unittest

from mothdash.analysis import habitat_summary
from mothdash.config import Settings
from mothdash.db import connect, init_db
from mothdash.render import _habitat_summary


FAKE_HOST_DATA = {
    "metadata": {
        "source": "Test HOSTS fixture",
        "source_url": "https://example.test/hosts",
        "coverage": "Synthetic fixture, not the real vendored dataset.",
        "retrieved_at": "2026-01-01",
    },
    "species": {
        # Confirmed at station-a. Shares genus "Quercus" with two others.
        "Catocala confirmed": [
            {"family": "Fagaceae", "genus": "Quercus", "species": "alba"},
        ],
        # Confirmed at station-b -- a "network" candidate for station-a.
        "Panopoda network": [
            {"family": "Fagaceae", "genus": "Quercus", "species": ""},
        ],
        # Never tracked by any station -- a "regional" candidate.
        "Actias regional": [
            {"family": "Fagaceae", "genus": "Quercus", "species": "rubra"},
        ],
        # Shares no genus with anything confirmed -- should never surface.
        "Unrelated species": [
            {"family": "Rosaceae", "genus": "Prunus", "species": ""},
        ],
    },
    "match_level": {
        "Catocala confirmed": "species",
        "Panopoda network": "species",
        "Actias regional": "species",
        "Unrelated species": "species",
    },
    "taxa": {
        "Catocala confirmed": {"taxon_id": 1001, "common_name": "Confirmed Underwing"},
        "Panopoda network": {"taxon_id": 1002, "common_name": "Network Panopoda"},
        "Actias regional": {"taxon_id": 1003, "common_name": "Regional Actias"},
        "Unrelated species": {"taxon_id": 1004, "common_name": "Unrelated Species"},
    },
}


class HabitatSummaryTests(unittest.TestCase):
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

    def _seed(self) -> None:
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
                    ("station-a", 1, "2026-07-10", "2026-07-10T21:00:00-04:00",
                     1001, "Catocala confirmed", "Confirmed Underwing", "species",
                     "https://example.test/obs/1"),
                    ("station-b", 2, "2026-07-10", "2026-07-10T21:00:00-04:00",
                     1002, "Panopoda network", "Network Panopoda", "species",
                     "https://example.test/obs/2"),
                ],
            )

    def test_reports_no_data_without_confirmed_species(self) -> None:
        with mock.patch("mothdash.analysis._load_host_plants", return_value=FAKE_HOST_DATA):
            result = habitat_summary(self.settings, "station-a")
        self.assertFalse(result["has_data"])

    def test_reports_no_data_without_reference_file(self) -> None:
        self._seed()
        with mock.patch(
            "mothdash.analysis._load_host_plants",
            return_value={"species": {}, "taxa": {}, "match_level": {}, "metadata": {}},
        ):
            result = habitat_summary(self.settings, "station-a")
        self.assertFalse(result["has_data"])

    def test_splits_candidates_into_network_and_regional_and_links_taxa(self) -> None:
        self._seed()
        with mock.patch("mothdash.analysis._load_host_plants", return_value=FAKE_HOST_DATA):
            result = habitat_summary(self.settings, "station-a")

        self.assertTrue(result["has_data"])
        self.assertEqual(result["confirmed_count"], 1)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["unmatched_count"], 0)

        self.assertEqual(len(result["host_plants"]), 1)
        self.assertEqual(result["host_plants"][0]["taxon_id"], 1001)
        self.assertEqual(result["host_plants"][0]["url"], "https://example.test/obs/1")

        network_ids = {c["taxon_id"] for c in result["network_candidates"]}
        regional_ids = {c["taxon_id"] for c in result["regional_candidates"]}
        self.assertEqual(network_ids, {1002})
        self.assertEqual(regional_ids, {1003})
        # The unrelated species (different host genus) should never surface.
        self.assertNotIn(1004, network_ids | regional_ids)

        for candidate in result["network_candidates"] + result["regional_candidates"]:
            self.assertEqual(
                candidate["inat_taxon_url"],
                f"https://www.inaturalist.org/taxa/{candidate['taxon_id']}",
            )

    def test_render_links_candidates_to_inaturalist_taxon_pages(self) -> None:
        self._seed()
        with mock.patch("mothdash.analysis._load_host_plants", return_value=FAKE_HOST_DATA):
            result = habitat_summary(self.settings, "station-a")
        html = _habitat_summary(result)

        self.assertIn("https://www.inaturalist.org/taxa/1002", html)
        self.assertIn("https://www.inaturalist.org/taxa/1003", html)
        self.assertIn("https://example.test/obs/1", html)
        self.assertIn('<details class="habitat-info">', html)
        self.assertIn("About this data", html)

    def test_profile_renders_a_bounded_preview_and_full_archive_link(self) -> None:
        self._seed()
        with mock.patch("mothdash.analysis._load_host_plants", return_value=FAKE_HOST_DATA):
            result = habitat_summary(self.settings, "station-a")
        second_row = dict(result["host_plants"][0])
        second_row["label"] = "Later Host Moth"
        result["host_plants"].append(second_row)
        result["host_preview"] = [result["host_plants"][0]]

        preview_html = _habitat_summary(result, "station-a-habitat.html")
        archive_html = _habitat_summary(result, full=True)

        self.assertIn('href="station-a-habitat.html"', preview_html)
        self.assertNotIn("Later Host Moth", preview_html)
        self.assertIn("Later Host Moth", archive_html)

    def test_specific_host_links_rank_above_generalist_overlap(self) -> None:
        self._seed()
        host_data = copy.deepcopy(FAKE_HOST_DATA)
        host_data["species"]["Catocala confirmed"].append(
            {"family": "Betulaceae", "genus": "Betula", "species": "alleghaniensis"}
        )
        host_data["species"]["Specific regional"] = [
            {"family": "Betulaceae", "genus": "Betula", "species": "papyrifera"},
        ]
        host_data["match_level"]["Specific regional"] = "species"
        host_data["taxa"]["Specific regional"] = {"taxon_id": 1005, "common_name": "Specific Moth"}
        for index in range(8):
            host_data["species"][f"Quercus noise {index}"] = [
                {"family": "Fagaceae", "genus": "Quercus", "species": "alba"},
            ]
            host_data["match_level"][f"Quercus noise {index}"] = "species"

        with mock.patch("mothdash.analysis._load_host_plants", return_value=host_data):
            result = habitat_summary(self.settings, "station-a")

        self.assertEqual(result["regional_candidates"][0]["taxon_id"], 1005)
        self.assertEqual(result["regional_candidates"][0]["shared_genera"], ["Betula"])

    def test_render_reports_quiet_state(self) -> None:
        html = _habitat_summary({"has_data": False})
        self.assertIn("No host-plant reference data", html)


if __name__ == "__main__":
    unittest.main()
