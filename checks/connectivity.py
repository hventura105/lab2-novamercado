"""Ejecutar dentro de api; solo stdlib y el driver ya instalado en la API."""

import json
import os
import socket
from urllib.request import Request, urlopen


def request(url, payload=None, method=None, raw=None):
    data = json.dumps(payload).encode() if payload is not None else raw
    headers = {"Content-Type": "application/json" if raw is None else "text/plain"}
    with urlopen(Request(url, data=data, headers=headers, method=method), timeout=15) as response:
        body = response.read()
        return json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body.decode()


def validate_airflow_health(payload):
    for component in ("metadatabase", "scheduler", "dag_processor", "triggerer"):
        if payload.get(component, {}).get("status") != "healthy":
            raise RuntimeError(f"Airflow: {component} no está healthy")


def main():
    for name, port in (("product-db", 5432), ("airflow-db", 5432), ("mlflow", 5000), ("api", 8000), ("airflow-api-server", 8080)):
        socket.getaddrinfo(name, port)
        with socket.create_connection((name, port), timeout=5):
            pass
        print(f"OK DNS y TCP: {name}:{port}")
    ready = request("http://api:8000/health")
    if ready.get("estado") != "ok":
        raise RuntimeError("API no disponible")
    print("OK API: modelo cargado, PostgreSQL, MLflow y Airflow")
    model = request("http://api:8000/modelo")
    if not all(isinstance(model.get(key), str) and model[key] for key in ("nombre", "alias", "version")):
        raise RuntimeError("Contrato /modelo inválido")
    result = request(os.environ["MLFLOW_TRACKING_URI"] + "/api/2.0/mlflow/experiments/search", {"max_results": 1})
    if not isinstance(result, dict):
        raise RuntimeError("Respuesta inválida de MLflow Tracking API")
    print("OK MLflow Tracking API")
    validate_airflow_health(request(os.environ["AIRFLOW_HEALTH_URL"]))
    print("OK Airflow: metadatabase, scheduler, dag_processor y triggerer")


if __name__ == "__main__":
    main()
