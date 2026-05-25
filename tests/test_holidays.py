import unittest
from datetime import date
from unittest.mock import patch

import app


class HolidayLogicTests(unittest.TestCase):
    def test_feriado_em_dia_util_deve_ser_plantao(self):
        self.assertTrue(app.is_plantao_day(date(2026, 7, 9), {"2026-07-09"}))

    def test_dia_util_sem_feriado_nao_eh_plantao(self):
        self.assertFalse(app.is_plantao_day(date(2026, 7, 8), {"2026-07-09"}))

    def test_parse_de_payload_de_feriados_da_api(self):
        payload = [
            {"date": "2026-07-09", "name": "Revolução Constitucionalista", "type": "national"},
            {"date": "2026-09-07", "name": "Independência do Brasil", "type": "national"},
        ]
        self.assertEqual(app.parse_holiday_payload(payload), {"2026-07-09", "2026-09-07"})

    def test_load_holidays_for_year_inclui_feriado_estadual_sp(self):
        with patch.object(app, "fetch_public_holidays", return_value={"2026-09-07"}):
            feriados = app.load_holidays_for_year(2026)

        self.assertIn("2026-07-09", feriados)
        self.assertIn("2026-09-07", feriados)


if __name__ == "__main__":
    unittest.main()
