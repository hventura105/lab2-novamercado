from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FamilyInput(StrictModel):
    familia_id: Any
    en_promocion: Any


class SaleInput(StrictModel):
    familia_id: Any
    ventas: Any


class StoreInput(StrictModel):
    tienda_id: Any = None
    tienda: Any = None  # Alias reparable; las contradicciones se comprueban en limpieza.
    fecha: Any


class PredictionInput(StoreInput):
    familias: list[FamilyInput] = Field(min_length=1, max_length=1000)


class ObservationInput(StoreInput):
    ventas: list[SaleInput] = Field(min_length=1, max_length=1000)


class Note(StrictModel):
    campo: str
    accion: Literal["reparar", "advertir"]
    detalle: str


class Quality(StrictModel):
    estado: Literal["ok", "corregido", "advertencia"]
    observaciones: list[Note]


class Forecast(StrictModel):
    familia_id: str
    venta_esperada: float = Field(ge=0, allow_inf_nan=False)
    cantidad_sugerida: int = Field(ge=0, strict=True)


class PredictionOutput(StrictModel):
    tienda_id: int
    fecha: str
    version_modelo: str
    predicciones: list[Forecast]
    calidad: Quality


class ObservationOutput(StrictModel):
    registros_guardados: int = Field(ge=0)
    calidad: Quality


class ModelOutput(StrictModel):
    nombre: str
    alias: str
    version: str


class RunStarted(StrictModel):
    id: str


class RunOutput(StrictModel):
    estado: Literal["en_curso", "exitoso", "fallido"]
    promovido: bool | None = None
    version: str | None = None
    motivo: str | None = None
