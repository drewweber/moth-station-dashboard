from datetime import date
import unittest

from mothdash.analysis import flight_season_date, session_date


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


if __name__ == "__main__":
    unittest.main()
