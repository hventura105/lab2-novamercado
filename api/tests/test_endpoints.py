"""Contrato ASGI con runtime real y dobles locales. No requiere MLflow activo."""

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import create_app
from app.core.temporal import Sale
from app.services.runtime import Runtime


def request(app, path, body=None, method="GET"):
    async def invoke():
        events = []

        async def receive():
            return {"type": "http.request", "body": b"" if body is None else json.dumps(body).encode(), "more_body": False}

        async def send(event):
            events.append(event)

        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                   "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                   "root_path": "", "query_string": b"", "headers": [(b"content-type", b"application/json")],
                   "server": ("api", 8000), "client": ("127.0.0.1", 1234)}, receive, send)
        status = next(event["status"] for event in events if event["type"] == "http.response.start")
        response_body = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
        return status, json.loads(response_body)

    return asyncio.run(invoke())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.tracking = MagicMock(name="tracking")
        self.tracking.name = "unit-model"
        self.tracking.alias = "champion"
        self.tracking.alias_version.return_value = "7"
        self.airflow = MagicMock()
        self.sources = SimpleNamespace(stores={1: {"fecha_apertura": "2020-01-01"}},
            families={"a": "Familia A", "b": "Familia B"}, costs={"a": (1, 1), "b": (1, 1)},
            history_start=date(2026, 1, 1), history_end=date(2026, 2, 28), calendar_end=date(2026, 12, 31),
            event_features=lambda sid, day: [0, 0, 0, 0])
        self.repository.sales.return_value = [Sale(1, family, date(2026, 2, 28) - timedelta(days=i), 10) for i in range(40) for family in ("a", "b")]
        self.runtime = Runtime(self.repository, self.tracking, self.airflow, self.sources)
        self.runtime.initialized = True
        self.runtime.loaded = {"version": "7", "artifact": {"algorithm": "baseline", "trained_through": "2026-02-28", "residuals": {"a": [0], "b": [0]}}}
        self.app = create_app(self.runtime, background=False)
        self.payload = {"tienda_id": 1, "fecha": "2026-03-01", "familias": [{"familia_id": "a", "en_promocion": 0}, {"familia_id": "b", "en_promocion": 0}]}

    def test_health_ok_and_model_exact_fields(self):
        self.assertEqual(request(self.app, "/health"), (200, {"estado": "ok"}))
        self.assertEqual(request(self.app, "/modelo"), (200, {"nombre": "unit-model", "alias": "champion", "version": "7"}))

    def test_no_model_returns_503(self):
        self.runtime.loaded = None
        self.assertEqual(request(self.app, "/health")[0], 503)
        self.assertEqual(request(self.app, "/modelo")[0], 503)

    def test_prediction_contract_and_repeated_requests_are_logged(self):
        for _ in range(2):
            status, body = request(self.app, "/v1/prediccion", self.payload, "POST")
            self.assertEqual(status, 200)
            self.assertEqual(set(body), {"tienda_id", "fecha", "version_modelo", "predicciones", "calidad"})
            self.assertEqual(body["version_modelo"], "7")
            self.assertEqual(body["calidad"], {"estado": "ok", "observaciones": []})
            self.assertIs(type(body["predicciones"][0]["cantidad_sugerida"]), int)
        self.assertEqual(self.repository.prediction.call_count, 2)

    def test_repair_and_warning_precedence(self):
        self.payload["tienda_id"] = "T01"
        self.payload["familias"] = self.payload["familias"][:1]
        status, body = request(self.app, "/v1/prediccion", self.payload, "POST")
        self.assertEqual(status, 200)
        self.assertEqual(body["calidad"]["estado"], "advertencia")
        self.assertEqual({note["accion"] for note in body["calidad"]["observaciones"]}, {"reparar", "advertir"})

    def test_structural_and_semantic_rejections_are_422(self):
        for body in ({"tienda_id": 1, "fecha": "2026-03-01", "familias": "incorrecto"},
                     {**self.payload, "fecha": "2025-11-17"},
                     {**self.payload, "tienda_id": True}):
            status, response = request(self.app, "/v1/prediccion", body, "POST")
            self.assertEqual(status, 422)
            self.assertIn("detail", response)

    def test_observation_idempotent_count(self):
        self.repository.observe.side_effect = [1, 0]
        payload = {"tienda_id": 1, "fecha": "2026-03-01", "ventas": [{"familia_id": "a", "ventas": 10}]}
        for expected in (1, 0):
            status, body = request(self.app, "/v1/observaciones", payload, "POST")
            self.assertEqual(status, 200)
            self.assertEqual(body["registros_guardados"], expected)

    def test_airflow_dispatch_and_failure(self):
        status, body = request(self.app, "/admin/reentrenar", method="POST")
        self.assertEqual(status, 202)
        self.assertIsInstance(body["id"], str)
        self.airflow.trigger.assert_called_once()
        self.airflow.trigger.side_effect = OSError("offline")
        self.assertEqual(request(self.app, "/admin/reentrenar", method="POST")[0], 503)
        self.assertEqual(request(self.app, "/admin/reentrenar", {}, "POST")[0], 422)

    def test_unknown_run_404_and_completed_fields(self):
        self.repository.get_run.return_value = None
        self.assertEqual(request(self.app, "/admin/reentrenar/desconocido")[0], 404)
        self.repository.get_run.return_value = {"estado": "exitoso", "promovido": False, "version": "7", "motivo": "No supera al vigente"}
        status, body = request(self.app, "/admin/reentrenar/conocido")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"estado", "promovido", "version", "motivo"})

    def test_mlflow_outage_and_recovery_do_not_interrupt_predictions(self):
        self.tracking.health.side_effect = OSError("offline")
        self.assertEqual(request(self.app, "/health")[1]["estado"], "degradado")
        self.assertEqual(request(self.app, "/v1/prediccion", self.payload, "POST")[0], 200)
        self.tracking.health.side_effect = None
        self.assertEqual(request(self.app, "/health")[1]["estado"], "ok")

    def test_version_refresh_without_restart(self):
        self.repository.active.return_value = {**self.runtime.loaded, "version": "8"}
        self.runtime.refresh()
        self.tracking.alias_version.return_value = "8"
        self.assertEqual(request(self.app, "/modelo")[1]["version"], "8")
        self.assertEqual(request(self.app, "/v1/prediccion", self.payload, "POST")[1]["version_modelo"], "8")


if __name__ == "__main__":
    unittest.main()
