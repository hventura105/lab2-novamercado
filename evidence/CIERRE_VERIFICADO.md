# Evidencia consolidada del laboratorio

Fuente: informes reales ejecutados por el usuario en Ubuntu e inspeccionados en disco por Codex. Los JSON completos son privados y permanecen excluidos de Git. No se han convertido estados globales incompletos en aprobados.

| Informe privado relativo al repositorio | Alcance aprobado |
| --- | --- |
| `evidence/private/integration/20261115T005651Z-8d163828/informe.json` | Diez ASGI, cero errores/fallos/omitidas; estado global aprobado solo para ese alcance |
| `evidence/private/integration/20261115T010229Z-57c9fd3e/informe.json` | HTTP/SQL/calidad/idempotencia, Registry/alias/artefactos, DAG y promoción real aislada; global incompleto |
| `evidence/private/integration/20261115T010528Z-7388a7e1/informe.json` | HTTP/SQL/Registry/DAG, resiliencia MLflow y persistencia; global incompleto |

SHA-256, respectivamente:

```text
d52c8d6e0cd7ce5c4b3801c67e258c795f8bed8bb7f2f8d5a251b2611fa5ea87
b20c690916e01fe9054a292a8659f0f4cac74703e3e28baa1c292359740640fc
9399a6e8a4d3fbf559830bb955c2d4ad765718845d61e5bf1b6744411b543aeb
```

- MLflow: degradación detectada en11.4455s; predicción HTTP200 con MLflow detenido; recuperación a ok en9.0142s.
- Reinicio:29.6917s hasta health ok; los hashes de datos comprobados coinciden y se conserva la versión del modelo.
- Champion productivo:1. El replay aprobado usa esquema/modelo propios, conserva recursos y no constituye promoción productiva por DAG.
- Antecedente:106 pruebas locales aprobadas. No sumar baterías solapadas de sesiones posteriores como si fueran pruebas distintas.
- Sesión de cierre:15 pruebas locales específicas del ejecutor de arranque limpio aprobadas, y docker compose config válido para el plan aislado. No se inició ese stack.

Actualización: primer arranque limpio APROBADO en74.4243s, informe y SHA-256 en evidence/AUDITORIA_FINAL.md. Sigue limitada por datos la trayectoria completa de promoción productiva natural por DAG; el replay sí aprobó. `pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. No se publicará ni creará tag hasta revisar el cierre completo. No se atribuyen integrales del usuario a ejecución propia de Codex.
