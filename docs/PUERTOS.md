# Actualización: publicación resuelta según verificación del usuario

El usuario confirmó desde Ubuntu los tres puertos y respuestas HTTP200 de /health y /modelo, después de reconstruir imágenes. Evidencia: `evidence/INFRAESTRUCTURA_USUARIO.md`. La prioridad actual es integración y cierre académico, no volver a cambiar redes o aplicar la reparación. Las comprobaciones propias de Codex continúan restringidas.

El texto siguiente se conserva como **registro histórico** de la preparación y limitaciones de la reparación en su sesión original.

---

# Reparación de publicación externa — estado pendiente de verificación real

Esta tarea modifica únicamente la publicación de FastAPI, MLflow y Airflow API Server. No continúa las fases de datos, modelos o reentrenamiento.

## Hallazgos comprobados

La configuración efectiva inicial tenía los siguientes bindings fijos, también confirmados en las variables públicas de `.env`:

| Servicio | Host IP | Publicado | Interno |
| --- | --- | ---: | ---: |
| api | 127.0.0.1 | 8000 | 8000 |
| mlflow | 127.0.0.1 | 5000 | 5000 |
| airflow-api-server | 127.0.0.1 | 8080 | 8080 |

No se declararon puertos aleatorios, rangos, `published: 0` ni `network_mode: host`. Compose normaliza la sintaxis corta con `mode: ingress`. Este campo describe publicación en Swarm; no demuestra un error en `docker compose up` standalone. Al ensayar `ports.mode: host`, Compose advirtió que solo se honra en Swarm; se quitó esa opción y la configuración final valida sin advertencias. No se usa red de host.

Los tres contenedores estaban declarados **únicamente en la red bridge `internal: true`**. Un reporte primario de Moby reproduce este patrón en Docker 29.x: `HostConfig.PortBindings` conserva la solicitud, pero `NetworkSettings.Ports` queda vacío/null y no existe publicación real hasta conectar un bridge no interno. Esto es consistente con el `:0` comunicado por el usuario, pero no se ha inspeccionado el daemon desde esta sesión para confirmar que sea exactamente su caso. El diagnóstico preparado mostrará versión del motor, bindings solicitados y bindings reales, sin leer variables de entorno del contenedor.

La documentación de Docker también distingue bridge NAT de `routed`: en modo routed no se utiliza el puerto del host. El bridge nuevo fija NAT explícitamente. Las fuentes están enlazadas al final.

## Corrección preparada

- Publicaciones con sintaxis larga: `target`, `published`, `host_ip: 127.0.0.1` y `protocol: tcp` explícitos. Los valores efectivos son exactamente 8000, 5000 y 8080; el script rechaza otros valores y cero.
- Nueva red propia `lab2-novamercado_publicacion`, bridge no interno con gateway IPv4 NAT.
- Solo `api`, `mlflow` y `airflow-api-server` se conectan además a esa red. Esto habilita publicación y conectividad externa para esos tres servicios; las entradas publicadas continúan limitadas a loopback.
- Los nueve servicios conservan la red privada existente y sus nombres DNS. No se altera `lab2-novamercado_internal`.
- PostgreSQL del producto y Airflow mantienen únicamente la red privada, sin `ports` ni conexión al bridge de publicación.
- Los cinco volúmenes, imágenes, aplicaciones, credenciales y puertos internos permanecen iguales.

Snapshots seguros de la configuración relevante: `evidence/puertos-config-antes.json` y `evidence/puertos-config-despues.json`. Excluyen entornos y secretos. La comparación efectiva mostró cambios en los tres servicios publicados y la nueva red; ninguna otra definición de servicio cambió.

## Aplicación sobre contenedores existentes desde Ubuntu

Ejecutar desde la terminal Ubuntu que sí puede consultar el daemon:

```bash
cd /home/gama/product-dev/lab2-novamercado
docker compose config --quiet
python3 scripts/puertos.py diagnostico
python3 scripts/puertos.py preflight
python3 scripts/puertos.py aplicar
python3 scripts/puertos.py verificar
```

Cada paso debe terminar correctamente antes del siguiente. `aplicar` repite internamente todas las comprobaciones antes de mutar Docker.

El script exige contenedores en ejecución con etiquetas del proyecto y exactamente los bindings solicitados correctos en `HostConfig.PortBindings`. Comprueba todos los puertos antes de crear/conectar nada, consulta otros publicadores Docker e intenta enlazar los puertos en Ubuntu. Si un binding ya está publicado correctamente por su propio contenedor lo reconoce, sin confundirlo con un conflicto externo.

