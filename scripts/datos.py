#!/usr/bin/env python3
"""Inspección, copia verificada y perfil de fuentes oficiales, sin modificar originales."""

import argparse
from collections import Counter
import contextlib
import csv
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data" / "entrada"
REQUIRED = ("tiendas.csv", "familias.csv", "historico_ventas.csv", "feriados.csv", "costos.csv", "catalogo_errores.md")
MAX_FILE = 1024 ** 3
MAX_TOTAL = 2 * 1024 ** 3


def digest(stream):
    result = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_FILE:
            raise ValueError("Archivo excede el límite de copia segura de 1 GiB")
        result.update(chunk)
    return size, result.hexdigest()


def safe_name(name):
    name = name.replace("\\", "/")
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or any(":" in part or "\x00" in part for part in path.parts):
        raise ValueError("Ruta insegura en archivo comprimido")
    return path


def selected_name(name):
    path = safe_name(name)
    canonical = {value.casefold(): value for value in (*REQUIRED, "Laboratorio_2_PD_26_c.pdf")}
    if path.name.casefold() in canonical:
        return Path(canonical[path.name.casefold()])
    parts = [part.casefold() for part in path.parts]
    if "ejemplos" in parts:
        offset = parts.index("ejemplos")
        return Path("ejemplos", *path.parts[offset + 1:]) if len(path.parts) > offset + 1 else None
    return None


