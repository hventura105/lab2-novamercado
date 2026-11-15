"""Clientes HTTP explícitos para MLflow 3.10.1 y Airflow 3.1.7."""

import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


def http(url, payload=None, method=None, headers=None, timeout=5, raw=None):
    data = json.dumps(payload, allow_nan=False).encode() if payload is not None else raw
    request_headers = {"Content-Type": "application/json" if raw is None else "application/octet-stream", **(headers or {})}
    with urlopen(Request(url, data=data, headers=request_headers, method=method), timeout=timeout) as response:
        result = response.read()
        return json.loads(result) if "application/json" in response.headers.get("Content-Type", "") else result


def error_code(error):
    try:
        return json.loads(error.read()).get("error_code")
    except (ValueError, AttributeError):
        return None


class Tracking:
    def __init__(self, url=None, name="novamercado_ventas_diarias", alias="champion"):
        self.url = (url or os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")).rstrip("/")
        self.name, self.alias = name, alias

    def call(self, path, payload=None, method=None):
        return http(self.url + "/api/2.0/mlflow/" + path, payload, method, timeout=10)

    def health(self):
        http(self.url + "/health", timeout=2)

    def alias_version(self):
        return str(self.call("registered-models/alias?" + urlencode({"name": self.name, "alias": self.alias}))["model_version"]["version"])

    def set_alias(self, version):
        self.call("registered-models/alias", {"name": self.name, "alias": self.alias, "version": str(version)})

    def experiment(self):
        try:
            return self.call("experiments/get-by-name?" + urlencode({"experiment_name": self.name}))["experiment"]["experiment_id"]
        except HTTPError as error:
            if error_code(error) != "RESOURCE_DOES_NOT_EXIST":
                raise
            return self.call("experiments/create", {"name": self.name})["experiment_id"]

    def upload(self, artifact_uri, name, value):
        uri = urlsplit(artifact_uri)
        if uri.scheme != "mlflow-artifacts" or uri.netloc:
            raise RuntimeError("MLflow debe servir artefactos mediante proxy")
        path = uri.path.strip("/") + "/" + name
        http(self.url + "/api/2.0/mlflow-artifacts/artifacts/" + path, method="PUT", raw=json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), timeout=15)

    def log_model(self, artifact, metrics, purpose, lineage):
        experiment = self.experiment()
        info = self.call("runs/create", {"experiment_id": experiment, "start_time": int(time.time() * 1000),
                    "tags": [{"key": "purpose", "value": purpose}, {"key": "mlflow.runName", "value": purpose + "_" + artifact["algorithm"]}]})["run"]["info"]
        try:
            scalar_metrics = {key: value for key, value in metrics.items() if isinstance(value, (int, float))}
            params = {"algorithm": artifact["algorithm"], "trained_through": artifact["trained_through"],
                      "fit_before": artifact["fit_before"], "calibration_days": 28, "ridge_alpha": 0.01 if artifact["algorithm"] == "ridge" else "not_applicable"}
            self.call("runs/log-batch", {"run_id": info["run_id"],
                "metrics": [{"key": key, "value": value, "timestamp": int(time.time() * 1000), "step": 0} for key, value in scalar_metrics.items()],
                "params": [{"key": key, "value": str(value)} for key, value in params.items()],
                "tags": [{"key": "simulation", "value": "sales_date_strictly_before_forecast_date"}]})
            self.upload(info["artifact_uri"], "model/model.json", artifact)
            self.upload(info["artifact_uri"], "model/MLmodel", {"flavors": {"novamercado_json": {"format_version": 1, "model_data": "model.json"}}, "run_id": info["run_id"]})
            self.upload(info["artifact_uri"], "lineage.json", {**lineage, "source_sha256": artifact["source_hashes"],
                "model_code_sha256": hashlib.sha256((Path(__file__).parent / "modelado.py").read_bytes()).hexdigest()})
            self.upload(info["artifact_uri"], "metrics.json", metrics)
            self.call("runs/update", {"run_id": info["run_id"], "status": "FINISHED", "end_time": int(time.time() * 1000)})
        except Exception:
            try:
                self.call("runs/update", {"run_id": info["run_id"], "status": "FAILED", "end_time": int(time.time() * 1000)})
            except Exception:
                pass
            raise
        return info

    def register(self, info):
        try:
            self.call("registered-models/create", {"name": self.name})
        except HTTPError as error:
            if error_code(error) != "RESOURCE_ALREADY_EXISTS":
                raise
        version = self.call("model-versions/create", {"name": self.name, "source": info["artifact_uri"].rstrip("/") + "/model", "run_id": info["run_id"]})["model_version"]
        if version.get("status", "READY") != "READY":
            raise RuntimeError("MLflow todavía no dejó la versión registrada en READY")
        return str(version["version"])


class Airflow:
    dag_id = "novamercado_reentrenamiento"

    def __init__(self):
        self.url = os.environ.get("AIRFLOW_URL", "http://airflow-api-server:8080")

    def headers(self):
        response = http(self.url + "/auth/token", {"username": os.environ["AIRFLOW_ADMIN_USER"], "password": os.environ["AIRFLOW_ADMIN_PASSWORD"]})
        return {"Authorization": "Bearer " + response["access_token"]}

    def trigger(self, identifier):
        headers = self.headers()
        http(self.url + f"/api/v2/dags/{self.dag_id}", {"is_paused": False}, "PATCH", headers)
        return http(self.url + f"/api/v2/dags/{self.dag_id}/dagRuns", {"dag_run_id": identifier, "logical_date": None, "conf": {"execution_id": identifier}}, headers=headers)

    def state(self, identifier):
        response = http(self.url + f"/api/v2/dags/{self.dag_id}/dagRuns/" + quote(identifier, safe=""), headers=self.headers())
        return response["state"]

    def health(self):
        result = http(self.url + "/api/v2/monitor/health", timeout=2)
        if any(result.get(name, {}).get("status") != "healthy" for name in ("metadatabase", "scheduler", "dag_processor", "triggerer")):
            raise RuntimeError("Un componente de Airflow no está saludable")
