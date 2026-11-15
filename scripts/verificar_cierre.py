#!/usr/bin/env python3
"""Un comando para pytest aislado y entrega Git; no reinicia el producto ni repite integrales."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import entrega_local
from scripts.prueba_arranque_limpio import write_private


def junit_counts(source):
    root = ET.fromstring(source)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    counts["contratos_asgi"] = sum(1 for case in root.iter("testcase") if case.attrib.get("classname", "").endswith("EndpointTests"))
    if counts["tests"] == 0 or any(counts[k] for k in ("failures", "errors", "skipped")) or counts["contratos_asgi"] != 10:
        raise RuntimeError("pytest/JUnit no acredita todas las unitarias y diez contratos sin omisiones")
    return counts


def run(arguments, folder, label, timeout=120):
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    output = result.stdout + "\n" + result.stderr
    for value in entrega_local.known_secrets():
        output = output.replace(value.decode(), "[REDACTADO]")
    write_private(folder / (label + ".log"), output, exclusive=True)
    if result.returncode:
        raise RuntimeError("No completado: " + label + "; revisar su log privado")
    return result.stdout.strip()


def main():
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    folder = ROOT / "evidence/private/cierre" / identifier
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {"estado": "en_curso", "alcance": "pytest unitario/contrato en Python3.12 sin red; no nuevas integrales productivas"}
    try:
        if (ROOT / "evidence/PYTEST_VERIFICADO.md").exists():
            raise RuntimeError("La evidencia pytest ya existe: revisar el informe previo antes de repetirla")
        run(["docker", "ps", "--format", "{{.ID}}"], folder, "daemon")
        source, hashes = entrega_local.export_source()
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
        image = "lab2-novamercado-tests:1.0.0-" + digest
        report.update(contexto=str(source.relative_to(ROOT)), imagen=image)
        write_private(folder / "informe.json", report)
        print("Construyendo imagen de pruebas; no se reconstruye el producto.", flush=True)
        run(["docker", "build", "--file", str(source / "docker/tests.Dockerfile"), "--tag", image, str(source)], folder, "build_pytest", timeout=1800)
        name = "novamercado-pytest-" + identifier.lower()
        run(["docker", "create", "--name", name, "--network", "none", "--label", "com.novamercado.scope=pytest",
             "--mount", "type=bind,src=" + str(ROOT / "data/entrada") + ",dst=/workspace/data/entrada,readonly", image], folder, "crear_pytest")
        report["contenedor"] = name
        print("Ejecutando pytest sin acceso a MLflow, Airflow ni red.", flush=True)
        # Guardar artefacto incluso si pytest retorna fallo.
        try:
            run(["docker", "start", "--attach", name], folder, "pytest", timeout=600)
        finally:
            run(["docker", "cp", name + ":/workspace/evidence/private/pytest.xml", str(folder / "pytest.xml")], folder, "junit")
        exit_code = run(["docker", "inspect", "--format", "{{.State.ExitCode}}", name], folder, "exit_pytest")
        if exit_code != "0":
            raise RuntimeError("El contenedor de pytest no terminó con código0")
        counts = junit_counts((folder / "pytest.xml").read_text())
        report.update(pytest=counts, estado="aprobado", sin_red=True, recursos_conservados=True)
        evidence = ROOT / "evidence/PYTEST_VERIFICADO.md"
        text = "# pytest verificado\n\nEjecución real mediante scripts/verificar_cierre.py en contenedor Python3.12, sin red ni servicios MLflow/Airflow.\n\n"
        text += "Resultado: " + json.dumps(counts, ensure_ascii=False) + ". Código0. Integrales productivas no repetidas.\n\nInforme privado: `" + str((folder / "informe.json").relative_to(ROOT)) + "`. JUnit SHA-256: `" + hashlib.sha256((folder / "pytest.xml").read_bytes()).hexdigest() + "`.\n"
        if evidence.exists():
            raise RuntimeError("Ya existe evidencia pytest; revisar antes de sobrescribir")
        evidence.write_text(text)
        for relative in ("README.md", "AGENTS.md", "docs/REQUISITOS.md", "docs/ENTREGA.md", "evidence/AUDITORIA_FINAL.md", "evidence/CIERRE_VERIFICADO.md",
                         "docs/progreso/ESTADO_ACTUAL.md", "docs/progreso/PENDIENTES.md"):
            path = ROOT / relative
            path.write_text(path.read_text().replace("`pytest`: pendiente de ejecución real", "`pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md").replace("[ ] pytest unitario", "[x] pytest unitario"))
        for path in (ROOT / "docs/progreso").glob("*.md"):
            path.write_text(path.read_text() + "\nCierre automático: pytest aprobado, " + json.dumps(counts) + "; informe " + str(folder.relative_to(ROOT)) + "/informe.json. No se repitió el arranque ni se tocó champion.\n")
        report["git"] = entrega_local.prepare_git()
    except (Exception, KeyboardInterrupt) as error:
        report.update(estado="no_completado", error_tipo=type(error).__name__,
                      motivo=str(error) if type(error) is RuntimeError else "Consultar evidencia privada; no se imprimen secretos")
    write_private(folder / "informe.json", report)
    print("Estado: " + report["estado"] + "; informe: " + str((folder / "informe.json").relative_to(ROOT)), flush=True)
    if "git" in report:
        print("Repositorio Git local: " + report["git"]["repositorio"])
    print("Sin push, tags, borrados ni interrupciones productivas.")
    return 0 if report["estado"] == "aprobado" else 1


if __name__ == "__main__":
    sys.exit(main())
