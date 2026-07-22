import unittest

from mothdash.render import (
    CSS,
    DASHBOARD_JS,
    LIVE_JS,
    PERIOD_CARD_PREVIEW_LIMIT,
    RECORD_CARD_PREVIEW_LIMIT,
    RECORD_TABLE_PAGE_SIZE,
    _daily_species_line_chart,
    _dashboard_section_nav,
    _insight_cards,
    _insight_feedback_id,
    _live_page,
    _mode_toggle,
    _record_cards,
    _record_table,
    _sampling_context,
    _taxa_period_dashboard,
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
    def test_station_pages_can_use_the_full_dashboard_navigation(self) -> None:
        nav = _dashboard_section_nav("../index.html")

        self.assertIn('aria-label="Dashboard sections"', nav)
        self.assertIn('href="../index.html#last-night"', nav)
        self.assertIn('href="../index.html#past-week"', nav)
        self.assertIn('href="../index.html#stations"', nav)
        self.assertIn('href="../index.html#feed"', nav)
        self.assertIn('href="../index.html#species"', nav)

    def test_history_live_mode_control_and_immediate_live_check_are_rendered(self) -> None:
        toggle = _mode_toggle("index.html", "live.html", "live")
        page = _live_page(
            {
                "stations": [],
                "api_base": "https://api.inaturalist.org/v1",
                "poll_seconds": 600,
                "live_mode_hours": 2,
            }
        )

        self.assertIn("History", toggle)
        self.assertIn("Live", toggle)
        self.assertIn('aria-current="page"', toggle)
        self.assertIn('class="live-page"', page)
        self.assertIn("Keep checking", page)
        self.assertIn('class="switch-track"', page)
        self.assertIn(".switch-track", page)
        self.assertIn("refresh every 10 minutes", page)
        self.assertIn('id="live-new-species-counter"', page)
        self.assertIn('id="last-check"', page)
        self.assertIn('id="latest-observation"', page)
        self.assertIn('id="latest-upload"', page)
        self.assertIn('class="live-freshness"', page)
        self.assertNotIn('class="live-meta"', page)
        self.assertNotIn("snapshot generated", page)
        self.assertIn("els.lastCheck.textContent = fmtMinuteStamp(now)", LIVE_JS)
        self.assertIn("async function startLiveUpdates", LIVE_JS)
        self.assertIn("summary.currentSpecies.size > 0", LIVE_JS)
        self.assertIn("els.newSpeciesCounter", LIVE_JS)
        self.assertIn("networkEventSpecies", LIVE_JS)
        self.assertIn("stationsPerEventSpecies", LIVE_JS)
        self.assertIn("eventUniqueCount", LIVE_JS)
        self.assertIn("unique ·", LIVE_JS)
        self.assertIn("All stations", LIVE_JS)
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
                "station_unique": {"alpha": 5, "beta": 0},
                "shared": 4,
                "total": 9,
                "active_stations": 2,
            }
        ]

        html = _daily_species_line_chart(rows, stations, "year")

        self.assertIn("Daily species richness by contribution and overlap", html)
        self.assertNotIn("daily-richness-network-line", html)
        self.assertEqual(html.count("daily-richness-station-bar"), 1)
        self.assertEqual(html.count("daily-richness-shared-bar"), 1)
        self.assertIn("9 network species", html)
        self.assertIn("Alpha: 7 total, 5 only", html)
        self.assertIn("Beta: 4 total, 0 only", html)
        self.assertIn("Shared by 2+ stations", html)
        self.assertIn(".daily-richness-line-chart", DASHBOARD_JS)
        self.assertIn('data-daily-richness-series="alpha"', html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn('data-daily-richness-height=', html)
        self.assertIn("initDailyRichnessLegendToggles();", DASHBOARD_JS)
        self.assertIn("Only shared contributions are shown.", DASHBOARD_JS)
        self.assertIn('bar.toggleAttribute("hidden", !visible)', DASHBOARD_JS)
        self.assertIn(".sr-only {", CSS)

    def test_dashboard_navigation_has_current_section_state(self) -> None:
        self.assertIn("data-dashboard-section-nav", DASHBOARD_JS)
        self.assertIn("initDashboardSectionNavigation();", DASHBOARD_JS)
        self.assertIn('aria-current", "location"', DASHBOARD_JS)

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

    def test_sampling_context_renders_only_derived_coverage_and_timing(self) -> None:
        html = _sampling_context(
            {
                "active_sessions": 12,
                "first_session": "2025-07-02",
                "latest_session": "2026-07-18",
                "yearly_coverage": [
                    {"year": 2025, "nights": 4, "species": 83},
                    {"year": 2026, "nights": 8, "species": 147},
                ],
                "upload_timing": {
                    "median_lag_minutes": 210,
                    "timestamped_records": 26,
                    "total_records": 28,
                },
            }
        )

        self.assertIn("species-recorded nights", html)
        self.assertIn("Moth-night coverage by year", html)
        self.assertIn("4 nights", html)
        self.assertIn("147 species", html)
        self.assertIn("median upload lag", html)
        self.assertIn("3h 30m", html)

    def test_period_station_chips_filter_station_only_species(self) -> None:
        stations = [
            Station(id="alpha", name="Alpha Station", enabled=True, active=True, query={}, color="#123456"),
            Station(id="beta", name="Beta Station", enabled=True, active=True, query={}, color="#abcdef"),
        ]
        payload = {
            "period_label": "2026-07-12 to 2026-07-18",
            "observations": 5,
            "station_counts": {"alpha": 2, "beta": 2},
            "taxa": [
                {
                    "label": "Alpha-only Moth",
                    "station_count": 1,
                    "total_count": 1,
                    "stations": {"alpha": {"station_name": "Alpha Station"}},
                },
                {
                    "label": "Shared Moth",
                    "station_count": 2,
                    "total_count": 4,
                    "stations": {
                        "alpha": {"station_name": "Alpha Station"},
                        "beta": {"station_name": "Beta Station"},
                    },
                },
            ],
        }

        html = _taxa_period_dashboard(payload, stations, "past 7 nights", "No moths.")

        self.assertIn('data-night-station-filter="alpha"', html)
        self.assertIn('data-night-station-total="1"', html)
        self.assertIn("data-night-shared-filter", html)
        self.assertIn('data-night-shared-total="1"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn('data-night-card', html)
        self.assertIn('data-single-station-id="alpha"', html)
        self.assertIn('data-single-station-id=""', html)
        self.assertIn('data-station-count="2"', html)
        self.assertIn('data-night-filter-status', html)
        self.assertIn('data-night-filter-empty', html)
        self.assertIn("initNightStationFilters();", DASHBOARD_JS)
        self.assertIn("card.dataset.singleStationId === stationId", DASHBOARD_JS)
        self.assertIn('mode === "shared"', DASHBOARD_JS)
        self.assertIn("sortSharedCards();", DASHBOARD_JS)
        self.assertIn("Number(b.dataset.stationCount || 0)", DASHBOARD_JS)
        self.assertIn("button.dataset.nightStationTotal", DASHBOARD_JS)
        self.assertIn("showing ${visible}", DASHBOARD_JS)
        self.assertIn(".night-card[hidden]", CSS)

    def test_period_preview_includes_station_only_cards_beyond_shared_default(self) -> None:
        stations = [
            Station(id="alpha", name="Alpha Station", enabled=True, active=True, query={}, color="#123456"),
            Station(id="beta", name="Beta Station", enabled=True, active=True, query={}, color="#abcdef"),
        ]
        shared_taxa = [
            {
                "taxon_id": index,
                "label": f"Shared {index}",
                "station_count": 2,
                "total_count": 2,
                "stations": {
                    "alpha": {"station_name": "Alpha Station"},
                    "beta": {"station_name": "Beta Station"},
                },
            }
            for index in range(PERIOD_CARD_PREVIEW_LIMIT + 1)
        ]
        alpha_only = {
            "taxon_id": 999,
            "label": "Alpha-only Moth",
            "station_count": 1,
            "total_count": 1,
            "stations": {"alpha": {"station_name": "Alpha Station"}},
        }
        html = _taxa_period_dashboard(
            {
                "period_label": "2026-07-12 to 2026-07-18",
                "observations": 75,
                "station_counts": {"alpha": 38, "beta": 37},
                "taxa": [*shared_taxa, alpha_only],
            },
            stations,
            "past 7 nights",
            "No moths.",
        )

        self.assertIn("Alpha-only Moth", html)
        self.assertIn('data-single-station-id="alpha"', html)
        self.assertIn('data-night-station-total="1"', html)

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

    def test_archive_rows_carry_card_rebuild_data(self) -> None:
        # The filtered photo grid is rebuilt client-side from data embedded
        # on the (always-complete) table rows, since the server-rendered
        # card grid intentionally only ever contains a bounded preview.
        html = _record_table(records(5))

        self.assertIn('data-label="Species 0000"', html)
        self.assertIn('data-station-name="Test Station"', html)
        self.assertIn('data-first="2026-07-01"', html)
        self.assertIn('data-photo-url="https://example.test/0.jpg"', html)
        self.assertIn('data-href="https://example.test/observations/0"', html)

    def test_archive_species_names_link_to_the_inaturalist_observation(self) -> None:
        html = _record_table(records(3))

        self.assertIn('<td><a href="https://example.test/observations/0">Species 0000</a></td>', html)
        self.assertIn('<td><a href="https://example.test/observations/1">Species 0001</a></td>', html)

    def test_archive_rows_tolerate_missing_photo_or_link(self) -> None:
        rows = [
            {
                "label": "No Photo Moth",
                "station_name": "Test Station",
                "station_id": "test-station",
                "first": "2026-07-01",
                "flags": ["first among tracked"],
                "photo_url": None,
                "url": None,
            }
        ]

        html = _record_table(rows)

        self.assertIn('data-photo-url=""', html)
        self.assertIn('data-href=""', html)

    def test_filtered_photo_grid_rebuilds_from_table_data_instead_of_hiding(self) -> None:
        # Earlier behavior force-hid the entire card grid whenever a filter
        # was active, which read to users as "the photos just disappear."
        # The grid should instead be rebuilt (bounded, with an explicit
        # expand action), never blanket-hidden.
        self.assertNotIn("cardGrid.hidden = filterActive", DASHBOARD_JS)
        self.assertIn("function buildRecordCardHtml", DASHBOARD_JS)
        self.assertIn("data-record-grid", DASHBOARD_JS)
        self.assertIn("data-record-grid-expand", DASHBOARD_JS)
        self.assertIn("matching.slice(0, cap).map(buildRecordCardHtml)", DASHBOARD_JS)
        self.assertIn("originalGridHtml", DASHBOARD_JS)

    def test_live_new_species_shows_network_count_and_first_badges(self) -> None:
        # "New species this event" previously omitted the network count
        # shown for "Other species", and had no way to flag that a new
        # arrival is the network's actual 1st/2nd/3rd tracked record.
        # ("Network" rather than "regional": this counts observations
        # across tracked stations, not a true county/state iNaturalist
        # search, so "regional" was a misleading label.)
        self.assertIn("function networkFirstBadge", LIVE_JS)
        self.assertIn('tier: "gold"', LIVE_JS)
        self.assertIn('tier: "silver"', LIVE_JS)
        self.assertIn('tier: "bronze"', LIVE_JS)
        self.assertIn("network-badge-${tier.tier}", LIVE_JS)
        self.assertIn(
            "renderSpeciesList(summary.stationFirstSpecies, summary.checked "
            '? "No new station species in this event yet." : "Waiting for '
            'the first check.", new Set(), 20, false, station.id, true, true)',
            LIVE_JS,
        )


if __name__ == "__main__":
    unittest.main()
