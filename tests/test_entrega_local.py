"""Revisión de exportación y resultados pytest; no servicios ni credenciales reales."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import entrega_local as export
from scripts import verificar_cierre as closing


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=export.ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "api").mkdir()
        (self.root / "api/app.py").write_text("print('código')\n")
        (self.root / "data/entrada").mkdir(parents=True)
        (self.root / "data/entrada/.gitkeep").touch()
        (self.root / "data/entrada/historico_ventas.csv").write_text("privado")
        (self.root / ".env").write_text("API_TOKEN=sentinela_credencial_123\n")

    def test_export_excludes_env_raw_data_and_private_evidence(self):
        with patch.object(export, "ROOT", self.root):
            target, hashes = export.export_source()
        self.assertIn("data/entrada/.gitkeep", hashes)
        self.assertNotIn("data/entrada/historico_ventas.csv", hashes)
        self.assertNotIn(".env", hashes)
        self.assertFalse((target / "evidence/private").exists())
        self.assertEqual((target / "api/app.py").read_bytes(), (self.root / "api/app.py").read_bytes())

    def test_actual_known_secret_blocks_export_before_creating_copy(self):
        (self.root / "api/app.py").write_text("sentinela_credencial_123")
        with patch.object(export, "ROOT", self.root):
            with self.assertRaisesRegex(RuntimeError, "Posible secreto") as captured:
                export.export_source()
        self.assertNotIn("sentinela_credencial_123", str(captured.exception))
        self.assertFalse((self.root / "evidence/private/entrega").exists())

    def test_source_symlinks_are_refused(self):
        (self.root / "api/enlace.py").symlink_to(self.root / ".env")
        with patch.object(export, "ROOT", self.root):
            with self.assertRaises(RuntimeError):
                export.selected_files()

    def test_private_key_header_is_blocked_even_if_not_in_env(self):
        (self.root / "api/app.py").write_bytes(b"-----BEGIN " + b"PRIVATE KEY-----\n")
        with patch.object(export, "ROOT", self.root):
            with self.assertRaisesRegex(RuntimeError, "Posible secreto"):
                export.export_source()


class ClosingTests(unittest.TestCase):
    def junit(self, **attributes):
        values = {"tests": 10, "failures": 0, "errors": 0, "skipped": 0, **attributes}
        opening = " ".join(f'{key}="{value}"' for key, value in values.items())
        cases = ''.join(f'<testcase classname="api.tests.test_endpoints.EndpointTests" name="test_{i}"/>' for i in range(10))
        return '<testsuites><testsuite ' + opening + '>' + cases + '</testsuite></testsuites>'

    def test_junit_requires_real_nonempty_success_and_ten_contracts(self):
        result = closing.junit_counts(self.junit())
        self.assertEqual(result["tests"], 10)
        self.assertEqual(result["contratos_asgi"], 10)
        with self.assertRaises(RuntimeError):
            closing.junit_counts(self.junit().replace("EndpointTests", "OtraClase"))

    def test_failures_errors_skips_and_empty_suite_cannot_pass(self):
        for attr in ({"failures": 1}, {"errors": 1}, {"skipped": 1}, {"tests": 0}):
            with self.subTest(attr=attr), self.assertRaises(RuntimeError):
                closing.junit_counts(self.junit(**attr))

    def test_docker_failure_cannot_build_create_or_export(self):
        with tempfile.TemporaryDirectory(dir=export.ROOT) as temporary, patch.object(closing, "ROOT", Path(temporary)), patch.object(closing, "run", side_effect=RuntimeError("daemon no disponible")) as run, patch.object(export, "export_source") as copy, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(closing.main(), 1)
        self.assertEqual(run.call_count, 1)
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
