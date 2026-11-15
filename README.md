# NovaMercado · Laboratorio 2

Servicio de pronóstico diario con FastAPI, PostgreSQL, MLflow y Airflow. Se conservan los nueve servicios y los cinco volúmenes de la infraestructura inicial.

**Estado verificable:** los informes reales ejecutados desde Ubuntu acreditan los diez contratos ASGI, predicciones/SQL, idempotencia, Registry/champion1, DAG, promoción aislada, resiliencia MLflow y persistencia. Detección/recuperación MLflow: 11.45/9.01 s, con inferencia HTTP200 durante la caída; reinicio hasta health ok: 29.69 s, hashes iguales. Antecedente:106 pruebas locales aprobadas. Véase [evidencia consolidada](evidence/CIERRE_VERIFICADO.md). El primer arranque limpio también está acreditado en74.4243s, sin modificar el principal. La promoción productiva natural no es demostrable con las ventas oficiales disponibles hasta el corte del champion; la promoción aislada sí aprobó. `pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. Codex no ejecutó esas integrales por restricciones del daemon; inspeccionó los informes aportados. Ver [estado actual](docs/progreso/ESTADO_ACTUAL.md) y [matriz](docs/REQUISITOS.md).

## Datos oficiales

Colocar los originales publicados, mediante copia, en:

```text
data/entrada/
  tiendas.csv
  familias.csv
  historico_ventas.csv
  feriados.csv
  costos.csv
  catalogo_errores.md
  ejemplos/
