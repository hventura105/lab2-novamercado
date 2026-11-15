-- Migración aditiva. No borra, trunca ni transforma tablas existentes.
CREATE SCHEMA IF NOT EXISTS novamercado;
CREATE TABLE IF NOT EXISTS novamercado.migraciones (
  version TEXT PRIMARY KEY, sha256 TEXT NOT NULL, aplicada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS novamercado.fuentes (
  archivo TEXT PRIMARY KEY, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS novamercado.tiendas (
  tienda_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, ciudad TEXT NOT NULL,
  departamento TEXT NOT NULL, tipo TEXT NOT NULL, fecha_apertura DATE NOT NULL
);
CREATE TABLE IF NOT EXISTS novamercado.familias (
  familia_id TEXT PRIMARY KEY, nombre TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS novamercado.costos (
  familia_id TEXT PRIMARY KEY REFERENCES novamercado.familias,
  costo_faltante DOUBLE PRECISION NOT NULL CHECK (costo_faltante > 0),
  costo_sobrante DOUBLE PRECISION NOT NULL CHECK (costo_sobrante > 0)
);
CREATE TABLE IF NOT EXISTS novamercado.feriados (
  fecha DATE NOT NULL, nombre TEXT NOT NULL, tipo TEXT NOT NULL, ambito TEXT NOT NULL,
  PRIMARY KEY (fecha, nombre, tipo, ambito)
);
CREATE TABLE IF NOT EXISTS novamercado.historico (
  tienda_id INTEGER NOT NULL REFERENCES novamercado.tiendas,
  familia_id TEXT NOT NULL REFERENCES novamercado.familias,
  fecha DATE NOT NULL, ventas DOUBLE PRECISION NOT NULL CHECK (ventas >= 0),
  en_promocion BIGINT NOT NULL CHECK (en_promocion >= 0),
  PRIMARY KEY (tienda_id, familia_id, fecha)
);
CREATE TABLE IF NOT EXISTS novamercado.solicitudes (
  id TEXT PRIMARY KEY, tipo TEXT NOT NULL, recibida_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  entrada JSONB NOT NULL, normalizada JSONB, calidad JSONB, codigo_http INTEGER NOT NULL, detalle TEXT
);
CREATE TABLE IF NOT EXISTS novamercado.modelos (
  version TEXT PRIMARY KEY, nombre TEXT NOT NULL, run_id TEXT NOT NULL,
  entrenado_hasta DATE NOT NULL, artefacto JSONB NOT NULL, metricas JSONB NOT NULL,
  creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS novamercado.modelo_activo (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  version TEXT NOT NULL REFERENCES novamercado.modelos,
  alias TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS novamercado.promociones (
  version TEXT PRIMARY KEY REFERENCES novamercado.modelos,
  activada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS novamercado.predicciones (
  solicitud_id TEXT NOT NULL REFERENCES novamercado.solicitudes,
  tienda_id INTEGER NOT NULL REFERENCES novamercado.tiendas,
  fecha DATE NOT NULL, familia_id TEXT NOT NULL REFERENCES novamercado.familias,
  version_modelo TEXT NOT NULL REFERENCES novamercado.modelos,
  venta_esperada DOUBLE PRECISION NOT NULL CHECK (venta_esperada >= 0),
  cantidad_sugerida BIGINT NOT NULL CHECK (cantidad_sugerida >= 0),
  en_promocion BIGINT NOT NULL CHECK (en_promocion >= 0),
  PRIMARY KEY (solicitud_id, familia_id)
);
CREATE TABLE IF NOT EXISTS novamercado.observaciones (
  tienda_id INTEGER NOT NULL REFERENCES novamercado.tiendas,
  fecha DATE NOT NULL, familia_id TEXT NOT NULL REFERENCES novamercado.familias,
  ventas DOUBLE PRECISION NOT NULL CHECK (ventas >= 0),
  solicitud_id TEXT NOT NULL REFERENCES novamercado.solicitudes,
  PRIMARY KEY (tienda_id, familia_id, fecha)
);
CREATE TABLE IF NOT EXISTS novamercado.reentrenamientos (
  id TEXT PRIMARY KEY, estado TEXT NOT NULL CHECK (estado IN ('en_curso','exitoso','fallido')),
  promovido BOOLEAN, version TEXT, motivo TEXT, airflow_run_id TEXT NOT NULL,
  creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  terminado_en TIMESTAMPTZ,
  CHECK (estado = 'en_curso' OR (promovido IS NOT NULL AND version IS NOT NULL AND motivo IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS un_reentrenamiento_activo
  ON novamercado.reentrenamientos ((estado)) WHERE estado = 'en_curso';
CREATE INDEX IF NOT EXISTS observaciones_fecha ON novamercado.observaciones (fecha);
CREATE INDEX IF NOT EXISTS predicciones_tienda_fecha ON novamercado.predicciones (tienda_id,fecha);
