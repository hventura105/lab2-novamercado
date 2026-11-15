"""Pruebas desde Airflow, sin DAG ni dependencias adicionales."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen


def run_variable(*arguments):
    return subprocess.run(["airflow", "variables", *arguments], check=True, capture_output=True, text=True).stdout


def main():
    mode = sys.argv[1]
    if mode == "connectivity":
        for url in (os.environ["NOVAMERCADO_API_URL"] + "/ready", os.environ["MLFLOW_TRACKING_URI"] + "/health"):
            with urlopen(url, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError("Dependencia no disponible")
        subprocess.run(["airflow", "db", "check"], check=True, capture_output=True)
        print("OK Airflow → API, MLflow y PostgreSQL de metadatos")
        return
    token = sys.argv[2]
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("Token de prueba inválido")
    name = "infra_phase1_" + token
    marker = Path("/opt/airflow/logs") / (name + ".txt")
    passwords = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    if mode == "seed":
        run_variable("set", name, token)
        marker.write_text(token)
    elif mode == "verify":
        if token not in run_variable("get", name).splitlines() or marker.read_text() != token:
            raise RuntimeError("Se perdió el marcador Airflow")
    else:
        raise ValueError("Modo inválido")
    print(json.dumps({"metadata": "ok", "logs": "ok", "config_sha256": hashlib.sha256(passwords.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
