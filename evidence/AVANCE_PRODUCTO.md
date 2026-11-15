# Evidencia de avance del producto

Fecha UTC de cierre: 2026-11-14T23:26:59.350331+00:00.

## Fuentes y simulación

18 fuentes de datos/catálogo/ejemplos idénticas a Windows por tamaño y SHA-256. Histórico: 83 052 registros, 2024-03-01–2026-02-28; 10 tiendas, 12 familias/costos. Calendario: 61 eventos hasta 2026-12-31. No hay nulos, duplicados, negativos, referencias inválidas o huecos tras apertura. Las 4 548 ausencias previas a apertura de tienda 10 no se rellenan. Ver docs/DATOS.md.

## Evaluación real local

Bloque de validación 2026-01-04–2026-02-28, 6720 observaciones, con ajuste/calibración anteriores al bloque. Predicciones diarias incorporan solo observaciones de días anteriores.

| Modelo | MAE | RMSE | Costo total |
| --- | ---: | ---: | ---: |
| Baseline semanal | 53.647359 | 95.589600 | 296985.30 |
| Ridge | 45.296511 | 83.034639 | 220691.70 |

Reducción del costo: 25.6894%. Segunda ejecución: 9.4976 s. SHA-256 de modelado.py: `ec40859412545437578118d47f4cb2eda88381b178723fed770e13966480f4d7`. Métricas completas, hashes de fuentes y modelo serializado están en evidence/private/, excluido de Git. El indicador promoted del JSON local significa que supera la regla matemática en este bloque; NO implica alias ni promoción de producción.

## Comprobaciones de código

- `python3 -m unittest discover -s tests -q`: 74 pruebas aprobadas con dobles/fixtures y lectura de fuentes reales donde corresponde. Incluyen limpieza, idempotencia transaccional simulada, fuga temporal, uso de archivo promovido al repetir fecha, costo, promoción/rechazo, fallos de MLflow/Airflow y refresco de versión.
- `docker compose config --quiet`: válido. Inspección estática: nueve servicios, cinco volúmenes, red privada, API 8000 y datos montados en solo lectura.
- AST de los 36 archivos Python: válido. Se detectó un corchete faltante en el archivo de pruebas integrales durante revisión y se corrigió antes del cierre.
- Hashes de las 18 fuentes y copias comprobados otra vez, sin modificar originales.
- Revisión de valores reales de contraseñas/tokens/Fernet de .env en archivos publicables: sin coincidencias; valores nunca impresos.

## No ejecutado y límites

Docker devuelve permiso denegado en /var/run/docker.sock. PyPI no resuelve DNS y FastAPI/Pydantic/pytest no están disponibles. Por ello NO se ejecutaron diez tests ASGI ni cinco integrales, no se aplicó SQL en PostgreSQL real, no se registró este modelo en MLflow ni se disparó este DAG. No hay medidas reales de arranque/DAG/caída/recuperación o recarga Docker. Git no es un repositorio utilizable: no hubo commits, push ni tag.

El código completo de integración está preparado; el producto no se declara operativo hasta verificarlo. Las cinco pruebas integrales escriben sus evidencias únicamente tras comprobación real, en evidence/private/integration/.
