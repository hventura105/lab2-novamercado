"""Comprobaciones reales; nunca devolver credenciales ni errores del driver."""

import logging
import os
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def database_connection():
    import psycopg

    return psycopg.connect(
        host=os.environ["PRODUCT_DB_HOST"],
        port=int(os.environ.get("PRODUCT_DB_PORT", "5432")),
        dbname=os.environ["PRODUCT_DB_NAME"],
        user=os.environ["PRODUCT_DB_USER"],
        password=os.environ["PRODUCT_DB_PASSWORD"],
        connect_timeout=3,
        options="-c statement_timeout=3000",
    )


def check_database():
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Respuesta inesperada de PostgreSQL")


def check_mlflow():
    endpoint = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    with urlopen(f"{endpoint.rstrip('/')}/health", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("MLflow no está disponible")


def readiness():
    checks = {}
    for name, probe in (("postgres", check_database), ("mlflow", check_mlflow)):
        try:
            probe()
            checks[name] = "ok"
        except Exception as error:
            # No imprimir mensajes de conexión ni DSN, que pueden incluir secretos.
            logger.warning("Dependencia %s no disponible (%s)", name, type(error).__name__)
            checks[name] = "unavailable"
    ready = all(value == "ok" for value in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}, 200 if ready else 503
