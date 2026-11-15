"""Pruebas de lógica de producto; las que leen fuentes reales se identifican aparte."""

import copy
import ast
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.core.temporal import Sale, TemporalLeakageError
from app.services.fuentes import Sources
from app.services.limpieza import Quality, clean_date, clean_request, number
from app.services.modelado import FeatureIndex, evaluate, promotion_decision
from app.services.repositorio import Repository

DATA = Path(__file__).resolve().parents[1] / "data" / "entrada"


@unittest.skipUnless((DATA / "historico_ventas.csv").exists(), "Requiere fuentes oficiales locales")
class OfficialSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = Sources(DATA)
        cls.valid = json.loads((DATA / "ejemplos" / "prediccion_valida.json").read_text())
        cls.valid["fecha"] = (cls.sources.history_end + timedelta(days=1)).isoformat()

    def test_official_sources_have_no_gaps_after_opening(self):
        report = self.sources.audit()
        self.assertEqual(report["huecos_tras_apertura"], 0)
        self.assertGreater(self.sources.calendar_end, self.sources.history_end)

    def test_canonical_request_has_no_quality_notes(self):
        _, quality = clean_request(self.valid, self.sources, "prediccion")
        self.assertEqual(quality, {"estado": "ok", "observaciones": []})

    def test_official_repair_examples(self):
        for code in ("E01", "E02", "E03", "E04", "E07"):
            path = next((DATA / "ejemplos" / "errores").glob(code + "*.json"))
            payload = json.loads(path.read_text())
            payload["fecha"] = "13/03/2026" if code == "E04" else self.valid["fecha"]
            with self.subTest(code=code):
                cleaned, quality = clean_request(payload, self.sources, "prediccion")
                self.assertEqual(quality["estado"], "corregido")
                self.assertEqual(cleaned["tienda_id"], 5)

    def test_partial_request_warns_and_does_not_invent_promotions(self):
        path = next((DATA / "ejemplos" / "errores").glob("E05*.json"))
        payload = json.loads(path.read_text())
        payload["fecha"] = self.valid["fecha"]
        cleaned, quality = clean_request(payload, self.sources, "prediccion")
        self.assertEqual(quality["estado"], "advertencia")
        self.assertEqual(len(cleaned["familias"]), 10)

    def test_contradictory_duplicates_rejected(self):
        path = next((DATA / "ejemplos" / "errores").glob("E06*.json"))
        payload = json.loads(path.read_text())
        payload["fecha"] = self.valid["fecha"]
        with self.assertRaisesRegex(ValueError, "contradictorios"):
            clean_request(payload, self.sources, "prediccion")

    def test_negative_sales_rejected_without_zero_imputation(self):
        path = next((DATA / "ejemplos" / "errores").glob("E08*.json"))
        with self.assertRaises(ValueError):
            clean_request(json.loads(path.read_text()), self.sources, "observaciones")

    def test_unknown_family_rejected(self):
        payload = copy.deepcopy(self.valid)
        payload["familias"][0]["familia_id"] = "familia desconocida de prueba"
        with self.assertRaisesRegex(ValueError, "desconocida"):
            clean_request(payload, self.sources, "prediccion")

    def test_historical_illustrative_date_does_not_bypass_simulation(self):
        payload = copy.deepcopy(self.valid)
        payload["fecha"] = "2025-11-17"
        with self.assertRaisesRegex(ValueError, "posterior"):
            clean_request(payload, self.sources, "prediccion")

    def test_future_calendar_boundary_is_enforced(self):
        payload = copy.deepcopy(self.valid)
        payload["fecha"] = (self.sources.calendar_end + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "calendario"):
            clean_request(payload, self.sources, "prediccion")


