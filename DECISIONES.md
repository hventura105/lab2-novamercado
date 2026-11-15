# Decisiones técnicas y de producto

## Fuentes y fechas

Se auditaron las fuentes reales y sus hashes; ver docs/DATOS.md. Importación estricta y transaccional, sin reparaciones silenciosas en CSV de entrenamiento. Cambios en fuentes ya importadas bloquean el bootstrap para revisión. La migración 001 es aditiva; cambios posteriores requieren otra migración, no editar una aplicada.

Las fechas válidas dependen del histórico y del calendario, nunca de now/today. Para D solo ventas < D. Un artefacto entrenado hasta D no puede pronosticar D. Para repetir una fecha después de un reentrenamiento se conservan las promociones anteriores y se selecciona una versión promovida con corte < D; nunca un candidato inferior o información futura. La respuesta identifica la versión elegida y /modelo describe la activa por defecto. La fecha ilustrativa de los ejemplos no sustituye los límites reales. Las ausencias antes de apertura no se convierten en ceros. Para huecos posteriores, características y avisos usan únicamente observaciones existentes: el núcleo temporal conserva None; la representación numérica de ridge puede usar la escala pasada como referencia y contadores/gap, sin insertar ventas en los datos. Promociones desconocidas se conservan como None y se codifican con indicador de ausencia, sin afirmar que hubo cero promociones.

Los eventos nacionales aplican a todas las tiendas, los locales solo a su ciudad exacta del catálogo. Dentro de la cobertura publicada, ausencia de evento significa ningún evento listado; después del último día conocido se rechaza por falta de calendario. No hay duración fija del periodo de evaluación.

## Defensa del contrato

| Problema | Política y motivo |
| --- | --- |
| Tienda como número textual o T05 | Reparar representación inequívoca contra catálogo. |
| Campo tienda en vez de tienda_id | Reparar si único o ambos equivalen; rechazar contradicción. |
| Familia con mayúsculas, tildes, espacios, nombre o identificador | Normalizar contra alias del catálogo solo si existe una única coincidencia; no coincidencias difusas. |
| Promoción textual o decimal integral | Convertir exactamente e informar; fraccionaria, negativa, booleano o ausente: 422. |
| Fecha ISO con espacios o timestamp de medianoche | Reparar sin cambio de día. Otros horarios/desplazamientos no se infieren. |
| Fecha con barras | Reparar solo si día/mes son inequívocos; 03/04/2026 se rechaza. |
| Familias omitidas | Advertir; devolver/procesar únicamente las recibidas, sin inventar promociones o ventas. |
| Duplicados idénticos dentro de lista | Consolidar e informar reparación. |
| Duplicados contradictorios | Rechazar toda la solicitud, sin escritura parcial de observaciones. |
| Ventas negativas | Rechazar; convertir a cero inventaría la demanda real. |
| Número con coma decimal de una/dos cifras | Convertir y registrar reparación, por ejemplo 50,0. |
| Número con coma y tres cifras | Rechazar si ambiguo, incluidos 1,292 y 1,000. Se pide número JSON o punto decimal. |
| Agrupación de miles con varias comas completas | Reparar solo agrupación inequívoca de tres cifras. |
| Nulos, no finitos, booleanos, desconocidos y campos extra | Rechazar con explicación. Límite numérico de 10^12 para cantidades de entrada; listas hasta 1000 elementos. |
| Observación idéntica a otra solicitud | UPSERT sin UPDATE cuando ventas no cambian; registros_guardados=0. |
| Observación corregida | Actualizar y contar, manteniendo auditoría de ambas solicitudes. |
| Huecos recientes de observaciones | Advertir y usar solo observaciones anteriores disponibles. |

Cualquier acción advertir prevalece en calidad.estado sobre reparar. Las reparaciones son deterministas y no añaden valores desconocidos. El catálogo es ilustrativo: se aplican principios generales, no una lista cerrada de JSON aceptados. Los valores ambiguos se rechazan aunque aparezcan como ejemplos de errores.

Pydantic valida estructura; limpieza semántica está separada. Las solicitudes válidas y rechazos se registran en PostgreSQL, incluyendo calidad; no se imprimen cuerpos privados en logs. Los errores de dependencias se devuelven sin DSN/SQL/secretos. El registro de un rechazo no se puede garantizar si PostgreSQL está caído; los endpoints no confirman escrituras en ese caso.

## Datos y transacciones

PostgreSQL del producto tiene esquema novamercado, separado de otra instancia para Airflow. Fuentes inmutables y observaciones operativas viven en tablas distintas. Las observaciones prevalecen al construir el snapshot por clave (tienda,familia,fecha); el histórico original permanece intacto. Las observaciones futuras nunca entran en características de un día anterior.

Cada solicitud y sus predicciones/observaciones se confirman en una misma transacción. La clave de observaciones garantiza idempotencia incluso concurrente; IS DISTINCT FROM evita contar repeticiones. Se registra cada pronóstico repetido con otro identificador de solicitud. FK y CHECK protegen integridad y cantidades.

## Modelado y costo

