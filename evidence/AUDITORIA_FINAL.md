# Auditoría final contra el documento oficial de siete páginas

Fuente: data/entrada/Laboratorio_2_PD_26_c.pdf, SHA-256 `13f8999da23f8afff9583ae5d300efafc01c7698340d9efaeaa26184578967ff`; se contrastaron las siete páginas de su extracción local y el contrato de los mensajes del usuario. El PDF/datos oficiales no se incorporan a Git. Matriz detallada: docs/REQUISITOS.md.

## Primer arranque real ya aprobado

Informe Ubuntu: `evidence/private/arranque-limpio/20261115t011732z-4299dce5/informe.json`. SHA-256 `26c5b8a716ab61897c4614b0b4363c683a74ef909a19816138c5bd957a84a37a`. Resultado aprobado en **74.4243 segundos**, sin build, sin acciones manuales de importación/entrenamiento después de up. Proyecto y cinco almacenes nuevos, nueve contenedores y cero puertos publicados. Los estados, hashes SQL, modelo/alias y contenedores del principal coinciden antes/después.

Se importaron83052 filas históricas,10 tiendas,12 familias/costos y61 eventos. Observaciones/solicitudes/reentrenamientos de prueba:0. Primer modelo/primera promoción:1. MLflow READY/champion1, artefacto igual a PostgreSQL, baseline/ridge con métricas y linaje comprobados. /modelo y /health HTTP200. La imagen coincidió con17 archivos del producto. No repetir esta prueba ni vaciar sus volúmenes.

## Resultados reales conservados

| Alcance | Resultado | Informe privado |
| --- | --- | --- |
| Diez contratos ASGI |10 aprobados,0 fallos/errores/omitidos |integration/20261115T005651Z-8d163828 |
| HTTP, PostgreSQL, calidad/422, idempotencia, Registry y DAG |Aprobados |integration/20261115T010229Z-57c9fd3e e integration/20261115T010528Z-7388a7e1 |
| Promoción/rechazo y cambio sin reiniciar, aislados |1 promoción y1 rechazo; recarga3.1242s; entrenamientos8.8219/9.9570s; total55.4650s |integration/20261115T010229Z-57c9fd3e |
| MLflow detenido |Detección11.4455s; predicciónHTTP200; recuperación9.0142s |integration/20261115T010528Z-7388a7e1 |
| Persistencia tras reinicio |Health ok29.6917s; hashes y versión conservados |integration/20261115T010528Z-7388a7e1 |
| Primer arranque limpio |74.4243s y principal sin cambios |arranque-limpio/20261115t011732z-4299dce5 |

Las rutas abreviadas parten de evidence/private/. Los informes de integración conservan su estado global incompleto histórico: no se editan para simular éxito. La evidencia nueva complementa sus alcances.

Ejemplos completos de respuestas válidas/defectuosas están en los casos `predicciones_http_y_auditoria_sql` y `calidad_reparaciones_advertencias_422` de esos JSON privados. Sus montos/entradas originales no se publican. La evidencia pública conserva contratos, estados, agregados y hashes. Respuestas no sensibles observadas:

```json
{"estado":"ok"}
{"nombre":"novamercado_ventas_diarias","alias":"champion","version":"1"}
```

Los controles reales verificaron enteros no negativos, versión textual, estado advertencia cuando coexistieron reparar/advertir,422 con detail y registros_guardados0 al repetir observación. No sustituir estos resultados por mocks.

## Límites explícitos

- La última versión productiva se entrenó hasta2026-02-28, máximo de todas las ventas auténticas oficiales disponibles. Las observaciones de integración corresponden al histórico; no aportan siete días nuevos posteriores. Las fechas futuras de feriados contienen eventos, NO etiquetas de ventas. Sin datos nuevos auténticos no puede demostrarse una promoción natural productiva ni cronometrar un DAG productivo que realmente ajuste/promueva. No se fabricaron observaciones, recortó el histórico productivo ni modificó el alias manualmente.
- El DAG real terminó exitosamente en aproximadamente2.43s, sin promover por evidencia insuficiente. Eso comprueba disparo/consulta/seguridad, no el tiempo de entrenamiento productivo completo. El pipeline sí entrenó/promovió y rechazó en el replay real aislado, bajo600s; la recarga aislada estuvo bajo120s. Son alcances diferentes.
- `pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. Diez ASGI pasaron mediante unittest en imagen; ejecutar el framework pytest es una verificación adicional obligatoria. El host no dispone de dependencias, pip no pudo obtenerlas y Docker está denegado en Codex. Un único comando Ubuntu completa pytest en una imagen Python3.12 propia, sin red durante pruebas, y exporta un Git local actualizado: `python3 scripts/verificar_cierre.py`.
- No se ha publicado GitHub ni creado entrega-lab2. Requiere autorización. El .git raíz está vacío y protegido; se prepara un repositorio independiente revisado dentro de evidence/private/entrega/, sin tocarlo.
