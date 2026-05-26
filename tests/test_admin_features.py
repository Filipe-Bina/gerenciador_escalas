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

    def test_obter_proximo_tecnico_uses_weighted_previous_month_history(self):
        test_technicians = [
            {"re": "1001", "nome": "Técnico 1", "area": "SJC"},
            {"re": "1002", "nome": "Técnico 2", "area": "SJC"},
        ]

        with patch.object(app, "TECNICOS", test_technicians):
            tecnico = app.obter_proximo_tecnico(
                "SJC",
                {"1001": 1},
                historico_turnos={"1001": 1, "1002": 0},
            )

        self.assertEqual(tecnico["re"], "1002")

    def test_gerar_escala_automatica_uses_previous_month_counts(self):
        class FakeCursor:
            def __init__(self):
                self.last_query = None
                self.last_params = None

            def execute(self, query, params=None):
                self.last_query = query
                self.last_params = params

            def fetchall(self):
                if self.last_query and "SELECT tecnico_re, COUNT(*) FROM escala WHERE data BETWEEN" in self.last_query:
                    return [("1001", 2), ("1002", 1)]
                return []

            def close(self):
                pass

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                pass

            def close(self):
                pass

        captured = {}

        def fake_obter_proximo_tecnico(area, contagem_turnos, tecnico_excluir=None, inactive_re=None, data=None, historico_turnos=None):
            if "initial_counts" not in captured:
                captured["initial_counts"] = dict(contagem_turnos)
                captured["historico_turnos"] = dict(historico_turnos or {})

            if area == "SJC":
                return {"re": "1001", "nome": "SJC 1", "area": area}
            if area == "TAUBATE":
                return {"re": "2001", "nome": "TAUBATE 1", "area": area}
            return {"re": "3001", "nome": "LITORAL 1", "area": area}

        with patch.object(app, "init_db"), patch.object(app, "get_db_connection", return_value=FakeConn()), patch.object(app, "load_holidays_for_year", return_value=set()), patch.object(app, "load_inactive_tecnicos_for_period", return_value={}), patch.object(app, "is_plantao_day", return_value=True), patch.object(app, "obter_proximo_tecnico", side_effect=fake_obter_proximo_tecnico):
            app.gerar_escala_automatica(2026, 7)

        self.assertEqual(captured["initial_counts"], {})
        self.assertEqual(captured["historico_turnos"], {"1001": 2, "1002": 1})


if __name__ == "__main__":
    unittest.main()