Baseline: media de mismo día de semana en ocho semanas anteriores, con respaldo en media pasada si falta contexto. Ridge por familia aprende coeficientes sobre demanda escalada por media anterior, rezagos/medias, calendario, promociones y eventos. Se eligió una implementación pequeña de ecuaciones normales con regularización/pivoteo para mantener inferencia JSON y entrenamiento rápido sin paquetes numéricos adicionales. Los coeficientes son aprendidos, no reglas asignadas manualmente.

El ajuste no usa los últimos 28 días de su entrenamiento: esos días calibran residuos normalizados. El bloque de evaluación comienza después de todos los días de ajuste/calibración. La evaluación es diaria: a cada nuevo día se incorporan ventas de días anteriores para características, sin reajustar coeficientes con etiquetas del bloque. Esto reproduce la llegada de observaciones definida por el enunciado.

Cantidad sugerida: minimizar cf*max(real-q,0)+cs*max(q-real,0) usando distribución empírica de residuos de calibración anterior. El cuantil objetivo es cf/(cf+cs); comparar los enteros vecinos y cero, con menor inventario en empate. La alternativa de redondear siempre la venta media no respeta costos asimétricos. No se usa el bloque de validación para calibrar cantidades.

En la validación real 2026-01-04–2026-02-28, 6720 filas: ridge MAE 45.2965, RMSE 83.0346 y costo 220691.70; baseline MAE 53.6474, RMSE 95.5896 y costo 296985.30. Se ha comprobado mejora en este bloque, no en fechas ocultas. La medición local repetida duró 9.50 segundos; no prueba tiempos de Docker ni del DAG.

## MLflow, promoción y resiliencia

MLflow 3.10.1 mantiene Tracking y Registry en backend SQL SQLite con artefactos persistentes y proxy. Adecuado a baja concurrencia del laboratorio; mayor concurrencia requeriría migración revisada a backend propio. No comparte su backend con tablas del producto o de Airflow.

Runs de baseline/ridge y refit distinguen evaluación del reajuste final. Artefactos JSON/MLmodel de flavor propio novamercado_json, métricas/hiperparámetros y linaje con hashes de fuentes, snapshot combinado y código. Evita pickle y permite al runtime cargar sin SDK ni servidor MLflow. El alias champion identifica la versión promovida. El soporte REST está basado en los protos oficiales de la versión fijada. Runs, Registry, alias y artefactos ya se verificaron contra MLflow real desde Ubuntu; informes indexados en evidence/CIERRE_VERIFICADO.md.

Criterio: costo al menos 1% menor y MAE no más de 5% peor. Para reentrenamiento, evaluar solamente días posteriores al entrenamiento del vigente; mínimo siete días nuevos, hasta 28 en validación. Si faltan días, terminar exitosamente sin promover ni inventar evidencia. Si hay datos, registrar también candidatos que no superan la regla, manteniendo el vigente.

Primero registrar y persistir candidato; luego actualizar alias y confirmar puntero activo/resultado de ejecución en una transacción PostgreSQL. Si la confirmación falla, intentar restaurar alias anterior. No existe transacción distribuida entre MLflow y PostgreSQL: ante cierre abrupto entre operaciones, salud detecta discrepancia. La reconciliación periódica bajo el lock de entrenamiento restaura el alias a la versión activa confirmada. Los fallos de compensación/reconciliación requieren evidencia integral y supervisión; no se afirman verificados con dobles.

El artefacto activo reside además en PostgreSQL JSONB y en memoria: inferencia no consulta MLflow. Se puede reiniciar y recuperar desde la base sin reentrenar innecesariamente. Refresco cada 20 s e inmediato tras promoción, sin reinicio manual. Salud comprueba PostgreSQL, MLflow/alias y componentes de Airflow en cada solicitud, con timeouts. Si falta modelo responde 503; si hay modelo y una dependencia falla, degradado. La integral real midió detección en11.4455s y recuperación en9.0142s, con predicción HTTP200 durante la caída. El reinicio conservó hashes/modelo y alcanzó health ok en29.6917s. La recarga de versión aprobó en replay aislado; no equivale a promoción productiva por DAG.

## Airflow y operación

Airflow 3.1.7 usa SDK público, api-server, scheduler LocalExecutor, dag-processor y triggerer. Un DAG manual con una tarea ejecuta por HTTP autenticado el pipeline del producto, que lee histórico/observaciones de PostgreSQL, ajusta/evalúa/registra/promueve y deja estado. No usa la base de metadatos como base del producto. max_active_runs=1 y lock PostgreSQL evitan promociones concurrentes.

DAG máximo 10 min, tarea 9 min, solicitud remota 530 s y presupuesto de entrenamiento 480 s. Estos son límites configurados, no tiempos comprobados en el entorno objetivo. Ejecuciones abandonadas expiran a fallido tras diez minutos operativos. El reloj para duración y auditoría no se usa para validar fechas de pronóstico.

Se conservan nueve servicios, cinco volúmenes, red privada y puertos loopback. Se agregaron montaje de datos solo lectura y token interno; no se borraron recursos. Las credenciales admin Airflow se entregan al backend para su API; el token interno es diferente y no va en imágenes. SimpleAuthManager se usa en este laboratorio local, sin proponer exposición externa de producción.

