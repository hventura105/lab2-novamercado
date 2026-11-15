# Integración: resultado de esta sesión

## Verificación aportada por el usuario

Ubuntu accede a FastAPI8000, MLflow5000 y Airflow8080. /health respondió200 estado ok y /modelo200 con novamercado_ventas_diarias, champion, versión textual1. No se reabrió ni modificó la reparación de puertos.

## Ejecutado por Codex

- 106 pruebas locales unittest aprobadas, incluidas20 nuevas de seguridad/aislamiento/reporte del ejecutor.
- Sintaxis AST válida en42 archivos Python y docker compose config --quiet correcto.
- Replay numérico con ventas oficiales: conserva vigente al2025-12-06; al2026-01-03 candidato cuesta137703.60 frente a151281.60, cumpliendo criterio. No hubo SQL/MLflow/HTTP de ese replay local. Ver REPLAY_LOCAL_VALIDACION.md.
- Intento real del runner: preflight bloqueado por acceso denegado al daemon. Informe privado en evidence/private/integration/20261115T001525Z-c56a5659/informe.json. Cero integrales aprobadas en ese intento; posteriores pendientes.
- Curl /health,/modelo bloqueados por sockets. pytest no instalado en host. Git no es repositorio utilizable; no commits, push o tag.

## Preparado para Ubuntu

Ejecutor stdlib scripts/pruebas_integrales.py, inspección SQL de solo lectura, replay aislado con PostgreSQL/MLflow/FastAPI reales, siete wrappers pytest, informes atómicos y hashes del ejecutor/helpers. No requiere reconstruir imágenes ni instalar paquetes en el host. Ver docs/PRUEBAS_INTEGRALES.md.

```bash
cd /home/gama/product-dev/lab2-novamercado
python3 scripts/pruebas_integrales.py --con-interrupciones --replay-promocion
```

El flag de interrupciones detiene/inicia solo MLflow y reinicia los ocho servicios propios, conservando IDs/volúmenes/datos. El replay crea esquema/modelo propios y conserva evidencias sin tocar champion/tablas productivos.

Quedan pendientes las ejecuciones reales desde Ubuntu, la trayectoria de promoción productiva con nuevas ventas legítimas y la medición de arranque Docker inicial vacío. No declarar cierre académico ni crear entrega-lab2 hasta verificarlos. El código2 del runner indica pendientes, no éxito total ni pérdida de datos.
