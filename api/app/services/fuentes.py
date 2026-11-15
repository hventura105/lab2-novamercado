"""Carga estricta de fuentes oficiales; no repara silenciosamente archivos de entrenamiento."""

from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
from pathlib import Path

from app.core.temporal import Sale


class Sources:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.hashes = {}
        required = {
            "tiendas.csv": {"tienda_id", "nombre", "ciudad", "departamento", "tipo", "fecha_apertura"},
            "familias.csv": {"familia_id", "nombre"},
            "costos.csv": {"familia_id", "costo_faltante", "costo_sobrante"},
            "feriados.csv": {"fecha", "nombre", "tipo", "ambito"},
            "historico_ventas.csv": {"fecha", "tienda_id", "familia_id", "ventas", "en_promocion"},
        }
        tables = {}
        for name, columns in required.items():
            path = self.directory / name
            self.hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if set(reader.fieldnames or []) != columns:
                    raise ValueError(f"Columnas inesperadas en {name}")
                tables[name] = list(reader)
            if not tables[name] or any(None in row or any(value is None or not value.strip() for value in row.values()) for row in tables[name]):
                raise ValueError(f"Fuente vacía o con valores ausentes: {name}")
        self.tables = tables
        self.stores = {int(row["tienda_id"]): row for row in tables["tiendas.csv"]}
        self.families = {row["familia_id"]: row["nombre"] for row in tables["familias.csv"]}
        self.costs = {row["familia_id"]: (float(row["costo_faltante"]), float(row["costo_sobrante"])) for row in tables["costos.csv"]}
        self.holidays = tables["feriados.csv"]
        self.history = [Sale(int(row["tienda_id"]), row["familia_id"], date.fromisoformat(row["fecha"]), float(row["ventas"]), int(row["en_promocion"])) for row in tables["historico_ventas.csv"]]
        self.history.sort(key=lambda row: (row.fecha, row.tienda_id, row.familia_id))
        self.history_start = min(row.fecha for row in self.history)
        self.history_end = max(row.fecha for row in self.history)
        self.calendar_end = max(date.fromisoformat(row["fecha"]) for row in self.holidays)
        self._validate()

    def _validate(self):
        if len(self.stores) != len(self.tables["tiendas.csv"]) or len(self.families) != len(self.tables["familias.csv"]):
            raise ValueError("Catálogos con identificadores duplicados")
        if len(self.costs) != len(self.tables["costos.csv"]) or set(self.costs) != set(self.families):
            raise ValueError("Costos duplicados o incompletos")
        from app.services.costos import costs
        for values in self.costs.values():
            costs(*values)
        seen = set()
        for row in self.history:
            key = row.tienda_id, row.familia_id, row.fecha
            if key in seen:
                raise ValueError("Histórico con claves duplicadas")
            seen.add(key)
            if row.tienda_id not in self.stores or row.familia_id not in self.families:
                raise ValueError("Referencia desconocida en histórico")
            if row.fecha < date.fromisoformat(self.stores[row.tienda_id]["fecha_apertura"]):
                raise ValueError("Ventas anteriores a la apertura de tienda")
        cities = {store["ciudad"] for store in self.stores.values()} | {"nacional"}
        if any(row["ambito"] not in cities for row in self.holidays):
            raise ValueError("Ámbito de calendario sin ciudad correspondiente")
        for row in self.holidays:
            date.fromisoformat(row["fecha"])

    def audit(self):
        observed = defaultdict(set)
        for row in self.history:
            observed[row.tienda_id, row.familia_id].add(row.fecha.toordinal())
        missing = 0
        coverage = []
        for sid, store in sorted(self.stores.items()):
            first = max(self.history_start, date.fromisoformat(store["fecha_apertura"]))
            expected = set(range(first.toordinal(), self.history_end.toordinal() + 1))
            gaps = sum(len(expected - observed[sid, family]) for family in self.families)
            missing += gaps
            coverage.append({"tienda_id": sid, "desde": first.isoformat(), "dias_por_familia": len(expected), "huecos": gaps})
        return {"fuentes_sha256": self.hashes, "filas": len(self.history), "tiendas": len(self.stores), "familias": len(self.families),
                "historico_min": self.history_start.isoformat(), "historico_max": self.history_end.isoformat(),
                "feriados_min": min(row["fecha"] for row in self.holidays), "feriados_max": self.calendar_end.isoformat(),
                "eventos": len(self.holidays), "tipos_eventos": dict(Counter(row["tipo"] for row in self.holidays)),
                "huecos_tras_apertura": missing, "cobertura": coverage}

    def event_features(self, sid, day):
        city = self.stores[sid]["ciudad"]
        events = {row["tipo"] for row in self.holidays if row["fecha"] == day.isoformat() and row["ambito"] in ("nacional", city)}
        # Dentro de la cobertura publicada, ausencia de evento significa ningún evento listado.
        return [float(name in events) for name in ("feriado", "comercial", "pago", "medio_dia")]
