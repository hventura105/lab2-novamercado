"""Invariantes de fechas simuladas, independientes del reloj y de servicios externos."""

from dataclasses import dataclass
from datetime import date
import math
from statistics import fmean
from typing import Iterable


class TemporalLeakageError(ValueError):
    """Se intenta usar una observación o modelo que todavía no estaba disponible."""


@dataclass(frozen=True)
class Sale:
    tienda_id: int
    familia_id: str
    fecha: date
    ventas: float
    en_promocion: int | None = None

    def __post_init__(self):
        if type(self.fecha) is not date:
            raise ValueError("La observación requiere una fecha sin hora")
        if isinstance(self.ventas, bool) or not isinstance(self.ventas, (int, float)) or not math.isfinite(self.ventas) or self.ventas < 0:
            raise ValueError("Las ventas deben ser numéricas, finitas y no negativas")
        if self.en_promocion is not None and (type(self.en_promocion) is not int or self.en_promocion < 0):
            raise ValueError("Promociones: entero no negativo o ausente; no se imputan observaciones")


def validate_forecast_date(target: date, official_history_end: date, calendar_end: date):
    """Los límites vienen de fuentes oficiales; no hay un horizonte oculto fijo."""
    if any(type(value) is not date for value in (target, official_history_end, calendar_end)):
        raise ValueError("Se requieren fechas, sin horas")
    if target <= official_history_end:
        raise ValueError("El pronóstico debe ser posterior al histórico oficial")
    if target > calendar_end:
        raise ValueError("La fecha excede la cobertura conocida de feriados.csv")


def assert_model_available(trained_through: date, target: date):
    if trained_through >= target:
        raise TemporalLeakageError("El modelo contiene ventas del mismo día o posteriores al pronóstico")


def available_sales(records: Iterable[Sale], target: date):
    """Ventas de D se conocen en D+1: para D solo observaciones con fecha < D."""
    return [row for row in records if row.fecha < target]


def chronological_split(records: Iterable[Sale], validation_days: int):
    rows = sorted(records, key=lambda row: (row.fecha, row.tienda_id, row.familia_id))
    dates = sorted({row.fecha for row in rows})
    if type(validation_days) is not int or validation_days <= 0 or len(dates) <= validation_days:
        raise ValueError("Se requieren días distintos para entrenamiento y validación")
    boundary = dates[-validation_days]
    train = [row for row in rows if row.fecha < boundary]
    validation = [row for row in rows if row.fecha >= boundary]
    if max(row.fecha for row in train) >= min(row.fecha for row in validation):
        raise TemporalLeakageError("Las particiones cronológicas se solapan")
    return train, validation


def past_features(records: Iterable[Sale], tienda_id: int, familia_id: str, target: date):
    """Ausencia se conserva como None, sin convertir días no observados en ventas cero."""
    rows = sorted((row for row in records if row.tienda_id == tienda_id and row.familia_id == familia_id and row.fecha < target), key=lambda row: row.fecha)
    if len(rows) != len({row.fecha for row in rows}):
        raise ValueError("Hay observaciones duplicadas para la misma tienda, familia y fecha")
    by_day = {row.fecha: row.ventas for row in rows}
    ordinal = target.toordinal()
    recent7 = [row.ventas for row in rows if 0 < ordinal - row.fecha.toordinal() <= 7]
    recent28 = [row.ventas for row in rows if 0 < ordinal - row.fecha.toordinal() <= 28]
    same_weekday = [row.ventas for row in rows if row.fecha.weekday() == target.weekday() and 0 < ordinal - row.fecha.toordinal() <= 56]
    return {
        "lag_1": by_day.get(date.fromordinal(ordinal - 1)),
        "lag_7": by_day.get(date.fromordinal(ordinal - 7)),
        "media_7": fmean(recent7) if recent7 else None,
        "media_28": fmean(recent28) if recent28 else None,
        "media_dia_semana": fmean(same_weekday) if same_weekday else None,
        "observaciones_7": len(recent7),
        "observaciones_28": len(recent28),
        "dias_desde_ultima": ordinal - rows[-1].fecha.toordinal() if rows else None,
    }
