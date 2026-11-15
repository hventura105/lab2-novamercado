"""Entrenamiento y promoción. El alias cambia solo después de persistir el artefacto."""

import hashlib
import json
from app.services.modelado import train_and_compare


def training_cycle(repository, tracking, sources, execution_id=None):
    with repository.training_lock():
        current = repository.active()
        if execution_id is None and current:
            return current  # Arranque posterior: nunca volver a entrenar por reiniciar.
        rows = repository.sales()
        result = train_and_compare(rows, sources, current["artifact"] if current else None)
        if result["candidate"] is None:
            if execution_id:
                repository.finish_run(execution_id, True, False, current["version"], result["reason"])
            return current
        snapshot = hashlib.sha256()
        for row in rows:
            snapshot.update(json.dumps([row.tienda_id, row.familia_id, row.fecha.isoformat(), row.ventas, row.en_promocion]).encode())
        lineage = {"validation_start": result["validation_start"], "training_snapshot_sha256": snapshot.hexdigest(), "observations_in_postgres": len(rows) - len(sources.history),
                   "promotion_rule": "business_cost improves >=1%; MAE deterioration <=5%; disjoint future validation"}
        for algorithm, artifact in result["validation_artifacts"].items():
            metrics = result["evaluations"].get(algorithm)
            if metrics:
                tracking.log_model(artifact, metrics, "temporal_validation", lineage)
        final_metrics = result["evaluations"]["ridge"] if result["candidate"]["algorithm"] == "ridge" else result["evaluations"]["baseline"]
        info = tracking.log_model(result["candidate"], final_metrics, "refit_candidate", lineage)
        version = tracking.register(info)
        repository.save_model(version, result["candidate"], info["run_id"], result["evaluations"], tracking.name)
        promote = current is None or result["promoted"]
        if promote:
            previous_version = current["version"] if current else None
            tracking.set_alias(version)
            try:
                repository.activate(version, tracking.alias, execution_id, result["reason"])
            except Exception:
                if previous_version is not None:
                    tracking.set_alias(previous_version)
                raise
            current = {"version": version, "artifact": result["candidate"]}
        if execution_id and not promote:
            repository.finish_run(execution_id, True, promote, current["version"], result["reason"])
        return current
