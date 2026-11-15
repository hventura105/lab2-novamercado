"""Protocolo de promoción con fallos de registro; no requiere MLflow activo."""

from pathlib import Path
from datetime import date
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.services.ciclo import training_cycle
from app.services.runtime import Runtime, Unavailable
from app.core.temporal import Sale


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.current = {"version": "4", "artifact": {"trained_through": "2026-02-28"}}
        self.repository.active.return_value = self.current
        self.tracking = MagicMock()
        self.tracking.name, self.tracking.alias = "unit", "champion"
        self.tracking.alias_version.return_value = "4"
        self.tracking.log_model.return_value = {"run_id": "unit-run"}
        self.tracking.register.return_value = "5"
        self.sources = MagicMock()
        self.result = {"candidate": {"algorithm": "ridge", "trained_through": "2026-03-10"}, "promoted": True,
            "evaluations": {"ridge": {"mae": 1, "business_cost": 1}}, "validation_artifacts": {},
            "validation_start": "2026-03-01", "reason": "Costo menor"}

    def test_restart_with_model_never_retrains(self):
        with patch("app.services.ciclo.train_and_compare") as train:
            self.assertEqual(training_cycle(self.repository, self.tracking, self.sources), self.current)
        train.assert_not_called()

    def test_inferior_candidate_never_changes_alias_or_active_pointer(self):
        self.result["promoted"] = False
        with patch("app.services.ciclo.train_and_compare", return_value=self.result):
            active = training_cycle(self.repository, self.tracking, self.sources, "execution")
        self.assertEqual(active["version"], "4")
        self.tracking.set_alias.assert_not_called()
        self.repository.activate.assert_not_called()
        self.repository.finish_run.assert_called_once_with("execution", True, False, "4", "Costo menor")

    def test_failed_registry_never_replaces_current(self):
        self.tracking.register.side_effect = OSError("offline")
        with patch("app.services.ciclo.train_and_compare", return_value=self.result):
            with self.assertRaises(OSError):
                training_cycle(self.repository, self.tracking, self.sources, "execution")
        self.repository.activate.assert_not_called()
        self.tracking.set_alias.assert_not_called()

    def test_failed_database_activation_restores_alias(self):
        self.repository.activate.side_effect = OSError("fallo de transacción")
        with patch("app.services.ciclo.train_and_compare", return_value=self.result):
            with self.assertRaises(OSError):
                training_cycle(self.repository, self.tracking, self.sources, "execution")
        self.assertEqual([call.args[0] for call in self.tracking.set_alias.call_args_list], ["5", "4"])

    def test_success_changes_alias_active_and_result(self):
        with patch("app.services.ciclo.train_and_compare", return_value=self.result):
            active = training_cycle(self.repository, self.tracking, self.sources, "execution")
        self.assertEqual(active["version"], "5")
        self.repository.activate.assert_called_once_with("5", "champion", "execution", "Costo menor")

    def test_mlflow_down_keeps_loaded_model_and_health_degrades_then_recovers(self):
        runtime = Runtime(self.repository, self.tracking, MagicMock(), self.sources)
        runtime.loaded = self.current
        self.tracking.health.side_effect = OSError("offline")
        self.assertEqual(runtime.health()[0]["estado"], "degradado")
        self.assertEqual(runtime.model()["version"], "4")
        self.tracking.health.side_effect = None
        self.assertEqual(runtime.health()[0]["estado"], "ok")

    def test_alias_reconciliation_uses_committed_active_version(self):
        runtime = Runtime(self.repository, self.tracking, MagicMock(), self.sources)
        runtime.loaded = self.current
        self.tracking.alias_version.return_value = "5"
        runtime.reconcile_alias()
        self.tracking.set_alias.assert_called_once_with("4")

    def test_airflow_dispatch_failure_is_recorded_without_training(self):
        airflow = MagicMock()
        airflow.trigger.side_effect = OSError("offline")
        runtime = Runtime(self.repository, self.tracking, airflow, self.sources)
        runtime.loaded = self.current
        with self.assertRaises(Unavailable):
            runtime.trigger()
        args = self.repository.finish_run.call_args.args
        self.assertEqual(args[1:4], (False, False, "4"))
        self.assertEqual(runtime.model()["version"], "4")

    def test_failed_training_preserves_model_and_records_failure(self):
        runtime = Runtime(self.repository, self.tracking, MagicMock(), self.sources)
        runtime.loaded = self.current
        self.repository.get_run.return_value = {"estado": "en_curso"}
        with patch("app.services.runtime.training_cycle", side_effect=OSError("offline")):
            with self.assertRaises(Unavailable):
                runtime.retrain("execution")
        self.assertEqual(runtime.model()["version"], "4")
        self.assertEqual(self.repository.finish_run.call_args.args[1:4], (False, False, "4"))

    def test_active_version_refresh_needs_no_restart_or_mlflow_download(self):
        runtime = Runtime(self.repository, self.tracking, MagicMock(), self.sources)
        runtime.loaded = self.current
        self.repository.active.return_value = {"version": "5", "artifact": {"trained_through": "2026-03-10"}}
        runtime.refresh()
        self.assertEqual(runtime.model()["version"], "5")
        self.tracking.log_model.assert_not_called()

    def test_repeated_old_forecast_uses_promoted_archive_without_future_leakage(self):
        sources = SimpleNamespace(stores={1: {"fecha_apertura": "2020-01-01"}}, families={"a": "A"}, costs={"a": (1, 1)},
            history_start=date(2026, 1, 1), history_end=date(2026, 2, 28), calendar_end=date(2026, 12, 31), event_features=lambda sid, day: [0, 0, 0, 0])
        archived = {"version": "4", "artifact": {"algorithm": "baseline", "trained_through": "2026-02-28", "residuals": {"a": [0]}}}
        runtime = Runtime(self.repository, self.tracking, MagicMock(), sources)
        runtime.initialized = True
        runtime.loaded = {"version": "5", "artifact": {**archived["artifact"], "trained_through": "2026-03-03"}}
        self.repository.model_before.return_value = archived
        self.repository.sales.return_value = [Sale(1, "a", date(2026, 2, 28), 10), Sale(1, "a", date(2026, 3, 1), 999999)]
        payload = {"tienda_id": 1, "fecha": "2026-03-01", "familias": [{"familia_id": "a", "en_promocion": 0}]}
        for _ in range(2):
            response = runtime.prediction(payload)
            self.assertEqual(response["version_modelo"], "4")
            self.assertEqual(response["predicciones"][0]["venta_esperada"], 10)
        self.assertEqual(runtime.model()["version"], "5")
        self.assertEqual(self.repository.prediction.call_count, 2)


if __name__ == "__main__":
    unittest.main()
