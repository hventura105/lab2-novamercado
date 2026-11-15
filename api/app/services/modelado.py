"""Baseline y regresión ridge por familia, con validación y calibración cronológicas.

Implementación numérica en Python: serialización JSON y ejecución sin un servidor
MLflow activo. Los eventos de D y promociones de la solicitud son información conocida.
"""

from bisect import bisect_left
from collections import defaultdict
from datetime import date
import math
from statistics import fmean
import time

from app.core.temporal import TemporalLeakageError, assert_model_available
from app.services.costos import business_cost, suggested_quantity, technical_metrics


class Series:
    def __init__(self):
        self.days, self.values, self.sums = [], [], [0.0]

    def add(self, day, value):
        if self.days and day <= self.days[-1]:
            raise ValueError("Serie con fechas duplicadas o desordenadas")
        self.days.append(day)
        self.values.append(value)
        self.sums.append(self.sums[-1] + value)

    def context(self, day):
        stop = bisect_left(self.days, day)
        if not stop:
            return None
        first28 = bisect_left(self.days, day - 28, 0, stop)
        first7 = bisect_left(self.days, day - 7, 0, stop)
        scale = max(1.0, (self.sums[stop] - self.sums[first28]) / (stop - first28)) if stop > first28 else max(1.0, self.values[stop - 1])
        recent = (self.sums[stop] - self.sums[first7]) / (stop - first7) if stop > first7 else scale
        def lag(offset):
            index = bisect_left(self.days, day - offset, 0, stop)
            return self.values[index] if index < stop and self.days[index] == day - offset else scale
        weekday = [self.values[index] for index in range(max(0, stop - 56), stop) if (day - self.days[index]) % 7 == 0 and day - self.days[index] <= 56]
        same = fmean(weekday) if weekday else scale
        return scale, recent, lag(1), lag(7), same, day - self.days[stop - 1], stop - first7


class FeatureIndex:
    def __init__(self, rows=()):
        self.series = defaultdict(Series)
        for row in sorted(rows, key=lambda item: (item.fecha, item.tienda_id, item.familia_id)):
            self.add(row)

    def add(self, row):
        self.series[row.tienda_id, row.familia_id].add(row.fecha.toordinal(), row.ventas)

    def features(self, sid, family, day, promotions, sources):
        context = self.series[sid, family].context(day.toordinal())
        if context is None:
            raise ValueError("No hay observaciones anteriores disponibles para la serie")
        scale, recent, lag1, lag7, weekday, gap, count7 = context
        values = [1.0, recent / scale, lag1 / scale, lag7 / scale, weekday / scale,
                  math.log1p(promotions) if promotions is not None else 0.0, float(promotions is None),
                  math.sin(2 * math.pi * day.timetuple().tm_yday / 365.25),
                  math.cos(2 * math.pi * day.timetuple().tm_yday / 365.25), min(gap, 60) / 60, count7 / 7]
        values += [float(day.weekday() == weekday_number) for weekday_number in range(1, 7)]
        values += sources.event_features(sid, day)
        return values, scale, weekday


def solve(matrix, target):
    size = len(target)
    work = [list(row) + [value] for row, value in zip(matrix, target)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(work[index][column]))
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("Sistema de regresión singular")
        work[column] = [value / divisor for value in work[column]]
        for row in range(size):
            if row != column:
                factor = work[row][column]
                work[row] = [a - factor * b for a, b in zip(work[row], work[column])]
    return [row[-1] for row in work]


def expected(artifact, index, sid, family, day, promotions, sources):
    x, scale, baseline = index.features(sid, family, day, promotions, sources)
    if artifact["algorithm"] == "baseline":
        result = baseline
    else:
        result = scale * sum(a * b for a, b in zip(artifact["coefficients"][family], x))
    return max(0.0, result), scale


def predict(artifact, index, sid, family, day, promotions, sources):
    assert_model_available(date.fromisoformat(artifact["trained_through"]), day)
    mean, scale = expected(artifact, index, sid, family, day, promotions, sources)
    samples = [max(0.0, mean + scale * residual) for residual in artifact["residuals"][family]]
    quantity = suggested_quantity(samples, *sources.costs[family])
    return {"familia_id": family, "venta_esperada": round(mean, 4), "cantidad_sugerida": quantity}


