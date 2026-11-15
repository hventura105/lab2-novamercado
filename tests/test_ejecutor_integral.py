"""Salvaguardas locales del ejecutor; no acreditan integración de servicios."""

import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from checks import replay_integral
from checks import inspeccion_integral
from scripts import pruebas_integrales as suite


class ReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=suite.ROOT)
        self.addCleanup(temporary.cleanup)
        self.report = suite.Report(Path(temporary.name) / "informe")

    def test_pending_is_never_success_exit(self):
        self.report.pending("servicio", "Sin acceso real")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.report.finish(), 2)
        self.assertEqual(self.report.data["estado"], "incompleto")

    def test_all_completed_checks_can_succeed(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.report.case("servicio", lambda: {"http": 200})
            self.assertEqual(self.report.finish(), 0)

    def test_unknown_errors_do_not_expose_private_messages(self):
        def fail():
            raise RuntimeError("password=sentinela_no_imprimir")
        with contextlib.redirect_stdout(io.StringIO()):
            row = self.report.case("servicio", fail)
            self.assertEqual(self.report.finish(), 1)
        self.assertEqual(row["estado"], "fallida")
        self.assertNotIn("sentinela_no_imprimir", (self.report.directory / "informe.json").read_text())

    def test_interruption_is_saved_as_interruption(self):
        def interrupt():
            raise KeyboardInterrupt()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                self.report.case("servicio", interrupt)
        saved = json.loads((self.report.directory / "informe.json").read_text())
        self.assertEqual(saved["estado"], "interrumpido")
        self.assertEqual(saved["casos"][0]["estado"], "interrumpida")

    def test_failed_preflight_cannot_trigger_any_write_or_interruption(self):
        integration = MagicMock()
        integration.preflight.side_effect = suite.Blocked("daemon denegado")
        with patch.object(suite, "Report", return_value=self.report), patch.object(suite, "Integration", return_value=integration), patch.object(suite.sys, "argv", ["runner", "--con-interrupciones", "--replay-promocion"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(suite.main(), 1)
        integration.observations.assert_not_called()
        integration.predictions.assert_not_called()
        integration.dag.assert_not_called()
        integration.replay.assert_not_called()
        integration.outage.assert_not_called()
        integration.persistence.assert_not_called()

    def test_failed_quality_stops_later_writes_and_interruptions(self):
        integration = MagicMock()
        integration.quality.side_effect = suite.Failed("Rechazo inválido")
        with patch.object(suite, "Report", return_value=self.report), patch.object(suite, "Integration", return_value=integration), patch.object(suite.sys, "argv", ["runner", "--con-interrupciones", "--replay-promocion"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(suite.main(), 1)
        integration.observations.assert_not_called()
        integration.dag.assert_not_called()
        integration.replay.assert_not_called()
        integration.outage.assert_not_called()
        integration.persistence.assert_not_called()
        integration.registry.assert_called_once()

    def test_solo_asgi_never_runs_product_checks_even_on_failure(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                integration = MagicMock()
                if fails:
                    integration.asgi_contract.side_effect = suite.Failed("Contrato no aprobado")
                self.report.data["casos"] = []
                with patch.object(suite, "Report", return_value=self.report), patch.object(suite, "Integration", return_value=integration), patch.object(suite.sys, "argv", ["runner", "--solo-asgi", "--trazas-asgi"]), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(suite.main(), 1 if fails else 0)
                self.assertTrue(integration.asgi_traces)
                self.assertEqual([call[0] for call in integration.method_calls], ["asgi_contract"])
                self.assertEqual(len(self.report.data["casos"]), 1)

    def test_solo_asgi_rejects_interruptions_and_replay_before_docker(self):
        for flag in ("--con-interrupciones", "--replay-promocion"):
            with self.subTest(flag=flag), patch.object(suite, "Integration") as integration, patch.object(suite.sys, "argv", ["runner", "--solo-asgi", flag]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as captured:
                    suite.main()
                self.assertEqual(captured.exception.code, 2)
                integration.assert_not_called()

    def test_asgi_failure_keeps_traces_and_counts_while_redacting_secrets(self):
        integration = suite.Integration(self.report)
        integration.asgi_traces = True
        outcome = {"ejecutadas": 10, "fallos": 5, "errores": 2, "omitidas": 0,
                   "trazas": [{"traza": "NameError: sentinela_privada_token"}],
                   "salida_unittest": "Traceback: sentinela_privada_token"}
        read_text = Path.read_text

        def content(path, *args, **kwargs):
            if path == suite.ROOT / ".env":
                return "API_TOKEN=sentinela_privada_token\n"
            return read_text(path, *args, **kwargs)

        with patch.object(integration, "compose", return_value=json.dumps(outcome)), patch.object(Path, "read_text", content):
            with self.assertRaises(suite.Failed):
                integration.asgi_contract()
        saved = json.loads((self.report.directory / "informe.json").read_text())
        self.assertEqual(saved["contrato_asgi"]["fallos"], 5)
        self.assertEqual(saved["contrato_asgi"]["errores"], 2)
        self.assertIn("NameError", saved["contrato_asgi"]["trazas"][0]["traza"])
        self.assertNotIn("sentinela_privada_token", (self.report.directory / "trazas_asgi.txt").read_text())
        self.assertNotIn("sentinela_privada_token", (self.report.directory / "informe.json").read_text())


class IsolationTests(unittest.TestCase):
    schema = "novamercado_it_0123456789abcdef"

    def test_entire_real_migration_is_redirected_to_private_schema(self):
        sql = (suite.ROOT / "api/migrations/001_producto.sql").read_text()
        rewritten = replay_integral.rewrite_sql(sql, self.schema)
        self.assertNotRegex(rewritten, r"\bnovamercado\.")
        self.assertIn("CREATE SCHEMA IF NOT EXISTS " + self.schema, rewritten)
        self.assertIn("REFERENCES " + self.schema + ".modelos", rewritten)

    def test_sql_lock_names_do_not_collide_with_product(self):
        first = replay_integral.rewrite_sql("SELECT pg_advisory_xact_lock(184002)", self.schema)
        second = replay_integral.rewrite_sql("SELECT pg_try_advisory_xact_lock(184003)", self.schema)
        a = int(re.search(r"\((\d+)\)", first)[1])
        b = int(re.search(r"\((\d+)\)", second)[1])
        self.assertGreaterEqual(a, 1 << 40)
        self.assertEqual(b, a + 1)

    def test_schema_cannot_select_product_or_inject_sql(self):
        for schema in ("novamercado", "public", "novamercado_it_x;DROP SCHEMA public", "novamercado_it_0123456789abcdef.extra"):
            with self.assertRaises(ValueError):
                replay_integral.rewrite_sql("SELECT 1", schema)

    def test_destructive_sql_is_refused_even_for_private_tables(self):
        for verb in ("DROP TABLE", "TRUNCATE", "DELETE FROM", "ALTER TABLE"):
            with self.assertRaises(ValueError):
                replay_integral.rewrite_sql(verb + " novamercado.historico", self.schema)

    def test_connection_is_real_transport_and_does_not_rewrite_values(self):
        connection = MagicMock()
        scoped = replay_integral.ScopedConnection(connection, self.schema)
        values = ("texto novamercado.historico como dato, no SQL",)
        scoped.execute("INSERT INTO novamercado.solicitudes(id) VALUES (%s)", values)
        sql, parameters = connection.execute.call_args.args
        self.assertIn(self.schema + ".solicitudes", sql)
        self.assertIs(parameters, values)

    def test_copy_and_bulk_writes_target_only_isolated_schema(self):
        cursor = MagicMock()
        scoped = replay_integral.ScopedCursor(cursor, self.schema)
        scoped.copy("COPY novamercado.historico FROM STDIN")
        scoped.executemany("INSERT INTO novamercado.familias VALUES (%s,%s)", [("a", "A")])
        self.assertIn(self.schema + ".historico", cursor.copy.call_args.args[0])
        self.assertIn(self.schema + ".familias", cursor.executemany.call_args.args[0])


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.report = MagicMock()
        self.report.data = {}
        self.integration = suite.Integration(self.report)

    def test_helpers_transmit_payload_by_stdin_not_process_arguments(self):
        with patch.object(self.integration, "compose", return_value='{"ok":true}') as compose:
            self.integration.inside("inspeccion_integral.py", "estado_observacion", {"valor": "sentinela_privada"})
        self.assertEqual(compose.call_args.args, ("exec", "-T", "api", "python", "-"))
        self.assertIn("sentinela_privada", compose.call_args.kwargs["source"])

    def test_docker_commands_always_select_lab2_explicitly(self):
        completed = SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with patch.object(suite.subprocess, "run", return_value=completed) as run:
            self.integration.compose("port", "api", "8000")
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--project-name") + 1], "lab2-novamercado")
        self.assertEqual(args[args.index("--file") + 1], str(suite.ROOT / "compose.yaml"))
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_child_errors_keep_type_and_sqlstate_without_stderr(self):
        completed = SimpleNamespace(returncode=1, stdout=json.dumps({"error_tipo": "UndefinedTable", "sqlstate": "42P01"}), stderr="password=secreto_no_imprimir")
        with patch.object(suite.subprocess, "run", return_value=completed):
            with self.assertRaises(suite.Failed) as captured:
                self.integration.compose("exec", "-T", "api", "python", "-")
        self.assertIn("42P01", str(captured.exception))
        self.assertNotIn("secreto_no_imprimir", str(captured.exception))

    def test_mlflow_is_restarted_even_if_prediction_during_outage_fails(self):
        self.integration.urls = {"api": "http://127.0.0.1:8000"}
        self.integration.prediction_request = {"tienda_id": 1, "fecha": "2026-03-01", "familias": []}
        with patch.object(self.integration, "no_active_training"), patch.object(self.integration, "inspect", return_value={"api": {"id": "unit"}}), patch.object(self.integration, "compose") as compose, patch.object(self.integration, "wait_health", return_value={}), patch.object(suite, "http", side_effect=[{"body": {"version": "1"}}, {"status": 503, "body": {}}]):
            with self.assertRaises(suite.Failed):
                self.integration.outage()
        self.assertEqual([call.args for call in compose.call_args_list], [("stop", "mlflow"), ("start", "mlflow")])

    def test_no_foreign_container_can_pass_inventory(self):
        rows = [{"ID": str(i), "Service": service} for i, service in enumerate(suite.infra.SERVICES)]
        foreign = "\n".join(json.dumps({"project": "otro", "running": True}) for _ in rows)
        with patch.object(suite.infra, "ps_rows", return_value=rows), patch.object(suite.infra, "execute", return_value=foreign):
            with self.assertRaises(suite.Failed):
                self.integration.inspect()


class ContractValidationTests(unittest.TestCase):
    def test_artifact_hash_matches_host_and_sql_helper_with_numeric_normalization(self):
        a = {"coefficients": [1.0, -0.0, 0.1234], "format": 1}
        b = {"format": 1.0, "coefficients": [1, 0, 0.1234]}
        self.assertEqual(suite.canonical_hash(a), inspeccion_integral.canonical_hash(b))
        self.assertNotEqual(suite.canonical_hash({"x": True}), suite.canonical_hash({"x": 1}))

    def test_warning_precedence_is_checked_in_actual_http_results(self):
        with self.assertRaises(suite.Failed):
            suite.validate_quality({"estado": "corregido", "observaciones": [{"campo": "x", "accion": "advertir", "detalle": "d"}]})

    def test_boolean_is_not_valid_inventory_integer(self):
        request = {"tienda_id": 1, "fecha": "2026-03-01", "familias": [{"familia_id": "a"}]}
        response = {"status": 200, "body": {"tienda_id": 1, "fecha": "2026-03-01", "version_modelo": "1",
                    "predicciones": [{"familia_id": "a", "venta_esperada": 1, "cantidad_sugerida": True}], "calidad": {"estado": "ok", "observaciones": []}}}
        with self.assertRaises(suite.Failed):
            suite.validate_prediction(response, request)


if __name__ == "__main__":
    unittest.main()
