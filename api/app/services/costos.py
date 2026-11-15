"""Métrica oficial y decisión de inventario por cuantil empírico, sin datos inventados."""

import math


def finite_nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} debe ser numérico, finito y no negativo")
    return float(value)


def costs(cfaltante, csobrante):
    missing = finite_nonnegative(cfaltante, "cfaltante")
    surplus = finite_nonnegative(csobrante, "csobrante")
    if missing + surplus == 0:
        raise ValueError("Al menos uno de los costos oficiales debe ser positivo")
    return missing, surplus


def business_cost(real, sugerido, cfaltante, csobrante):
    real = finite_nonnegative(real, "real")
    if type(sugerido) is not int or sugerido < 0:
        raise ValueError("cantidad_sugerida debe ser entero no negativo")
    missing, surplus = costs(cfaltante, csobrante)
    return missing * max(real - sugerido, 0) + surplus * max(sugerido - real, 0)


def suggested_quantity(demand_samples, cfaltante, csobrante):
    """Minimiza costo empírico en enteros usando el cuantil cf/(cf+cs).

    La distribución debe provenir exclusivamente del entrenamiento disponible.
    No se construye ni se completa una distribución cuando faltan observaciones.
    """
    missing, surplus = costs(cfaltante, csobrante)
    values = sorted(finite_nonnegative(value, "demanda") for value in demand_samples)
    if not values:
        raise ValueError("No hay observaciones disponibles para decidir una cantidad")
    quantile = missing / (missing + surplus)
    boundary = values[max(0, math.ceil(quantile * len(values)) - 1)]
    candidates = {0, math.floor(boundary), math.ceil(boundary)}
    # En empates se elige el menor inventario; nunca hay cantidades negativas.
    return min(candidates, key=lambda quantity: (sum(business_cost(value, quantity, missing, surplus) for value in values), quantity))


def technical_metrics(actual, predicted):
    actual, predicted = list(actual), list(predicted)
    if not actual or len(actual) != len(predicted):
        raise ValueError("Las series de evaluación deben tener igual longitud y no estar vacías")
    errors = [finite_nonnegative(prediction, "predicción") - finite_nonnegative(real, "real") for real, prediction in zip(actual, predicted)]
    return {"mae": sum(abs(error) for error in errors) / len(errors),
            "rmse": math.sqrt(sum(error ** 2 for error in errors) / len(errors))}
