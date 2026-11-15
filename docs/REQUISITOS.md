# Matriz completa de cumplimiento

Fuente: documento oficial siete páginas; auditoría y hashes en evidence/AUDITORIA_FINAL.md. Resultados de servicios: informes Ubuntu existentes inspeccionados, no ejecución Docker propia de Codex. Claves de evidencia: **A**=integration/20261115T005651Z-8d163828; **B**=integration/20261115T010229Z-57c9fd3e; **C**=integration/20261115T010528Z-7388a7e1; **D**=arranque-limpio/20261115t011732z-4299dce5. Todas parten de evidence/private/ y contienen informe.json.

| Requisito académico | Implementación | Prueba | Resultado | Evidencia | Pendientes/límites |
| --- | --- | --- | --- | --- | --- |
| p2/6 POST prediccion, campos/tipos exactos |main.py, schemas/contrato.py, runtime.py |Contrato ASGI y HTTP/SQL, solicitudes repetidas |APROBADO |A/B/C |No garantiza desempeño futuro |
| p6 Calidad ok/corregido/advertencia y acciones |limpieza.py y modelos Pydantic |Ejemplos oficiales y HTTP, precedencia advertir |APROBADO |A/B/C |Reglas generales documentadas |
| p6 Rechazos422 con detail |Handlers y limpieza separados |Estructura/semántica, ambiguos y datos desconocidos |APROBADO |A/B/C |Errores no listados se rigen por mismas reglas |
| p6/7 POST observaciones, conteo nuevos/modificados |Repositorio y UNIQUE/UPSERT |Repetición real y auditoría SQL |APROBADO |A/B/C |Sin inventar promociones observadas |
| p7 POST admin sin cuerpo,202/id o503 |Runtime y cliente Airflow |ASGI/fallo de cliente y disparo real |APROBADO |A/B/C |Fallo real de Airflow no inducido; rama503 tiene dobles |
| p7 GET estado ejecución,404 desconocido |Repositorio/Runtime/cliente estado |Contrato y ejecución real, tareas success |APROBADO |A/B/C |Promoción real productiva pendiente de datos |
| p7 GET modelo tres textos activos |Modelo en memoria y punteroSQL |ASGI y HTTP/Registry |APROBADO |A/B/C/D |Champion1 |
| p7 GET health200 ok/degradado;503 sin modelo |Sondas y runtime |ASGI503, caída real y arranque |APROBADO |A/C/D |Degradación200 no equivale a ok |
| p2 Contrato pytest sin MLflow activo |pytest.ini/conftest/tests y Docker tests |Diez ASGI unittest pasados; imagen pytest sin red preparada |`pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md |A; cierre/20261115T054352Z-d544884d bloqueado |Un comando Ubuntu, no afirmar pytest aprobado |
| p3 PostgreSQL separado de Airflow |Dos servicios/bases/volúmenes |Inventario real y consultas |APROBADO |B/C/D |Sin puertos PostgreSQL públicos |
| p3 Guardar solicitudes/predicciones/correcciones/observaciones |Migración001, transacciones y calidadJSONB |Comparación HTTP/SQL |APROBADO |B/C |Rechazo no auditable si PostgreSQL caído, documentado |
| p3 Idempotencia y conservación |UNIQUE/UPSERT y cinco volúmenes |Observación repetida y reinicio con hashes |APROBADO |B/C |Ningún volumen borrado |
| p2 Fechas simuladas y observaciones anteriores |temporal.py, Sources y cortes temporales |Unitarias/no-fuga/replay con fuentes reales |APROBADO por alcance |B y tests/test_temporal_costos.py |Sin usar now/today para validez; fechas futuras no son ventas |
| p2 PromocionesD desde solicitud; observaciones sin promoción |Limpieza y combinación histórico/observaciones |Unitarias y replay sin promociones inventadas |APROBADO |B y tests/test_producto.py |Días faltantes no se inventan |
| p3 Baseline y ML que mejora |Baseline semanal y ridge aprendida |Holdout cronológico real6720 filas |APROBADO |evidence/AVANCE_PRODUCTO.md; B |MAE45.2965 vs53.6474; costo220691.70 vs296985.30 |
| p2/3 Costos y cantidad sugerida |Cuantil cf/(cf+cs), vecinos enteros |Optimizador/costos y validación real |APROBADO |tests/test_temporal_costos.py;B |No calibrar con bloque evaluado |
| p3 Experimentos/modelos/linaje/alias |Tracking REST y artefactos JSON/JSONB |Runs/params/métricas/hash/Registry reales |APROBADO |B/C/D |Datos/credenciales fuera de imagen/Git |
| p3 Criterio automático promoción |Costo≥1% mejor, MAE≤5% peor |Candidato promovido y candidato inferior |APROBADO aislado |B |No forzar alias productivo |
| p3 DAG usa histórico+observaciones; dispara/consulta |DAG SDK3.1.7, endpoint interno autenticado, SQL |DAG real y pipeline aislado |APROBADO por alcance |B/C |DAG productivo sin siete días nuevos termina sin promover |
| p3 No reiniciar API al promover,≤120s |refresh20s e inmediato |Servidor de replay sin reinicio,3.1242s |APROBADO aislado |B |Promoción productiva no demostrable con fuentes actuales |
| p3 Mantener vigente si falla/no mejora |Locks/compensación/puntero confirmado |Rechazo real aislado; fallos y compensación unitarios |APROBADO por alcance |B;tests/test_ciclo.py |No atribuir compensación distribuida a prueba real |
| p4 Reentrenamiento≤600s |Presupuestos480/530/540/600s |Pipeline real8.82/9.96s; DAG sin entrenamiento2.43s |MEDIDO por alcance |B/C y DAG |DAG productivo que entrena/promueve no medido por falta de datos |
| p3 Compose up con servicio mlflow y versiones fijas |compose.yaml y Dockerfiles |Config e inventario de9 servicios |APROBADO |B/C/D |Build excluido del cronómetro |
| p3/4 Primer arranque automático≤600s |Bootstrap/registro sin modelo previo |Proyecto nuevo,5 volúmenes, importación/Registry/health |APROBADO74.4243s |D |No repetir ni reutilizar sus volúmenes como vacíos |
| p3 Arranques siguientes sin repetir entrenamiento |Puntero y respaldo persistido |Reinicio real, mismas huellas/modelo |APROBADO29.6917s |C |Respaldo código no sustituye backup de bases |
| p3 MLflow caído: inferir y detectar<60s |Inferencia con modelo en memoria |MLflow detenido, predicción200 |APROBADO11.4455s |C |Otros fallos concurrentes no inducidos |
| p3 Recuperación MLflow<120s |Sondas sin depender de reinicio |Retorno real a health ok |APROBADO9.0142s |C |Medición del entorno objetivo |
| p3 Env ejemplo/datos y secretos fuera |.env.example/.gitignore/.dockerignore, bindRO |Escaneo conocido y revisión Git de exportación |APROBADO por revisión |manifest.json/git.json de entrega local |No subir evidencia privada ni CSV |
| p4 Contexto/README/DECISIONES y alternativas |AGENTS y docs de operación/recuperación |Lectura y auditoría de7 páginas |PREPARADO |docs/ y evidence/AUDITORIA_FINAL.md |Mantener límites explícitos |
| p5 Evidencia experimentos/DAG/API |Informes privados y resúmenes sanitizados |Hashes y resultados reales inspeccionados |APROBADO por alcance |A/B/C/D |JSON originales privados no se publican |
| p4/5 GitHub/tag/acceso docente |Repositorio Git local independiente, sin remotos/tags |Índice permitido, secretos, diff/status e historia |PREPARADO local |evidence/private/entrega/ |Autorización y destino GitHub; no crear tag definitivo aún |

Estado general: producto y primer arranque acreditados en los alcances descritos. No se declara cierre completo mientras pytest no tenga ejecución real. La promoción productiva natural tiene una limitación legítima de datos; conservar y explicar su evidencia aislada.
