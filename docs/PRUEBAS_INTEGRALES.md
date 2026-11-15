# Integración real y cierre académico

**Estado actualizado:** ASGI, HTTP/SQL/idempotencia, Registry/DAG, promoción aislada, resiliencia MLflow y reinicio persistente aprobados según [evidencia consolidada](../evidence/CIERRE_VERIFICADO.md). No repetir esos casos por defecto. Pendientes: [primer arranque limpio](ARRANQUE_LIMPIO.md) y promoción productiva por DAG con datos legítimos. Los apartados de comandos ASGI e interrupciones conservan el procedimiento reproducible; no son una instrucción para repetirlo ahora.

La publicación y el modelo inicial están comprobados **por el usuario desde Ubuntu**: `/health` HTTP 200 con `estado: ok`, y `/modelo` HTTP 200 con `novamercado_ventas_diarias`, alias `champion`, versión textual `1`. Esa evidencia se registra en `evidence/INFRAESTRUCTURA_USUARIO.md`.

Codex sigue sin acceso al daemon ni a sockets. El informe Ubuntu `evidence/private/integration/20261115T004023Z-f65a37ca/informe.json` acredita ocho casos aprobados, uno fallido (ASGI) y cinco pendientes. No se ha cambiado Compose, la aplicación productiva ni la configuración de redes en esta corrección.

## Corrección ASGI prioritaria: ejecución aislada

El informe real `20261115T004023Z-f65a37ca` acredita ocho integrales aprobadas, una fallida (ASGI) y cinco pendientes. Para verificar la corrección actual sin repetir las aprobadas:

```bash
cd /home/gama/product-dev/lab2-novamercado
python3 scripts/pruebas_integrales.py --solo-asgi --trazas-asgi
```

Este modo solo ejecuta las diez pruebas unitarias en el contenedor existente, con dobles locales. Conserva trazas y versiones en el informe privado y rechaza combinarse con interrupciones/replay. No exige reconstrucción. Para reproducir antes/después, consultar [DIAGNOSTICO_ASGI.md](DIAGNOSTICO_ASGI.md). No ejecutar las opciones de interrupción que aparecen en la guía general durante esta reparación.

## Comando completo desde Ubuntu (reservado para una ventana autorizada)

Desde la raíz del proyecto, con los servicios ya operativos:

```bash
cd /home/gama/product-dev/lab2-novamercado
python3 scripts/pruebas_integrales.py --con-interrupciones --replay-promocion
```

Requiere Python 3.10+ y acceso normal a Docker. **No requiere pytest, pip ni paquetes nuevos en Ubuntu.** Usa los paquetes ya instalados en la imagen API. Transmite los helpers por stdin a `docker compose exec`; no reconstruye ni recrea contenedores.

Efectos explícitos de las opciones:

- `--con-interrupciones`: detiene/inicia temporalmente **solo `mlflow` de este proyecto** y después reinicia los ocho servicios permanentes de este Compose. Conserva IDs, volúmenes, modelos y datos. La restauración de MLflow se intenta en `finally`, incluso si la prueba intermedia falla. Si esa recuperación falla, no reinicia automáticamente el resto y el informe indica revisar `docker compose start mlflow`.
- `--replay-promocion`: crea un esquema PostgreSQL `novamercado_it_<token>` y un experimento/modelo MLflow propios. Carga allí una partición del histórico oficial y añade observaciones oficiales posteriores para probar cambios de versión. Los datos y artefactos de prueba se conservan; no hay limpieza destructiva.

Para ejecutar primero sin interrupciones ni replay:

```bash
python3 scripts/pruebas_integrales.py
```

Este modo sigue enviando solicitudes reales, registra predicciones y observaciones reales de prueba y dispara un DAG. Omite las dos opciones anteriores y las deja como pendientes, no como aprobadas.

Ejecutar sin otros clientes escribiendo simultáneamente en el producto. Las huellas se comparan para detectar pérdida/cambio real de información y pueden señalar escrituras concurrentes; el ejecutor no restaura ni sobrescribe datos automáticamente para ocultar diferencias.

## Qué verifica