```

Para copiar una carpeta, ZIP o TAR sin modificar su origen ni sobrescribir contenidos diferentes:

```bash
python3 scripts/datos.py copiar '/ruta/real/datos_lab2'
python3 scripts/datos.py perfil --exigir-completo
```

La copia verifica tamaños y SHA-256 y rechaza rutas inseguras, enlaces y ambigüedades. El perfil y los manifiestos permanecen privados en `data/entrada/`. Los datos no forman parte de Git ni de las imágenes; se montan en solo lectura.

Las fuentes actuales tienen 83 052 ventas entre **2024-03-01 y 2026-02-28**, diez tiendas y doce familias. El calendario de 61 eventos llega a **2026-12-31**. No hay huecos después de la apertura de tiendas. La tienda 10 abrió el 2025-03-15: los días anteriores no se rellenan. Ver [auditoría de datos](docs/DATOS.md).

## Arranque desde cero

Requiere Docker Engine accesible, Compose V2 o superior y Python 3.10+ para scripts del host. Imágenes de versión fija; API y Airflow usan Python 3.12. Reservar preferiblemente 8 GB de memoria para el conjunto. En otro checkout, ejecutar los mismos comandos desde la raíz del repositorio y colocar los datos en su `data/entrada/` relativo; los scripts resuelven esa raíz automáticamente.

```bash
# Desde la raíz de este repositorio, cualquiera que sea su ubicación:
python3 scripts/infra.py init-env
python3 scripts/datos.py perfil --exigir-completo
python3 scripts/infra.py preflight
docker compose up --build
```

El último comando equivale a `docker compose up` cuando las imágenes locales aún no existen. `--build` también incorpora cambios posteriores de código. Para segundo plano con preflight y smoke automáticos:

```bash
python3 scripts/infra.py up
```

`init-env` crea secretos aleatorios con permisos 0600. En instalaciones existentes agrega únicamente `INTERNAL_API_TOKEN` si falta, conservando todas las credenciales previas. No imprimir ni publicar `.env`, ni la salida completa de `docker compose config`; utilizar `docker compose config --quiet` para validar.

`preflight` inventaría contenedores y comprueba los puertos antes de arrancar. Ante conflictos o imposibilidad de inspección, bloquea sin cambiar recursos. Identificar propietario y explicar la solución antes de elegir otro `API_HOST_PORT`, `MLFLOW_HOST_PORT` o `AIRFLOW_HOST_PORT` en `.env`. La API siempre mantiene **8000 dentro de Docker**. No detener servicios de otros proyectos.

Si los contenedores ya están saludables pero `docker compose port` devuelve `:0`, atender primero la [reparación de publicación externa](docs/PUERTOS.md). La configuración incorpora un bridge NAT no interno solo para API, MLflow y Airflow API Server, conservando la red privada y PostgreSQL sin publicar. Aplicar sobre los contenedores existentes, después de comprobar puertos:

```bash
docker compose config --quiet
python3 scripts/puertos.py diagnostico
python3 scripts/puertos.py preflight
python3 scripts/puertos.py aplicar
python3 scripts/puertos.py verificar
```

El script crea/conecta únicamente el bridge de publicación y conserva los IDs de contenedores. Si sus bindings solicitados son incorrectos, se detiene para revisión y autorización antes de una recreación. **El usuario ya confirmó resuelta la publicación desde Ubuntu; no volver a aplicar la reparación durante las integrales.** La guía conserva el diagnóstico y las comprobaciones de Windows como referencia histórica.

En el primer arranque la API ejecuta en segundo plano: migración aditiva, importación transaccional de las fuentes, validación/entrenamiento temporal, registro MLflow, persistencia del artefacto JSONB y activación del alias. `/health` responde 503 hasta cargar un modelo. En arranques siguientes carga la versión persistida y evita repetir entrenamiento. Una modificación de hashes de fuentes ya cargadas requiere revisión; no se reemplazan silenciosamente los datos.

Para demostrar ese primer arranque sin tocar los recursos existentes, está preparado un [ejecutor aislado](docs/ARRANQUE_LIMPIO.md). Crea un plan sin usar Docker:

```bash
python3 scripts/prueba_arranque_limpio.py preparar
```

El comando imprime la carpeta del plan. `validar --plan <carpeta>` revisa Compose sin iniciar recursos. `ejecutar --plan <carpeta> --autorizar-recursos` requiere autorización previa: crea nueve contenedores, dos redes y cinco volúmenes nuevos, sin puertos publicados; usa imágenes ya construidas y mide hasta `/health ok` en máximo600s. No carga datos ni entrena mediante comandos de prueba: únicamente comprueba el bootstrap automático del producto. Conserva todos los recursos y las evidencias; no incluye limpieza automática. La ejecución real del plan actual aprobó en74.4243s; no reutilizarlo para otro arranque vacío. Ver evidence/AUDITORIA_FINAL.md.

## Servicios

| Servicio | Versión / función | Acceso del host por defecto |
| --- | --- | --- |
| api | Python 3.12.12, FastAPI 0.121.3; contrato y pipeline | 127.0.0.1:8000 |
| product-db | PostgreSQL 16.11; producto y respaldo de modelos | Sin publicar |
| mlflow | MLflow 3.10.1; Tracking y Model Registry | 127.0.0.1:5000 |
| airflow-db | PostgreSQL 16.11; metadatos exclusivos Airflow | Sin publicar |
| airflow-init | Airflow 3.1.7; inicialización de una sola ejecución | Sin publicar |
| airflow-api-server | Airflow 3.1.7; UI/API | 127.0.0.1:8080 |
| airflow-scheduler | Airflow 3.1.7; LocalExecutor | Sin publicar |
| airflow-dag-processor | Airflow 3.1.7; procesamiento de DAGs | Sin publicar |
| airflow-triggerer | Airflow 3.1.7; tareas diferibles | Sin publicar |

Red privada `lab2-novamercado_internal`, DNS por nombres de servicio e `internal: true`. API, MLflow y Airflow API Server tienen además el bridge NAT `lab2-novamercado_publicacion`, con publicaciones TCP limitadas a `127.0.0.1`; esos tres servicios adquieren conectividad externa por ese bridge. PostgreSQL del producto y Airflow permanecen solo en la red privada, sin puertos públicos, con instancias y volúmenes separados. El DAG llama por HTTP autenticado al pipeline del producto; no necesita paquetes ML adicionales en Airflow. Las credenciales del administrador de Airflow permiten al backend disparar y consultar sus ejecuciones; el token interno es independiente.

## Contrato

| Endpoint | Comportamiento |
| --- | --- |
| POST /v1/prediccion | tienda_id, fecha, familias; versión textual, venta esperada, cantidad entera no negativa y calidad. Registra cada solicitud, incluidas repeticiones. |
| POST /v1/observaciones | tienda_id, fecha, ventas por familia; cuenta filas nuevas o modificadas; repetición idéntica devuelve 0. |
| POST /admin/reentrenar | Sin cuerpo. Inicia un DAG real: 202 con id o 503 si falla el inicio. |
| GET /admin/reentrenar/{id} | en_curso, exitoso o fallido; resultado terminado con promovido, version y motivo; desconocido 404. |
| GET /modelo | nombre, alias y version textuales del modelo cargado. |
| GET /health | 200 ok si modelo y dependencias están disponibles; 200 degradado con motivo; 503 sin modelo. |

Rechazos 422 con `detail`; estructura Pydantic y limpieza en módulos separados. `/docs` expone OpenAPI. La ruta interna de entrenamiento exige el token compartido con el DAG.

Ejemplo de consulta, una vez comprobado el arranque:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/modelo
curl --fail -X POST http://127.0.0.1:8000/admin/reentrenar
```

