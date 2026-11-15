#!/usr/bin/env python3
"""Operaciones limitadas al Compose de este laboratorio. Solo biblioteca estándar."""

import argparse
import base64
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "lab2-novamercado"
SERVICES = ("product-db", "airflow-db", "mlflow", "api", "airflow-api-server", "airflow-scheduler", "airflow-dag-processor", "airflow-triggerer")


def execute(arguments, *, capture=True, input=None, timeout=120):
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=capture, input=input, timeout=timeout)
    if result.returncode:
        # No volcar stdout de config ni DSN de los contenedores.
        detail = result.stderr.strip() if result.stderr else "consultar los logs del servicio"
        raise RuntimeError(f"Falló {arguments[0]}: {detail}")
    return result.stdout if capture else ""


def compose(*arguments, **kwargs):
    return execute(["docker", "compose", "--project-directory", str(ROOT), "--project-name", PROJECT,
                    "--file", str(ROOT / "compose.yaml"), "--env-file", str(ROOT / ".env"), *arguments], **kwargs)


def init_env():
    target = ROOT / ".env"
    if target.exists():
        lines = target.read_text().splitlines()
        existing = dict(line.split("=", 1) for line in lines if line and not line.startswith("#") and "=" in line)
        if not existing.get("INTERNAL_API_TOKEN"):
            lines = [line for line in lines if not line.startswith("INTERNAL_API_TOKEN=")]
            lines.append("INTERNAL_API_TOKEN=" + secrets.token_hex(32))
            target.write_text("\n".join(lines) + "\n")
            print("Se agregó únicamente el token interno faltante; se conservaron las credenciales existentes.")
            return
        print(".env ya existe; no se sobrescribió.")
        return
    values = {name: secrets.token_hex(32) for name in (
        "PRODUCT_DB_PASSWORD", "AIRFLOW_DB_PASSWORD", "AIRFLOW_JWT_SECRET", "AIRFLOW_API_SECRET_KEY", "AIRFLOW_ADMIN_PASSWORD", "INTERNAL_API_TOKEN")}
    values["AIRFLOW_FERNET_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    template = (ROOT / ".env.example").read_text()
    lines = []
    for line in template.splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={values[key]}" if key in values else line)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write("\n".join(lines) + "\n")
    print(".env creado con secretos aleatorios y permisos 0600. No se imprimieron credenciales.")


def configuration():
    config = json.loads(compose("config", "--format", "json"))
    if config.get("name") != PROJECT:
        raise RuntimeError("El proyecto Compose no corresponde al laboratorio")
    return config


def check_ports(config, own_ports=()):
    checked = set()
    conflicts = []
    for service, settings in config["services"].items():
        for port in settings.get("ports", []):
            host = port.get("host_ip", "127.0.0.1")
            number = int(port["published"])
            if not 1024 <= number <= 65535:
                raise RuntimeError(f"Puerto inválido para {service}: {number}; usar 1024–65535")
            if number in checked:
                raise RuntimeError(f"Puerto de host duplicado: {number}")
            checked.add(number)
            if (service, number) in own_ports:
                print(f"OK {host}:{number}: ya publicado por {PROJECT}/{service}")
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind((host, number))
                print(f"OK {host}:{number}: disponible para {service}")
            except PermissionError as error:
                raise RuntimeError("El entorno impide inspeccionar puertos; no se autoriza el arranque sin esa comprobación") from error
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    raise
                conflicts.append(f"{service}: {host}:{number} ocupado")
    if conflicts:
        raise RuntimeError("Conflictos de puertos: " + "; ".join(conflicts) +
                           ". No se cambió ningún puerto. Revisar propietario en el inventario; elegir un puerto libre en .env y repetir preflight. El puerto interno de api sigue siendo 8000.")


def ps_rows():
    result = compose("ps", "--all", "--format", "json").strip()
    if not result:
        return []
    # Compose V2 usa JSONL; otras versiones devuelven un array JSON.
    if result.startswith("["):
        return json.loads(result)
    return [json.loads(line) for line in result.splitlines()]


def preflight():
    config = configuration()
    inventory = execute(["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"])
    print("Inventario de contenedores activos (solo lectura):\n" + (inventory or "(ninguno)"))
    own_ports = {(row["Service"], int(port["PublishedPort"])) for row in ps_rows()
                 if row.get("State") == "running" for port in (row.get("Publishers") or [])
                 if port.get("URL") == "127.0.0.1" and port.get("PublishedPort")}
    check_ports(config, own_ports)
    print("Preflight completado; no se modificaron recursos.")


def wait_healthy(timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = {row["Service"]: row for row in ps_rows()}
        init = rows.get("airflow-init", {})
        if init.get("State") == "exited" and init.get("ExitCode", 0) != 0:
            raise RuntimeError("Falló airflow-init; revisar sus logs")
        if init.get("State") == "exited" and init.get("ExitCode") == 0 and all(rows.get(service, {}).get("Health") == "healthy" and rows[service].get("State") == "running" for service in SERVICES):
            print("OK: los ocho servicios permanentes están healthy; airflow-init es una tarea de una sola ejecución.")
            return
        failed = [service for service in SERVICES if rows.get(service, {}).get("Health") == "unhealthy" or rows.get(service, {}).get("State") in ("dead", "exited")]
        if failed:
            raise RuntimeError("Servicios fallidos: " + ", ".join(failed))
        time.sleep(3)
    raise RuntimeError("Tiempo agotado esperando salud de los servicios; revisar docker compose ps y logs")


def smoke():
    wait_healthy()
    config = configuration()
    for service, endpoint in (("api", "/ready"), ("mlflow", "/health"), ("airflow-api-server", "/api/v2/monitor/health")):
        port = config["services"][service]["ports"][0]["published"]
        with urlopen(f"http://127.0.0.1:{port}{endpoint}", timeout=15) as response:
            if response.status != 200:
                raise RuntimeError(f"Falló el acceso del host a {service}")
        print(f"OK host → {service}:{port}{endpoint}")
    print(compose("exec", "-T", "api", "python", "/app/checks/connectivity.py"), end="")
    print(compose("exec", "-T", "airflow-scheduler", "python", "/opt/checks/airflow_probe.py", "connectivity"), end="")
    compose("exec", "-T", "api", "python", "-m", "unittest", "discover", "-s", "/app/tests", "-v", capture=False)


def persistence():
    smoke()
    token = secrets.token_hex(16)
    # Guardar antes de reiniciar para que una verificación fallida deje evidencia recuperable.
    state = json.loads(compose("exec", "-T", "api", "python", "/app/checks/product_persistence.py", "seed", token))
    before = json.loads(compose("exec", "-T", "airflow-scheduler", "python", "/opt/checks/airflow_probe.py", "seed", token))
    evidence = ROOT / "evidence" / "runtime"
    evidence.mkdir(parents=True, exist_ok=True)
    record = {"time_utc": datetime.now(timezone.utc).isoformat(), "state": state, "airflow_before": before, "status": "seeded_pending_restart"}
    path = evidence / f"persistence-{token}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    print("Reiniciando exclusivamente los servicios de lab2-novamercado; no se eliminan contenedores ni volúmenes.", flush=True)
    compose("restart", *SERVICES, capture=False, timeout=180)
    wait_healthy()
    record["product_after"] = json.loads(compose("exec", "-T", "api", "python", "/app/checks/product_persistence.py", "verify", input=json.dumps(state)))
    after = json.loads(compose("exec", "-T", "airflow-scheduler", "python", "/opt/checks/airflow_probe.py", "verify", token))
    if after != before:
        raise RuntimeError("Cambió el archivo de autenticación persistente de Airflow")
    record.update(airflow_after=after, status="passed_after_restart")
    path.write_text(json.dumps(record, indent=2) + "\n")
    smoke()
    print("OK persistencia de producto, MLflow (registro y artefacto), metadatos, logs y configuración Airflow.")
    print(f"Evidencia sin credenciales: {path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init-env", "preflight", "up", "smoke", "persistence"))
    args = parser.parse_args()
    try:
        if args.action == "init-env":
            init_env()
        elif args.action == "preflight":
            preflight()
        elif args.action == "up":
            preflight()
            compose("up", "-d", "--build", capture=False, timeout=1800)
            smoke()
        elif args.action == "smoke":
            smoke()
        elif args.action == "persistence":
            persistence()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
