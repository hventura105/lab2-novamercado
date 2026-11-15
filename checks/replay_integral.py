"""Replay con PostgreSQL/MLflow/FastAPI reales y ventas oficiales, en un espacio aislado.

Se transmite por stdin al contenedor API. No modifica el esquema novamercado,
el alias productivo, los archivos oficiales ni los contenedores.
"""

import copy
from datetime import date, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


def rewrite_sql(query, schema):
    if not re.fullmatch(r"novamercado_it_[a-f0-9]{16}", schema):
        raise ValueError("El replay exige un esquema de prueba inequívoco")
    if not isinstance(query, str) or re.search(r"\b(?:DROP|DELETE|TRUNCATE|ALTER)\b", query, re.I):
        raise ValueError("SQL destructivo o dinámico no admitido en replay")
    result = re.sub(r"\bnovamercado\.", schema + ".", query)
    result = re.sub(r"(CREATE SCHEMA IF NOT EXISTS\s+)novamercado\b", lambda match: match[1] + schema, result, flags=re.I)
    if "pg_advisory" in result or "pg_try_advisory" in result:
        lock = (1 << 40) + int.from_bytes(hashlib.sha256(schema.encode()).digest()[:4], "big") * 2
        keys = {"184002": lock, "184003": lock + 1}
        result = re.sub(r"\b(184002|184003)\b", lambda match: str(keys[match[1]]), result)
    if re.search(r"\bnovamercado\.", result):
        raise ValueError("No se pudo aislar una referencia SQL")
    return result


class ScopedCursor:
    def __init__(self, cursor, schema):
        self.cursor, self.schema = cursor, schema

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *arguments):
        return self.cursor.__exit__(*arguments)

    def execute(self, query, *arguments, **kwargs):
        return self.cursor.execute(rewrite_sql(query, self.schema), *arguments, **kwargs)

    def executemany(self, query, *arguments, **kwargs):
        return self.cursor.executemany(rewrite_sql(query, self.schema), *arguments, **kwargs)

    def copy(self, query, *arguments, **kwargs):
        return self.cursor.copy(rewrite_sql(query, self.schema), *arguments, **kwargs)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class ScopedConnection:
    """Transporte real de psycopg; redirige solamente identificadores SQL constantes."""

    def __init__(self, connection, schema):
        self.connection, self.schema = connection, schema

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *arguments):
        return self.connection.__exit__(*arguments)

    def execute(self, query, *arguments, **kwargs):
        return self.connection.execute(rewrite_sql(query, self.schema), *arguments, **kwargs)

    def cursor(self, *arguments, **kwargs):
        return ScopedCursor(self.connection.cursor(*arguments, **kwargs), self.schema)