Cuando las condiciones se cumplen, crea únicamente la red de publicación con etiquetas del proyecto si todavía no existe y ejecuta `docker network connect` sobre los tres IDs existentes. Comprueba que conserven sus IDs y su red privada. **No elimina, recrea, reinicia o reconstruye contenedores; no modifica volúmenes, bases ni datos.** Se puede repetir para completar conexiones pendientes. Si una operación falla a mitad, no se desconecta lo ya conectado: revisar el diagnóstico antes de repetir.

Si `HostConfig.PortBindings` está ausente o difiere, conectar otra red no basta. El script se detiene sin recrear contenedores. En ese caso hay que revisar la evidencia y solicitar autorización para una recreación selectiva antes de ejecutarla, conforme a [AGENTS.md](../AGENTS.md): «No borrar contenedores, bases ni volúmenes». No se incluyó un comando automático de recreación.

La nueva red queda declarada en Compose para futuros despliegues. Los comandos generales de `compose up` pueden decidir recrear contenedores si cambian sus hashes de configuración; esta reparación de los contenedores ya creados usa únicamente conexión de red, con IDs conservados.

## Conflictos de puertos

No se ha identificado ni descartado un conflicto real desde esta sesión. Si el script detecta otro publicador, muestra el nombre y se detiene. Si el puerto está ocupado por un proceso del host, identificarlo antes de cambiar o detener nada:

```bash
ss -ltnp '( sport = :8000 or sport = :5000 or sport = :8080 )'
docker ps --format '{{.Names}}\t{{.Ports}}'
```

En Windows PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,5000,8080 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

La comprobación de sockets de Ubuntu y el inventario Docker no sustituyen la inspección de procesos exclusivos de Windows. Si Docker detecta después una colisión del host Windows al conectar, la operación debe revisarse; no se detiene automáticamente ningún proceso. Para detener un servicio ajeno se debe identificarlo, explicar el efecto y pedir autorización.

## Verificación real de publicación y HTTP

`verificar` exige los tres bindings reales en `NetworkSettings.Ports`, la salida exacta de `docker compose port` y cuatro HTTP 200: API `/health` y `/modelo`, MLflow `/health`, Airflow `/api/v2/monitor/health`. También valida los campos textuales de `/modelo`. `:0`, null, arrays vacíos, timeouts y respuestas 503 son fallos, no éxito. `/health` con `degradado` acredita acceso HTTP, pero deja pendiente la salud de la dependencia indicada.

Comprobación manual equivalente en Ubuntu:

```bash
docker compose port api 8000
docker compose port mlflow 5000
docker compose port airflow-api-server 8080
curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8000/health
curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8000/modelo
curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:5000/health
curl --noproxy '*' --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8080/api/v2/monitor/health
```

Los comandos `port` deben devolver, respectivamente, `127.0.0.1:8000`, `127.0.0.1:5000` y `127.0.0.1:8080`. Healthchecks internos saludables no sustituyen esta prueba.

Comprobar por separado desde Windows PowerShell:

```powershell
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8000/health
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8000/modelo
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:5000/health
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 --fail-with-body http://127.0.0.1:8080/api/v2/monitor/health
```

Si Ubuntu responde y Windows no, registrar ese resultado antes de evaluar Docker Desktop/WSL localhost forwarding. No se han cambiado firewall, portproxy ni configuración global de Windows/WSL.

## Pruebas ejecutadas y límite de esta sesión

- `docker compose config --quiet`: correcto y sin advertencias con la versión local v5.6.0.
- Comparación filtrada de configuración: solo tres servicios incorporan publicación; nueve servicios y cinco volúmenes conservados; PostgreSQL sin puertos; red privada idéntica.
- `python3 -m unittest discover -s tests -p test_puertos.py -v`: **12 pruebas locales aprobadas**. Comprueban bloqueo por conflictos, inspección denegada, port 0, red ajena, bindings ausentes y HTTP fallido; y aplicación limitada a crear/conectar red con IDs existentes. Son dobles locales, no prueba Docker.
- Acceso al daemon: permiso denegado en `/var/run/docker.sock`; no se pudo inspeccionar ni modificar el runtime.
- Pruebas de sockets en 8000/5000/8080: `Operation not permitted`; disponibilidad real no comprobada.
- HTTP local de API `/health` y `/modelo`: curl no pudo abrir sockets (`Operation not permitted`), diferente del timeout observado por el usuario en su terminal.

**Estado: corrección preparada, no aplicada ni declarada resuelta. Faltan mappings y respuestas HTTP reales en Ubuntu y Windows.** No se continuó ninguna otra fase ni se modificaron aplicaciones, datos o GitHub.

Referencias primarias:

- [Moby: publicación ausente en contenedores conectados solo a bridge interno](https://github.com/moby/moby/discussions/53256).
- [Docker: sintaxis de ports y alcance de mode para Swarm](https://docs.docker.com/reference/compose-file/services/#ports).
- [Docker: publicación, NAT y modo routed](https://docs.docker.com/engine/network/port-publishing/).