| Comprobación | Evidencia exigida |
| --- | --- |
| Identidad del despliegue | Proyecto y etiquetas propios, ocho servicios permanentes presentes, puertos reales 8000/5000/8080 y PostgreSQL sin publicación |
| Código ejecutado | SHA-256 de todos los módulos y migración local iguales a los archivos en la imagen API; sin reconstrucción automática ante diferencias |
| Estado inicial | `/health`, `/modelo` y fila activa de PostgreSQL coinciden; ninguna ejecución previa en curso |
| Contrato ASGI | Ejecuta diez tests locales dentro de la imagen; se etiquetan como unitarios con dobles, no sustituyen HTTP/SQL reales |
| Predicciones | Dos POST HTTP reales, validación de todos los campos del anexo y cantidades enteras, dos IDs nuevos de solicitud y filas/versiones de predicciones en SQL |
| Calidad | Ejemplos E01–E08/E10, fecha con formato alternativo no ambiguo, listas parciales, precedencia de advertencias y rechazos 422/detail; los casos inválidos no modifican las observaciones |
| Observaciones/E09 | Ventas reales del histórico en una tienda/fecha sin observaciones previas, o reenvío de observaciones ya existentes si no hay hueco disponible; segunda respuesta `registros_guardados=0` y valores SQL iguales |
| MLflow | Experimento, runs terminados de baseline/ridge con parámetros/MAE/RMSE/costo, versión READY, alias, run_id, flavor, linaje y artefacto iguales al respaldo JSONB |
| FastAPI → Airflow | POST administrativo 202 con id, estado final en API/SQL y DAG/tareas realmente `success` en Airflow; duración ≤600 s |
| Promoción productiva | Si ocurre legítimamente, versión del endpoint y alias actualizados sin cambiar ID ni StartedAt de FastAPI, en <120 s desde el fin real del DAG |
| MLflow caído | `/health` degradado en <60 s, predicción HTTP 200 y mismo modelo sin reiniciar API; después `/health` ok en <120 s |
| Persistencia | SHA-256 y conteos de las 14 tablas de producto, modelo/alias/versiones, contenedores y montajes conservados tras restart; no vuelve a entrenar el inicial |
| Tiempo de recuperación | Reinicio hasta `/health` ok ≤600 s. Se etiqueta como reinicio, no como arranque inicial vacío |

Las predicciones usan una fecha derivada de histórico, observaciones y corte del modelo, siempre dentro del calendario. Las promociones de la solicitud proceden del JSON oficial como valores declarados de prueba; no se registran como ventas reales. No se usa el reloj para decidir fechas simuladas.

La observación válida se selecciona mediante SQL de solo lectura para evitar sobrescribir una tienda/fecha que ya tenga observaciones distintas. No se cargan las ventas ilustrativas de E09 sobre las ventas reales: la repetición se comprueba con valores reales. Los ejemplos negativos/ambiguos solo deben producir rechazo; sus pruebas comparan la huella de observaciones antes y después.

## Replay de promoción con componentes reales

No existen ventas oficiales posteriores a 2026-02-28 en las fuentes actuales. Por eso no se inventan ventas futuras, no se degrada el vigente ni se fuerza su alias para demostrar una promoción productiva.

El replay define un entrenamiento inicial hasta `max(historico)-112 días` (**2025-11-08** en estas fuentes). Después incorpora bloques de 28 días con ventas reales del CSV como observaciones, **sin promociones en las observaciones**. Para pronosticar el día siguiente utiliza las promociones oficiales de ese día como solicitud, sin incluir sus ventas.

El escenario numérico se ejecutó localmente y obtuvo:

| Bloque terminado | Costo candidato | Costo vigente | Regla |
| --- | ---: | ---: | --- |
| 2025-12-06 | 109 601,60 | 109 601,60 | Conservar vigente |
| 2026-01-03 | 137 703,60 | 151 281,60 | Promover |

Esta tabla es evidencia numérica local, no ejecución integral. El helper preparado comprueba esos comportamientos usando:

