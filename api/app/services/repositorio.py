"""Persistencia PostgreSQL del producto; transacciones completas y SQL parametrizado."""

from contextlib import contextmanager
from datetime import date
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.core.health import database_connection
from app.core.temporal import Sale


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


class Repository:
    def __init__(self, connection_factory=database_connection):
        self.connect = connection_factory

    def ping(self):
        with self.connect() as db:
            if db.execute("SELECT 1").fetchone() != (1,):
                raise RuntimeError("PostgreSQL no respondió correctamente")

    def expire_runs(self, version):
        with self.connect() as db:
            db.execute("""UPDATE novamercado.reentrenamientos SET estado='fallido',promovido=false,version=%s,
                motivo='Se superó el límite operativo de diez minutos',terminado_en=CURRENT_TIMESTAMP
                WHERE estado='en_curso' AND creado_en < CURRENT_TIMESTAMP - INTERVAL '10 minutes'""", (str(version),))

    def initialize(self, sources):
        migration = Path(__file__).resolve().parents[2] / "migrations" / "001_producto.sql"
        content = migration.read_text()
        sha = hashlib.sha256(content.encode()).hexdigest()
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(184002)")
            db.execute(content)
            previous = db.execute("SELECT sha256 FROM novamercado.migraciones WHERE version='001'").fetchone()
            if previous and previous[0] != sha:
                raise RuntimeError("La migración ya aplicada difiere; preparar nueva migración aditiva sin sobrescribir historial")
            db.execute("INSERT INTO novamercado.migraciones(version,sha256) VALUES ('001',%s) ON CONFLICT DO NOTHING", (sha,))
            fingerprints = dict(db.execute("SELECT archivo,sha256 FROM novamercado.fuentes").fetchall())
            if fingerprints:
                if fingerprints != sources.hashes:
                    raise RuntimeError("Las fuentes difieren de la carga persistida; se requiere revisión antes de reemplazar datos")
                return False
            with db.cursor() as cursor:
                cursor.executemany("INSERT INTO novamercado.tiendas VALUES (%s,%s,%s,%s,%s,%s)", [(sid, row['nombre'], row['ciudad'], row['departamento'], row['tipo'], row['fecha_apertura']) for sid, row in sources.stores.items()])
                cursor.executemany("INSERT INTO novamercado.familias VALUES (%s,%s)", list(sources.families.items()))
                cursor.executemany("INSERT INTO novamercado.costos VALUES (%s,%s,%s)", [(family, *values) for family, values in sources.costs.items()])
                cursor.executemany("INSERT INTO novamercado.feriados VALUES (%s,%s,%s,%s)", [(row['fecha'], row['nombre'], row['tipo'], row['ambito']) for row in sources.holidays])
                with cursor.copy("COPY novamercado.historico (tienda_id,familia_id,fecha,ventas,en_promocion) FROM STDIN") as copy:
                    for row in sources.history:
                        copy.write_row((row.tienda_id, row.familia_id, row.fecha, row.ventas, row.en_promocion))
                cursor.executemany("INSERT INTO novamercado.fuentes VALUES (%s,%s)", list(sources.hashes.items()))
        return True

    def sales(self):
        with self.connect() as db:
            rows = db.execute("""SELECT h.tienda_id,h.familia_id,h.fecha,h.ventas,h.en_promocion
                FROM novamercado.historico h WHERE NOT EXISTS (SELECT 1 FROM novamercado.observaciones o
                    WHERE (o.tienda_id,o.familia_id,o.fecha)=(h.tienda_id,h.familia_id,h.fecha))
                UNION ALL SELECT o.tienda_id,o.familia_id,o.fecha,o.ventas,h.en_promocion
                FROM novamercado.observaciones o LEFT JOIN novamercado.historico h
                ON (o.tienda_id,o.familia_id,o.fecha)=(h.tienda_id,h.familia_id,h.fecha)
                ORDER BY 3,1,2""").fetchall()
        return [Sale(sid, family, day, value, promo) for sid, family, day, value, promo in rows]

    def _request(self, db, kind, raw, clean, quality, code=200, detail=None):
        identifier = str(uuid4())
        db.execute("INSERT INTO novamercado.solicitudes(id,tipo,entrada,normalizada,calidad,codigo_http,detalle) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)",
                   (identifier, kind, encoded(raw), encoded(clean), encoded(quality), code, detail))
        return identifier

    def rejection(self, kind, raw, detail, code=422):
        with self.connect() as db:
            self._request(db, kind, raw, None, None, code, detail)

    def observe(self, raw, clean, quality):
        with self.connect() as db:
            identifier = self._request(db, "observaciones", raw, clean, quality)
            saved = 0
            for row in clean["ventas"]:
                changed = db.execute("""INSERT INTO novamercado.observaciones(tienda_id,fecha,familia_id,ventas,solicitud_id)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tienda_id,familia_id,fecha) DO UPDATE
                    SET ventas=EXCLUDED.ventas, solicitud_id=EXCLUDED.solicitud_id
                    WHERE novamercado.observaciones.ventas IS DISTINCT FROM EXCLUDED.ventas RETURNING familia_id""",
                    (clean["tienda_id"], clean["fecha"], row["familia_id"], row["ventas"], identifier)).fetchone()
                saved += changed is not None
        return saved

    def prediction(self, raw, clean, response):
        promotions = {row["familia_id"]: row["en_promocion"] for row in clean["familias"]}
        with self.connect() as db:
            identifier = self._request(db, "prediccion", raw, clean, response["calidad"])
            for row in response["predicciones"]:
                db.execute("INSERT INTO novamercado.predicciones VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                           (identifier, clean["tienda_id"], clean["fecha"], row["familia_id"], response["version_modelo"], row["venta_esperada"], row["cantidad_sugerida"], promotions[row["familia_id"]]))
        return identifier

    def active(self):
        with self.connect() as db:
            row = db.execute("SELECT m.version,m.artefacto FROM novamercado.modelos m JOIN novamercado.modelo_activo a ON a.version=m.version WHERE a.singleton=1").fetchone()
        return {"version": row[0], "artifact": row[1]} if row else None

    def model_before(self, day):
        with self.connect() as db:
            row = db.execute("""SELECT m.version,m.artefacto FROM novamercado.modelos m
                JOIN novamercado.promociones p ON p.version=m.version WHERE m.entrenado_hasta < %s
                ORDER BY m.entrenado_hasta DESC,p.activada_en DESC LIMIT 1""", (day,)).fetchone()
        return {"version": row[0], "artifact": row[1]} if row else None

    def save_model(self, version, artifact, run_id, metrics, name):
        with self.connect() as db:
            db.execute("INSERT INTO novamercado.modelos(version,nombre,run_id,entrenado_hasta,artefacto,metricas) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
                       (str(version), name, run_id, artifact["trained_through"], encoded(artifact), encoded(metrics)))

    def activate(self, version, alias, execution_id=None, reason=None):
        with self.connect() as db:
            db.execute("INSERT INTO novamercado.promociones(version) VALUES (%s) ON CONFLICT DO NOTHING", (str(version),))
            db.execute("INSERT INTO novamercado.modelo_activo VALUES (1,%s,%s) ON CONFLICT(singleton) DO UPDATE SET version=EXCLUDED.version,alias=EXCLUDED.alias", (str(version), alias))
            if execution_id:
                updated = db.execute("""UPDATE novamercado.reentrenamientos SET estado='exitoso',promovido=true,
                    version=%s,motivo=%s,terminado_en=CURRENT_TIMESTAMP WHERE id=%s AND estado='en_curso' RETURNING id""",
                    (str(version), reason, execution_id)).fetchone()
                if updated is None:
                    raise RuntimeError("La ejecución ya no está activa; no se promueve")

    def create_run(self, identifier):
        with self.connect() as db:
            db.execute("INSERT INTO novamercado.reentrenamientos(id,estado,airflow_run_id) VALUES (%s,'en_curso',%s)", (identifier, identifier))

    def get_run(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT estado,promovido,version,motivo FROM novamercado.reentrenamientos WHERE id=%s", (identifier,)).fetchone()
        if row is None:
            return None
        return {"estado": row[0]} if row[0] == "en_curso" else dict(zip(("estado", "promovido", "version", "motivo"), row))

    def finish_run(self, identifier, success, promoted, version, reason):
        with self.connect() as db:
            db.execute("UPDATE novamercado.reentrenamientos SET estado=%s,promovido=%s,version=%s,motivo=%s,terminado_en=CURRENT_TIMESTAMP WHERE id=%s AND estado='en_curso'",
                       ("exitoso" if success else "fallido", promoted, str(version), reason, identifier))

    @contextmanager
    def training_lock(self):
        with self.connect() as db:
            locked = db.execute("SELECT pg_try_advisory_xact_lock(184003)").fetchone()[0]
            if not locked:
                raise RuntimeError("Ya hay un entrenamiento en curso")
            yield