## Verificación y referencias

La evidencia anterior de Fase 1 se conserva como histórica. La matriz y progreso distinguen implementación, tests locales, evaluación real de datos e integración real. Docker/pytest/servicios no ejecutados no se marcan aprobados. No se crearon commits por Git no utilizable ni tag/push.

Fuentes primarias consultadas:

- [Airflow 3.1.7: interfaz pública y Task SDK](https://airflow.apache.org/docs/apache-airflow/3.1.7/public-airflow-interface.html).
- [Airflow 3.1.7: salud y contenido de monitor/health](https://airflow.apache.org/docs/apache-airflow/3.1.7/administration-and-deployment/logging-monitoring/check-health.html).
- [Airflow 3.1.7: ruta de autenticación SimpleAuthManager](https://github.com/apache/airflow/blob/3.1.7/airflow-core/src/airflow/api_fastapi/auth/managers/simple/routes/login.py).
- [MLflow 3.10.1: protocolo REST de Model Registry y alias](https://github.com/mlflow/mlflow/blob/v3.10.1/mlflow/protos/model_registry.proto).
- [MLflow 3.10.1: protocolo REST de Tracking](https://github.com/mlflow/mlflow/blob/v3.10.1/mlflow/protos/service.proto).

## Primer arranque aislado y entrega

El primer arranque Docker vacío ya aprobó en74.4243s: proyecto propio, fuentes/modelo inicial automáticos y principal idéntico antes/después, informe indexado en evidence/AUDITORIA_FINAL.md. scripts/prueba_arranque_limpio.py deriva el Compose en un proyecto único con cinco volúmenes y dos redes propios, sin publicaciones, sin builds/pulls y con credenciales nuevas. Verifica imágenes y ausencia de recursos antes de up; mide con monotonic desde antes de compose up hasta HTTP200/estado ok en≤600s. Las sondas posteriores son de solo lectura: comparan fuentes, modelo/Registry/artefacto y recursos reales. No invocan importación ni entrenamiento para ayudar al producto. Se comparan contenedores, hashes SQL y alias del principal antes/después, aun si falla. No hay borrados, paradas ni restauraciones automáticas.

Preparar y validar config no crea recursos; ejecutar exige autorización explícita. Los recursos quedan disponibles para diagnóstico y consumen capacidad hasta una decisión posterior. Los secretos/Compose resuelto/reportes permanecen privados. Se rechaza reutilizar un plan intentado para no llamar limpio a un arranque con almacenes anteriores. Esta prueba no necesita publicar puertos ni cambiar el puerto interno8000.

La instalación usa rutas relativas al checkout; los CSV oficiales y credenciales son prerrequisitos externos excluidos de Git/imágenes. Los respaldos de código no sustituyen los volúmenes ni la evidencia privada. docs/ENTREGA.md mantiene pendientes la revisión de Git y la autorización de publicación/tag; no se ha realizado ninguna.

## Auditoría final y límites demostrables

El FileNotFoundError se reprodujo al leer plan.json en una variante con T/Z mayúsculas; el directorio real tenía t/z minúsculas. Se resuelven únicamente coincidencias únicas entre hermanos directos, se rechazan ambigüedades/salidas de la carpeta privada y se identifican archivos faltantes sin exponer secretos. Diagnosticar puede leer un plan ejecutado; ejecutar/validar siguen rechazando reutilizar sus volúmenes. El informe aprobado existente se conservó íntegro, sin lanzar otra instancia para aparentar una prueba nueva.

Las ventas oficiales terminan en2026-02-28, también corte del champion1. Feriados futuros no son etiquetas. Las observaciones de integración son históricas y no habilitan siete días nuevos. No es legítimo fabricar ventas o recortar el histórico productivo: se conserva como limitación la promoción natural por DAG y su cronometraje completo. El replay auténtico aislado sí demuestra promoción/rechazo y recarga3.1242s, con entrenamientos menores de10s. El DAG productivo existente aprobó sin promover por insuficiencia de datos; no se presenta esa ejecución como entrenamiento completo.

Pytest no está instalado en Codex y pip no pudo obtener las dependencias; Docker sigue denegado. No son fallos demostrados del modelo ni motivo para cambiar versiones que ya funcionan en imágenes reales. Se añadió una imagen de prueba separada Python3.12, requirements-test fijado y red none en ejecución, sin ampliar la imagen de producción. Un comando Ubuntu acredita pytest y genera evidencia/JUnit y Git actualizados. Hasta verlo aprobado, se mantiene el pendiente explícito.

El .git raíz vacío/protegido no se sobrescribe. La alternativa elegida es exportar solo archivos permitidos a un repositorio nuevo privado y portable, revisar valores de secretos conocidos y claves privadas, índice y whitespace, y crear un commit con identidad de automatización Codex. Se conservan manifest/hash/estado/historia, sin hooks externos, firma interactiva, remotos, push o tag. Esto evita mezclar Laboratorio1 y no exige permisos globales.
