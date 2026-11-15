"""Sondas de solo lectura del primer arranque; se transmiten por stdin a API."""

import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

sys.path.insert(0, "/app")


def health():
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=8) as response:
            return {"http": response.status, "body": json.loads(response.read())}
    except HTTPError as error:
        return {"http": error.code}
    except OSError:
        return {"http": None}


def verify():
    from app.core.health import database_connection
    from app.services.fuentes import Sources
    from app.services.integraciones import Tracking, http

    def require(condition):
        if not condition:
            raise RuntimeError("Evidencia del arranque inicial inconsistente")

    def digest(value):
        def normalize(item):
            if isinstance(item, float) and item.is_integer():
                return int(item)
            if isinstance(item, dict):
                return {k: normalize(v) for k, v in item.items()}
            if isinstance(item, list):
                return [normalize(v) for v in item]
            return item
        return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    sources = Sources(Path("/data/entrada"))
    expected = {"historico": len(sources.history), "tiendas": len(sources.stores),
                "familias": len(sources.families), "costos": len(sources.costs), "feriados": len(sources.holidays)}
    with database_connection() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        counts = {table: db.execute(f"SELECT count(*) FROM novamercado.{table}").fetchone()[0]
                  for table in (*expected, "observaciones", "solicitudes", "modelos", "promociones", "reentrenamientos")}
        require(all(counts[k] == v for k, v in expected.items()))
        require(all(counts[k] == 0 for k in ("observaciones", "solicitudes", "reentrenamientos")))
        require(counts["modelos"] == counts["promociones"] == 1)
        hashes = dict(db.execute("SELECT archivo,sha256 FROM novamercado.fuentes").fetchall())
        require(hashes == sources.hashes)
        row = db.execute("""SELECT m.nombre,m.version,a.alias,m.run_id,m.entrenado_hasta,m.artefacto
            FROM novamercado.modelo_activo a JOIN novamercado.modelos m ON m.version=a.version WHERE a.singleton=1""").fetchone()
        require(row is not None and str(row[1]) == "1" and row[4] == sources.history_end)

    with urlopen("http://127.0.0.1:8000/modelo", timeout=10) as response:
        model = json.loads(response.read())
    require(model == {"nombre": row[0], "version": str(row[1]), "alias": row[2]})
    tracking = Tracking()
    version = tracking.call("registered-models/alias?" + urlencode({"name": row[0], "alias": row[2]}))["model_version"]
    require(str(version["version"]) == "1" and version["status"] == "READY" and version["run_id"] == row[3])
    experiment = tracking.call("experiments/get-by-name?" + urlencode({"experiment_name": row[0]}))["experiment"]
    runs = tracking.call("runs/search", {"experiment_ids": [experiment["experiment_id"]], "max_results": 100})["runs"]
    algorithms = set()
    for run in runs:
        params = {p["key"]: p["value"] for p in run["data"].get("params", [])}
        metrics = {m["key"] for m in run["data"].get("metrics", [])}
        if run["info"]["status"] == "FINISHED" and {"mae", "rmse", "business_cost"} <= metrics:
            algorithms.add(params.get("algorithm"))
    require({"baseline", "ridge"} <= algorithms)
    run = tracking.call("runs/get?" + urlencode({"run_id": row[3]}))["run"]
    uri = urlsplit(run["info"]["artifact_uri"])
    require(uri.scheme == "mlflow-artifacts" and not uri.netloc)
    prefix = tracking.url + "/api/2.0/mlflow-artifacts/artifacts/" + uri.path.strip("/")

    def artifact(path):
        result = http(prefix + path)
        return json.loads(result) if isinstance(result, (bytes, str)) else result

    require(digest(artifact("/model/model.json")) == digest(row[5]))
    lineage = artifact("/lineage.json")
    require(lineage["source_sha256"] == hashes)
    require("novamercado_json" in artifact("/model/MLmodel")["flavors"])
    require(health() == {"http": 200, "body": {"estado": "ok"}})
    return {"tablas": counts, "fuentes_sha256": hashes, "modelo": model,
            "entrenado_hasta": row[4].isoformat(), "run_id": row[3], "artefacto_sha256": digest(row[5]),
            "algoritmos_con_metricas": sorted(a for a in algorithms if a), "health": {"http": 200, "body": {"estado": "ok"}}}


if __name__ == "__main__":
    try:
        print(json.dumps(health() if sys.argv[1] == "health" else verify(), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"error_tipo": type(error).__name__}))
        sys.exit(1)
