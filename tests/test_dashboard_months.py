import datetime
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
            {"data_formatada": "09/07/2026", "area": "SJC", "turno": "08:00 às 17:00", "tecnico_nome": "TÉCNICO A"},
            {"data_formatada": "09/07/2026", "area": "TAUBATE", "turno": "17:00 às 06:00", "tecnico_nome": "TÉCNICO B"},
        ]

        calendar = app.build_month_calendar_view(datetime.date(2026, 7, 1), rows)

        self.assertEqual(calendar[0]["empty"], True)
        self.assertEqual(calendar[10]["day"], 9)
        self.assertEqual(len(calendar[10]["entries"]), 2)
        self.assertEqual(calendar[10]["entries"][0]["area"], "SJC")


if __name__ == '__main__':
    unittest.main()
