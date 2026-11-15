# Diagnóstico y recuperación del contrato ASGI

**Actualización de cierre:** corregido y aprobado desde Ubuntu: `evidence/private/integration/20261115T005651Z-8d163828/informe.json`, diez ejecutadas, cero fallos/errores/omitidas. El resto de este documento conserva el diagnóstico histórico; no repetir comparación ni seguir sus pendientes anteriores. Continuar desde docs/progreso/ESTADO_ACTUAL.md.

## Evidencia de partida

El informe real `evidence/private/integration/20261115T004023Z-f65a37ca/informe.json` contiene ocho casos integrales aprobados, uno fallido y cinco pendientes. `contrato_asgi_en_imagen` ejecutó diez pruebas: cinco fallos, dos errores y ninguna omitida. El informe incluye identificadores, pero no las trazas completas. No se modifica ese informe histórico.

## Causa reproducida antes de corregir

Se conservó el archivo original en `evidence/private/asgi-diagnostico/test_endpoints_antes.py` y se extrajo su función `request` mediante AST. Al ejecutarla contra un consumidor ASGI que realmente espera `receive()`, Python produjo:

```text
File "api/tests/test_endpoints.py", line 23, in receive
NameError: cannot access free variable 'body' where it is not associated with a value in enclosing scope
```

La traza completa está en `evidence/private/asgi-diagnostico/traza-helper-original.txt`. Es una ejecución real del helper original en Python del host, sin FastAPI; no sustituye las siete trazas del contenedor.

Dentro de `invoke()` se asignaba `body` al decodificar la respuesta, después de `await app(...)`. Esa asignación ocultaba el parámetro del cuerpo de solicitud. La función anidada `receive()` capturaba la variable interna todavía no inicializada. Se renombró únicamente la variable de respuesta a `response_body` y su lectura. Las diez pruebas y todas sus aserciones permanecen idénticas según comparación AST.

Los siete casos reportados utilizan ese helper al consumir un POST:

| Caso | Solicitud que atraviesa el helper defectuoso |
| --- | --- |
| `test_observation_idempotent_count` | Observaciones repetidas |
| `test_prediction_contract_and_repeated_requests_are_logged` | Predicciones repetidas |
| `test_repair_and_warning_precedence` | Reparaciones y advertencias |
| `test_structural_and_semantic_rejections_are_422` | Validación estructural y semántica |
| `test_airflow_dispatch_and_failure` | Reentrenamiento sin cuerpo y rechazo de cuerpo no permitido |
| `test_mlflow_outage_and_recovery_do_not_interrupt_predictions` | Predicción durante caída simulada de tracking |
| `test_version_refresh_without_restart` | Predicción después de recargar versión |

La causa común del transporte está comprobada; atribuirle por completo los siete resultados es una hipótesis pendiente de comparación en la imagen. No hay evidencia nueva de defectos en idempotencia PostgreSQL, modelos, mocks o dependencias. No se cambiaron aplicación, mocks, versiones, Compose ni esquemas. Los ocho casos reales aprobados se conservan.

## Ejecución exacta desde Ubuntu

Primero capturar las trazas originales sin sobrescribir el archivo corregido (esta ejecución puede devolver código 1 porque reproduce el defecto):

```bash
cd /home/gama/product-dev/lab2-novamercado
python3 scripts/pruebas_integrales.py --solo-asgi --trazas-asgi --archivo-asgi evidence/private/asgi-diagnostico/test_endpoints_antes.py
```

Después ejecutar las mismas diez pruebas corregidas:

```bash
python3 scripts/pruebas_integrales.py --solo-asgi --trazas-asgi
```

Ambos comandos transmiten los tests y el colector por stdin al proceso Python de `api`, usando las dependencias ya instaladas. No reconstruyen imágenes ni llaman al HTTP/SQL/DAG productivo. Los tests usan sus dobles locales. Este modo rechaza combinarse con interrupciones o replay.

Cada ejecución imprime una ruta propia a `informe.json`; en la misma carpeta privada queda `trazas_asgi.txt`. Revisar `contrato_asgi`: versiones de Python/FastAPI/Pydantic/Starlette/anyio/uvicorn, hash del archivo ejecutado y trazas. La suite corregida solo estará aprobada si ejecuta las diez pruebas con cero fallos, errores y omitidas. El resultado global de `--solo-asgi` no acredita el cierre académico completo.

Si persiste algún fallo, usar su traza concreta para distinguir aplicación, expectativa/mock o dependencia antes de modificar más código. No instalar paquetes ni reconstruir por suposición.

## Verificaciones de esta sesión

- Seis regresiones del transporte/colector aprobadas sin dependencias externas.
- Veintitrés pruebas relacionadas del ejecutor aprobadas: incluyen exclusividad ASGI, rechazo de flags de interrupción/replay y conservación de trazas con redacción de secretos.
- Sintaxis válida de los cinco archivos Python cambiados; clase `EndpointTests` idéntica por AST; dieciséis archivos productivos `api/app` idénticos al snapshot previo.
- Intento real de `--solo-asgi --trazas-asgi`: Docker denegó ejecución, código 1. Informe: `evidence/private/integration/20261115T005003Z-0ad5141b/informe.json`. No se ejecutaron los diez contratos en Codex.
- No se repitió la batería completa de 106 pruebas ni las ocho integrales ya aprobadas. Las 29 verificaciones específicas no se suman a 106 como si fueran suites disjuntas.

## Recuperación

Snapshot previo: `evidence/private/checkpoints/asgi-antes-20261115T004527Z/`, archivo `codigo.tar.gz` con 64 archivos y `sha256.json`. Excluye datos originales, `.env`, artefactos y volúmenes. Git no es un repositorio utilizable; no se pudo crear commit y no se inicializó ni alteró `.git`. El estado al cierre y siguiente comando están en `docs/progreso/ESTADO_ACTUAL.md`.
