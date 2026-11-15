"""Entrada pytest para los mismos chequeos reales del ejecutor stdlib."""

import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.pruebas_integrales import Integration, Report

pytestmark = pytest.mark.integration


def checked(core, name, function):
    row = core.report.case(name, function)
    assert row["estado"] == "aprobada", f"{name}: {row['estado']}; ver {core.report.directory}/informe.json"


@pytest.fixture(scope="module")
def stack():
    if os.environ.get("RUN_DOCKER_INTEGRATION") != "1":
        pytest.skip("Requiere RUN_DOCKER_INTEGRATION=1 y servicios reales")
    report = Report()
    report.data["suite"] = "pytest_integrales_seleccionadas"
    core = Integration(report)
    try:
        checked(core, "preflight", core.preflight)
        checked(core, "estado_inicial", core.live_state)
        checked(core, "coherencia_imagen", core.code_coherence)
        yield core
    finally:
        report.pending("cierre_academico_completo", "Esta selección pytest no sustituye todos los casos del runner ni la medición de arranque inicial Docker")
        report.finish()


def test_real_predictions_and_quality(stack):
    checked(stack, "predicciones_sql", stack.predictions)
    checked(stack, "calidad_422", stack.quality)


def test_real_observation_idempotence(stack):
    checked(stack, "observaciones_idempotentes_sql", stack.observations)


def test_real_registry_lineage_alias(stack):
    checked(stack, "mlflow_registry_linaje", stack.registry)


def test_real_airflow_dag(stack):
    checked(stack, "disparo_dag_real", stack.dag)


def test_real_mlflow_outage_recovery(stack):
    if os.environ.get("RUN_DOCKER_INTERRUPTION") != "1":
        pytest.skip("Interrupción de MLflow requiere RUN_DOCKER_INTERRUPTION=1")
    checked(stack, "caida_y_recuperacion_mlflow", stack.outage)


def test_real_restart_preserves_data(stack):
    if os.environ.get("RUN_DOCKER_INTERRUPTION") != "1":
        pytest.skip("Reinicio requiere RUN_DOCKER_INTERRUPTION=1")
    checked(stack, "persistencia_tras_reinicio", stack.persistence)


def test_real_isolated_promotion_replay(stack):
    if os.environ.get("RUN_DOCKER_REPLAY") != "1":
        pytest.skip("Replay real aislado requiere RUN_DOCKER_REPLAY=1")
    checked(stack, "replay_promocion_aislado", stack.replay)
