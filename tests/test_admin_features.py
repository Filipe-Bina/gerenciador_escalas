import datetime
from unittest.mock import patch
import unittest

import app


class AdminFeaturesTests(unittest.TestCase):
    def test_load_holidays_for_year_includes_manual_holidays(self):
        class FakeCursor:
            def execute(self, query, params=None):
                self.query = (query, params)

            def fetchall(self):
                return [{"data": datetime.date(2026, 7, 9)}]

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        with patch.object(app, "fetch_public_holidays", return_value=set()), patch.object(app, "load_school_holidays", return_value=set()), patch.object(app, "get_db_connection", return_value=FakeConn()):
            holidays = app.load_holidays_for_year(2026)

        self.assertIn("2026-07-09", holidays)

    def test_obter_proximo_tecnico_respects_inactive_re(self):
        test_technicians = [
            {"re": "1001", "nome": "Técnico 1", "area": "SJC"},
            {"re": "1002", "nome": "Técnico 2", "area": "SJC"},
        ]

        with patch.object(app, "TECNICOS", test_technicians):
            tecnico = app.obter_proximo_tecnico("SJC", {}, inactive_re={"1001"}, data=datetime.date(2026, 7, 9))

        self.assertEqual(tecnico["re"], "1002")


if __name__ == "__main__":
    unittest.main()
