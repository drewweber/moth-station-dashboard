import unittest

from mothdash.render import (
    DASHBOARD_JS,
    RECORD_CARD_PREVIEW_LIMIT,
    RECORD_TABLE_PAGE_SIZE,
    _insight_cards,
    _insight_feedback_id,
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
    def test_insight_feedback_cards_have_stable_rating_hooks(self) -> None:
        insight = {
            "category": "Early emergence",
            "title": "A moth arrived early",
            "body": "Earlier than its tracked history.",
            "meta": "2026",
        }

        insight_id = _insight_feedback_id(insight)
        html = _insight_cards([insight])

        self.assertEqual(insight_id, _insight_feedback_id(dict(insight)))
        self.assertIn(f'data-insight-id="{insight_id}"', html)
        self.assertIn('data-insight-rating="up"', html)
        self.assertIn('data-insight-rating="down"', html)
        self.assertIn('data-insight-feedback-copy', DASHBOARD_JS)
        self.assertIn('INSIGHT_FEEDBACK_KEY', DASHBOARD_JS)

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
