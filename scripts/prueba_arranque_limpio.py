#!/usr/bin/env python3
"""Prepara y mide un primer arranque aislado; nunca borra ni detiene recursos."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.pruebas_integrales import Integration

MAIN = "lab2-novamercado"
VOLUMES = {"product-db-data", "airflow-db-data", "mlflow-data", "airflow-logs", "airflow-config"}
SERVICES = {"product-db", "airflow-db", "mlflow", "api", "airflow-init", "airflow-api-server",
            "airflow-scheduler", "airflow-dag-processor", "airflow-triggerer"}
PROJECT_PATTERN = r"novamercado-arranque-\d{8}t\d{6}z-[a-f0-9]{8}"


class Refused(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def write_private(path, value, exclusive=False):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n" if not isinstance(value, str) else value
    if exclusive:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
    else:
        descriptor, temporary = tempfile.mkstemp(prefix=".estado-", dir=path.parent)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
        os.replace(temporary, path)


def command(arguments, *, source=None, timeout=60, environment=None):
    try:
        result = subprocess.run(arguments, cwd=ROOT, env=environment, input=source,
                                text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused("Comando no completado: " + type(error).__name__) from None
    require(result.returncode == 0, "Comando Docker falló; no se vuelcan stderr ni credenciales")
    return result.stdout


def isolated_config(config, project):
    require(re.fullmatch(PROJECT_PATTERN, project) is not None, "Nombre aislado inválido")
    require(set(config["services"]) == SERVICES and set(config["volumes"]) == VOLUMES, "Servicios/volúmenes inesperados")
    require(set(config["networks"]) == {"internal", "publicacion"}, "Redes inesperadas")
    config["name"] = project
    allowed_binds = {str((ROOT / p).resolve()) for p in ("data/entrada", "checks", "airflow/dags", "airflow/plugins", "airflow/scripts")}
    for name, settings in config["volumes"].items():
        require(not settings.get("external") and not settings.get("driver_opts"), "Volumen externo o redirigido")
        settings["name"] = project + "_" + name
    for name, settings in config["networks"].items():
        require(not settings.get("external") and settings.get("driver", "bridge") == "bridge", "Red ajena no permitida")
        settings["name"] = project + "_" + name
    for service, settings in config["services"].items():
        require(not any(settings.get(k) for k in ("container_name", "network_mode", "privileged", "devices", "volumes_from")), "Servicio fuera del aislamiento")
        settings.pop("ports", None)
        settings.pop("build", None)
        settings["pull_policy"] = "never"
        for mount in settings.get("volumes", []):
            if mount["type"] == "volume":
                require(mount["source"] in VOLUMES, "Volumen desconocido")
            else:
                require(mount["type"] == "bind" and mount["source"] in allowed_binds and mount.get("read_only"), "Bind no permitido o escribible")
        if service == "api":
            require(any(v.get("target") == "/data/entrada" and v["source"] == str((ROOT / "data/entrada").resolve()) for v in settings["volumes"]), "Falta dataset oficial read-only")
            require(settings["environment"]["PRODUCT_DB_HOST"] == "product-db" and settings["environment"]["MLFLOW_TRACKING_URI"] == "http://mlflow:5000", "Dependencias del producto fuera de su red")
    return config


def prepare():
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower() + "-" + secrets.token_hex(4)
    project = "novamercado-arranque-" + identifier
    folder = ROOT / "evidence/private/arranque-limpio" / identifier
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    values = {key: secrets.token_hex(32) for key in ("PRODUCT_DB_PASSWORD", "AIRFLOW_DB_PASSWORD",
              "AIRFLOW_JWT_SECRET", "AIRFLOW_API_SECRET_KEY", "AIRFLOW_ADMIN_PASSWORD", "INTERNAL_API_TOKEN")}
    values["AIRFLOW_FERNET_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        key = line.split("=", 1)[0]
        lines.append(key + "=" + values[key] if key in values else line)
    write_private(folder / "prueba.env", "\n".join(lines) + "\n", exclusive=True)
    write_private(folder / "plan.json", {"proyecto": project, "estado": "preparado_sin_recursos",
                  "limite_segundos": 600, "puertos_publicados": [], "volumenes": sorted(project + "_" + v for v in VOLUMES),
                  "nota": "Necesita autorización antes de ejecutar. Sin borrado ni parada automáticos; recursos conservados."}, exclusive=True)
    return folder


def resolve_plan_folder(folder):
    base = (ROOT / "evidence/private/arranque-limpio").resolve()
    folder = (ROOT / folder if not folder.is_absolute() else folder).resolve()
    try:
        folder.relative_to(base)
    except ValueError:
        raise Refused("El plan debe permanecer dentro de evidence/private/arranque-limpio") from None
    if not folder.is_dir() and folder.parent.is_dir():
        # Solo hermanos directos; no buscar recursivamente ni adivinar otros planes.
        matches = [p for p in folder.parent.iterdir() if p.is_dir() and p.name.casefold() == folder.name.casefold()]
        require(len(matches) <= 1, "Ruta ambigua por mayúsculas; indicar el nombre exacto")
        if matches:
            folder = matches[0].resolve()
            folder.relative_to(base)
    require(folder.is_dir(), "No existe la carpeta del plan: " + folder.relative_to(ROOT).as_posix())
    return folder


def load_plan(folder, allow_attempted=False):
    folder = resolve_plan_folder(folder)
    require((folder / "plan.json").is_file(), "Falta plan.json en " + folder.relative_to(ROOT).as_posix())
    try:
        plan = json.loads((folder / "plan.json").read_text())
    except ValueError:
        raise Refused("plan.json no contiene JSON válido; no se modifica la evidencia") from None
    require(isinstance(plan, dict) and isinstance(plan.get("proyecto"), str) and re.fullmatch(PROJECT_PATTERN, plan["proyecto"]) is not None, "Proyecto inválido")
    if not allow_attempted:
        require(plan.get("estado") == "preparado_sin_recursos" and not (folder / "informe.json").exists(),
                "Plan ya intentado; consultar " + (folder / "informe.json").relative_to(ROOT).as_posix() + "; no reutilizar sus volúmenes")
    return plan


def diagnose(folder):
    folder = resolve_plan_folder(folder)
    plan = load_plan(folder, allow_attempted=True)
    require((folder / "prueba.env").is_file(), "Falta prueba.env; no copiar credenciales productivas")
    values = dict(line.split("=", 1) for line in (folder / "prueba.env").read_text().splitlines() if "=" in line and not line.startswith("#"))
    keys = ("PRODUCT_DB_PASSWORD", "AIRFLOW_DB_PASSWORD", "AIRFLOW_FERNET_KEY", "AIRFLOW_JWT_SECRET", "AIRFLOW_API_SECRET_KEY", "AIRFLOW_ADMIN_PASSWORD", "INTERNAL_API_TOKEN")
    require(all(values.get(key) for key in keys), "Variables privadas incompletas; preparar otro plan sin sobrescribir")
    files = ("tiendas.csv", "familias.csv", "costos.csv", "feriados.csv", "historico_ventas.csv")
    require(all((ROOT / "data/entrada" / name).is_file() for name in files), "Faltan fuentes oficiales en data/entrada")
    result = {"carpeta": folder.relative_to(ROOT).as_posix(), "proyecto": plan["proyecto"],
              "env_completo": True, "fuentes_presentes": list(files), "compose_base_presente": (ROOT / "compose.yaml").is_file()}
    target = folder / "compose.prueba.json"
    if target.is_file():
        config = isolated_config(json.loads(target.read_text()), plan["proyecto"])
        result["imagenes_configuradas"] = sorted({s["image"] for s in config["services"].values()})
    report = folder / "informe.json"
    if report.is_file():
        data = json.loads(report.read_text())
        result["informe"] = {"estado": data.get("estado"), "seconds_hasta_health_ok": data.get("seconds_hasta_health_ok"),
                             "principal_sin_cambios": data.get("principal_sin_cambios"), "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}
    return result


class ColdStart:
    def __init__(self, folder):
        self.folder = resolve_plan_folder(folder)
        self.plan = load_plan(self.folder)
        self.project = self.plan["proyecto"]
        self.record = {"proyecto": self.project, "estado": "preflight", "limite_segundos": 600}
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "AIRFLOW_", "PRODUCT_", "MLFLOW_", "API_HOST_")) and k != "INTERNAL_API_TOKEN"}
        # Valores del entorno explícitos prevalecen sobre .env implícitos y shell.
        require((self.folder / "prueba.env").is_file(), "Falta prueba.env; preparar otro plan sin sobrescribir")
        for line in (self.folder / "prueba.env").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                self.environment[key] = value

    def save(self):
        write_private(self.folder / "informe.json", self.record)

    def compose(self, *args, source=None, timeout=60, original=False):
        path = ROOT / "compose.yaml" if original else self.folder / "compose.prueba.json"
        return command(["docker", "compose", "--project-directory", str(ROOT), "--project-name", self.project,
                        "--env-file", str(self.folder / "prueba.env"), "--file", str(path), *args],
                       source=source, timeout=timeout, environment=self.environment)

    def client(self):
        client = Integration(SimpleNamespace(data={}, save=lambda: None))
        client.compose = self.compose
        return client

    def probe(self, action):
        return self.client().inside("arranque_limpio.py", action, timeout=45)

    def primary(self):
        client = Integration(SimpleNamespace(data={}, save=lambda: None))
        state = client.inside("inspeccion_integral.py", "snapshot")
        require(state["ejecuciones_en_curso"] == 0, "Hay entrenamiento productivo activo; no iniciar prueba")
        return {"contenedores": client.inspect(), "huellas": state["huellas"], "modelo": state["activo"],
                "sonda": client.inside("arranque_limpio.py", "health"),
                "registry": self.main_alias(client)}

    @staticmethod
    def main_alias(client):
        code = "from app.services.integraciones import Tracking\nimport json\nt=Tracking()\nprint(json.dumps({'nombre':t.name,'alias':t.alias,'version':t.alias_version()}))\n"
        return json.loads(client.compose("exec", "-T", "api", "python", "-", source=code))

    def configure(self):
        config = json.loads(self.compose("config", "--format", "json", original=True))
        config = isolated_config(config, self.project)
        target = self.folder / "compose.prueba.json"
        if target.exists():
            require(json.loads(target.read_text()) == config, "La configuración cambió desde su revisión; preparar otro plan")
        else:
            write_private(target, config, exclusive=True)
        self.compose("config", "--quiet")
        return config

    def preflight(self):
        config = self.configure()
        require(not command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + self.project]).strip(), "Ya existen contenedores de este proyecto")
        for kind, names in (("volume", [v["name"] for v in config["volumes"].values()]), ("network", [v["name"] for v in config["networks"].values()])):
            existing = set(command(["docker", kind, "ls", "--format", "{{.Name}}", "--filter", "label=com.docker.compose.project=" + self.project]).splitlines())
            all_names = set(command(["docker", kind, "ls", "--format", "{{.Name}}"] ).splitlines())
            require(not existing and not all_names.intersection(names), "Ya existen recursos: no es un primer arranque vacío")
        images = {}
        for image in sorted({s["image"] for s in config["services"].values()}):
            images[image] = command(["docker", "image", "inspect", "--format", "{{.Id}}", image]).strip()
        self.record.update(imagenes=images, volumenes_nuevos=sorted(v["name"] for v in config["volumes"].values()), puertos_publicados=[])

    def runtime_resources(self):
        ids = self.compose("ps", "-aq").split()
        require(len(ids) == 9, "No existen exactamente nueve contenedores aislados")
        template = '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"mounts":{{json .Mounts}},"ports":{{json .NetworkSettings.Ports}},"networks":{{json .NetworkSettings.Networks}},"state":{{json .State.Status}},"exit":{{json .State.ExitCode}}}'
        rows = [json.loads(line) for line in command(["docker", "inspect", "--format", template, *ids]).splitlines()]
        require({r["service"] for r in rows} == SERVICES, "Inventario aislado incompleto")
        for row in rows:
            require(row["project"] == self.project, "Contenedor ajeno")
            require(not any((row["ports"] or {}).values()), "Se publicaron puertos inesperadamente")
            require(all(name.startswith(self.project + "_") for name in (row["networks"] or {})), "Red compartida con otro proyecto")
            for mount in row["mounts"]:
                require(mount["Type"] != "volume" or mount.get("Name") in self.record["volumenes_nuevos"], "Volumen ajeno")
                require(mount["Type"] != "bind" or not mount.get("RW"), "Bind escribible en contenedor real")
            require((row["state"] == "exited" and row["exit"] == 0) if row["service"] == "airflow-init" else row["state"] == "running", "Servicio aislado detenido/fallido")
        return {"servicios": sorted(SERVICES), "volumenes": self.record["volumenes_nuevos"], "sin_puertos_publicados": True}

    def run(self):
        before = None
        try:
            self.preflight()
            before = self.primary()
            require(before["sonda"] == {"http": 200, "body": {"estado": "ok"}}, "Producto principal no está ok antes de la prueba")
            self.record.update(principal_antes=before, estado="arrancando", inicio_utc=datetime.now(timezone.utc).isoformat())
            self.save()
            started = time.monotonic()
            self.compose("up", "-d", "--no-build", "--pull", "never", "--no-recreate", timeout=600)
            while True:
                result = self.probe("health")
                elapsed = time.monotonic() - started
                require(elapsed <= 600, "Primer arranque excedió 600 segundos; no se detienen ni borran recursos")
                if result == {"http": 200, "body": {"estado": "ok"}}:
                    self.record["seconds_hasta_health_ok"] = elapsed
                    break
                time.sleep(min(3, max(0, 600 - elapsed)))
            self.record["verificacion"] = self.probe("verificar")
            self.record["aislamiento_real"] = self.runtime_resources()
            self.record["codigo_imagen"] = self.client().code_coherence()
            self.record["estado"] = "aprobado"
        except (Exception, KeyboardInterrupt) as error:
            self.record.update(estado="no_aprobado", error_tipo=type(error).__name__,
                               motivo=str(error) if isinstance(error, Refused) else "Consultar diagnóstico seguro; no se vuelcan secretos")
        finally:
            if before is not None:
                try:
                    after = self.primary()
                    self.record["principal_despues"] = after
                    require(before == after, "Producto principal cambió: revisar actividad concurrente; no se restaura ni oculta diferencia")
                    self.record["principal_sin_cambios"] = True
                except Exception as error:
                    self.record.update(estado="no_aprobado", principal_sin_cambios=False, error_aislamiento=type(error).__name__)
            self.save()
        return 0 if self.record["estado"] == "aprobado" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("preparar", "diagnosticar", "validar", "ejecutar"))
    parser.add_argument("--plan", type=Path, help="Carpeta privada creada por preparar")
    parser.add_argument("--autorizar-recursos", action="store_true", help="Autorización explícita para nueve contenedores, dos redes y cinco volúmenes nuevos; sin limpieza")
    args = parser.parse_args()
    if args.accion == "diagnosticar":
        if args.plan is None or args.autorizar_recursos:
            parser.error("diagnosticar requiere --plan; no inicia recursos")
        print(json.dumps(diagnose(args.plan), ensure_ascii=False, indent=2))
        return 0
    if args.accion == "preparar":
        require(not args.autorizar_recursos and args.plan is None, "Preparar no inicia recursos ni reutiliza planes")
        folder = prepare()
        print("Plan preparado sin usar Docker: " + str(folder.relative_to(ROOT)))
        print("Tras autorización, ejecutar desde la raíz:")
        print("python3 scripts/prueba_arranque_limpio.py ejecutar --plan " + str(folder.relative_to(ROOT)) + " --autorizar-recursos")
        return 0
    if args.accion == "validar":
        if args.plan is None or args.autorizar_recursos:
            parser.error("validar requiere --plan; no autoriza ni inicia recursos")
        runner = ColdStart(args.plan)
        runner.configure()
        write_private(runner.folder / "validacion.json", {"estado": "configuracion_valida_sin_arranque",
                      "proyecto": runner.project, "servicios": 9, "volumenes": 5, "redes": 2, "puertos_publicados": []})
        print("Configuración Compose válida; no se crearon recursos. Plan: " + str(args.plan))
        return 0
    if not args.autorizar_recursos or args.plan is None:
        parser.error("ejecutar requiere --plan y --autorizar-recursos; crea recursos nuevos")
    runner = ColdStart(args.plan)
    code = runner.run()
    print("Resultado: " + runner.record["estado"] + "; informe: " + str((runner.folder / "informe.json").relative_to(ROOT)))
    print("Recursos conservados; no se ejecutó ninguna limpieza ni parada.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, Refused) else type(error).__name__
        print("No completado: " + detail + ". No se imprimen credenciales.", file=sys.stderr)
        sys.exit(1)
