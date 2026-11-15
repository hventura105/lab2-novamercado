"""Modelo en memoria y respaldo JSONB persistente; MLflow no está en la ruta de inferencia."""

from datetime import date
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4
from urllib.error import HTTPError

from app.services.ciclo import training_cycle
from app.services.fuentes import Sources
from app.services.integraciones import Airflow, Tracking
from app.services.limpieza import clean_request
from app.services.modelado import FeatureIndex, predict
from app.services.repositorio import Repository

logger = logging.getLogger(__name__)


class Unavailable(RuntimeError):
    pass


class Runtime:
    def __init__(self, repository=None, tracking=None, airflow=None, sources=None):
        self.repository = repository or Repository()
        self.tracking = tracking or Tracking()
        self.airflow = airflow or Airflow()
        self.sources = sources
        self.loaded = None
        self.initialized = False
        self.stop_event = threading.Event()
        self.worker = None

    def start(self):
        self.worker = threading.Thread(target=self._background, daemon=True, name="novamercado-bootstrap-refresh")
        self.worker.start()

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=3)

    def refresh(self):
        active = self.repository.active()
        if active:
            self.loaded = active
        return active

    def reconcile_alias(self):
        try:
            version = self.tracking.alias_version()
        except HTTPError as error:
            if error.code != 404:
                raise
            version = None
        if self.loaded and version != str(self.loaded["version"]):
            # La fila activa confirmada es la autoridad tras un cierre entre dos sistemas.
            # El mismo lock evita interferir con una promoción que sigue en curso.
            with self.repository.training_lock():
                active = self.repository.active()
                if active:
                    self.tracking.set_alias(active["version"])

    def _background(self):
        while not self.stop_event.is_set():
            try:
                if not self.initialized:
                    self.sources = self.sources or Sources(Path(os.environ.get("DATA_DIRECTORY", "/data/entrada")))
                    self.repository.initialize(self.sources)
                    self.initialized = True
                if not self.refresh():
                    self.loaded = training_cycle(self.repository, self.tracking, self.sources)
                if self.loaded:
                    self.repository.expire_runs(self.loaded["version"])
                    self.reconcile_alias()
            except Exception as error:
                # Nunca imprimir DSN, tokens o cuerpos de solicitudes.
                logger.warning("Inicialización/actualización pendiente (%s)", type(error).__name__)
            self.stop_event.wait(20)

    def health(self):
        if not self.loaded:
            return {"estado": "sin_modelo", "motivo": "Todavía no existe un modelo cargado"}, 503
        unavailable = []
        def tracking_health():
            self.tracking.health()
            if self.tracking.alias_version() != str(self.loaded["version"]):
                raise RuntimeError("El alias no coincide con la versión cargada")

        for name, probe in (("PostgreSQL", self.repository.ping), ("MLflow", tracking_health), ("Airflow", self.airflow.health)):
            try:
                probe()
            except Exception:
                unavailable.append(name)
        if unavailable:
            return {"estado": "degradado", "motivo": "Dependencias no disponibles: " + ", ".join(unavailable)}, 200
        return {"estado": "ok"}, 200

    def model(self):
        active = self.loaded
        if not active:
            raise Unavailable("Todavía no existe un modelo cargado")
        return {"nombre": self.tracking.name, "alias": self.tracking.alias, "version": str(active["version"])}

    def clean(self, raw, kind):
        if not self.sources or not self.initialized:
            raise Unavailable("Las fuentes y la base del producto todavía no están preparadas")
        try:
            return clean_request(raw, self.sources, kind)
        except ValueError as error:
            self.repository.rejection(kind, raw, str(error))
            raise

    def prediction(self, raw):
        clean, quality = self.clean(raw, "prediccion")
        active = self.loaded
        if not active:
            raise Unavailable("Todavía no existe un modelo cargado")
        day = date.fromisoformat(clean["fecha"])
        if date.fromisoformat(active["artifact"]["trained_through"]) >= day:
            # Repetir una fecha anterior sigue permitido después de reentrenar,
            # usando únicamente una versión previamente promovida y temporalmente válida.
            active = self.repository.model_before(day)
            if active is None:
                raise ValueError("No existe un modelo compatible con esta fecha sin utilizar información futura")
        index = FeatureIndex(self.repository.sales())
        result = []
        for row in clean["familias"]:
            context = index.series[clean["tienda_id"], row["familia_id"]].context(day.toordinal())
            if context and context[5] > 1:
                quality["observaciones"].append({"campo": "fecha", "accion": "advertir", "detalle": "Faltan observaciones recientes; se usan únicamente días anteriores disponibles sin rellenar ventas"})
                quality["estado"] = "advertencia"
            result.append(predict(active["artifact"], index, clean["tienda_id"], row["familia_id"], day, row["en_promocion"], self.sources))
        response = {"tienda_id": clean["tienda_id"], "fecha": clean["fecha"], "version_modelo": str(active["version"]), "predicciones": result, "calidad": quality}
        self.repository.prediction(raw, clean, response)
        return response

    def observe(self, raw):
        clean, quality = self.clean(raw, "observaciones")
        return {"registros_guardados": self.repository.observe(raw, clean, quality), "calidad": quality}

    def trigger(self):
        model = self.model()
        identifier = "manual__" + str(uuid4())
        try:
            self.repository.create_run(identifier)
        except Exception:
            raise Unavailable("No se puede reservar otra ejecución; revisar disponibilidad y ejecución en curso") from None
        try:
            self.airflow.trigger(identifier)
        except Exception:
            self.repository.finish_run(identifier, False, False, model["version"], "Airflow no pudo iniciar la ejecución")
            raise Unavailable("Airflow no pudo iniciar el DAG") from None
        return {"id": identifier}

    def run_status(self, identifier):
        result = self.repository.get_run(identifier)
        if result and result["estado"] == "en_curso":
            try:
                state = self.airflow.state(identifier)
            except Exception:
                return result
            if state in ("failed", "success"):
                # Un DAG exitoso tiene que haber dejado un resultado; si no, es un fallo de protocolo.
                self.repository.finish_run(identifier, False, False, self.model()["version"], "DAG terminó sin completar el protocolo del producto")
                result = self.repository.get_run(identifier)
        return result

    def retrain(self, identifier):
        status = self.repository.get_run(identifier)
        if status is None:
            return None
        if status["estado"] != "en_curso":
            return status
        try:
            active = training_cycle(self.repository, self.tracking, self.sources, identifier)
            self.loaded = active  # Sin esperar al siguiente ciclo del refresco periódico.
        except Exception as error:
            self.repository.finish_run(identifier, False, False, self.model()["version"], "Entrenamiento falló; se conserva el vigente (" + type(error).__name__ + ")")
            raise Unavailable("Entrenamiento fallido; se conserva el modelo vigente") from None
        return self.repository.get_run(identifier)
