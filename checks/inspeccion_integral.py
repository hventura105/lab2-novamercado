"""Inspección real, de solo lectura, ejecutable por stdin dentro del contenedor API."""

import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, "/app")


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


def table_hash(db, table, columns, ordering):
    digest = hashlib.sha256()
    count = 0
    with db.cursor() as cursor:
        # Identificadores constantes definidos por el programa; nunca valores del usuario.
        cursor.execute(f"SELECT {columns} FROM novamercado.{table} ORDER BY {ordering}")
        while rows := cursor.fetchmany(1000):
            for row in rows:
                digest.update(json.dumps(row, sort_keys=True, default=str, allow_nan=False).encode() + b"\n")
                count += 1
    return {"filas": count, "sha256": digest.hexdigest()}


def snapshot(db, fingerprints=False):
    tables = ("migraciones", "fuentes", "tiendas", "familias", "costos", "feriados", "historico", "solicitudes", "predicciones", "observaciones", "modelos", "modelo_activo", "promociones", "reentrenamientos")
    counts = {table: db.execute(f"SELECT count(*) FROM novamercado.{table}").fetchone()[0] for table in tables}
    row = db.execute("""SELECT m.nombre,m.version,a.alias,m.run_id,m.entrenado_hasta,m.artefacto,m.metricas
        FROM novamercado.modelo_activo a JOIN novamercado.modelos m ON m.version=a.version WHERE a.singleton=1""").fetchone()
    if row is None:
        raise RuntimeError("No hay modelo activo persistido")
    new_days = db.execute("SELECT count(DISTINCT fecha) FROM novamercado.observaciones WHERE fecha > %s", (row[4],)).fetchone()[0]
    bounds = db.execute("SELECT min(fecha),max(fecha) FROM novamercado.historico").fetchone()
    latest_observation = db.execute("SELECT max(fecha) FROM novamercado.observaciones").fetchone()[0]
    active_runs = db.execute("SELECT count(*) FROM novamercado.reentrenamientos WHERE estado='en_curso'").fetchone()[0]
    result = {"tablas": counts, "hist_min": bounds[0], "hist_max": bounds[1], "ultima_observacion": latest_observation,
        "dias_nuevos": new_days, "ejecuciones_en_curso": active_runs,
        "activo": {"nombre": row[0], "version": str(row[1]), "alias": row[2], "run_id": row[3], "entrenado_hasta": row[4],
                   "artefacto_sha256": canonical_hash(row[5]), "metricas": row[6]},
        "fuentes_sha256": dict(db.execute("SELECT archivo,sha256 FROM novamercado.fuentes").fetchall())}
    if fingerprints:
        result["huellas"] = {
            "migraciones": table_hash(db, "migraciones", "version,sha256", "version"),
            "fuentes": table_hash(db, "fuentes", "archivo,sha256", "archivo"),
            "tiendas": table_hash(db, "tiendas", "tienda_id,nombre,ciudad,departamento,tipo,fecha_apertura", "tienda_id"),
            "familias": table_hash(db, "familias", "familia_id,nombre", "familia_id"),
            "costos": table_hash(db, "costos", "familia_id,costo_faltante,costo_sobrante", "familia_id"),
            "feriados": table_hash(db, "feriados", "fecha,nombre,tipo,ambito", "fecha,nombre,tipo,ambito"),
            "historico": table_hash(db, "historico", "tienda_id,familia_id,fecha,ventas,en_promocion", "tienda_id,familia_id,fecha"),
            "observaciones": table_hash(db, "observaciones", "tienda_id,familia_id,fecha,ventas,solicitud_id", "tienda_id,familia_id,fecha"),
            "predicciones": table_hash(db, "predicciones", "solicitud_id,tienda_id,fecha,familia_id,version_modelo,venta_esperada,cantidad_sugerida,en_promocion", "solicitud_id,familia_id"),
            "solicitudes": table_hash(db, "solicitudes", "id,tipo,entrada,normalizada,calidad,codigo_http,detalle", "id"),
            "modelos": table_hash(db, "modelos", "version,nombre,run_id,entrenado_hasta,artefacto,metricas", "version"),
            "modelo_activo": table_hash(db, "modelo_activo", "singleton,version,alias", "singleton"),
            "promociones": table_hash(db, "promociones", "version,activada_en", "version"),
            "reentrenamientos": table_hash(db, "reentrenamientos", "id,estado,promovido,version,motivo,airflow_run_id", "id"),
        }
    return result