class QualityTests(unittest.TestCase):
    def test_warning_precedes_repairs(self):
        quality = Quality()
        quality.add("campo", "reparación")
        quality.add("campo", "ausencia", "advertir")
        self.assertEqual(quality.result()["estado"], "advertencia")

    def test_ambiguous_number_is_not_guessed(self):
        for value in ("1,292", "1,000"):
            with self.assertRaisesRegex(ValueError, "ambiguos"):
                number(value, "ventas", Quality())
        self.assertEqual(number("50,0", "ventas", Quality()), 50)

    def test_nonfinite_negative_boolean_and_fractional_promotions_are_invalid(self):
        for value in (float("nan"), float("inf"), -1, True, 2.3):
            with self.assertRaises(ValueError):
                number(value, "en_promocion", Quality(), integer=True)

    def test_ambiguous_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguos"):
            clean_date("03/04/2026", Quality())
        self.assertEqual(clean_date("17/03/2026", Quality()), date(2026, 3, 17))


class ModelSafetyTests(unittest.TestCase):
    def test_forecasting_modules_never_call_calendar_clock(self):
        base = Path(__file__).resolve().parents[1] / "api/app"
        for relative in ("core/temporal.py", "services/fuentes.py", "services/limpieza.py", "services/modelado.py"):
            tree = ast.parse((base / relative).read_text())
            calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            self.assertFalse({"now", "today", "utcnow"}.intersection(calls), relative)

    def test_actual_feature_engine_excludes_same_day_and_future(self):
        day = date(2026, 3, 1)
        before = [Sale(1, "a", day - timedelta(days=i), float(i)) for i in range(1, 40)]
        future = [Sale(1, "a", day + timedelta(days=i), 1000000) for i in range(3)]
        a = FeatureIndex(before).series[1, "a"].context(day.toordinal())
        b = FeatureIndex(before + future).series[1, "a"].context(day.toordinal())
        self.assertEqual(a, b)

    def test_in_sample_validation_is_rejected(self):
        with self.assertRaises(TemporalLeakageError):
            evaluate({"trained_through": "2026-03-01"}, [], date(2026, 3, 1), None)

    def test_inferior_cost_or_mae_never_promoted(self):
        reference = {"business_cost": 100, "mae": 10}
        for candidate in ({"business_cost": 101, "mae": 9}, {"business_cost": 90, "mae": 11}, {"business_cost": 99.5, "mae": 10}):
            self.assertFalse(promotion_decision(candidate, reference))
        self.assertTrue(promotion_decision({"business_cost": 98, "mae": 10}, reference))


class RepositoryUnitTests(unittest.TestCase):
    def test_upsert_counts_only_new_or_modified_rows_and_is_transactional(self):
        connection = MagicMock()
        db = connection.__enter__.return_value
        # INSERT solicitud, primer UPSERT nuevo, segundo UPSERT idéntico.
        db.execute.side_effect = [MagicMock(), MagicMock(fetchone=lambda: ("a",)), MagicMock(fetchone=lambda: None)]
        repository = Repository(lambda: connection)
        clean = {"tienda_id": 1, "fecha": "2026-03-01", "ventas": [{"familia_id": "a", "ventas": 10}, {"familia_id": "b", "ventas": 20}]}
        self.assertEqual(repository.observe(clean, clean, {"estado": "ok", "observaciones": []}), 1)
        connection.__exit__.assert_called_once_with(None, None, None)
        self.assertIn("IS DISTINCT FROM", db.execute.call_args_list[1].args[0])

    def test_partial_failure_escapes_context_to_roll_back(self):
        connection = MagicMock()
        connection.__exit__.return_value = False
        db = connection.__enter__.return_value
        db.execute.side_effect = [MagicMock(), RuntimeError("fallo de escritura")]
        repository = Repository(lambda: connection)
        clean = {"tienda_id": 1, "fecha": "2026-03-01", "ventas": [{"familia_id": "a", "ventas": 10}]}
        with self.assertRaises(RuntimeError):
            repository.observe(clean, clean, {})
        self.assertIs(connection.__exit__.call_args.args[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
