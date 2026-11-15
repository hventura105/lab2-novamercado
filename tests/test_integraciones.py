"""Contrato de clientes REST con dobles HTTP; no prueba servidores reales."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.services.integraciones import Airflow, Tracking


class ClientTests(unittest.TestCase):
    def test_registry_returns_text_version_and_run_artifact_source(self):
        tracking = Tracking("http://mlflow:5000")
        tracking.call = MagicMock(side_effect=[{}, {"model_version": {"version": 3, "status": "READY"}}])
        version = tracking.register({"artifact_uri": "mlflow-artifacts:/1/run/artifacts", "run_id": "run"})
        self.assertEqual(version, "3")
        self.assertEqual(tracking.call.call_args.args[1]["source"], "mlflow-artifacts:/1/run/artifacts/model")

    def test_pending_registry_version_is_never_promoted(self):
        tracking = Tracking()
        tracking.call = MagicMock(side_effect=[{}, {"model_version": {"version": "3", "status": "PENDING_REGISTRATION"}}])
        with self.assertRaises(RuntimeError):
            tracking.register({"artifact_uri": "mlflow-artifacts:/1/run/artifacts", "run_id": "run"})

    def test_artifact_upload_refuses_local_paths(self):
        with patch("app.services.integraciones.http") as http:
            with self.assertRaises(RuntimeError):
                Tracking().upload("file:///unmounted/model", "model.json", {})
        http.assert_not_called()

    def test_airflow_manual_run_has_no_simulated_wall_clock(self):
        airflow = Airflow()
        airflow.headers = MagicMock(return_value={"Authorization": "Bearer unit-test-token"})
        with patch("app.services.integraciones.http", return_value={}) as http:
            airflow.trigger("manual__unit")
        payload = http.call_args_list[-1].args[1]
        self.assertIsNone(payload["logical_date"])
        self.assertEqual(payload["conf"], {"execution_id": "manual__unit"})


if __name__ == "__main__":
    unittest.main()
