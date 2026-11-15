#!/usr/bin/env python3
"""Evaluación local REAL de fuentes oficiales, independiente de MLflow y Docker."""

import json
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from app.services.fuentes import Sources
from app.services.modelado import train_and_compare


def main():
    sources = Sources(ROOT / "data" / "entrada")
    print("Fuentes validadas. Entrenando baseline y ridge con corte temporal...", flush=True)
    result = train_and_compare(sources.history, sources)
    directory = ROOT / "evidence" / "private"
    directory.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in result.items() if key not in ("candidate", "validation_artifacts")}
    summary["model_code_sha256"] = hashlib.sha256((ROOT / "api/app/services/modelado.py").read_bytes()).hexdigest()
    summary["source_sha256"] = sources.hashes
    (directory / "validacion_local.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (directory / "modelo_local.json").write_text(json.dumps(result["candidate"], ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Artefacto y evaluación locales guardados en evidence/private/. No implica registro en MLflow ni promoción en producción.")


if __name__ == "__main__":
    main()
