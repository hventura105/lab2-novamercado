from contextlib import asynccontextmanager
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.contrato import ModelOutput, ObservationInput, ObservationOutput, PredictionInput, PredictionOutput, RunOutput, RunStarted
from app.services.runtime import Runtime, Unavailable


def create_app(runtime=None, background=True):
    runtime = runtime or Runtime()

    @asynccontextmanager
    async def lifespan(app):
        if background:
            runtime.start()
        yield
        runtime.close()

    app = FastAPI(title="NovaMercado · Pronóstico diario", version="1.0.0", lifespan=lifespan)
    app.state.runtime = runtime

    @app.exception_handler(Unavailable)
    async def unavailable(request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        # Los errores del driver o integraciones no se devuelven con SQL, filas o secretos.
        return JSONResponse(status_code=503, content={"detail": "Una dependencia necesaria no está disponible; la operación no se confirmó"})

    @app.exception_handler(RequestValidationError)
    async def invalid_structure(request, error):
        detail = [{"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        try:
            runtime.repository.rejection(request.url.path, error.body, "Validación estructural Pydantic")
        except Exception:
            pass
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.get("/")
    def root():
        return {"service": "novamercado-api", "version": "1.0.0"}

    @app.get("/health")
    def health():
        body, status = runtime.health()
        return JSONResponse(content=body, status_code=status)

    @app.get("/ready", include_in_schema=False)
    def ready():
        return health()

    @app.get("/modelo", response_model=ModelOutput)
    def model():
        return runtime.model()

    @app.post("/v1/prediccion", response_model=PredictionOutput)
    def prediction(body: PredictionInput):
        return runtime.prediction(body.model_dump(exclude_unset=True))

    @app.post("/v1/observaciones", response_model=ObservationOutput)
    def observe(body: ObservationInput):
        return runtime.observe(body.model_dump(exclude_unset=True))

    @app.post("/admin/reentrenar", status_code=202, response_model=RunStarted)
    async def retrain(request: Request):
        if await request.body():
            raise HTTPException(422, "Este endpoint no recibe cuerpo")
        # La llamada HTTP es corta; se ejecuta en un hilo para no bloquear el event loop.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(runtime.trigger)

    @app.get("/admin/reentrenar/{identifier}", response_model=RunOutput, response_model_exclude_none=True)
    def status(identifier: str):
        result = runtime.run_status(identifier)
        if result is None:
            raise HTTPException(404, "Identificador de ejecución desconocido")
        return result

    @app.post("/internal/reentrenar/{identifier}", include_in_schema=False)
    def execute_training(identifier: str, x_internal_token: str = Header(default="")):
        expected_token = os.environ.get("INTERNAL_API_TOKEN", "")
        if not expected_token or not hmac.compare_digest(x_internal_token, expected_token):
            raise HTTPException(403, "Acceso interno no autorizado")
        result = runtime.retrain(identifier)
        if result is None:
            raise HTTPException(404, "Identificador de ejecución desconocido")
        if result["estado"] == "fallido":
            raise HTTPException(503, "Reentrenamiento fallido; revisar su estado")
        return result

    return app


app = create_app()