- PostgreSQL real, con esquema propio. Un transporte de conexión redirige los identificadores constantes de SQL al esquema de prueba; los datos parametrizados no se alteran. Rechaza nombres inseguros y SQL destructivo. Sus locks no coinciden con los productivos.
- MLflow real, con nombre/experimento/alias de prueba. Se registran candidatos, incluso los no promovidos, y se inspecciona su versión READY/run_id.
- FastAPI y Uvicorn reales en un servidor HTTP adicional, solo en loopback **dentro del contenedor API**. El puerto efímero de ese servidor no se publica en Docker ni altera 8000/5000/8080. Se utiliza el mismo servidor durante todas las etapas.
- Pipeline real de entrenamiento/promoción. La recarga del servidor de prueba se produce por el refresco periódico real desde PostgreSQL, sin reemplazar a mano su modelo cargado.
- Repetición de un pronóstico anterior después de promover: exige versión histórica promovida y predicciones idénticas, aunque ya existan ventas posteriores en la base aislada. Detecta incorporación de etiquetas futuras.

El proceso productivo, sus tablas y su alias se comparan antes/después para asegurar que el replay no los cambió. El DAG productivo se comprueba por separado mediante el endpoint real. **No se afirma que el replay sea una promoción a través del DAG productivo:** el pipeline del replay se invoca directamente para mantener separados datos y alias de prueba. Esa trayectoria productiva completa requiere observaciones nuevas legítimas.

El bootstrap aislado se mide desde la creación del servidor de prueba hasta salud ok. No equivale a levantar toda una arquitectura Docker desde volúmenes vacíos.

## Informes, recuperación y códigos de salida

Cada ejecución crea un directorio privado independiente:

```text
evidence/private/integration/<fechaUTC-token>/
  informe.json
  RESUMEN.md
```

El JSON se guarda de forma atómica antes y después de cada caso. Registra IDs de DAG/replay antes de operaciones largas. No incluye contraseñas, tokens, DSN, stderr arbitrario ni filas originales de ventas. Las respuestas de predicción y métricas son evidencias privadas y quedan excluidas de Git. El esquema y modelo del replay se conservan para inspección, sin eliminarlos al terminar.

Estados por caso: `aprobada`, `fallida`, `bloqueada`, `pendiente` o `interrumpida`. Los casos omitidos o no accesibles nunca se convierten en éxito.

- **0:** todos los casos registrados están aprobados.
- **1:** existe fallo, bloqueo o interrupción.
- **2:** las comprobaciones ejecutadas no fallaron, pero hay requisitos pendientes.
- **130:** interrupción por teclado; conservar informe parcial y comprobar recuperación de MLflow.

Con el diseño actual, el arranque inicial Docker vacío queda pendiente de una medición separada; por ello una ejecución funcionalmente exitosa puede devolver **2**. Tampoco una no-promoción legítima prueba por sí sola una promoción productiva. Revisar `informe.json`, no solo el código de salida.

Un fallo HTTP/SQL detiene las escrituras posteriores, los reentrenamientos y las interrupciones; aún se puede recoger inspección MLflow de solo lectura. El preflight fallido bloquea todo antes de escribir o detener servicios. Si la imagen difiere del código local, revisar la reconstrucción fuera del ejecutor y respetar las autorizaciones para recrear contenedores.

## Ejecución opcional con pytest

El mismo núcleo de verificaciones está disponible en siete tests integrales pytest si ya existe un entorno virtual con sus dependencias:

```bash
RUN_DOCKER_INTEGRATION=1 RUN_DOCKER_INTERRUPTION=1 RUN_DOCKER_REPLAY=1 .venv/bin/python -m pytest -m integration
```

Sin las dos últimas variables, las pruebas de interrupciones/replay se omiten explícitamente. La selección pytest no acredita por sí sola todo el cierre académico; el runner stdlib produce la matriz más completa.

## Pendientes que no se pueden cerrar retrospectivamente

1. Ejecutar el runner contra los servicios reales desde Ubuntu y revisar el informe. Esta sesión de Codex no lo pudo hacer: falló el preflight por permisos.
2. Medir el arranque inicial completo Docker con datos/modelos vacíos, sin borrar el producto existente. Si requiere un stack de validación adicional, preparar recursos/puertos y solicitar autorización antes de iniciarlo.
3. Observar promoción productiva con nuevas ventas reales y su trayectoria completa FastAPI → DAG → promoción → recarga. El replay acredita otro alcance, que debe mantenerse separado.
4. Completar evidencia final y commits locales cuando Git sea utilizable. No crear `entrega-lab2` ni publicar aún.

Referencia de implementación del servidor de prueba: [Uvicorn 0.38.0, Server.run con sockets proporcionados](https://github.com/encode/uvicorn/blob/0.38.0/uvicorn/server.py).
