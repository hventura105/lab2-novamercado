"""Regresión del helper ASGI exacto, sin dependencias ni servicios externos."""

import ast
import asyncio
import json
from pathlib import Path
import unittest

from checks.contrato_asgi import run_suite

ROOT = Path(__file__).resolve().parents[1]


def load_request():
    path = ROOT / "api/tests/test_endpoints.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "request")
    namespace = {"asyncio": asyncio, "json": json}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["request"]


async def echo_body(scope, receive, send):
    event = await receive()
    payload = json.loads(event["body"]) if event["body"] else None
    response = json.dumps({"method": scope["method"], "payload": payload}).encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": response})


class TransportRegressionTests(unittest.TestCase):
    def test_post_body_is_available_before_response_and_repeated_requests(self):
        request = load_request()
        raw = {"campo": "prueba de protocolo, no datos de negocio"}
        for path in ("/v1/prediccion", "/v1/observaciones", "/v1/prediccion"):
            status, body = request(echo_body, path, raw, "POST")
            self.assertEqual(status, 200)
            self.assertEqual(body, {"method": "POST", "payload": raw})

    def test_bodyless_admin_post_does_not_raise_unbound_free_variable(self):
        status, body = load_request()(echo_body, "/admin/reentrenar", method="POST")
        self.assertEqual((status, body["payload"]), (200, None))

    def test_empty_json_body_remains_different_from_no_body(self):
        request = load_request()
        _, response = request(echo_body, "/admin/reentrenar", {}, "POST")
        self.assertEqual(response["payload"], {})

    def test_get_and_response_decoding_preserve_input(self):
        request = load_request()
        self.assertEqual(request(echo_body, "/modelo")[1], {"method": "GET", "payload": None})


class DiagnosticCollectorTests(unittest.TestCase):
    def test_real_unittest_failure_and_error_traces_are_preserved(self):
        source = '''import unittest
class EndpointTests(unittest.TestCase):
    def test_assertion(self): self.assertEqual(200, 400)
    def test_error(self): raise NameError("sentinela diagnostica")
    def test_pass(self): self.assertTrue(True)
'''
        result = run_suite(source, include_traces=True)
        self.assertEqual((result["ejecutadas"], result["fallos"], result["errores"]), (3, 1, 1))
        self.assertEqual(len(result["trazas"]), 2)
        self.assertIn("sentinela diagnostica", result["salida_unittest"])
        self.assertIn("Traceback", result["trazas"][1]["traza"])

    def test_import_error_has_trace_and_dependency_metadata(self):
        result = run_suite("import modulo_diagnostico_inexistente_de_prueba", include_traces=True)
        self.assertEqual(result["error_carga"], "ModuleNotFoundError")
        self.assertEqual(result["ejecutadas"], 0)
        self.assertIn("fastapi", result["dependencias"])
        self.assertIn("ModuleNotFoundError", result["trazas"][0]["traza"])


if __name__ == "__main__":
    unittest.main()
