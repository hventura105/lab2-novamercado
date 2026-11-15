# Contexto y continuidad — NovaMercado Laboratorio2

Leer primero los cinco docs/progreso/. Actualizar tras cada tarea importante, antes de operación larga y cada10–15min. No reiniciar el proyecto ni repetir pruebas aprobadas. ESTADO_ACTUAL contiene rutas exactas de informes, Git y checkpoint; docs/RECUPERACION.md explica verificación SHA-256 y restauración en carpeta NUEVA.

## Alcance/autorización vigentes

Trabajar únicamente en /home/gama/product-dev/lab2-novamercado; originales Windows solo lectura. El usuario YA autoriza modificaciones reversibles, dependencias del proyecto, builds, creación/inicio/parada/reinicio de recursos exclusivos del laboratorio, entrenamiento/pruebas y Git/commits locales revisados. No pedir esas autorizaciones otra vez. Pedir autorización específica antes de borrar datos/volúmenes/respaldos, modificar otros proyectos/sistema o publicar GitHub/tag. No ejecutar down -v ni limpiezas globales, no compartir credenciales en Codex.

## Estado verificado

Nueve servicios, contrato ASGI10/10, predicciones/SQL/calidad/422/idempotencia, Registry/champion1, DAG real y replay de promoción/rechazo aprobados. MLflow detección11.4455s/inferencia200/recuperación9.0142s. Persistencia29.6917s, hashes/version iguales. Primer arranque limpio YA aprobado74.4243s, importación/primer modelo automáticos, principal intacto; informe existente en evidence/private/arranque-limpio/20261115t011732z-4299dce5/. No reutilizar plan ejecutado. FileNotFoundError era una variante comprobada T/Z mayúsculas; tooling corregido y19 pruebas aprobadas.

Los datos oficiales ya están copiados/verificados:83052 filas,2024-03-01 a2026-02-28,10 tiendas/12 familias,61 eventos hasta2026-12-31, catálogo y12 ejemplos. Documento oficial siete páginas en data/entrada/Laboratorio_2_PD_26_c.pdf; texto extraído auxiliar. No relocalizar/copiar/entrenar otra vez por defecto. Auditoría y matriz: evidence/AUDITORIA_FINAL.md y docs/REQUISITOS.md.

## Invariantes

API interna8000; servicio mlflow; PostgreSQL del producto independiente de Airflow; DNS por servicios y volúmenes propios. Para pronosticarD solo ventas anteriores aD y artefacto entrenado antes deD; promocionesD desde la solicitud, observaciones sin promociones. No usar now/today para validar fechas simuladas ni inventar ausencias. Validación cronológica, costos cf*max(real-q,0)+cs*max(q-real,0), cantidad entera no negativa. Conservar vigente ante fallo/no mejora; recarga≤120s. Las ventas auténticas disponibles no superan corte2026-02-28: promoción natural productiva y tiempo completo de ese DAG no demostrables; NO manipular alias ni fabricar nuevas observaciones. Replay aislado sí aprobado y medido.

## Único siguiente paso técnico

`pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. Docker ps está denegado en Codex; pip no obtuvo paquetes. No repetir intentos idénticos ni solicitar privilegios globales. Un comando desde Ubuntu: `python3 scripts/verificar_cierre.py`. Construye imagen tests Python3.12 fijada, pytest unitario/contrato sin red, datosRO, JUnit estricto y exportación Git nueva. No repite integrales ni cambia champion. Si informe existe, inspeccionarlo antes de ejecutar otra vez; no aprobar por código/mock solamente.

## Entrega y privacidad

.env/datos oficiales/evidencias privadas/modelos/respaldos fuera de Git e imágenes. Git raíz aparece vacío/protegido y no se toca. Repositorio independiente revisado en evidence/private/entrega/; manifest.json/git.json identifican archivos/commit/estado. No tiene remotos/tags; identidad del commit Codex <codex@local.invalid>, no la del estudiante. Usar scripts/entrega_local.py solo para exportaciones nuevas; no sobrescribir candidatos anteriores. Publicar/tag solo al autorizar el usuario después de revisar pytest. Mantener informes históricos intactos y evidencias públicas sanitizadas.