def call(base, path, payload=None, timeout=30):
    data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def wait_for(base, path, predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            code, body = call(base, path, timeout=min(5, max(0.1, deadline - time.monotonic())))
            if code == 200 and predicate(body):
                return body
        except OSError:
            pass
        time.sleep(0.5)
    raise TimeoutError("El replay no alcanzó el estado esperado dentro del límite")


def main():
    sys.path.insert(0, "/app")
    import uvicorn
    from app.core.health import database_connection
    from app.main import create_app
    from app.services.ciclo import training_cycle
    from app.services.fuentes import Sources
    from app.services.integraciones import Airflow, Tracking
    from app.services.repositorio import Repository
    from app.services.runtime import Runtime

    parameters = json.loads(sys.argv[2])
    token = parameters["token"]
    if not re.fullmatch(r"[a-f0-9]{16}", token):
        raise ValueError("Identificador de replay inválido")
    schema = "novamercado_it_" + token
    name = schema + "_ventas"
    with database_connection() as db:
        check(db.execute("SELECT to_regnamespace(%s)", (schema,)).fetchone()[0] is None, "El esquema de replay ya existe; no se sobrescribe")
    tracking = Tracking(name=name)
    try:
        tracking.call("registered-models/get?name=" + name)
    except HTTPError as error:
        check(error.code == 404, "No se pudo comprobar ausencia del modelo aislado")
    else:
        raise RuntimeError("El modelo aislado ya existe; no se modifica")
    sources = Sources(Path(os.environ.get("DATA_DIRECTORY", "/data/entrada")))
    cutoff = sources.history_end - timedelta(days=112)
    initial = copy.copy(sources)
    initial.history = [row for row in sources.history if row.fecha <= cutoff]
    initial.history_end = cutoff
    check(len({row.fecha for row in initial.history}) >= 120, "Histórico insuficiente para replay sin fuga")
    repository = Repository(lambda: ScopedConnection(database_connection(), schema))
    runtime = Runtime(repository, tracking, Airflow(), initial)
    logging.getLogger("app.services.runtime").setLevel(logging.CRITICAL)
    app = create_app(runtime, background=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Puerto efímero solo dentro del contenedor para el servidor de prueba; no se publica en Docker/host.
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    started = time.monotonic()
    thread.start()
    base = f"http://127.0.0.1:{port}"
    result = {"schema": schema, "modelo_registry": name, "fuentes_sha256": sources.hashes,
              "historia_inicial_hasta": cutoff.isoformat(), "servidor": "FastAPI HTTP real en loopback del contenedor, separado del puerto 8000",
              "orquestacion": "Pipeline de entrenamiento real; DAG productivo se comprueba por separado",
              "etapas": [], "promociones_observadas": 0, "rechazos_observados": 0, "repeticion_historica_sin_fuga": False}
    try:
        wait_for(base, "/health", lambda body: body == {"estado": "ok"}, 600)
        result["seconds_bootstrap_aislado"] = time.monotonic() - started
        check(result["seconds_bootstrap_aislado"] <= 600, "Bootstrap aislado excedió diez minutos")
        initial_model = call(base, "/modelo")[1]
        check(initial_model["nombre"] == name and initial_model["alias"] == "champion", "Modelo inicial del replay incorrecto")
        by_day = {}
        for row in sources.history:
            if row.fecha > cutoff:
                by_day.setdefault(row.fecha, {}).setdefault(row.tienda_id, []).append(row)
        previous_cutoff = cutoff
        previous_forecast = None
        for extra in (28, 56, 84, 112):
            end = cutoff + timedelta(days=extra)
            stored = 0
            for day in sorted(day for day in by_day if previous_cutoff < day <= end):
                for sid, rows in sorted(by_day[day].items()):
                    raw = {"tienda_id": sid, "fecha": day.isoformat(), "ventas": [{"familia_id": row.familia_id, "ventas": row.ventas} for row in rows]}
                    code, body = call(base, "/v1/observaciones", raw)
                    check(code == 200 and body["registros_guardados"] == len(rows), "No se guardaron observaciones reales nuevas del replay")
                    stored += len(rows)
            before = call(base, "/modelo")[1]
            active_before = repository.active()
            identifier = "replay__" + token + "__" + str(extra)
            repository.create_run(identifier)
            training_started = time.monotonic()
            # Mismo pipeline real que invoca el DAG, sobre las dependencias aisladas.
            training_cycle(repository, tracking, initial, identifier)
            elapsed = time.monotonic() - training_started
            check(elapsed <= 600, "Pipeline de replay excedió diez minutos")
            finished = repository.get_run(identifier)
            check(finished["estado"] == "exitoso", "El pipeline aislado no terminó exitosamente")
            active_after = repository.active()
            with repository.connect() as db:
                candidate = db.execute("SELECT version,metricas,run_id FROM novamercado.modelos ORDER BY creado_en DESC LIMIT 1").fetchone()
            registered = tracking.call("model-versions/get?name=" + name + "&version=" + str(candidate[0]))["model_version"]
            check(registered.get("status") == "READY" and registered.get("run_id") == candidate[2], "Falta versión real del candidato en MLflow")
            if finished["promovido"]:
                reload_started = time.monotonic()
                current = wait_for(base, "/modelo", lambda body: body.get("version") == finished["version"], 120)
                reload_seconds = time.monotonic() - reload_started
                check(current["version"] != before["version"] and thread.is_alive(), "No hubo cambio real de versión sin reiniciar API")
                result["promociones_observadas"] += 1
                if previous_forecast:
                    old_request, old_response = previous_forecast
                    code, repeated = call(base, "/v1/prediccion", old_request)
                    check(code == 200 and repeated["version_modelo"] == old_response["version_modelo"] and repeated["predicciones"] == old_response["predicciones"], "Repetición histórica incorporó etiquetas futuras o un artefacto posterior")
                    result["repeticion_historica_sin_fuga"] = True
            else:
                current = call(base, "/modelo")[1]
                check(current == before and active_before == active_after, "Un candidato no promovido cambió el vigente")
                reload_seconds = None
                result["rechazos_observados"] += 1
            check(tracking.alias_version() == current["version"], "Alias del replay no coincide con la API")
            next_day = end + timedelta(days=1)
            sid = sorted(sources.stores)[0]
            promotions = {row.familia_id: row.en_promocion for row in sources.history if row.fecha == next_day and row.tienda_id == sid}
            # Si el último día ya no tiene solicitud oficial de promoción, no se inventa ninguna.
            predicted = None
            if set(promotions) == set(sources.families):
                raw = {"tienda_id": sid, "fecha": next_day.isoformat(), "familias": [{"familia_id": family, "en_promocion": promotions[family]} for family in sorted(promotions)]}
                code, forecast = call(base, "/v1/prediccion", raw)
                check(code == 200 and forecast["version_modelo"] == current["version"], "La inferencia no utiliza la versión incorporada")
                predicted = {"fecha": next_day.isoformat(), "version": forecast["version_modelo"], "familias": len(forecast["predicciones"])}
                previous_forecast = raw, forecast
            result["etapas"].append({"hasta": end.isoformat(), "observaciones_nuevas": stored, "resultado": finished,
                "candidato_version": str(candidate[0]), "metricas": candidate[1],
                "seconds_entrenamiento": elapsed, "seconds_recarga": reload_seconds, "prediccion": predicted})
            previous_cutoff = end
            if result["promociones_observadas"] and result["rechazos_observados"] and result["repeticion_historica_sin_fuga"]:
                break
        result["seconds_total"] = time.monotonic() - started
        result["api_prueba_sin_reinicio"] = thread.is_alive()
        result["nota"] = "Se conservan esquema/modelos aislados como evidencia. No se cambió champion ni datos productivos. Bootstrap no equivale a arranque Docker vacío."
        return result
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        runtime.close()
        sock.close()


if __name__ == "__main__":
    try:
        print(json.dumps(main(), ensure_ascii=False, allow_nan=False, default=str))
    except Exception as error:
        print(json.dumps({"error_tipo": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
                          "detalle": "Replay fallido; se preservan evidencias y no se muestran filas o credenciales"}))
        sys.exit(1)
