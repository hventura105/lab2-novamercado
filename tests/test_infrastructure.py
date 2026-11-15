"""Pruebas locales de fallo seguro; no requieren daemon ni paquetes de la API."""

import base64
import contextlib
import errno
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT))
from app.core import health
from checks.connectivity import validate_airflow_health
from scripts import infra


class HealthTests(unittest.TestCase):
    def test_dependencies_ready(self):
        with patch.object(health, "check_database"), patch.object(health, "check_mlflow"):
            payload, code = health.readiness()
        self.assertEqual(code, 200)
        self.assertEqual(payload["status"], "ready")

    def test_database_failure_does_not_hide_mlflow_status_or_leak_password(self):
        with patch.object(health, "check_database", side_effect=OSError("password=secret")), patch.object(health, "check_mlflow") as mlflow:
            with self.assertLogs(health.logger, level="WARNING") as logs:
                payload, code = health.readiness()
        self.assertEqual(code, 503)
        self.assertEqual(payload["checks"], {"postgres": "unavailable", "mlflow": "ok"})
        mlflow.assert_called_once()
        self.assertNotIn("secret", str(logs.output) + json.dumps(payload))

    def test_mlflow_failure_returns_not_ready(self):
        with patch.object(health, "check_database"), patch.object(health, "check_mlflow", side_effect=TimeoutError()):
            with self.assertLogs(health.logger, level="WARNING"):
                payload, code = health.readiness()
        self.assertEqual((code, payload["status"]), (503, "not_ready"))

    def test_database_check_executes_query(self):
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        with patch.object(health, "database_connection", return_value=connection):
            health.check_database()
        cursor.execute.assert_called_once_with("SELECT 1")

    def test_airflow_http_200_with_failed_scheduler_is_rejected(self):
        payload = {name: {"status": "healthy"} for name in ("metadatabase", "scheduler", "dag_processor", "triggerer")}
        payload["scheduler"]["status"] = "unhealthy"
        with self.assertRaisesRegex(RuntimeError, "scheduler"):
            validate_airflow_health(payload)

    def test_missing_airflow_component_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "metadatabase"):
            validate_airflow_health({})


class SafetyTests(unittest.TestCase):
    def config(self, api_port=8000, mlflow_port=5000):
        return {"services": {name: {"ports": [{"host_ip": "127.0.0.1", "published": str(port)}]}
                             for name, port in (("api", api_port), ("mlflow", mlflow_port))}}

    def test_conflict_blocks_without_mutation(self):
        sock = MagicMock()
        sock.__enter__.return_value.bind.side_effect = OSError(errno.EADDRINUSE, "in use")
        with patch.object(infra.socket, "socket", return_value=sock), patch.object(infra, "compose") as compose:
            with self.assertRaisesRegex(RuntimeError, "No se cambió ningún puerto"):
                infra.check_ports(self.config())
        compose.assert_not_called()

    def test_forbidden_inspection_blocks(self):
        with patch.object(infra.socket, "socket", side_effect=PermissionError()):
            with self.assertRaisesRegex(RuntimeError, "impide inspeccionar"):
                infra.check_ports(self.config())

    def test_duplicate_ports_block(self):
        with patch.object(infra.socket, "socket"), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "duplicado"):
                infra.check_ports(self.config(8000, 8000))

    def test_ports_owned_by_this_project_are_not_rebound(self):
        with patch.object(infra.socket, "socket") as sock, contextlib.redirect_stdout(io.StringIO()):
            infra.check_ports(self.config(), {("api", 8000), ("mlflow", 5000)})
        sock.assert_not_called()

    def test_failed_preflight_never_starts_compose(self):
        with patch.object(sys, "argv", ["infra.py", "up"]), patch.object(infra, "preflight", side_effect=RuntimeError("blocked")), patch.object(infra, "compose") as compose:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(infra.main(), 1)
        compose.assert_not_called()

    def test_env_creation_is_private_random_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            temporary = Path(directory)
            (temporary / ".env.example").write_text((ROOT / ".env.example").read_text())
            with patch.object(infra, "ROOT", temporary), contextlib.redirect_stdout(io.StringIO()):
                infra.init_env()
                first = (temporary / ".env").read_text()
                infra.init_env()
            self.assertEqual(first, (temporary / ".env").read_text())
            self.assertEqual(stat.S_IMODE((temporary / ".env").stat().st_mode), 0o600)
            values = dict(line.split("=", 1) for line in first.splitlines() if line and not line.startswith("#"))
            self.assertEqual(len(base64.urlsafe_b64decode(values["AIRFLOW_FERNET_KEY"])), 32)
            self.assertNotEqual(values["PRODUCT_DB_PASSWORD"], values["AIRFLOW_DB_PASSWORD"])

    def test_compose_command_is_scoped_to_this_project(self):
        with patch.object(infra, "execute", return_value="") as execute:
            infra.compose("restart", "api")
        arguments = execute.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--project-name") + 1], "lab2-novamercado")
        self.assertEqual(arguments[arguments.index("--file") + 1], str(ROOT / "compose.yaml"))

    def test_ps_supports_jsonl_and_json_array(self):
        row = {"Service": "api", "State": "running"}
        for payload in (json.dumps([row]), json.dumps(row) + "\n"):
            with patch.object(infra, "compose", return_value=payload):
                self.assertEqual(infra.ps_rows(), [row])

    def test_healthy_services_do_not_hide_missing_initialization(self):
        rows = [{"Service": service, "State": "running", "Health": "healthy"} for service in infra.SERVICES]
        with patch.object(infra, "ps_rows", return_value=rows), patch.object(infra.time, "monotonic", side_effect=[0, 0, 4]), patch.object(infra.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "Tiempo agotado"):
                infra.wait_healthy(timeout=1)

    def test_failed_initialization_stops_health_wait(self):
        with patch.object(infra, "ps_rows", return_value=[{"Service": "airflow-init", "State": "exited", "ExitCode": 1}]):
            with self.assertRaisesRegex(RuntimeError, "Falló airflow-init"):
                infra.wait_healthy()


if __name__ == "__main__":
    unittest.main()
