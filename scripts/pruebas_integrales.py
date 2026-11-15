#!/usr/bin/env python3
"""Ejecutor real de integración desde Ubuntu; solo stdlib en el host, sin borrar recursos."""

import argparse
import ast
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import infra


class Failed(RuntimeError):
    pass


class Blocked(RuntimeError):
    pass


class Pending(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Failed(message)


def canonical_hash(value):
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return item
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, allow_nan=False, default=str).encode()).hexdigest()


def http(base, path, payload=None, method=None, timeout=15):
    data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    opener = build_opener(ProxyHandler({}))
    started = time.monotonic()
    request = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        body = response.read(8 * 1024 * 1024)
        value = json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body.decode("utf-8", errors="replace")
        return {"status": response.code, "body": value, "seconds": time.monotonic() - started}


def validate_quality(value):
    require(isinstance(value, dict) and isinstance(value.get("observaciones"), list), "Contrato de calidad inválido")
    actions = []
    for note in value["observaciones"]:
        require(isinstance(note, dict) and all(isinstance(note.get(key), str) for key in ("campo", "accion", "detalle")), "Observación de calidad incompleta")
        require(note["accion"] in ("reparar", "advertir"), "Acción de calidad no permitida")
        actions.append(note["accion"])
    expected = "advertencia" if "advertir" in actions else "corregido" if actions else "ok"
    require(value.get("estado") == expected, "Estado de calidad no respeta precedencia de advertencias")


def validate_prediction(result, request):
    require(result["status"] == 200, "Predicción no respondió HTTP 200")
    body = result["body"]
    require(isinstance(body, dict) and all(key in body for key in ("tienda_id", "fecha", "version_modelo", "predicciones", "calidad")), "Faltan campos del anexo")
    require(body["tienda_id"] == int(request["tienda_id"]) and body["fecha"] == request["fecha"], "Tienda/fecha de respuesta no coinciden")
    require(isinstance(body["version_modelo"], str) and bool(body["version_modelo"]), "Versión de modelo no textual")
    require(isinstance(body["predicciones"], list), "Predicciones no es una lista")
    families = [item["familia_id"] for item in body["predicciones"]]
    require(set(families) == {item["familia_id"] for item in request["familias"]} and len(families) == len(set(families)), "Familias faltantes, inventadas o duplicadas")
    for item in body["predicciones"]:
        require(type(item.get("cantidad_sugerida")) is int and item["cantidad_sugerida"] >= 0, "Cantidad sugerida no entera o negativa")
        value = item.get("venta_esperada")
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "Venta esperada inválida")
    validate_quality(body["calidad"])


class Report:
    def __init__(self, directory=None):
        identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        self.directory = Path(directory) if directory else ROOT / "evidence/private/integration" / identifier
        self.directory.resolve().relative_to(ROOT.resolve())
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.data = {"id": identifier, "inicio_utc": datetime.now(timezone.utc).isoformat(), "estado": "en_curso", "casos": [],
                     "nota": "Solo 'aprobada' acredita un resultado ejecutado. Pendiente/bloqueada no es éxito. No se incluyen contraseñas ni filas originales."}
        self.data["ejecutor_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.data["helpers_sha256"] = {name: hashlib.sha256((ROOT / "checks" / name).read_bytes()).hexdigest()
                                       for name in ("inspeccion_integral.py", "replay_integral.py", "contrato_asgi.py")}
        self.save()

    def save(self):
        self.data["actualizado_utc"] = datetime.now(timezone.utc).isoformat()
        descriptor, name = tempfile.mkstemp(prefix=".informe-", dir=self.directory)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
            stream.write("\n")
        os.replace(name, self.directory / "informe.json")
        lines = ["# Resultados de integración real", "", "Estado: " + self.data["estado"], "", "| Caso | Alcance | Resultado | Segundos |", "| --- | --- | --- | ---: |"]
        for item in self.data["casos"]:
            lines.append(f"| {item['nombre']} | {item['alcance']} | {item['estado']} | {item.get('seconds', 0):.3f} |")
        (self.directory / "RESUMEN.md").write_text("\n".join(lines) + "\n\nDetalles y pendientes en informe.json. No contiene credenciales ni filas originales.\n")

    def case(self, name, function, scope="servicios_reales"):
        started = time.monotonic()
        row = {"nombre": name, "alcance": scope, "estado": "en_curso"}
        self.data["casos"].append(row)
        self.save()
        print(f"Ejecutando {name}...", flush=True)
        try:
            row["evidencia"] = function()
            row["estado"] = "aprobada"
        except KeyboardInterrupt:
            row.update(estado="interrumpida", seconds=time.monotonic() - started, motivo="Interrupción solicitada; no se declara éxito")
            self.data["estado"] = "interrumpido"
            self.save()
            raise
        except Pending as error:
            row.update(estado="pendiente", motivo=str(error))
        except Blocked as error:
            row.update(estado="bloqueada", motivo=str(error))
        except Failed as error:
            row.update(estado="fallida", motivo=str(error))
        except Exception as error:
            # Ni driver, HTTPError bodies o stderr arbitrario se vuelcan a informes.
            row.update(estado="fallida", motivo="Error de ejecución: " + type(error).__name__)
        row["seconds"] = time.monotonic() - started
        self.save()
        print(f"{name}: {row['estado']}", flush=True)
        return row

    def pending(self, name, reason, scope="servicios_reales"):
        self.data["casos"].append({"nombre": name, "alcance": scope, "estado": "pendiente", "motivo": reason, "seconds": 0})
        self.save()

    def finish(self):
        states = {item["estado"] for item in self.data["casos"]}
        code = 1 if states.intersection({"fallida", "bloqueada", "en_curso", "interrumpida"}) else 2 if "pendiente" in states else 0
        self.data["estado"] = "fallido_o_bloqueado" if code == 1 else "incompleto" if code == 2 else "aprobado"
        self.save()
        print(f"Informe: {self.directory / 'informe.json'}", flush=True)
        return code


