import unittest

from mothdash.render import (
    DASHBOARD_JS,
    RECORD_CARD_PREVIEW_LIMIT,
    RECORD_TABLE_PAGE_SIZE,
    _record_cards,
    _record_table,
)


def records(count: int) -> list[dict]:
    return [
        {
            "label": f"Species {index:04d}",
            "station_name": "Test Station",
            "station_id": "test-station",
            "first": f"2026-07-{(index % 28) + 1:02d}",
            "flags": ["county iNat first"],
            "photo_url": f"https://example.test/{index}.jpg",
            "url": f"https://example.test/observations/{index}",
        }
        for index in range(count)
    ]


class RecordRenderingTests(unittest.TestCase):
    def test_photo_grid_renders_only_newest_preview(self) -> None:
        html = _record_cards(records(150))

        self.assertEqual(html.count('class="record-card"'), RECORD_CARD_PREVIEW_LIMIT)
        self.assertNotIn("data-default-hidden", html)
        self.assertNotIn("Species 0012", html)

    def test_archive_contains_every_record_without_server_hidden_rows(self) -> None:
        html = _record_table(records(150))

        self.assertEqual(html.count("data-record-row"), 150)
        self.assertIn("Species 0000", html)
        self.assertIn("Species 0149", html)
        self.assertNotIn("data-default-hidden", html)
        self.assertNotIn("<tr hidden", html)

    def test_archive_includes_pagination_and_filtering_hooks(self) -> None:
        html = _record_table(records(150))

        self.assertIn("data-record-table", html)
        self.assertIn("data-record-show-more", html)
        self.assertIn(f'data-page-size="{RECORD_TABLE_PAGE_SIZE}"', html)
        self.assertIn("data-record-count", html)
        self.assertIn('data-record-filter="type"', DASHBOARD_JS)
        self.assertIn('data-record-filter="location"', DASHBOARD_JS)
        self.assertIn('archive.open = true', DASHBOARD_JS)


if __name__ == "__main__":
    unittest.main()
