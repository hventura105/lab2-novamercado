"""Defensa semántica independiente de FastAPI/Pydantic; sin inferencias ambiguas."""

from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
import unicodedata


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    return re.sub(r"[\W_]+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


class Quality:
    def __init__(self):
        self.notes = []

    def add(self, field, detail, action="reparar"):
        self.notes.append({"campo": field, "accion": action, "detalle": detail})

    def result(self):
        status = "advertencia" if any(note["accion"] == "advertir" for note in self.notes) else "corregido" if self.notes else "ok"
        return {"estado": status, "observaciones": self.notes}


def number(value, field, quality, integer=False):
    if value is None or isinstance(value, bool) or not isinstance(value, (str, float, int)):
        raise ValueError(f"{field}: se requiere un número")
    original = value
    if isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"\d{1,3}(?:,\d{3}){2,}", value):
            value = value.replace(",", "")
        elif "," in value:
            if re.fullmatch(r"\d+,\d{1,2}", value):
                value = value.replace(",", ".")
            else:
                raise ValueError(f"{field}: separadores ambiguos; enviar un número JSON o decimal con punto")
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
            raise ValueError(f"{field}: formato numérico no admitido")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field}: número inválido") from None
    if not parsed.is_finite() or parsed < 0 or parsed > Decimal("1e12"):
        raise ValueError(f"{field}: valor fuera del intervalo finito permitido [0, 10^12]")
    if integer and parsed != parsed.to_integral_value():
        raise ValueError(f"{field}: no se redondean cantidades fraccionarias")
    result = int(parsed) if integer else float(parsed)
    if isinstance(original, str) or (integer and type(original) is not int):
        quality.add(field, "Representación numérica convertida de manera inequívoca")
    return result


def clean_date(value, quality):
    if not isinstance(value, str):
        raise ValueError("fecha: se requiere una cadena de fecha")
    raw = value.strip()
    result = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            result = date.fromisoformat(raw)
        except ValueError:
            pass
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]00:00:00(?:\.0+)?(?:Z|\+00:00)?", raw):
        try:
            result = date.fromisoformat(raw[:10])
        except ValueError:
            pass
    elif match := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw):
        left, right, year = map(int, match.groups())
        if left <= 12 and right <= 12 and left != right:
            raise ValueError("fecha: día/mes ambiguos; usar AAAA-MM-DD")
        try:
            result = date(year, right, left) if left > 12 or left == right else date(year, left, right)
        except ValueError:
            pass
    if result is None:
        raise ValueError("fecha: fecha inválida o formato no admitido; usar AAAA-MM-DD")
    if result.isoformat() != value:
        quality.add("fecha", "Fecha convertida a AAAA-MM-DD sin cambiar de día")
    return result


def clean_request(payload, sources, kind):
    quality = Quality()
    payload = dict(payload)
    if "tienda" in payload:
        if "tienda_id" in payload:
            def store_value(value):
                if isinstance(value, str) and re.fullmatch(r"[Tt]\d+", value.strip()):
                    value = value.strip()[1:]
                return number(value, "tienda_id", Quality(), integer=True)
            if store_value(payload["tienda_id"]) != store_value(payload["tienda"]):
                raise ValueError("tienda y tienda_id son contradictorios")
        payload["tienda_id"] = payload.pop("tienda")
        quality.add("tienda_id", "Campo tienda interpretado como tienda_id")
    store = payload.get("tienda_id")
    if isinstance(store, str) and re.fullmatch(r"[Tt]\d+", store.strip()):
        store = store.strip()[1:]
        quality.add("tienda_id", "Se eliminó el prefijo de identificador de tienda")
    store = number(store, "tienda_id", quality, integer=True)
    if store not in sources.stores:
        raise ValueError("tienda_id: tienda desconocida")
    day = clean_date(payload.get("fecha"), quality)
    if day < date.fromisoformat(sources.stores[store]["fecha_apertura"]):
        raise ValueError("fecha: anterior a la apertura de la tienda")
    if not sources.history_start <= day <= sources.calendar_end:
        raise ValueError("fecha: fuera del rango de fuentes oficiales y calendario conocido")
    if kind == "prediccion" and day <= sources.history_end:
        raise ValueError("fecha: el pronóstico debe ser posterior al histórico oficial")
    key = "familias" if kind == "prediccion" else "ventas"
    value_key = "en_promocion" if kind == "prediccion" else "ventas"
    allowed = {"tienda_id", "fecha", key}
    if set(payload) - allowed:
        raise ValueError("Hay campos desconocidos fuera del contrato")
    items = payload.get(key)
    if not isinstance(items, list) or not items or len(items) > 1000:
        raise ValueError(f"{key}: se requiere una lista no vacía de hasta 1000 elementos")
    aliases = {}
    for fid, name in sources.families.items():
        for alias in (fid, name):
            aliases.setdefault(normalized(alias), set()).add(fid)
    result = {}
    for index, item in enumerate(items):
        field = f"{key}[{index}]"
        if not isinstance(item, dict) or set(item) != {"familia_id", value_key}:
            raise ValueError(f"{field}: campos obligatorios familia_id y {value_key}")
        raw_family = item["familia_id"]
        if not isinstance(raw_family, str):
            raise ValueError(f"{field}.familia_id: se requiere texto")
        matches = aliases.get(normalized(raw_family), set())
        if len(matches) != 1:
            raise ValueError(f"{field}.familia_id: familia desconocida o ambigua")
        family = next(iter(matches))
        if raw_family != family:
            quality.add(field + ".familia_id", "Familia normalizada contra el catálogo oficial")
        value = number(item[value_key], field + "." + value_key, quality, integer=kind == "prediccion")
        if family in result:
            if result[family] != value:
                raise ValueError(f"{field}: familia duplicada con valores contradictorios")
            quality.add(field, "Duplicado idéntico consolidado en un registro")
        result[family] = value
    missing = set(sources.families) - set(result)
    if missing:
        quality.add(key, "Solicitud parcial: se procesan solo las familias recibidas; no se inventan promociones ni ventas de las ausentes", "advertir")
    return {"tienda_id": store, "fecha": day.isoformat(), key: [{"familia_id": family, value_key: value} for family, value in result.items()]}, quality.result()
