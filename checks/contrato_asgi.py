"""Ejecuta únicamente los contratos ASGI y conserva trazas; no inicia servicios."""

import importlib.metadata
import io
import linecache
import platform
import traceback
import unittest


def run_suite(source, include_traces=False):
    filename = "<contrato_asgi_host>"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    namespace = {"__name__": "contrato_unittest", "__file__": "/app/tests/test_endpoints.py"}
    dependencies = {}
    for name in ("fastapi", "pydantic", "starlette", "anyio", "uvicorn"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "no_instalado"
    outcome = {"python": platform.python_version(), "dependencias": dependencies}
    try:
        exec(compile(source, filename, "exec"), namespace)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace["EndpointTests"])
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        outcome.update(ejecutadas=result.testsRun, fallos=len(result.failures), errores=len(result.errors),
                       omitidas=len(result.skipped), identificadores_fallidos=[str(case) for case, _ in result.failures + result.errors])
        if include_traces:
            outcome["trazas"] = [{"caso": str(case), "tipo": kind, "traza": text}
                                 for kind, values in (("fallo", result.failures), ("error", result.errors)) for case, text in values]
            outcome["salida_unittest"] = stream.getvalue()
    except Exception as error:
        outcome.update(ejecutadas=0, fallos=0, errores=1, omitidas=0, error_carga=type(error).__name__, identificadores_fallidos=["carga_de_suite"])
        if include_traces:
            outcome["trazas"] = [{"caso": "carga_de_suite", "tipo": "error", "traza": traceback.format_exc()}]
    return outcome
