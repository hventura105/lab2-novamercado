# Pruebas realmente ejecutadas y límites

## Informes reales de Ubuntu inspeccionados

Rutas/SHA-256 exactos en ESTADO_ACTUAL. ASGI10/10, HTTP+auditoríaSQL, idempotencia, calidad/422, Registry/artefactos/alias, DAG real, replay/promoción/rechazo, resiliencia y persistencia: aprobados por alcance.

Primer arranque: evidence/private/arranque-limpio/20261115t011732z-4299dce5/informe.json,74.424332s; primer modelo/alias y datos oficiales importados, cero observaciones/solicitudes manuales; principal antes/después idéntico. NO se repitió en Codex.

Replay aislado:8.8219/9.9570s entrenamiento,3.1242s recarga; no confundir con trayectoria productiva por DAG. DAG productivo aprox2.43s, sin entrenar/promover por insuficiencia de días nuevos.

## Esta misión en Codex

- Traza real de FileNotFoundError ANTES del cambio en diagnóstico-final/20261115T053839Z/file_not_found_original.txt: plan.json buscado en variante T/Z mayúsculas inexistente. Directorio real inspeccionado directamente con archivos completos y reporte aprobado.
- `python3 -m unittest discover -s tests -p test_arranque_limpio.py -v`:19 aprobadas. Incluye mayúsculas, ambigüedad, archivo interno ausente, escape y plan ejecutado.
- `python3 scripts/prueba_arranque_limpio.py diagnosticar --plan evidence/private/arranque-limpio/20261115T011732Z-4299dce5`: código0, resuelve carpeta real y reporta aprobado sin secretos ni Docker.
- `python3 -m unittest discover -s tests -p test_entrega_local.py -v`:7 aprobadas (exportación/exclusiones/secretos/clave/symlinks/JUnit/fallo daemon). Son pruebas de control, no aprobación simulada de pytest.
- Sintaxis de5 archivos nuevos/modificados válida.17 archivos del producto mantienen manifest b97fc83ad597459ed696775d9cf690f762931919f87cdc3e2359efbf13ded19d, idéntico a evidencia Docker aprobada.
- Docker ps: código1/permission denied. .venv creado; pip código1 sin versiones disponibles desde su entorno; FastAPI/Pydantic/pytest siguen ausentes en host. No se cambiaron versiones para forzar instalación, ni software del sistema.
- `python3 scripts/verificar_cierre.py`: código1, bloqueado en primer acceso daemon, informe cierre/20261115T054352Z-d544884d/informe.json. Cero builds/contenedores nuevos. No se entra en ciclos de intentos.
- Exportación Git real: commit local0d16b2910f10b98ef3c91b4d0ab4596fb570334f, índice explícito87 archivos en punto previo, status limpio, check-ignore/exclusiones/diff sin errores, sin remotos/tags. Root .git vacío/protegido intacto. Entrega final y hashes en ESTADO_ACTUAL.
- La revisión previa bloqueó un marcador de clave en el propio escáner y whitespace en RECUPERACION; corregidos sin retirar la detección de claves. Prueba específica asegura que claves reales siguen bloqueadas.

Antecedente:106 locales aprobadas y10 ASGI reales unittest. No sumar suites solapadas ni atribuir unittest al framework pytest. No se repitió suite completa, entrenamientos ni las integrales aprobadas.

## Falta de evidencia

`pytest`: pendiente de ejecución real; el único comando Ubuntu ejecuta pruebas/contratos en imagen Python3.12 fijada, sin red ni servidor MLflow. No marca éxito sin JUnit no vacío, diez contratos y cero fallos/errores/omisiones. Los siete tests de integración quedan fuera del alcance unitario por diseño, no cuentan como aprobados ni se repiten.

Cierre automático: pytest aprobado, {"tests": 167, "failures": 0, "errors": 0, "skipped": 0, "contratos_asgi": 10}; informe evidence/private/cierre/20261115T060616Z-0705ebbc/informe.json. No se repitió el arranque ni se tocó champion.
