"""DAG real: el servicio de producto ejecuta el pipeline con histórico y observaciones PostgreSQL."""

from datetime import timedelta
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen

from airflow.sdk import dag, task, get_current_context


@dag(dag_id="novamercado_reentrenamiento", schedule=None, catchup=False,
     is_paused_upon_creation=False, max_active_runs=1, dagrun_timeout=timedelta(minutes=10),
     tags=["novamercado", "reentrenamiento"])
def retraining_dag():
    @task(execution_timeout=timedelta(minutes=9), retries=0)
    def train_evaluate_promote():
        context = get_current_context()
        identifier = context["dag_run"].conf.get("execution_id")
        if not identifier:
            raise ValueError("Falta execution_id creado por POST /admin/reentrenar")
        endpoint = os.environ["NOVAMERCADO_API_URL"] + "/internal/reentrenar/" + quote(identifier, safe="")
        request = Request(endpoint, data=b"", method="POST", headers={"X-Internal-Token": os.environ["INTERNAL_API_TOKEN"]})
        with urlopen(request, timeout=530) as response:
            result = json.load(response)
        if result.get("estado") != "exitoso":
            raise RuntimeError("El pipeline no terminó exitosamente")
        # Solo resumen de operación, nunca datos de entrenamiento ni credenciales.
        return {"estado": result["estado"], "promovido": result["promovido"], "version": result["version"]}

    train_evaluate_promote()


retraining_dag()
