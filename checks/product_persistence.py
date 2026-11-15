"""Marcadores técnicos aislados; no genera datos de negocio ni modelos."""

import json
import os
import re
import sys
import time
from urllib.parse import quote, urlsplit

sys.path.insert(0, "/app")
from app.core.health import database_connection
from connectivity import request

MLFLOW = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")


def artifact_url(artifact_uri):
    uri = urlsplit(artifact_uri)
    if uri.scheme != "mlflow-artifacts" or uri.netloc:
        raise RuntimeError("El experimento no usa el proxy de artefactos de MLflow")
    return MLFLOW + "/api/2.0/mlflow-artifacts/artifacts/" + uri.path.lstrip("/") + "/infra-probe.txt"


def seed(token):
    with database_connection() as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS infra_checks")
        connection.execute("CREATE TABLE IF NOT EXISTS infra_checks.persistence_probe (token TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO infra_checks.persistence_probe (token) VALUES (%s)", (token,))
    experiment = request(MLFLOW + "/api/2.0/mlflow/experiments/create", {"name": "infra-check-" + token})
    run = request(MLFLOW + "/api/2.0/mlflow/runs/create", {
        "experiment_id": experiment["experiment_id"], "start_time": int(time.time() * 1000),
        "tags": [{"key": "purpose", "value": "phase1-infrastructure"}, {"key": "infra_token", "value": token}],
    })["run"]["info"]
    url = artifact_url(run["artifact_uri"])
    request(url, raw=token.encode(), method="PUT")
    request(MLFLOW + "/api/2.0/mlflow/runs/update", {"run_id": run["run_id"], "status": "FINISHED", "end_time": int(time.time() * 1000)})
    # Registro vacío de infraestructura: verifica el Model Registry sin crear un modelo predictivo.
    registry_name = "infra-check-" + token
    request(MLFLOW + "/api/2.0/mlflow/registered-models/create", {"name": registry_name, "description": "Marcador técnico de persistencia de Fase 1; sin versiones ni modelo."})
    return {"token": token, "run_id": run["run_id"], "artifact_uri": run["artifact_uri"], "registry_name": registry_name}


def verify(state):
    token = state["token"]
    with database_connection() as connection:
        row = connection.execute("SELECT token FROM infra_checks.persistence_probe WHERE token = %s", (token,)).fetchone()
        if row != (token,):
            raise RuntimeError("Se perdió el marcador PostgreSQL")
    run = request(MLFLOW + "/api/2.0/mlflow/runs/get?run_id=" + quote(state["run_id"]))["run"]
    tags = {item["key"]: item["value"] for item in run["data"].get("tags", [])}
    if tags.get("infra_token") != token or run["info"]["status"] != "FINISHED":
        raise RuntimeError("Se perdió el registro MLflow")
    if request(artifact_url(state["artifact_uri"])) != token:
        raise RuntimeError("Se perdió el artefacto MLflow")
    registry = request(MLFLOW + "/api/2.0/mlflow/registered-models/get?name=" + quote(state["registry_name"]))
    if registry["registered_model"]["name"] != state["registry_name"]:
        raise RuntimeError("Se perdió el registro de modelos MLflow")
    return {"postgres": "ok", "mlflow_run": "ok", "mlflow_artifact": "ok", "mlflow_registry": "ok"}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "seed":
        token = sys.argv[2]
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Token de prueba inválido")
        print(json.dumps(seed(token)))
    elif mode == "verify":
        print(json.dumps(verify(json.load(sys.stdin))))
    else:
        raise ValueError("Usar seed TOKEN o verify (JSON por stdin)")
