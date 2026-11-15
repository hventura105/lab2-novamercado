#!/usr/bin/env python3
"""Exportación revisada y Git independiente; no toca .git raíz, remotos ni tags."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("api", "checks", "scripts", "docker", "airflow/dags", "airflow/scripts", "airflow/plugins", "tests", "docs")
ROOT_FILES = (".gitignore", ".dockerignore", ".env.example", "AGENTS.md", "README.md", "DECISIONES.md",
              "compose.yaml", "pytest.ini", "conftest.py", "requirements-test.txt", "data/entrada/.gitkeep")
PUBLIC_EVIDENCE = ("evidence/CIERRE_VERIFICADO.md", "evidence/AUDITORIA_FINAL.md", "evidence/PYTEST_VERIFICADO.md",
                   "evidence/INFRAESTRUCTURA_USUARIO.md", "evidence/REPLAY_LOCAL_VALIDACION.md", "evidence/FASE1.md",
                   "evidence/INTEGRACION_SESION.md", "evidence/AVANCE_PRODUCTO.md")


def selected_files():
    paths = {ROOT / name for name in ROOT_FILES if (ROOT / name).is_file()}
    for name in DIRECTORIES:
        paths.update(p for p in (ROOT / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix not in (".pyc", ".log") and p.name != ".DS_Store")
    paths.update(ROOT / name for name in PUBLIC_EVIDENCE if (ROOT / name).is_file())
    for path in paths:
        relative = path.relative_to(ROOT)
        if path.is_symlink() or path.name == ".env" or path.suffix in (".key", ".pem", ".db", ".sqlite"):
            raise RuntimeError("Archivo privado/enlace excluido: " + relative.as_posix())
        if relative.parts[0] == "data" and relative.as_posix() != "data/entrada/.gitkeep":
            raise RuntimeError("Dataset no permitido en entrega")
    return sorted(paths)


def known_secrets():
    sources = [ROOT / ".env"]
    base = ROOT / "evidence/private/arranque-limpio"
    if base.is_dir():
        sources.extend(p / "prueba.env" for p in base.iterdir() if p.is_dir())
    values = set()
    for path in sources:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                value = value.strip().strip("\"'")
                if len(value) >= 8 and any(k in key.upper() for k in ("PASSWORD", "SECRET", "TOKEN", "FERNET")):
                    values.add(value.encode())
    return values


def export_source(destination=None):
    paths = selected_files()
    sensitive = known_secrets()
    content = {}
    for path in paths:
        blob = path.read_bytes()
        if any(value in blob for value in sensitive) or (b"-----BEGIN " + b"PRIVATE KEY-----") in blob:
            raise RuntimeError("Posible secreto en " + path.relative_to(ROOT).as_posix())
        content[path.relative_to(ROOT).as_posix()] = blob
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    folder = Path(destination) if destination is not None else ROOT / "evidence/private/entrega" / identifier
    folder = folder.resolve()
    folder.relative_to((ROOT / "evidence/private/entrega").resolve())
    repository = folder / "repositorio"
    repository.mkdir(parents=True, mode=0o700, exist_ok=False)
    hashes = {}
    for name, blob in content.items():
        target = repository / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        hashes[name] = hashlib.sha256(blob).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[name]:
            raise RuntimeError("Copia no íntegra")
    (folder / "manifest.json").write_text(json.dumps({"archivos": hashes, "secretos": "sin coincidencias de credenciales conocidas"}, indent=2) + "\n")
    return repository, hashes


def git(repository, *arguments, identity=False):
    command = ["git", "-C", str(repository), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]
    if identity:
        command += ["-c", "user.name=Codex", "-c", "user.email=codex@local.invalid"]
    result = subprocess.run([*command, *arguments], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Git local no completado: " + arguments[0])
    return result.stdout.strip()


def prepare_git(destination=None):
    repository, hashes = export_source(destination)
    git(repository, "init", "--initial-branch=main")
    git(repository, "add", "--", *hashes)
    tracked = set(git(repository, "ls-files", "-z").split("\0")) - {""}
    if tracked != set(hashes):
        raise RuntimeError("El índice no corresponde a los archivos revisados")
    for name in (".env", "data/entrada/historico_ventas.csv", "evidence/private/privado.json", ".aws/credentials"):
        git(repository, "check-ignore", "--", name)
    git(repository, "diff", "--cached", "--check")
    git(repository, "commit", "-m", "Preparar entrega verificada de NovaMercado Lab2", identity=True)
    if git(repository, "status", "--porcelain") or git(repository, "remote") or git(repository, "tag", "--list"):
        raise RuntimeError("La entrega no está limpia o contiene remotos/tags inesperados")
    result = {"repositorio": str(repository.relative_to(ROOT)), "commit": git(repository, "rev-parse", "HEAD"),
              "archivos": len(hashes), "estado": "limpio", "remotos": [], "tags": [],
              "autor": "Codex <codex@local.invalid>; identidad de automatización local, no del usuario"}
    (repository.parent / "git.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(prepare_git(), ensure_ascii=False, indent=2))
