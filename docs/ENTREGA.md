# Preparación de entrega GitHub y entrega-lab2

No se ha hecho push ni creado tag. La matriz completa contra siete páginas está en docs/REQUISITOS.md, y la evidencia pública sanitizada en evidence/AUDITORIA_FINAL.md.

- [x] CSV oficiales verificados por hashes;83,052 ventas, fechas/catálogos/costos/referencias auditados.
- [x] Diez contratos ASGI y predicciones HTTP/SQL/calidad/422/idempotencia reales.
- [x] MLflow experimentos/Registry/alias/linaje/artefactos y champion1.
- [x] FastAPI dispara DAG real y consulta resultado; no-promoción legítima preserva vigente.
- [x] Replay real aislado: promoción y rechazo, cambio sin reinicio3.1242s.
- [x] MLflow detección11.4455s, inferencia200 durante caída, recuperación9.0142s.
- [x] Persistencia tras reinicio29.6917s, hashes y versión conservados.
- [x] Primer arranque vacío real74.4243s, importación/entrenamiento/registro automáticos, principal intacto.
- [x] FileNotFoundError diagnosticado y corregido;19 pruebas del ejecutor aprobadas.
- [x] README/DECISIONES/contexto/recuperación y matriz por requisito actualizados.
- [x] Git independiente local preparado con commit y revisión de secretos/índice/estado; root .git vacío preservado. Identidad Codex explícita. Sin remotos ni tags.
- [x] pytest unitario y contrato en framework pytest: `pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. Un comando Ubuntu: python3 scripts/verificar_cierre.py. El script verifica JUnit/exit0/diez contratos sin red, actualiza progreso y genera Git final.
- [x] Limitación documentada: sin ventas auténticas posteriores a2026-02-28 no se fuerza promoción productiva. DAG productivo que realmente entrena/promueve y tiempo completo no acreditados; pipeline aislado sí medido. No exigir datos inventados para tachar esta casilla.
- [ ] Revisar el nuevo informe pytest y el repositorio actualizado; si falla, corregir según su log privado, sin omitir/debilitar tests.
- [ ] Obtener autorización del usuario para repositorio destino/visibilidad/publicación y tag definitivo. Confirmar plazo de entrega docente. No configurar GitHub ni autenticar hasta que la publicación sea solicitada.

## Revisión antes de publicar

El repositorio exportado solo contiene código, configuración, documentación, resúmenes sanitizados y placeholders. .env, datos oficiales, evidencias privadas, respaldos y metadatos Codex/AWS se excluyen. scripts/entrega_local.py verifica secretos conocidos, cabeceras de clave privada, copiasSHA-256, índice permitido, check-ignore, diff --check, estado limpio, sin remotos/tags. Los scripts no usan staging global ciego.

La revisión comprende la historia NUEVA del repositorio exportado (un commit automatizado). El .git raíz no tenía archivos/historia; no se sobrescribió ni se mezcla Laboratorio1. manifest.json y git.json quedan junto al repositorio privado; consultar ESTADO_ACTUAL para su ruta.

Solo después de revisión del informe y autorización: conectar el destino GitHub con el mecanismo seguro, comprobar acceso docente, publicar el commit revisado y crear el tag anotado entrega-lab2 sobre ese commit. No se realiza ninguno de esos pasos automáticamente. No compartir contraseñas/tokens dentro de Codex.