def observation_fixture(db):
    # No seleccionar una tienda/fecha con observaciones existentes para insertar sobre ella.
    row = db.execute("""SELECT h.tienda_id,h.fecha FROM novamercado.historico h
        WHERE NOT EXISTS (SELECT 1 FROM novamercado.observaciones o WHERE o.tienda_id=h.tienda_id AND o.fecha=h.fecha)
        GROUP BY h.tienda_id,h.fecha ORDER BY h.fecha DESC,h.tienda_id LIMIT 1""").fetchone()
    fresh = row is not None
    if row is None:
        row = db.execute("SELECT tienda_id,fecha FROM novamercado.observaciones GROUP BY tienda_id,fecha ORDER BY fecha DESC,tienda_id LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No hay ventas reales para una observación de prueba")
    table = "historico" if fresh else "observaciones"
    values = db.execute(f"SELECT familia_id,ventas FROM novamercado.{table} WHERE tienda_id=%s AND fecha=%s ORDER BY familia_id", row).fetchall()
    raw = {"tienda_id": row[0], "fecha": row[1].isoformat(), "ventas": [{"familia_id": family, "ventas": value} for family, value in values]}
    return {"raw": raw, "nuevos_esperados": len(values) if fresh else 0, "origen": "historico_oficial_sin_observacion" if fresh else "observacion_real_existente", "sha256": canonical_hash(raw)}


def observation_state(db, raw):
    matches = 0
    for item in raw["ventas"]:
        found = db.execute("SELECT ventas FROM novamercado.observaciones WHERE tienda_id=%s AND fecha=%s AND familia_id=%s", (raw["tienda_id"], raw["fecha"], item["familia_id"])).fetchone()
        matches += bool(found is not None and found[0] == item["ventas"])
    return {"coincidencias": matches, "esperadas": len(raw["ventas"]), "entrada_sha256": canonical_hash(raw)}


def request_audit(db, raw):
    rows = db.execute("""SELECT s.id,s.codigo_http,s.calidad,count(p.familia_id),count(DISTINCT p.familia_id),
        array_agg(DISTINCT p.version_modelo) FILTER (WHERE p.familia_id IS NOT NULL)
        FROM novamercado.solicitudes s LEFT JOIN novamercado.predicciones p ON p.solicitud_id=s.id
        WHERE s.tipo='prediccion' AND s.entrada=%s::jsonb GROUP BY s.id ORDER BY s.recibida_en DESC,s.id LIMIT 100""", (json.dumps(raw, allow_nan=False),)).fetchall()
    return {"solicitudes": [{"id": r[0], "http": r[1], "calidad": r[2], "predicciones": r[3], "familias_distintas": r[4], "versiones": r[5] or []} for r in rows]}


def airflow_evidence(identifier):
    from app.services.integraciones import Airflow, http
    client = Airflow()
    base = client.url + f"/api/v2/dags/{client.dag_id}/dagRuns/" + quote(identifier, safe="")
    headers = client.headers()
    run = http(base, headers=headers)
    tasks = http(base + "/taskInstances", headers=headers).get("task_instances", [])
    return {"dag_id": client.dag_id, "dag_run_id": run.get("dag_run_id"), "state": run.get("state"),
            "start_date": run.get("start_date"), "end_date": run.get("end_date"),
            "tareas": [{key: item.get(key) for key in ("task_id", "state", "try_number")} for item in tasks]}


def main():
    action = sys.argv[1]
    payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if action == "code_hashes":
        result = {}
        for relative in payload["paths"]:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or path.parts[0] not in ("app", "migrations"):
                raise ValueError("Ruta de código no permitida")
            result[relative] = hashlib.sha256((Path("/app") / path).read_bytes()).hexdigest()
    elif action == "airflow":
        result = airflow_evidence(payload["id"])
    else:
        from app.core.health import database_connection
        with database_connection() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if action in ("metadata", "snapshot"):
                result = snapshot(db, action == "snapshot")
            elif action == "fixture_observacion":
                result = observation_fixture(db)
            elif action == "estado_observacion":
                result = observation_state(db, payload)
            elif action == "solicitudes":
                result = request_audit(db, payload)
            else:
                raise ValueError("Inspección no admitida")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error_tipo": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None), "detalle": "No se pudo completar la inspección; no se muestran consultas, valores ni credenciales"}))
        sys.exit(1)
