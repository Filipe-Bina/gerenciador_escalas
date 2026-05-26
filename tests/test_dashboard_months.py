import datetime
from unittest.mock import patch
import unittest

import app


class DashboardMonthTests(unittest.TestCase):
    def test_resolve_dashboard_month_defaults_to_current_month(self):
        with app.app.test_request_context('/'):
            self.assertEqual(app.resolve_dashboard_month(), datetime.date.today().replace(day=1))

    def test_resolve_dashboard_month_uses_query_params(self):
        with app.app.test_request_context('/?ano=2026&mes=7'):
            self.assertEqual(app.resolve_dashboard_month(), datetime.date(2026, 7, 1))

    def test_resolve_dashboard_month_falls_back_for_invalid_params(self):
        with app.app.test_request_context('/?ano=abc&mes=15'):
            self.assertEqual(app.resolve_dashboard_month(), datetime.date.today().replace(day=1))

    def test_resolve_dashboard_weekend_dates_for_future_month(self):
        selected_month = datetime.date(2026, 7, 1)
        saturday, sunday = app.resolve_dashboard_weekend_dates(selected_month, reference_date=datetime.date(2026, 5, 1))
        self.assertEqual(saturday, datetime.date(2026, 7, 4))
        self.assertEqual(sunday, datetime.date(2026, 7, 5))

    def test_resolve_dashboard_weekend_dates_for_current_month_uses_next_weekend(self):
        reference = datetime.date(2026, 5, 22)
        saturday, sunday = app.resolve_dashboard_weekend_dates(datetime.date(2026, 5, 1), reference_date=reference)
        self.assertEqual(saturday, datetime.date(2026, 5, 23))
        self.assertEqual(sunday, datetime.date(2026, 5, 24))

    def test_build_month_calendar_view_groups_rows_by_day(self):
        rows = [
            {"data_formatada": "09/07/2026", "area": "SJC", "turno": "08:00 às 17:00", "tecnico_nome": "TÉCNICO A", "tecnico_re": "123"},
            {"data_formatada": "09/07/2026", "area": "TAUBATE", "turno": "17:00 às 06:00", "tecnico_nome": "TÉCNICO B", "tecnico_re": "456"},
        ]

        calendar = app.build_month_calendar_view(datetime.date(2026, 7, 1), rows)

        self.assertEqual(calendar[0]["empty"], True)
        self.assertEqual(calendar[10]["day"], 9)
        self.assertEqual(len(calendar[10]["entries"]), 2)
        self.assertEqual(calendar[10]["entries"][0]["area"], "SJC")
        self.assertEqual(calendar[10]["entries"][0]["tecnico_re"], "123")

    def test_dashboard_renders_holiday_badges_and_omits_empty_message(self):
        class FakeCursor:
            def __init__(self):
                self.last_query = None

            def execute(self, query, params=None):
                self.last_query = query

            def fetchall(self):
                if self.last_query and "FROM escala WHERE data BETWEEN" in self.last_query:
                    return [{
                        "data_formatada": "09/07/2026",
                        "area": "SJC",
                        "turno": "08:00 às 17:00",
                        "tecnico_re": "123",
                        "tecnico_nome": "TÉCNICO A",
                    }]
                if self.last_query and "FROM escala WHERE data IN" in self.last_query:
                    return []
                return []

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        with patch.object(app, "get_db_connection", return_value=FakeConn()), patch.object(app, "load_holidays_for_year", return_value={"2026-07-09"}):
            with app.app.test_client() as client:
                response = client.get('/?ano=2026&mes=7')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Feriado', html)
        self.assertIn('RE 123', html)
        self.assertNotIn('Sem escala', html)


if __name__ == '__main__':
    unittest.main()