@contextlib.contextmanager
def source_entries(source):
    """Abrir miembros seleccionados; nunca usar extractall ni seguir enlaces."""
    source = Path(source)
    if source.is_symlink():
        raise ValueError("El origen debe ser un archivo o directorio real, sin enlace simbólico")
    entries = []
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                if selected_name(path.relative_to(source).as_posix()):
                    raise ValueError("No se copian fuentes mediante enlaces simbólicos")
                continue
            if path.is_file() and (name := selected_name(path.relative_to(source).as_posix())):
                entries.append((name, path.stat().st_size, lambda path=path: path.open("rb")))
        yield entries
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                safe_name(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("El ZIP contiene enlaces simbólicos")
                if member.is_dir():
                    continue
                if name := selected_name(member.filename):
                    if member.flag_bits & 1:
                        raise ValueError("No se admiten archivos ZIP cifrados")
                    entries.append((name, member.file_size, lambda member=member: archive.open(member)))
            yield entries
    elif source.is_file() and tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            for member in archive:
                safe_name(member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise ValueError("El TAR contiene enlaces o archivos especiales")
                if member.isfile() and (name := selected_name(member.name)):
                    entries.append((name, member.size, lambda member=member: archive.extractfile(member)))
            yield entries
    elif source.is_file() and (name := selected_name(source.name)):
        yield [(name, source.stat().st_size, lambda: source.open("rb"))]
    else:
        raise ValueError("Origen no encontrado o formato no admitido; usar directorio, ZIP, TAR o archivo oficial")


def copy_official(source, destination=DESTINATION):
    destination = Path(destination)
    destination.resolve().relative_to(ROOT.resolve())
    destination.mkdir(parents=True, exist_ok=True)
    with source_entries(source) as entries:
        if not entries:
            raise ValueError("No se encontraron archivos oficiales seleccionables en el origen")
        names = [name for name, _, _ in entries]
        if len(names) != len(set(names)):
            raise ValueError("Origen ambiguo: varios archivos corresponden al mismo destino")
        if any(size > MAX_FILE or size < 0 for _, size, _ in entries) or sum(size for _, size, _ in entries) > MAX_TOTAL:
            raise ValueError("El origen excede los límites de copia segura (1 GiB por archivo, 2 GiB total)")
        # Preparar y validar TODOS los miembros antes de copiar el primero al destino.
        with tempfile.TemporaryDirectory(prefix=".copia-", dir=destination) as staging:
            manifest = []
            for name, expected_size, opener in entries:
                target = destination / name
                if any(parent.is_symlink() for parent in (target, *target.parents)):
                    raise ValueError("Destino con enlaces simbólicos: se requiere revisión")
                stage = Path(staging) / name
                stage.parent.mkdir(parents=True, exist_ok=True)
                with opener() as original, stage.open("xb") as output:
                    shutil.copyfileobj(original, output, length=1024 * 1024)
                with stage.open("rb") as stream:
                    size, sha256 = digest(stream)
                if size != expected_size:
                    raise ValueError(f"El tamaño del origen cambió o el archivo está incompleto: {name}")
                if target.exists():
                    with target.open("rb") as stream:
                        existing = digest(stream)
                    if existing != (size, sha256):
                        raise FileExistsError(f"{name} ya existe con contenido diferente; solicitar autorización antes de sobrescribir")
                manifest.append({"archivo": name.as_posix(), "bytes": size, "sha256": sha256})
            for entry in manifest:
                name = Path(entry["archivo"])
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    # 'xb' también protege de una colisión ocurrida después de la validación.
                    with (Path(staging) / name).open("rb") as original, target.open("xb") as output:
                        shutil.copyfileobj(original, output)
                with target.open("rb") as stream:
                    if digest(stream) != (entry["bytes"], entry["sha256"]):
                        raise ValueError(f"Fallo de integridad en copia: {name}")
    manifest_path = destination / "integridad.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"archivos": []}
    combined = {entry["archivo"]: entry for entry in previous["archivos"]}
    combined.update({entry["archivo"]: entry for entry in manifest})
    manifest_path.write_text(json.dumps({"algoritmo": "SHA-256", "archivos": list(combined.values())}, ensure_ascii=False, indent=2) + "\n")
    return manifest


def normalized(value):
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    return re.sub(r"[\s-]+", "_", "".join(c for c in decomposed if not unicodedata.combining(c)))


def parse_iso(value):
    # El perfil no presupone día/mes frente a mes/día para fechas ambiguas.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def profile_csv(path):
    path = Path(path)
    with path.open("rb") as stream:
        size, sha256 = digest(stream)
    # UTF-8 con BOM o sin BOM. No adivinar codificación si hay bytes inválidos.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(65536)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        columns = reader.fieldnames
        if not columns or len(set(columns)) != len(columns):
            raise ValueError(f"Cabecera ausente o duplicada: {path.name}")
        canonical = {normalized(column): column for column in columns}
        missing = Counter({column: 0 for column in columns})
        explicit_null = Counter({column: 0 for column in columns})
        numeric = Counter()
        integer = Counter()
        dates = {column: [] for column in columns if "fecha" in normalized(column)}
        identifiers = {column: set() for column in columns if normalized(column) in ("tienda_id", "familia_id")}
        seen, keys = set(), set()
        duplicates = key_duplicates = rows = malformed = 0
        key_columns = [canonical[name] for name in ("tienda_id", "familia_id", "fecha") if name in canonical]
        for row in reader:
            rows += 1
            if None in row or any(row[column] is None for column in columns):
                malformed += 1
            identity = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).digest() if None not in row else repr(row).encode()
            duplicates += identity in seen
            seen.add(identity)
            if key_columns:
                key = tuple((row.get(column) or "").strip() for column in key_columns)
                key_duplicates += key in keys
                keys.add(key)
            for column in columns:
                value = (row.get(column) or "").strip()
                missing[column] += not value
                explicit_null[column] += value.casefold() in {"null", "none", "nan", "n/a", "na"}
                if value:
                    try:
                        from decimal import Decimal, InvalidOperation
                        number = Decimal(value)
                        if number.is_finite():
                            numeric[column] += 1
                            integer[column] += number == number.to_integral_value()
                    except InvalidOperation:
                        pass
                if column in dates and value:
                    parsed = parse_iso(value)
                    dates[column].append(parsed)
                if column in identifiers and value:
                    identifiers[column].add(value)
    date_report = {}
    for column, values in dates.items():
        valid = [value for value in values if value is not None]
        unique = set(valid)
        date_report[column] = {"min": min(valid).isoformat() if valid else None, "max": max(valid).isoformat() if valid else None,
                               "validas_iso": len(valid), "no_interpretadas": len(values) - len(valid), "dias_distintos": len(unique)}
    types = {}
    for column in columns:
        filled = rows - missing[column]
        types[column] = "vacio" if not filled else "fecha_iso" if column in dates and date_report[column]["validas_iso"] == filled else "entero" if integer[column] == filled else "numero" if numeric[column] == filled else "texto_o_mixto"
    return {"archivo": path.name, "bytes": size, "sha256": sha256, "columnas": columns, "delimitador": dialect.delimiter,
            "filas": rows, "filas_malformadas": malformed, "tipos_inferidos": types, "faltantes_vacios": dict(missing),
            "marcadores_nulos_texto": dict(explicit_null), "duplicados_exactos": duplicates,
            "clave_analizada": key_columns, "duplicados_clave": key_duplicates if key_columns else None,
            "identificadores_distintos": {column: len(values) for column, values in identifiers.items()}, "fechas": date_report}


def profile_directory(directory=DESTINATION):
    directory = Path(directory)
    absent = [name for name in REQUIRED if not (directory / name).is_file()]
    profiles = [profile_csv(directory / name) for name in REQUIRED if name.endswith(".csv") and (directory / name).is_file()]
    report = {"fuentes_completas": not absent and (directory / "ejemplos").is_dir(), "faltantes": absent,
              "ejemplos_presentes": (directory / "ejemplos").is_dir(), "csv": profiles,
              "nota": "Los rangos solo describen fechas ISO realmente leídas. Un feriado listado no demuestra por sí solo cobertura de todos los días intermedios."}
    (directory / "perfil.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    copy_parser = sub.add_parser("copiar")
    copy_parser.add_argument("origen", type=Path)
    profile_parser = sub.add_parser("perfil")
    profile_parser.add_argument("--exigir-completo", action="store_true")
    args = parser.parse_args()
    try:
        result = copy_official(args.origen) if args.action == "copiar" else profile_directory()
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile, tarfile.TarError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.action == "perfil" and args.exigir_completo and not result["fuentes_completas"]:
        parser.exit(1, "ERROR: faltan fuentes oficiales; no continuar con carga ni entrenamiento real\n")


if __name__ == "__main__":
    main()