def fit(rows, sources, algorithm, deadline=None):
    """Últimos 28 días para calibración; sus ventas nunca ajustan los coeficientes."""
    rows = sorted(rows, key=lambda row: (row.fecha, row.tienda_id, row.familia_id))
    days = sorted({row.fecha for row in rows})
    if len(days) < 60:
        raise ValueError("Se requieren al menos 60 días para ajuste y calibración temporal")
    calibration_start = days[-28]
    index = FeatureIndex()
    sufficient = {}
    for row in rows:
        if deadline and time.monotonic() > deadline:
            raise TimeoutError("Presupuesto de entrenamiento agotado")
        if row.fecha >= calibration_start:
            break
        series = index.series[row.tienda_id, row.familia_id]
        if len(series.days) >= 14 and algorithm == "ridge":
            x, scale, _ = index.features(row.tienda_id, row.familia_id, row.fecha, row.en_promocion, sources)
            if row.familia_id not in sufficient:
                sufficient[row.familia_id] = ([[0.0] * len(x) for _ in x], [0.0] * len(x))
            matrix, target = sufficient[row.familia_id]
            nonzero = [(i, value) for i, value in enumerate(x) if value]
            y = row.ventas / scale
            for i, a in nonzero:
                target[i] += a * y
                for j, b in nonzero:
                    matrix[i][j] += a * b
        index.add(row)
    artifact = {"format": 1, "algorithm": algorithm, "trained_through": days[-1].isoformat(),
                "fit_before": calibration_start.isoformat(), "coefficients": {}, "residuals": {}, "source_hashes": sources.hashes}
    if algorithm == "ridge":
        for family in sources.families:
            matrix, target = sufficient[family]
            for i in range(len(target)):
                matrix[i][i] += 0.01 if i else 0.000001
            artifact["coefficients"][family] = solve(matrix, target)
    residuals = defaultdict(list)
    for row in rows:
        if row.fecha < calibration_start:
            continue
        value, scale = expected(artifact, index, row.tienda_id, row.familia_id, row.fecha, row.en_promocion, sources)
        residuals[row.familia_id].append((row.ventas - value) / scale)
        index.add(row)
    for family in sources.families:
        values = residuals[family]
        # Muestreo determinista de calibración anterior al corte; no usa validación externa.
        stride = max(1, math.ceil(len(values) / 500))
        artifact["residuals"][family] = values[::stride]
    return artifact


def evaluate(artifact, rows, validation_start, sources):
    if date.fromisoformat(artifact["trained_through"]) >= validation_start:
        raise TemporalLeakageError("El artefacto ya vio etiquetas del bloque de validación")
    index = FeatureIndex()
    actual, forecasts = [], []
    total = 0.0
    family_cost = defaultdict(float)
    for row in sorted(rows, key=lambda item: (item.fecha, item.tienda_id, item.familia_id)):
        if row.fecha >= validation_start:
            result = predict(artifact, index, row.tienda_id, row.familia_id, row.fecha, row.en_promocion, sources)
            value = business_cost(row.ventas, result["cantidad_sugerida"], *sources.costs[row.familia_id])
            total += value
            family_cost[row.familia_id] += value
            actual.append(row.ventas)
            forecasts.append(result["venta_esperada"])
        index.add(row)
    return {**technical_metrics(actual, forecasts), "business_cost": total, "records": len(actual), "family_cost": dict(family_cost)}


def promotion_decision(candidate, incumbent, min_improvement=0.01):
    improves = candidate["business_cost"] <= incumbent["business_cost"] * (1 - min_improvement)
    technical = candidate["mae"] <= incumbent["mae"] * 1.05
    return improves and technical


def train_and_compare(rows, sources, incumbent=None):
    start = time.monotonic()
    deadline = start + 480
    rows = sorted(rows, key=lambda row: (row.fecha, row.tienda_id, row.familia_id))
    days = sorted({row.fecha for row in rows})
    if incumbent:
        new_days = [day for day in days if day > date.fromisoformat(incumbent["trained_through"])]
        if len(new_days) < 7:
            return {"promoted": False, "reason": "Se requieren al menos siete días nuevos para comparar sin fuga temporal", "candidate": None, "evaluations": {}}
        validation_start = new_days[-min(28, len(new_days))]
    else:
        validation_start = days[-56]
    training = [row for row in rows if row.fecha < validation_start]
    baseline = fit(training, sources, "baseline", deadline)
    candidate = fit(training, sources, "ridge", deadline)
    reference = incumbent or baseline
    candidate_metrics = evaluate(candidate, rows, validation_start, sources)
    reference_metrics = evaluate(reference, rows, validation_start, sources)
    evaluations = {"ridge": candidate_metrics, "incumbent" if incumbent else "baseline": reference_metrics}
    promoted = promotion_decision(candidate_metrics, reference_metrics)
    chosen = "ridge" if promoted or incumbent else "baseline"
    final = fit(rows, sources, chosen, deadline)
    if time.monotonic() > deadline:
        raise TimeoutError("Entrenamiento excedió ocho minutos; el vigente se conserva")
    return {"promoted": promoted, "candidate": final, "validation_artifacts": {"baseline": baseline, "ridge": candidate}, "evaluations": evaluations, "validation_start": validation_start.isoformat(),
            "elapsed_seconds": time.monotonic() - start,
            "reason": f"Costo candidato {candidate_metrics['business_cost']:.2f} frente a referencia {reference_metrics['business_cost']:.2f}; mejora mínima 1%, MAE sin deterioro >5%"}