class Integration:
    def __init__(self, report):
        self.report = report
        self.config = None
        self.urls = {}
        self.metadata = None
        self.prediction_request = None
        self.production_promoted = False
        self.asgi_traces = False
        self.asgi_source = ROOT / "api/tests/test_endpoints.py"

    def compose(self, *arguments, source=None, timeout=120):
        command = ["docker", "compose", "--project-directory", str(ROOT), "--project-name", infra.PROJECT,
                   "--file", str(ROOT / "compose.yaml"), "--env-file", str(ROOT / ".env"), *arguments]
        try:
            result = subprocess.run(command, cwd=ROOT, text=True, input=source, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as error:
            raise Failed("No se completó el comando Docker: " + type(error).__name__) from None
        if result.returncode:
            diagnostic = ""
            try:
                detail = json.loads(result.stdout)
                if isinstance(detail, dict) and str(detail.get("error_tipo", "")).isidentifier():
                    diagnostic = "; helper " + detail["error_tipo"]
                    sqlstate = detail.get("sqlstate")
                    if isinstance(sqlstate, str) and len(sqlstate) == 5 and sqlstate.isalnum():
                        diagnostic += "; SQLSTATE " + sqlstate
            except ValueError:
                pass
            raise Failed(f"Docker Compose terminó con código {result.returncode}{diagnostic}; no se copia stderr ni datos privados al informe")
        return result.stdout

    def inside(self, filename, action=None, payload=None, timeout=120):
        path = ROOT / "checks" / filename
        source = path.read_text()
        ast.parse(source)
        # Código y datos viajan por stdin, no por argumentos de proceso ni shell.
        argv = [filename] + ([action, json.dumps(payload or {}, allow_nan=False)] if action else [])
        program = "import sys\nsys.argv=" + repr(argv) + "\n" + source
        output = self.compose("exec", "-T", "api", "python", "-", source=program, timeout=timeout)
        try:
            result = json.loads(output)
        except ValueError:
            raise Failed("El helper no devolvió JSON íntegro; no se publica salida arbitraria") from None
        require(not result.get("error_tipo"), "La inspección en contenedor falló sin exponer credenciales")
        return result

    def inspect(self):
        rows = infra.ps_rows()
        identifiers = [row["ID"] for row in rows if row.get("Service") in infra.SERVICES]
        require(len(identifiers) == len(infra.SERVICES), "Faltan servicios permanentes del proyecto")
        template = ('{"id":{{json .Id}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                    '"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
                    '"mounts":{{json .Mounts}}}')
        result = infra.execute(["docker", "inspect", "--type", "container", "--format", template, *identifiers])
        values = [json.loads(line) for line in result.splitlines()]
        require(all(row["project"] == infra.PROJECT and row["running"] for row in values), "Hay contenedores fuera del proyecto o detenidos")
        return {row["service"]: {"id": row["id"], "started": row["started"],
            "volumes": sorted((mount.get("Name", ""), mount["Destination"]) for mount in row["mounts"] if mount["Type"] == "volume")} for row in values}

    def preflight(self):
        try:
            self.config = infra.configuration()
            containers = self.inspect()
        except Exception as error:
            raise Blocked("Daemon Docker no accesible o inventario no comprobable: " + type(error).__name__) from None
        for service, settings in self.config["services"].items():
            if service in ("product-db", "airflow-db"):
                require(not settings.get("ports"), "PostgreSQL tiene publicación inesperada")
        for service, expected in (("api", 8000), ("mlflow", 5000), ("airflow-api-server", 8080)):
            ports = self.config["services"][service].get("ports", [])
            require(len(ports) == 1 and ports[0].get("host_ip") == "127.0.0.1" and int(ports[0]["published"]) == expected, "Publicación distinta de la verificada por el usuario")
            require(self.compose("port", service, str(expected)).strip() == f"127.0.0.1:{expected}", "Binding real ausente o distinto; no continuar")
            self.urls[service] = f"http://127.0.0.1:{expected}"
        return {"proyecto": infra.PROJECT, "contenedores": containers, "publicaciones": self.urls}

    def live_state(self):
        health = http(self.urls["api"], "/health")
        require(health["status"] == 200 and isinstance(health["body"], dict) and health["body"].get("estado") == "ok", "El producto no está completamente saludable")
        model = http(self.urls["api"], "/modelo")
        require(model["status"] == 200 and all(isinstance(model["body"].get(key), str) and model["body"][key] for key in ("nombre", "alias", "version")), "Contrato /modelo inválido")
        self.metadata = self.inside("inspeccion_integral.py", "metadata")
        active = self.metadata["activo"]
        require(model["body"] == {key: active[key] for key in ("nombre", "alias", "version")}, "API y modelo activo de PostgreSQL discrepan")
        require(self.metadata["ejecuciones_en_curso"] == 0, "Hay una ejecución en curso; no interferir con ella")
        calendar = ROOT / "data/entrada/feriados.csv"
        import csv
        with calendar.open(encoding="utf-8-sig", newline="") as stream:
            end = max(date.fromisoformat(row["fecha"]) for row in csv.DictReader(stream))
        latest = max(date.fromisoformat(value) for value in (self.metadata["hist_max"], active["entrenado_hasta"], self.metadata["ultima_observacion"]) if value)
        target = latest + timedelta(days=1)
        require(target <= end, "No hay siguiente fecha dentro del calendario; no inventar cobertura")
        self.prediction_request = json.loads((ROOT / "data/entrada/ejemplos/prediccion_valida.json").read_text())
        self.prediction_request["fecha"] = target.isoformat()
        return {"health": health, "modelo": model["body"], "metadata": self.metadata, "fecha_prueba": target.isoformat(),
                "nota_promociones": "Valores declarados del ejemplo oficial como solicitud de contrato; no se convierten en observaciones"}

    def asgi_contract(self):
        path = self.asgi_source.resolve()
        path.relative_to(ROOT.resolve())
        source = path.read_text()
        helper = (ROOT / "checks/contrato_asgi.py").read_text()
        program = "import sys,json\nsys.path.insert(0,'/app')\n" + helper
        program += "\nprint(json.dumps(run_suite(" + repr(source) + ",include_traces=" + repr(self.asgi_traces) + "),ensure_ascii=False))\n"
        result = json.loads(self.compose("exec", "-T", "api", "python", "-", source=program))
        result["archivo_pruebas"] = path.relative_to(ROOT).as_posix()
        result["sha256_pruebas"] = hashlib.sha256(source.encode()).hexdigest()
        if self.asgi_traces:
            # No guardar valores secretos aunque una excepción externa los incluyera.
            sensitive = []
            for line in (ROOT / ".env").read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    if len(value) >= 4 and any(token in key for token in ("PASSWORD", "TOKEN", "SECRET", "FERNET")):
                        sensitive.append(value)
            def redact(value):
                if isinstance(value, str):
                    for secret in sensitive:
                        value = value.replace(secret, "[REDACTADO]")
                    return value
                if isinstance(value, list):
                    return [redact(item) for item in value]
                if isinstance(value, dict):
                    return {key: redact(item) for key, item in value.items()}
                return value
            result = redact(result)
            traces_path = self.report.directory / "trazas_asgi.txt"
            descriptor = os.open(traces_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(result.get("salida_unittest", "") or "\n".join(item["traza"] for item in result.get("trazas", [])))
        self.report.data["contrato_asgi"] = result
        self.report.save()
        require(result["ejecutadas"] > 0 and result["fallos"] == result["errores"] == result["omitidas"] == 0, "Pruebas ASGI no aprobadas íntegramente; identificadores en informe")
        return result

    def code_coherence(self):
        paths = sorted([path for path in (ROOT / "api/app").rglob("*.py")] + list((ROOT / "api/migrations").glob("*.sql")))
        expected = {path.relative_to(ROOT / "api").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        actual = self.inside("inspeccion_integral.py", "code_hashes", {"paths": list(expected)})
        require(actual == expected, "La imagen API difiere del código local; revisar reconstrucción antes de probar, sin recreación automática")
        return {"archivos": len(paths), "manifest_sha256": canonical_hash(expected), "coinciden": True}

    def predictions(self):
        before = self.inside("inspeccion_integral.py", "solicitudes", self.prediction_request)
        responses = [http(self.urls["api"], "/v1/prediccion", self.prediction_request) for _ in range(2)]
        for response in responses:
            validate_prediction(response, self.prediction_request)
        after = self.inside("inspeccion_integral.py", "solicitudes", self.prediction_request)
        old_ids = {row["id"] for row in before["solicitudes"]}
        new = [row for row in after["solicitudes"] if row["id"] not in old_ids]
        require(len(new) >= 2, "No se registraron dos solicitudes nuevas al repetir el pronóstico")
        require(all(row["http"] == 200 and row["predicciones"] == row["familias_distintas"] == len(self.prediction_request["familias"]) for row in new), "Registro de predicciones incompleto en PostgreSQL")
        require(all(row["versiones"] and all(isinstance(version, str) for version in row["versiones"]) for row in new), "Falta versión persistida")
        require(all(any(row["calidad"] == response["body"]["calidad"] for response in responses) for row in new), "La calidad devuelta no quedó registrada en PostgreSQL")
        return {"respuestas": responses, "solicitudes_sql": new, "entrada_sha256": canonical_hash(self.prediction_request)}

    def quality(self):
        snapshot_before = self.inside("inspeccion_integral.py", "snapshot")
        raw = json.loads(json.dumps(self.prediction_request))
        raw["tienda_id"] = "T" + str(raw["tienda_id"]).zfill(2)
        raw["familias"] = raw["familias"][:-1]
        repaired = http(self.urls["api"], "/v1/prediccion", raw)
        require(repaired["status"] == 200, "Solicitud reparable rechazada")
        validate_quality(repaired["body"]["calidad"])
        require(repaired["body"]["calidad"]["estado"] == "advertencia", "Advertencia no prevalece sobre reparación")
        require({item["accion"] for item in repaired["body"]["calidad"]["observaciones"]} == {"reparar", "advertir"}, "No se informaron ambas acciones")
        repaired_audit = self.inside("inspeccion_integral.py", "solicitudes", raw)
        require(any(row["calidad"] == repaired["body"]["calidad"] and row["predicciones"] == len(repaired["body"]["predicciones"]) for row in repaired_audit["solicitudes"]), "Correcciones/advertencias o predicciones reparadas no están persistidas")
        raw["familias"][0]["familia_id"] = "familia_desconocida_de_prueba"
        invalid = http(self.urls["api"], "/v1/prediccion", raw)
        structural = http(self.urls["api"], "/v1/prediccion", {"tienda_id": 1, "fecha": self.prediction_request["fecha"], "familias": "invalido"})
        require(all(row["status"] == 422 and "detail" in row["body"] for row in (invalid, structural)), "Rechazo 422/detail no conforme")
        unknown = http(self.urls["api"], "/admin/reentrenar/desconocido_" + secrets.token_hex(8))
        require(unknown["status"] == 404, "Identificador administrativo desconocido no devuelve 404")
        examples = {}
        directory = ROOT / "data/entrada/ejemplos/errores"
        for code in ("E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E10"):
            path = next(directory.glob(code + "*.json"))
            payload = json.loads(path.read_text())
            prediction = code not in ("E08", "E10")
            if prediction:
                day = date.fromisoformat(self.prediction_request["fecha"])
                if code == "E04":
                    while day.day <= 12:
                        day += timedelta(days=1)
                    payload["fecha"] = day.strftime("%d/%m/%Y")
                else:
                    payload["fecha"] = day.isoformat()
            result = http(self.urls["api"], "/v1/prediccion" if prediction else "/v1/observaciones", payload)
            if code in ("E06", "E08", "E10"):
                require(result["status"] == 422 and "detail" in result["body"], f"{code}: se esperaba rechazo explicativo sin inventar valores")
            else:
                require(result["status"] == 200, f"{code}: reparación/advertencia no respondió 200")
                validate_quality(result["body"]["calidad"])
                actions = {item["accion"] for item in result["body"]["calidad"]["observaciones"]}
                require(("advertir" if code == "E05" else "reparar") in actions, f"{code}: falta la acción de calidad esperada")
            examples[code] = result
        ambiguous = json.loads(json.dumps(self.prediction_request))
        ambiguous["fecha"] = "03/04/" + self.prediction_request["fecha"][:4]
        ambiguous_response = http(self.urls["api"], "/v1/prediccion", ambiguous)
        require(ambiguous_response["status"] == 422, "Fecha ambigua no se rechazó")
        snapshot_after = self.inside("inspeccion_integral.py", "snapshot")
        require(snapshot_before["huellas"]["observaciones"] == snapshot_after["huellas"]["observaciones"], "Una observación defectuosa modificó ventas persistidas")
        return {"reparable": repaired, "rechazo_semantico": invalid, "rechazo_estructural": structural,
                "id_desconocido": unknown["status"], "ejemplos_oficiales": examples, "fecha_ambigua": ambiguous_response,
                "correcciones_y_advertencias_sql": repaired_audit,
                "E09": "La repetición se prueba con ventas reales del histórico en observaciones_reales_idempotencia_sql, sin escribir ventas ilustrativas"}

    def observations(self):
        fixture = self.inside("inspeccion_integral.py", "fixture_observacion")
        first = http(self.urls["api"], "/v1/observaciones", fixture["raw"])
        second = http(self.urls["api"], "/v1/observaciones", fixture["raw"])
        for response in (first, second):
            require(response["status"] == 200, "Observaciones no respondieron 200")
            validate_quality(response["body"]["calidad"])
        require(first["body"]["registros_guardados"] == fixture["nuevos_esperados"], "Cantidad de observaciones nuevas distinta a la esperada; revisar concurrencia")
        require(second["body"]["registros_guardados"] == 0, "Reenvío idéntico no es idempotente")
        stored = self.inside("inspeccion_integral.py", "estado_observacion", fixture["raw"])
        require(stored["coincidencias"] == stored["esperadas"], "PostgreSQL no conserva las ventas reales enviadas")
        return {"primera": first, "segunda": second, "sql": stored, "origen": fixture["origen"], "nota": "Solo valores reales existentes; no se sobrescribió intencionalmente una observación distinta"}

    def registry(self):
        metadata = self.inside("inspeccion_integral.py", "metadata")
        active = metadata["activo"]
        base = self.urls["mlflow"]
        prefix = "/api/2.0/mlflow/"
        alias = http(base, prefix + "registered-models/alias?" + urlencode({"name": active["nombre"], "alias": active["alias"]}))
        require(alias["status"] == 200 and str(alias["body"]["model_version"]["version"]) == active["version"], "Alias MLflow no corresponde al modelo activo")
        version = alias["body"]["model_version"]
        require(version.get("status") == "READY" and version.get("run_id") == active["run_id"], "Versión no READY o linaje run_id distinto")
        experiment = http(base, prefix + "experiments/get-by-name?" + urlencode({"experiment_name": active["nombre"]}))
        require(experiment["status"] == 200, "Experimento no encontrado")
        experiment_id = experiment["body"]["experiment"]["experiment_id"]
        runs = http(base, prefix + "runs/search", {"experiment_ids": [experiment_id], "max_results": 100, "order_by": ["attributes.start_time DESC"]})
        require(runs["status"] == 200, "No se pudieron leer runs")
        algorithms = set()
        for run in runs["body"].get("runs", []):
            params = {item["key"]: item["value"] for item in run["data"].get("params", [])}
            metrics = {item["key"] for item in run["data"].get("metrics", [])}
            if run["info"]["status"] == "FINISHED" and {"mae", "rmse", "business_cost"} <= metrics:
                if params.get("algorithm") in ("baseline", "ridge"):
                    algorithms.add(params["algorithm"])
        require({"baseline", "ridge"} <= algorithms, "Faltan baseline/ridge con parámetros y métricas terminados")
        run = http(base, prefix + "runs/get?" + urlencode({"run_id": active["run_id"]}))
        require(run["status"] == 200, "No existe el run del modelo activo")
        uri = urlsplit(run["body"]["run"]["info"]["artifact_uri"])
        require(uri.scheme == "mlflow-artifacts" and not uri.netloc, "Artefactos no usan el proxy esperado")
        root = "/api/2.0/mlflow-artifacts/artifacts/" + uri.path.strip("/")
        model = http(base, root + "/model/model.json")
        lineage = http(base, root + "/lineage.json")
        flavor = http(base, root + "/model/MLmodel")
        def parsed(response):
            require(response["status"] == 200, "No se pudo recuperar un artefacto")
            return json.loads(response["body"]) if isinstance(response["body"], str) else response["body"]
        model_body, lineage_body, flavor_body = parsed(model), parsed(lineage), parsed(flavor)
        require(canonical_hash(model_body) == active["artefacto_sha256"], "Modelo de MLflow difiere del respaldo JSONB")
        require(lineage_body.get("source_sha256") == metadata["fuentes_sha256"], "Linaje no corresponde a fuentes importadas")
        require(isinstance(lineage_body.get("model_code_sha256"), str) and isinstance(lineage_body.get("training_snapshot_sha256"), str), "Faltan hashes de código/snapshot")
        require("novamercado_json" in flavor_body.get("flavors", {}), "El Registry no apunta al flavor del producto")
        return {"experimento_id": experiment_id, "alias": active["alias"], "version": active["version"], "run_id": active["run_id"],
                "algoritmos_con_metricas": sorted(algorithms), "artefacto_sha256": active["artefacto_sha256"], "linaje": lineage_body}

    def dag(self):
        metadata = self.inside("inspeccion_integral.py", "metadata")
        require(metadata["ejecuciones_en_curso"] == 0, "Hay otro reentrenamiento activo")
        before = http(self.urls["api"], "/modelo")["body"]
        process = self.inspect()["api"]
        started = time.monotonic()
        dispatch = http(self.urls["api"], "/admin/reentrenar", method="POST")
        self.report.data["disparo_airflow"] = dispatch
        self.report.save()
        require(dispatch["status"] == 202 and isinstance(dispatch["body"].get("id"), str), "FastAPI no aceptó el disparo real de Airflow")
        identifier = dispatch["body"]["id"]
        self.report.data["ejecucion_airflow_solicitada"] = identifier
        self.report.save()
        result = airflow = None
        while time.monotonic() - started < 600:
            response = http(self.urls["api"], "/admin/reentrenar/" + identifier)
            require(response["status"] == 200, "No se pudo consultar la ejecución")
            result = response["body"]
            require(result.get("estado") in ("en_curso", "exitoso", "fallido"), "Estado administrativo fuera del contrato")
            if result["estado"] == "fallido":
                raise Failed("El producto registró el reentrenamiento como fallido; consultar su id en el informe")
            if result["estado"] == "exitoso":
                require(all(key in result for key in ("promovido", "version", "motivo")) and isinstance(result["version"], str), "Resultado final incompleto")
                airflow = self.inside("inspeccion_integral.py", "airflow", {"id": identifier})
                require(airflow["state"] != "failed", "El DAG terminó fallido")
                if airflow["state"] == "success":
                    break
            time.sleep(2)
        else:
            raise Failed("El DAG no terminó exitosamente en diez minutos")
        elapsed = time.monotonic() - started
        require(elapsed <= 600 and airflow["tareas"] and all(task["state"] == "success" for task in airflow["tareas"]), "No hay evidencia de tareas exitosas dentro del límite")
        if result["promovido"]:
            reload_started = time.monotonic()
            after = self.wait_model(result["version"], 120)
            reload_seconds = time.monotonic() - reload_started
            require(airflow.get("end_date"), "Falta end_date para comprobar recarga desde final real del DAG")
            ended = datetime.fromisoformat(airflow["end_date"].replace("Z", "+00:00"))
            since_end = (datetime.now(timezone.utc) - ended).total_seconds()
            require(0 <= since_end < 120, "Recarga no acreditada dentro de dos minutos del fin del DAG; revisar tiempos y relojes operativos")
        else:
            after = http(self.urls["api"], "/modelo")["body"]
            require(after == before and result["version"] == before["version"], "Un candidato no promovido cambió el modelo activo")
            reload_seconds = None
            since_end = None
        require(self.inspect()["api"] == process, "FastAPI se reinició o recreó durante el entrenamiento")
        self.production_promoted = bool(result["promovido"])
        return {"id": identifier, "resultado": result, "airflow": airflow, "seconds_dag": elapsed,
                "seconds_recarga_observada": reload_seconds, "modelo_final": after, "api_sin_reinicio": True,
                "seconds_desde_fin_real_dag": since_end,
                "nota": "No-promoción legítima no prueba promoción; el tiempo de recarga se mide desde la observación de finalización"}

    def wait_model(self, version, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = http(self.urls["api"], "/modelo", timeout=min(10, max(0.1, deadline - time.monotonic())))
            if response["status"] == 200 and response["body"].get("version") == version:
                return response["body"]
            time.sleep(1)
        raise Failed("La API no incorporó la versión dentro de dos minutos")

    def wait_health(self, expected, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = http(self.urls["api"], "/health", timeout=min(10, max(0.1, deadline - time.monotonic())))
                if response["status"] == 200 and isinstance(response["body"], dict) and response["body"].get("estado") == expected:
                    return response
            except OSError:
                pass
            time.sleep(1)
        raise Failed("Salud no alcanzó el estado requerido dentro del límite")

    def no_active_training(self):
        require(self.inside("inspeccion_integral.py", "metadata")["ejecuciones_en_curso"] == 0, "Hay entrenamiento activo; no interrumpir servicios")

    def replay(self):
        self.no_active_training()
        before = self.inside("inspeccion_integral.py", "snapshot")
        process = self.inspect()["api"]
        token = secrets.token_hex(8)
        self.report.data["replay_aislado"] = {"schema": "novamercado_it_" + token, "modelo": "novamercado_it_" + token + "_ventas"}
        self.report.save()
        result = self.inside("replay_integral.py", "run", {"token": token}, timeout=1800)
        after = self.inside("inspeccion_integral.py", "snapshot")
        require(before == after, "El replay cambió el estado productivo; revisar concurrencia")
        require(self.inspect()["api"] == process, "Se reinició/recreó FastAPI productivo durante replay")
        self.registry()  # Confirma alias productivo y respaldo sin cambios.
        if not result["promociones_observadas"]:
            raise Pending("Replay ejecutado sin promoción legítima; no se fuerza un candidato inferior")
        require(result["rechazos_observados"] >= 1, "El replay no acreditó rechazo de un candidato sin mejora")
        require(result.get("repeticion_historica_sin_fuga"), "El replay no acreditó repetición histórica tras promover sin ventas futuras")
        require(result["api_prueba_sin_reinicio"], "El servidor real de prueba no permaneció activo")
        return result

    def outage(self):
        self.no_active_training()
        before = http(self.urls["api"], "/modelo")["body"]
        process = self.inspect()["api"]
        failure = None
        result = {}
        started = time.monotonic()
        try:
            self.compose("stop", "mlflow", timeout=45)
            self.wait_health("degradado", max(0.1, 60 - (time.monotonic() - started)))
            result["seconds_deteccion"] = time.monotonic() - started
            require(result["seconds_deteccion"] < 60, "Detección de caída excedió un minuto")
            response = http(self.urls["api"], "/v1/prediccion", self.prediction_request)
            validate_prediction(response, self.prediction_request)
            require(http(self.urls["api"], "/modelo")["body"] == before, "Se perdió el modelo durante la caída")
            result["prediccion_con_mlflow_detenido"] = response
        except Exception as error:
            failure = error
        finally:
            recovery = time.monotonic()
            self.compose("start", "mlflow", timeout=45)
            self.wait_health("ok", max(0.1, 120 - (time.monotonic() - recovery)))
            result["seconds_recuperacion"] = time.monotonic() - recovery
            require(result["seconds_recuperacion"] < 120, "Recuperación de MLflow excedió dos minutos")
        if failure:
            raise failure
        require(self.inspect()["api"] == process, "FastAPI se reinició durante la caída/recuperación")
        return result

    def persistence(self):
        self.no_active_training()
        before = self.inside("inspeccion_integral.py", "snapshot")
        process = self.inspect()
        model = http(self.urls["api"], "/modelo")["body"]
        started = time.monotonic()
        self.compose("restart", *infra.SERVICES, timeout=180)
        self.wait_health("ok", max(0.1, 600 - (time.monotonic() - started)))
        elapsed = time.monotonic() - started
        require(elapsed <= 600, "Recuperación tras reinicio excedió diez minutos")
        after = self.inside("inspeccion_integral.py", "snapshot")
        require(before["huellas"] == after["huellas"], "Cambió o se perdió información persistida; revisar escrituras concurrentes")
        require(before["tablas"] == after["tablas"] and before["activo"] == after["activo"], "El reinicio cambió datos/modelos o repitió entrenamiento")
        require(http(self.urls["api"], "/modelo")["body"] == model, "Modelo cargado cambió al reiniciar")
        current = self.inspect()
        require(all(process[name]["id"] == current[name]["id"] and process[name]["volumes"] == current[name]["volumes"] for name in infra.SERVICES), "Se recrearon contenedores o cambiaron montajes")
        require(current["api"]["started"] != process["api"]["started"], "No hay evidencia de reinicio del proceso API")
        registry = self.registry()
        return {"seconds_reinicio_hasta_ok": elapsed, "huellas_antes": before["huellas"], "huellas_despues": after["huellas"],
                "tablas": after["tablas"], "version_conservada": model["version"], "registro": registry,
                "nota": "Medición de reinicio con volúmenes existentes, no arranque inicial vacío"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--con-interrupciones", action="store_true", help="Autoriza stop/start de mlflow y restart de los ocho servicios propios; sin borrar recursos")
    parser.add_argument("--replay-promocion", action="store_true", help="Replay real en esquema/modelo aislados; conserva las evidencias sin tocar champion productivo")
    parser.add_argument("--solo-asgi", action="store_true", help="Solo diez contratos unitarios dentro de la imagen; sin HTTP productivo, SQL, DAG o interrupciones")
    parser.add_argument("--trazas-asgi", action="store_true", help="Conservar trazas completas y versiones de dependencias en el informe privado")
    parser.add_argument("--archivo-asgi", type=Path, help="Archivo de pruebas dentro del proyecto; permite comparar el snapshot original sin reconstruir")
    arguments = parser.parse_args()
    if arguments.solo_asgi and (arguments.con_interrupciones or arguments.replay_promocion):
        parser.error("--solo-asgi es incompatible con interrupciones o replay")
    if arguments.archivo_asgi and not arguments.solo_asgi:
        parser.error("--archivo-asgi exige --solo-asgi")
    report = Report()
    integration = Integration(report)
    integration.asgi_traces = arguments.trazas_asgi
    if arguments.archivo_asgi:
        integration.asgi_source = (ROOT / arguments.archivo_asgi).resolve()
        integration.asgi_source.relative_to(ROOT.resolve())
    if arguments.solo_asgi:
        report.data["suite"] = "solo_asgi_unitario_en_imagen_sin_interrupciones"
        report.case("contrato_asgi_en_imagen", integration.asgi_contract, "unitario_en_contenedor")
        return report.finish()
    first = report.case("preflight_docker_y_publicaciones", integration.preflight)
    if first["estado"] != "aprobada":
        for name in ("contrato_http_sql", "observaciones_idempotencia", "mlflow", "airflow", "promocion_recarga", "resiliencia", "persistencia", "arranque_inicial_docker"):
            report.pending(name, "No ejecutada: el preflight real no está disponible")
        return report.finish()
    ready = report.case("estado_real_api_y_postgresql", integration.live_state)
    if ready["estado"] != "aprobada":
        report.pending("resto_integrales", "No se realizan escrituras/interrupciones sin estado inicial confirmado")
        return report.finish()
    coherence = report.case("coherencia_codigo_imagen", integration.code_coherence)
    if coherence["estado"] != "aprobada":
        report.pending("resto_integrales", "No se realizan escrituras/interrupciones con código desplegado distinto")
        return report.finish()
    report.case("contrato_asgi_en_imagen", integration.asgi_contract, "unitario_en_contenedor")
    for name, function in (("predicciones_http_y_auditoria_sql", integration.predictions),
                           ("calidad_reparaciones_advertencias_422", integration.quality),
                           ("observaciones_reales_idempotencia_sql", integration.observations)):
        row = report.case(name, function)
        if row["estado"] != "aprobada":
            report.case("mlflow_inspeccion_solo_lectura", integration.registry)
            report.pending("resto_integrales", "Revisar el fallo HTTP/SQL antes de otras escrituras, reentrenamientos o interrupciones")
            return report.finish()
    report.case("mlflow_runs_registry_alias_artefactos", integration.registry)
    report.case("fastapi_a_airflow_y_resultado_sql", integration.dag)
    if integration.production_promoted:
        report.case("promocion_productiva_y_recarga", integration.registry)
    else:
        report.pending("promocion_productiva_y_recarga", "No hubo promoción natural; no se fuerzan alias ni ventas futuras")
    if arguments.replay_promocion:
        report.case("promocion_replay_real_aislado", integration.replay, "replay_sql_mlflow_api_reales")
    else:
        report.pending("promocion_replay_real_aislado", "Omitido: activar --replay-promocion para usar solo ventas oficiales en esquema/modelo propios", "replay_sql_mlflow_api_reales")
    if arguments.con_interrupciones:
        outage = report.case("mlflow_caida_inferencia_recuperacion", integration.outage)
        if outage["estado"] == "aprobada":
            report.case("persistencia_y_reinicio_sin_reentrenar", integration.persistence)
        else:
            report.pending("persistencia_y_reinicio_sin_reentrenar", "Revisar y recuperar primero MLflow: docker compose start mlflow; no se reinicia el resto automáticamente")
    else:
        report.pending("mlflow_caida_inferencia_recuperacion", "Omitida sin --con-interrupciones")
        report.pending("persistencia_y_reinicio_sin_reentrenar", "Omitida sin --con-interrupciones")
    report.pending("arranque_inicial_docker_vacio", "No se borra el producto para cronometrarlo. Reinicio y replay no sustituyen esa medición")
    return report.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrumpido; conservar el informe parcial y comprobar recuperación de MLflow.", file=sys.stderr)
        sys.exit(130)
