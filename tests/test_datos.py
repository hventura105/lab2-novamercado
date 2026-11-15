"""Fixtures efímeras de seguridad; nunca sustituyen datos oficiales en data/entrada/."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import datos


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=datos.ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "origen"
        self.source.mkdir()
        self.target = self.root / "destino"

    def test_copy_checks_hash_and_preserves_original(self):
        raw = b"tienda_id\n123\n"
        (self.source / "tiendas.csv").write_bytes(raw)
        result = datos.copy_official(self.source, self.target)
        self.assertEqual((self.source / "tiendas.csv").read_bytes(), raw)
        self.assertEqual((self.target / "tiendas.csv").read_bytes(), raw)
        self.assertEqual(result[0]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result, datos.copy_official(self.source, self.target))

    def test_conflicting_copy_never_overwrites_or_partially_imports(self):
        self.target.mkdir()
        (self.target / "tiendas.csv").write_text("original importante")
        (self.source / "tiendas.csv").write_text("diferente")
        (self.source / "familias.csv").write_text("familia_id\nx\n")
        with self.assertRaises(FileExistsError):
            datos.copy_official(self.source, self.target)
        self.assertEqual((self.target / "tiendas.csv").read_text(), "original importante")
        self.assertFalse((self.target / "familias.csv").exists())

    def test_zip_preserves_examples_and_ignores_unrelated_members(self):
        archive = self.root / "fuentes.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("paquete/tiendas.csv", "tienda_id\n123\n")
            handle.writestr("paquete/ejemplos/valido.json", "{}")
            handle.writestr("paquete/ajeno.txt", "no copiar")
        result = datos.copy_official(archive, self.target)
        self.assertEqual({entry["archivo"] for entry in result}, {"tiendas.csv", "ejemplos/valido.json"})
        self.assertFalse((self.target / "ajeno.txt").exists())

    def test_zip_path_traversal_is_rejected_before_writing(self):
        archive = self.root / "inseguro.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("tiendas.csv", "tienda_id\n123\n")
            handle.writestr("../../fuera.txt", "x")
        with self.assertRaisesRegex(ValueError, "insegura"):
            datos.copy_official(archive, self.target)
        self.assertFalse((self.target / "tiendas.csv").exists())

    def test_zip_windows_absolute_path_is_rejected(self):
        for name in ("C:\\Users\\tiendas.csv", "/tiendas.csv", "a/../tiendas.csv"):
            with self.assertRaises(ValueError):
                datos.safe_name(name)

    def test_archive_duplicate_destination_is_ambiguous(self):
        archive = self.root / "duplicado.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("uno/tiendas.csv", "a")
            handle.writestr("dos/tiendas.csv", "b")
        with self.assertRaisesRegex(ValueError, "ambiguo"):
            datos.copy_official(archive, self.target)

    def test_tar_symlink_is_rejected(self):
        archive = self.root / "enlace.tar"
        with tarfile.open(archive, "w") as handle:
            member = tarfile.TarInfo("tiendas.csv")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            handle.addfile(member)
        with self.assertRaisesRegex(ValueError, "enlaces"):
            datos.copy_official(archive, self.target)

    def test_oversized_archive_is_rejected(self):
        (self.source / "tiendas.csv").write_text("datos")
        with patch.object(datos, "MAX_FILE", 2):
            with self.assertRaisesRegex(ValueError, "límites"):
                datos.copy_official(self.source, self.target)


class ProfileTests(unittest.TestCase):
    def profile(self, content):
        with tempfile.TemporaryDirectory(dir=datos.ROOT) as directory:
            path = Path(directory) / "prueba.csv"
            path.write_text(content)
            return datos.profile_csv(path)

    def test_profile_counts_real_rows_nulls_duplicates_and_range(self):
        result = self.profile("tienda_id,familia_id,fecha,ventas\n1,a,2024-02-28,10\n1,a,2024-02-29,\n1,a,2024-02-28,10\n")
        self.assertEqual(result["filas"], 3)
        self.assertEqual(result["duplicados_exactos"], 1)
        self.assertEqual(result["duplicados_clave"], 1)
        self.assertEqual(result["faltantes_vacios"]["ventas"], 1)
        self.assertEqual(result["fechas"]["fecha"]["min"], "2024-02-28")
        self.assertEqual(result["fechas"]["fecha"]["max"], "2024-02-29")
        self.assertEqual(result["identificadores_distintos"], {"tienda_id": 1, "familia_id": 1})

    def test_profile_does_not_guess_ambiguous_dates(self):
        result = self.profile("fecha,valor\n01/02/2025,1\n2025-02-30,2\n")
        self.assertIsNone(result["fechas"]["fecha"]["min"])
        self.assertEqual(result["fechas"]["fecha"]["no_interpretadas"], 2)

    def test_missing_sources_never_report_complete(self):
        with tempfile.TemporaryDirectory(dir=datos.ROOT) as directory:
            result = datos.profile_directory(Path(directory))
        self.assertFalse(result["fuentes_completas"])
        self.assertEqual(len(result["faltantes"]), 6)


if __name__ == "__main__":
    unittest.main()