## Fechas, modelos y promoción

Las fechas son simuladas; nunca se validan contra el reloj. Los pronósticos deben ser posteriores al histórico y estar dentro del calendario publicado. La primera fecha posible actual es 2026-03-01. Para repetir una fecha tras promover un modelo más reciente se elige, si hace falta, una versión previamente promovida con entrenamiento anterior a la fecha solicitada. La respuesta identifica esa versión; /modelo informa la versión activa por defecto. La fecha 2025-11-17 de los ejemplos oficiales es ilustrativa y no abre una excepción histórica.

Para D solo se usan ventas de fechas < D y las promociones de D de la solicitud. La validación reproduce la llegada diaria de observaciones: incorpora etiquetas de días anteriores al predecir el siguiente, manteniendo congelados los coeficientes durante el bloque de validación. No inventa observaciones ni promociones ausentes.

Baseline: media del mismo día de semana de las últimas ocho semanas. ML: ridge por familia, implementado mediante ecuaciones normales y resolución con pivoteo, con variables temporales, rezagos, medias anteriores, promociones y eventos nacionales/locales. Últimos 28 días del entrenamiento para calibrar residuos, separados del ajuste de coeficientes; validación inicial de 56 días posteriores. No se usan residuos de validación para ajustar inventario.

La cantidad sugerida minimiza el costo empírico con cuantil `costo_faltante/(costo_faltante+costo_sobrante)`, comparando cantidades enteras. Se promueve cuando el costo mejora al menos 1% y el MAE no empeora más de 5%, sobre exactamente el mismo bloque futuro. Para reentrenar se requieren al menos siete días nuevos posteriores al corte del vigente; si no existen se termina sin promoción por evidencia insuficiente. El nuevo artefacto se reajusta con la información disponible después de evaluar.

MLflow registra runs separados, parámetros, métricas, artefactos JSON, hashes de fuentes/código y snapshot, versiones y alias `champion`. El flavor propio `novamercado_json` se carga con el código de la API; no usa pickle ni requiere mlflow.pyfunc en inferencia. El modelo se respalda en PostgreSQL JSONB y se mantiene en memoria. La API no consulta MLflow para predecir. La versión se refresca cada 20 segundos y también inmediatamente tras promover; la recarga se comprobó en el replay real aislado; la trayectoria de promoción productiva por DAG sigue pendiente.

## Pruebas

Pruebas locales y evaluación REAL de los archivos oficiales, sin servidor MLflow:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validar_modelos.py
```

Las pruebas efímeras usan fixtures de test, nunca sustitutos de los archivos de `data/entrada/`. El entrenamiento local deja métricas y modelo en `evidence/private/`, sin registrar o promover nada en producción.

Con dependencias en un entorno virtual local:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -m unit
```

Las diez pruebas ASGI usan runtime/limpieza reales y dobles locales, sin necesitar servidores MLflow/Airflow activos. Para verificar exclusivamente la corrección del transporte ASGI en la imagen existente, sin repetir integrales ni interrumpir servicios:

```bash
python3 scripts/pruebas_integrales.py --solo-asgi --trazas-asgi
```

El informe privado incluye trazas, versiones de dependencias y hash del archivo de pruebas. Un resultado aprobado de este modo acredita únicamente los contratos unitarios. El [diagnóstico ASGI](docs/DIAGNOSTICO_ASGI.md) conserva la causa reproducida y los comandos para comparar antes/después.

Las integrales de servicios reales usan un ejecutor stdlib, sin instalar pytest ni paquetes en Ubuntu y sin reconstruir otra vez las imágenes. **La ejecución siguiente incluye interrupciones; queda reservada para una ventana autorizada, no para la corrección ASGI actual:**

