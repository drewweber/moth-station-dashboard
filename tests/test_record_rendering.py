import unittest

from mothdash.render import (
    DASHBOARD_JS,
    LIVE_JS,
    RECORD_CARD_PREVIEW_LIMIT,
    RECORD_TABLE_PAGE_SIZE,
    _daily_species_line_chart,
    _insight_cards,
    _insight_feedback_id,
    _live_page,
    _mode_toggle,
    _record_cards,
    _record_table,
)
from mothdash.config import Station


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
    def test_history_live_mode_control_and_immediate_live_check_are_rendered(self) -> None:
        toggle = _mode_toggle("index.html", "live.html", "live")
        page = _live_page()

        self.assertIn("History", toggle)
        self.assertIn("Live", toggle)
        self.assertIn('aria-current="page"', toggle)
        self.assertIn('class="live-page"', page)
        self.assertIn("Keep checking", page)
        self.assertIn("refresh every 10 minutes", page)
        self.assertIn('id="live-new-species-counter"', page)
        self.assertIn('id="last-check"', page)
        self.assertIn('id="latest-observation"', page)
        self.assertIn('id="latest-upload"', page)
        self.assertNotIn("snapshot generated", page)
        self.assertIn("els.lastCheck.textContent = fmtMinuteStamp(now)", LIVE_JS)
        self.assertIn("async function startLiveUpdates", LIVE_JS)
        self.assertIn("summary.currentSpecies.size > 0", LIVE_JS)
        self.assertIn("els.newSpeciesCounter", LIVE_JS)
        self.assertIn('href="#live-station-${escapeHtml(summary.station.id)}"', LIVE_JS)
        self.assertIn('id="live-station-${escapeHtml(station.id)}"', LIVE_JS)
        self.assertIn("obs.time_observed_at", LIVE_JS)
        self.assertIn("obs.created_at", LIVE_JS)
        self.assertIn(
            "await loadSnapshot();\n  updateToggleState();\n  window.setInterval(updateToggleState, 30000);\n\n  try {\n    await runCheck();",
            LIVE_JS,
        )

    def test_daily_richness_chart_keeps_network_union_separate_from_station_lines(self) -> None:
        stations = [
            Station(id="alpha", name="Alpha", enabled=True, active=True, query={}, color="#123456"),
            Station(id="beta", name="Beta", enabled=True, active=True, query={}, color="#abcdef"),
        ]
        rows = [
            {
                "key": "2026-07-15",
                "label": "Jul 15",
                "stations": {"alpha": 7, "beta": 4},
                "total": 9,
                "active_stations": 2,
            }
        ]

        html = _daily_species_line_chart(rows, stations, "year")

        self.assertIn("Daily species richness by station", html)
        self.assertIn("daily-richness-network-line", html)
        self.assertEqual(html.count("daily-richness-station-line"), 2)
        self.assertIn("9 network species", html)
        self.assertIn("Alpha: 7", html)
        self.assertIn("Beta: 4", html)
        self.assertIn(".daily-richness-line-chart", DASHBOARD_JS)

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
