# Evidencia de implementación · Fase 1

Fecha: 2026-11-14. Directorio de trabajo: `/home/gama/product-dev/lab2-novamercado`.

**Resultado: infraestructura preparada y validada estáticamente; ejecución e integración pendientes por restricciones del entorno. No se declara operativo ningún servicio.**

## Revisión inicial

- La estructura inicial contenía `api/`, `airflow/`, `ml/`, `data/entrada/`, `docker/`, `scripts/` y `evidence/`. Los archivos existentes `AGENTS.md`, `README.md`, `DECISIONES.md`, `.env.example` y `.gitignore` estaban vacíos. No había aplicación, dependencias ni Compose existentes.
- `AGENTS.md` no incluía instrucciones adicionales.
- Docker CLI: `29.9.1`, build `dfc520d`. Compose: `v5.6.0`. Python del host: `3.14.4`.
- `.git` no es un repositorio Git utilizable en esta sesión: `git status --short` devuelve `fatal: not a git repository`. No se inicializó un repositorio ni se publicó nada.
- No se pudo consultar la versión de imágenes o componentes previamente instalados: el daemon es inaccesible. Se fijó explícitamente Airflow 3.1.7 en la nueva configuración y se consultó su documentación oficial.

## Comprobaciones realizadas

| Comprobación | Resultado observado |
| --- | --- |
| `docker --version` y `docker compose version` | CLI disponibles; versiones indicadas arriba |
| `docker ps --format ...` | Bloqueado: permiso denegado sobre `/var/run/docker.sock` |
| `docker images --format ...` | Bloqueado por el mismo acceso denegado |
| `ss -ltn` | `Cannot open netlink socket: Operation not permitted`; no permite concluir que los puertos estén libres |
| Lectura de `/proc/net/tcp` y `/proc/net/tcp6` | Solo encabezados en este namespace; no demuestra disponibilidad de puertos en el host del daemon |
| Socket de prueba en loopback:8000 | `PermissionError: [Errno 1] Operation not permitted`; no se pudo inspeccionar disponibilidad |
| Acceso a PyPI desde terminal con `curl -I`, timeout acotado | `Could not resolve host: pypi.org`; no se descargaron paquetes |
| `python3 scripts/infra.py init-env` | Creó `.env` con secretos aleatorios; `stat` confirmó permisos `600`; no se imprimieron credenciales |
| `docker compose --env-file .env.example config --no-interpolate --quiet` | Código 0; sintaxis Compose válida sin interpolar secretos |
| `docker compose config --quiet` | Código 0 con el `.env` local generado |
| `python3 -m unittest discover -s tests -v` | 16 pruebas locales aprobadas; usan dobles para dependencias y sockets, no demuestran comunicación real |
| Análisis AST de los 13 archivos Python | Sin errores de sintaxis, usando Python 3.14 del host; la ejecución en Python 3.12 de las imágenes sigue pendiente |
| Inspección programática del JSON de `docker compose config`, sin imprimirlo | Nueve servicios; ocho permanentes y un inicializador; API target 8000; cinco volúmenes; red `internal: true`; puertos solo loopback; PostgreSQL sin publicar; bases y contraseñas distintas; sin tags `latest`; contraseña admin solo entregada al inicializador |
| `python3 scripts/infra.py preflight` | Código 1 por acceso denegado al daemon; no hubo cambios de puertos ni recursos Docker |
| `python3 scripts/infra.py up` | Código 1 en preflight, antes de ejecutar `docker compose up`; no hubo construcción ni arranque |

Las 16 pruebas locales cubren salud de dependencias, degradación a 503, consultas PostgreSQL, ausencia de secretos en errores, lectura del estado real de Airflow, rechazo de conflictos/puertos duplicados/inspección denegada, aislamiento del comando Compose, formato de salida de `ps`, creación privada e idempotente de `.env`, bloqueo del arranque tras preflight fallido y rechazo de inicialización ausente o fallida.

## Archivos implementados

- `compose.yaml`: nueve servicios, healthchecks, dependencias, red y cinco volúmenes.
- `docker/api.Dockerfile`, `docker/mlflow.Dockerfile`: imágenes de versión fija y usuarios sin privilegios para los servicios permanentes.
- `api/requirements.txt`: dependencias fijadas para Python 3.12/Linux.
- `api/app/__init__.py`, `api/app/core/__init__.py`, `api/app/core/health.py`, `api/app/main.py`: aplicación mínima y comprobaciones PostgreSQL/MLflow.
- `api/tests/test_endpoints.py`: cuatro pruebas ASGI de endpoints; pendientes de ejecución dentro de la imagen.
- `airflow/scripts/init_airflow.py`: preparación persistente de autenticación y migraciones de Airflow 3.
- `checks/__init__.py`, `checks/connectivity.py`, `checks/product_persistence.py`, `checks/airflow_probe.py`: pruebas reales para ejecutar dentro de los servicios.
- `scripts/__init__.py`, `scripts/infra.py`: generación de entorno, preflight, arranque protegido, smoke y prueba de persistencia por reinicio.
- `tests/test_infrastructure.py`: 16 pruebas locales de salud y salvaguardas.
- `.env.example`, `.gitignore`, `.dockerignore`: plantilla pública y exclusiones de secretos, datos y archivos locales.
- `.env`: archivo local generado, privado y excluido; no forma parte de los archivos publicables.
- `README.md`, `DECISIONES.md`, `evidence/FASE1.md`: operación, decisiones, referencias y límites de verificación.
- `airflow/dags/.gitkeep`, `airflow/plugins/.gitkeep`, `data/entrada/.gitkeep`: conservación de directorios vacíos, sin datos ni DAGs.

Los archivos vacíos preexistentes de documentación y configuración se completaron. No se modificó `AGENTS.md`, ni se implementó contenido en los directorios de modelos o datos oficiales.

## Verificaciones pendientes

Desde una terminal con acceso legítimo al daemon y capacidad de inspeccionar puertos, en este mismo directorio:

```bash
python3 scripts/infra.py preflight
python3 scripts/infra.py up
python3 scripts/infra.py persistence
```

1. Obtener el inventario real de servicios y puertos antes del arranque. No se ha identificado ni descartado ningún conflicto real. Si aparece uno, documentar propietario y solución antes de modificar únicamente el puerto del host de este laboratorio; conservar `api:8000`.
2. Descargar las imágenes y construir la API; confirmar disponibilidad de tags, resolución efectiva de dependencias y compatibilidad en Python 3.12. No se ejecutó una instalación de dependencias ni una construcción Docker en esta sesión.
3. Comprobar migraciones de Airflow, finalización de `airflow-init` con código 0 y salud de los ocho servicios permanentes.
4. Ejecutar pruebas reales desde el host y los contenedores: DNS, TCP, SQL, HTTP, Tracking API y salud detallada de Airflow. Ejecutar las cuatro pruebas ASGI dentro de la API.
5. Ejecutar la prueba de persistencia y conservar su JSON en `evidence/runtime/`. Exige recuperar PostgreSQL, run, artefacto, entrada vacía del Registry, variable Airflow, archivo de logs y hash de autenticación después del reinicio del proyecto.

No hay evidencia de integración o persistencia real hasta completar esos pasos. No se ejecutó ningún comando de eliminación de contenedores, volúmenes o limpieza global. No se detuvieron servicios de otros proyectos ni se solicitó ampliar permisos del sandbox.