```bash
python3 scripts/pruebas_integrales.py --con-interrupciones --replay-promocion
```

`--con-interrupciones` detiene/inicia temporalmente solo MLflow y reinicia los ocho servicios permanentes de este proyecto, conservando datos y volúmenes. `--replay-promocion` crea un esquema/modelo aislados con ventas oficiales para comprobar promoción, rechazo y recarga sin tocar champion productivo. El modo sin opciones omite esos casos explícitamente. Las solicitudes de prueba quedan auditadas; no se sobrescriben deliberadamente observaciones distintas.

El runner exige HTTP y filas SQL reales, runs/versiones/alias/artefactos MLflow, estado real de DAG/tareas y huellas antes/después del reinicio. Valida los ejemplos de errores y la ausencia de cambios en observaciones rechazadas. Guarda progreso en `evidence/private/integration/<id>/informe.json` y `RESUMEN.md`. Código 1 indica fallo/bloqueo; 2 indica requisitos pendientes. Un caso omitido no cuenta como aprobado.

La [guía de integración](docs/PRUEBAS_INTEGRALES.md) explica efectos, alcance del replay, comandos pytest opcionales y pendientes académicos. Las siete integrales pytest comparten los mismos chequeos y requieren opciones explícitas para interrupciones y replay. El arranque inicial Docker vacío y una promoción productiva con observaciones futuras legítimas no se acreditan con un reinicio o un replay aislado. No borrar el producto ni inventar datos para cerrar esas mediciones.

## Operación y persistencia

Volúmenes conservados: `product-db-data`, `airflow-db-data`, `mlflow-data`, `airflow-logs`, `airflow-config`; nombres reales con prefijo `lab2-novamercado_`. Los contenedores permanentes de aplicación se ejecutan sin root. El inicializador ajusta únicamente sus dos volúmenes y baja de privilegios antes de migrar.

```bash
docker compose ps -a
docker compose logs --tail=100 api mlflow airflow-init airflow-api-server airflow-scheduler
docker compose stop
```

No borrar contenedores, bases ni volúmenes ni ejecutar limpieza global. No cambiar las claves persistidas sin un procedimiento revisado. Se usa SimpleAuthManager de Airflow para el laboratorio en loopback; no se propone como autenticación para exposición externa.

Guardar avances en los cinco documentos de `docs/progreso/`. El .git raíz está vacío y protegido; se preparó un Git independiente con commit local revisado en evidence/private/entrega/, sin remotos ni tags. No publicar ni crear el tag `entrega-lab2` hasta verificar el producto completo.

La [lista de entrega](docs/ENTREGA.md) separa verificaciones aprobadas de requisitos pendientes e indica cómo revisar datos/secretos antes de preparar GitHub. La [guía de recuperación](docs/RECUPERACION.md) explica cómo verificar y usar los respaldos sin sobrescribir el trabajo existente.

## Cierre técnico pendiente: un comando

Las integrales y el primer arranque ya cuentan con informes reales; no repetirlos. Para acreditar por primera vez pytest, ejecutar desde Ubuntu (también funciona desde cualquier otro directorio usando la ruta absoluta al script):

```bash
python3 scripts/verificar_cierre.py
```

Construye únicamente una imagen de pruebas Python3.12 con versiones fijadas, copia código revisado sin .env/datasets/evidencias privadas, monta fuentes oficiales read-only y ejecuta pytest unitario/contrato con red desactivada. Exige cero fallos/errores/omisiones y diez contratos ASGI. No levanta/reinicia el producto, no modifica champion, no repite integrales. Guarda logs/JUnit privados y, al aprobar, actualiza evidencia/progreso y crea una exportación Git local revisada. Conserva imagen/contenedor de prueba para diagnóstico. Si PyPI/daemon no están disponibles, falla con evidencia y no declara aprobación. La construcción no forma parte del tiempo74.42s ya medido.

La identidad del commit automatizado es Codex <codex@local.invalid>, no la del estudiante. El repositorio independiente contiene código/config/docs y placeholders vacíos, sin datos originales/credenciales ni respaldos; su estado y hash están en git.json junto a su carpeta. Ningún remoto o tag se crea automáticamente.
