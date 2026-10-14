"""Archive output contracts: first load stays bounded and all data stays accessible."""

import unittest
import json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory

import mothdash.render as renderer
from mothdash.render import _archive_page


class ArchiveMarkup(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.elements = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def archive_inputs():
    return dict(
        year=2026, pulses=[], all_time_pulses=[], records=[], uniques=[],
        stations=[], year_calendar=[{
            "key": "2026-07-15", "sort_key": "2026-07-15", "label": "Jul 15",
            "stations": {}, "station_unique": {}, "shared": 0,
            "total": 0, "active_stations": 0,
        }], all_time_calendar=[],
        taxa=[{"label": "Comparison-only species", "stations": {}, "station_count": 0}],
        year_taxa=[], recent_week_taxa=[], latest_night_taxa=[],
    )


class ArchiveLoadingTests(unittest.TestCase):
    def test_archive_does_not_parse_calendar_charts_or_comparison_rows_initially(self):
        # Rendering these collections in hidden panels still causes the original
        # parse and DOM cost; they must live behind ordinary navigable links.
        markup = _archive_page(**archive_inputs())
        parsed = ArchiveMarkup(markup)
        self.assertFalse(any(tag == "svg" for tag, _ in parsed.elements))
        self.assertNotIn("Comparison-only species", markup)
        hrefs = {attrs.get("href") for tag, attrs in parsed.elements if tag == "a"}
        self.assertIn("archive-calendar-year.html", hrefs)
        self.assertIn("archive-calendar-all-years.html", hrefs)
        self.assertIn("archive-species-all-time.html", hrefs)
        self.assertIn("archive-species-year.html", hrefs)
        self.assertIn("archive-species-past-week.html", hrefs)
        self.assertIn("archive-species-last-night.html", hrefs)

    def test_archive_products_keep_all_records_and_comparison_species_accessible(self):
        inputs = archive_inputs()
        inputs["records"] = [{
            "label": f"Record {i:04d}", "station_name": "Alpha", "station_id": "alpha",
            "first": date(2026, 7, 15), "flags": ["county iNat first"],
            "url": f"https://example.test/{i}", "photo_url": None,
        } for i in range(225)]
        inputs["taxa"] = [{
            "label": f"Comparison species {i:04d}", "stations": {}, "station_count": 0,
        } for i in range(260)]
        with TemporaryDirectory() as directory:
            output = Path(directory)
            renderer._write_archive_assets(output, **inputs)
            markup = (output / "archive.html").read_text()
            self.assertEqual(markup.count("data-record-row"), 100)
            loaded = json.loads((output / "assets/archive-records.json").read_text())
            self.assertEqual(len(loaded), 225)
            self.assertEqual(loaded[-1]["label"], "Record 0224")
            self.assertEqual(loaded[-1]["first"], "2026-07-15")
            full_records = (output / "archive-records-all.html").read_text()
            self.assertIn("Record 0224", full_records)
            self.assertEqual(full_records.count("data-record-row"), 225)
            comparison = (output / "archive-species-all-time.html").read_text()
            self.assertIn("Comparison species 0259", comparison)
            self.assertIn('href="archive.html#archive-species"', comparison)
            calendar = (output / "archive-calendar-year.html").read_text()
            self.assertIn("Jul 15", calendar)
            self.assertIn("daily-richness-line-chart", calendar)
            for tag, attrs in ArchiveMarkup(markup).elements:
                href = attrs.get("href", "").split("#")[0]
                if tag == "a" and href.startswith("archive-"):
                    self.assertTrue((output / href).is_file(), href)


if __name__ == "__main__":
    unittest.main()
