"""Guardas del ejecutor aislado; no acreditan un arranque real de Docker."""

import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import prueba_arranque_limpio as cold

PROJECT = "novamercado-arranque-20261115t011732z-4299dce5"
OK = {"http": 200, "body": {"estado": "ok"}}


def configuration():
    services = {s: {"image": "version:1", "networks": {"internal": None}} for s in cold.SERVICES}
    services["api"].update(build={"context": str(cold.ROOT)}, ports=[{"published": "8000"}],
        environment={"PRODUCT_DB_HOST": "product-db", "MLFLOW_TRACKING_URI": "http://mlflow:5000"},
        volumes=[{"type": "bind", "source": str(cold.ROOT / "data/entrada"), "target": "/data/entrada", "read_only": True}])
    return {"name": cold.MAIN, "services": services, "volumes": {v: {} for v in cold.VOLUMES},
            "networks": {"internal": {"internal": True}, "publicacion": {"driver": "bridge"}}}


class IsolationTests(unittest.TestCase):
    def test_config_has_unique_resources_no_ports_and_no_build(self):
        config = cold.isolated_config(configuration(), PROJECT)
        self.assertEqual(config["name"], PROJECT)
        self.assertTrue(all(v["name"].startswith(PROJECT + "_") for v in config["volumes"].values()))
        self.assertTrue(all(n["name"].startswith(PROJECT + "_") for n in config["networks"].values()))
        self.assertFalse(any(s.get("ports") or s.get("build") for s in config["services"].values()))
        self.assertTrue(all(s["pull_policy"] == "never" for s in config["services"].values()))

    def test_refuses_existing_project_and_unknown_resources(self):
        for name in (cold.MAIN, "novamercado-arranque-../otro"):
            with self.assertRaises(cold.Refused):
                cold.isolated_config(configuration(), name)
        config = configuration()
        config["volumes"]["desconocido"] = {}
        with self.assertRaises(cold.Refused):
            cold.isolated_config(config, PROJECT)

    def test_refuses_external_and_redirected_volumes(self):
        for setting in ({"external": True}, {"driver_opts": {"device": "/var/lib/otro"}}):
            config = configuration()
            config["volumes"]["product-db-data"] = setting
            with self.assertRaises(cold.Refused):
                cold.isolated_config(config, PROJECT)

    def test_refuses_privilege_host_network_or_foreign_container_name(self):
        for key, value in (("privileged", True), ("network_mode", "host"), ("container_name", "ajeno")):
            config = configuration()
            config["services"]["api"][key] = value
            with self.assertRaises(cold.Refused):
                cold.isolated_config(config, PROJECT)

    def test_refuses_writable_or_unknown_binds_and_remote_database(self):
        for key, value in (("read_only", False), ("source", "/var/run/docker.sock")):
            config = configuration()
            config["services"]["api"]["volumes"][0][key] = value
            with self.assertRaises(cold.Refused):
                cold.isolated_config(config, PROJECT)
        config = configuration()
        config["services"]["api"]["environment"]["PRODUCT_DB_HOST"] = "otra-base"
        with self.assertRaises(cold.Refused):
            cold.isolated_config(config, PROJECT)

    def test_prepare_never_calls_docker_and_generates_own_secrets(self):
        with tempfile.TemporaryDirectory(dir=cold.ROOT) as temporary:
            root = Path(temporary)
            (root / ".env.example").write_text("PRODUCT_DB_PASSWORD=\nAIRFLOW_FERNET_KEY=\n")
            with patch.object(cold, "ROOT", root), patch.object(cold, "command") as command:
                first, second = cold.prepare(), cold.prepare()
                command.assert_not_called()
            self.assertNotEqual(first, second)
            self.assertNotEqual((first / "prueba.env").read_text(), (second / "prueba.env").read_text())
            self.assertEqual((first / "prueba.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((first / "plan.json").read_text())["puertos_publicados"], [])

    def test_command_errors_do_not_expose_stderr(self):
        result = subprocess.CompletedProcess([], 1, "", "password=sentinela_privada")
        with patch.object(cold.subprocess, "run", return_value=result):
            with self.assertRaises(cold.Refused) as captured:
                cold.command(["docker", "info"])
        self.assertNotIn("sentinela_privada", str(captured.exception))

    def test_cli_requires_explicit_authorization_before_runner(self):
        with patch.object(cold.sys, "argv", ["runner", "ejecutar", "--plan", "cualquier-plan"]), patch.object(cold, "ColdStart") as runner, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as captured:
                cold.main()
            self.assertEqual(captured.exception.code, 2)
            runner.assert_not_called()


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        base = cold.ROOT / "evidence/private/arranque-limpio"
        base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        cold.write_private(self.folder / "plan.json", {"proyecto": PROJECT, "estado": "preparado_sin_recursos"}, exclusive=True)
        cold.write_private(self.folder / "prueba.env", "PRODUCT_DB_PASSWORD=unit-test-only\n", exclusive=True)
        self.runner = cold.ColdStart(self.folder)

    def test_preflight_failure_cannot_start_services(self):
        with patch.object(self.runner, "preflight", side_effect=cold.Refused("Daemon no disponible")), patch.object(self.runner, "compose") as compose:
            self.assertEqual(self.runner.run(), 1)
        compose.assert_not_called()

    def run_scenario(self, elapsed=25, changed=False):
        before = {"sonda": OK, "huellas": {"historico": "sha"}}
        after = copy.deepcopy(before)
        if changed:
            after["huellas"]["historico"] = "cambio"
        client = MagicMock()
        client.code_coherence.return_value = {"coinciden": True}
        with patch.object(self.runner, "preflight"), patch.object(self.runner, "primary", side_effect=[before, after]), patch.object(self.runner, "compose") as compose, patch.object(self.runner, "probe", side_effect=[OK, {"verificado": True}]), patch.object(self.runner, "runtime_resources", return_value={"sin_puertos": True}), patch.object(self.runner, "client", return_value=client), patch.object(cold.time, "monotonic", side_effect=[10, 10 + elapsed]):
            code = self.runner.run()
        self.assertEqual(compose.call_args.args, ("up", "-d", "--no-build", "--pull", "never", "--no-recreate"))
        return code

    def test_elapsed_includes_compose_up_and_never_builds_or_cleans(self):
        self.assertEqual(self.run_scenario(), 0)
        self.assertEqual(self.runner.record["seconds_hasta_health_ok"], 25)
        self.assertTrue(self.runner.record["principal_sin_cambios"])

    def test_health_after_ten_minutes_is_rejected_even_if_ok(self):
        self.assertEqual(self.run_scenario(elapsed=601), 1)
        self.assertNotIn("verificacion", self.runner.record)
        self.assertTrue(self.runner.record["principal_sin_cambios"])

    def test_change_in_main_project_prevents_success(self):
        self.assertEqual(self.run_scenario(changed=True), 1)
        self.assertFalse(self.runner.record["principal_sin_cambios"])

    def test_attempted_plan_cannot_be_reused_as_empty(self):
        cold.write_private(self.folder / "informe.json", {"estado": "anterior"})
        with self.assertRaises(cold.Refused):
            cold.load_plan(self.folder)

    def test_case_variant_resolves_unique_existing_folder_without_recreating(self):
        real = self.folder / "20261115t011732z-4299dce5"
        real.mkdir()
        cold.write_private(real / "plan.json", {"proyecto": PROJECT, "estado": "preparado_sin_recursos"}, exclusive=True)
        requested = self.folder / "20261115T011732Z-4299dce5"
        self.assertEqual(cold.resolve_plan_folder(requested), real)
        self.assertEqual(cold.load_plan(requested)["proyecto"], PROJECT)
        self.assertFalse(requested.exists())

    def test_missing_folder_and_internal_file_have_controlled_diagnostics(self):
        with self.assertRaisesRegex(cold.Refused, "No existe la carpeta"):
            cold.load_plan(self.folder / "inexistente")
        empty = self.folder / "sin-plan"
        empty.mkdir()
        with self.assertRaisesRegex(cold.Refused, "Falta plan.json"):
            cold.load_plan(empty)

    def test_case_resolution_does_not_bypass_executed_plan_or_escape_root(self):
        cold.write_private(self.folder / "informe.json", {"estado": "aprobado"})
        with self.assertRaisesRegex(cold.Refused, "Plan ya intentado"):
            cold.load_plan(self.folder)
        self.assertEqual(cold.load_plan(self.folder, allow_attempted=True)["proyecto"], PROJECT)
        with self.assertRaisesRegex(cold.Refused, "debe permanecer"):
            cold.resolve_plan_folder(cold.ROOT / "afuera")

    def test_ambiguous_case_match_is_rejected(self):
        (self.folder / "Prueba").mkdir()
        (self.folder / "pRUEBA").mkdir()
        with self.assertRaisesRegex(cold.Refused, "ambigua"):
            cold.resolve_plan_folder(self.folder / "PRUEBA")

    def test_existing_named_volume_blocks_up(self):
        config = cold.isolated_config(configuration(), PROJECT)
        def answer(args, **kwargs):
            if args[:3] == ["docker", "volume", "ls"] and "--filter" not in args:
                return PROJECT + "_product-db-data\n"
            return ""
        with patch.object(self.runner, "configure", return_value=config), patch.object(cold, "command", side_effect=answer), patch.object(self.runner, "compose") as compose:
            with self.assertRaises(cold.Refused):
                self.runner.preflight()
        compose.assert_not_called()

    def test_actual_inventory_handles_exited_init_and_rejects_shared_resources(self):
        self.runner.record["volumenes_nuevos"] = [PROJECT + "_product-db-data"]
        rows = [{"project": PROJECT, "service": service, "mounts": [], "ports": None,
                 "networks": {PROJECT + "_internal": {}},
                 "state": "exited" if service == "airflow-init" else "running", "exit": 0}
                for service in sorted(cold.SERVICES)]
        with patch.object(self.runner, "compose", return_value=" ".join(str(i) for i in range(9))), patch.object(cold, "command", return_value="\n".join(json.dumps(row) for row in rows)):
            self.assertTrue(self.runner.runtime_resources()["sin_puertos_publicados"])
        for field, value in (("ports", {"8000/tcp": [{"HostPort": "8000"}]}),
                             ("mounts", [{"Type": "volume", "Name": cold.MAIN + "_product-db-data"}]),
                             ("mounts", [{"Type": "bind", "RW": True}])):
            changed = copy.deepcopy(rows)
            changed[0][field] = value
            with self.subTest(field=field, value=value), patch.object(self.runner, "compose", return_value=" ".join(str(i) for i in range(9))), patch.object(cold, "command", return_value="\n".join(json.dumps(row) for row in changed)):
                with self.assertRaises(cold.Refused):
                    self.runner.runtime_resources()


if __name__ == "__main__":
    unittest.main()
