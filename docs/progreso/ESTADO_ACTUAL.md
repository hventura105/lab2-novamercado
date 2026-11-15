# Estado actual — misión final

Fecha UTC: 20261115T054953Z. Trabajar únicamente en este Laboratorio2. Producto y primer arranque real acreditados; no volver a empezar ni repetir las integrales aprobadas.

## Hallazgo resuelto y resultados

- El FileNotFoundError se reprodujo en la ruta con T/Z mayúsculas. El directorio real usa t/z minúsculas y contiene plan/env/Compose e informe aprobado. Corrección segura: coincidencia única entre hermanos directos; diagnóstico explícito de archivos internos faltantes y bloqueo de planes ejecutados.19 pruebas relacionadas aprobadas.
- Primer arranque real YA APROBADO en74.424332s, límite600s sin build, proyecto independiente y cinco volúmenes nuevos. Importación83052/10/12/12/61, modelo inicial/Registry/artefacto/linaje/health comprobados; principal antes/después idéntico.
- Diez ASGI, HTTP/SQL/calidad/422/idempotencia, MLflow Registry/champion1, DAG real y replay de promoción/rechazo aprobados.
- Replay: entrenamientos8.8219/9.9570s; cambio de versión3.1242s sin reiniciar; alcance aislado.
- MLflow detección11.4455s, predicción200 durante caída, recuperación9.0142s. Reinicio29.6917s, hashes/version conservados.
- Código producto sin cambios:17 archivos, manifest b97fc83ad597459ed696775d9cf690f762931919f87cdc3e2359efbf13ded19d; evidencia anterior sigue aplicando.

## Informes reales en disco

| Ruta | Resultado y SHA-256 |
| --- | --- |
| evidence/private/integration/20261115T005651Z-8d163828/informe.json |ASGI aprobado; d52c8d6e0cd7ce5c4b3801c67e258c795f8bed8bb7f2f8d5a251b2611fa5ea87 |
| evidence/private/integration/20261115T010229Z-57c9fd3e/informe.json |HTTP/SQL/Registry/DAG/replay aprobados por alcance; b20c690916e01fe9054a292a8659f0f4cac74703e3e28baa1c292359740640fc |
| evidence/private/integration/20261115T010528Z-7388a7e1/informe.json |Resiliencia/persistencia aprobadas;9399a6e8a4d3fbf559830bb955c2d4ad765718845d61e5bf1b6744411b543aeb |
| evidence/private/arranque-limpio/20261115t011732z-4299dce5/informe.json |Arranque aprobado74.4243s;26c5b8a716ab61897c4614b0b4363c683a74ef909a19816138c5bd957a84a37a |

Los informes anteriores incompletos/fallidos son históricos, permanecen intactos. La auditoría pública y matriz completa son evidence/AUDITORIA_FINAL.md y docs/REQUISITOS.md; no subir JSON privados.

## Única verificación técnica ejecutable pendiente

`pytest`: aprobado; ver evidence/PYTEST_VERIFICADO.md. Los contratos sí pasaron en unittest real de imagen; no confundir framework con servicios. En Codex Docker ps está denegado, y pip no obtuvo paquetes en la nueva .venv (sin instalaciones del sistema). No repetir intentos idénticos ni pedir contraseñas/sudo.

Un comando desde Ubuntu, desde cualquier directorio:

```bash
python3 /home/gama/product-dev/lab2-novamercado/scripts/verificar_cierre.py
```

Construye SOLO imagen de tests, monta datos read-only, ejecuta pytest unitario/contratos sin red; exige JUnit/exit0 y diez contratos, actualiza evidencia y exporta Git nuevo. No toca servicios/champion, no repite integrales ni arranque. Imagen/contenedor se conservan; sin limpieza. Intento desde Codex quedó bloqueado en daemon, sin crear recursos: evidence/private/cierre/20261115T054352Z-d544884d/informe.json.

## Limitación legítima

Champion1 entrenado hasta2026-02-28; fuentes auténticas terminan ese día. No hay siete días nuevos demostrables; feriados no son etiquetas. DAG productivo aprobó sin promover (aprox2.43s). Promoción natural por DAG, su entrenamiento completo y recarga productiva no se pueden demostrar con esas fuentes; replay aislado sí aprobado. No fabricar ventas, recortar base productiva ni manipular alias para cerrar una casilla.

## Git y protección

.git raíz aparece vacío/protegido en este entorno: no se alteró. Se creó Git independiente con revisión de secretos/índice/whitespace/check-ignore/historia, identidad Codex local, sin remotos/tags. Punto estable previo: evidence/private/entrega/20261115T054528Z-81de3e6a/repositorio (commit0d16b2910f10b98ef3c91b4d0ab4596fb570334f).

Entrega final: `evidence/private/entrega/final-20261115T054953Z/repositorio`; manifest.json/git.json junto a ella registran hash de archivos, commit y estado limpio. El comando Ubuntu generará otra entrega actualizada tras pytest y escribirá la ruta en su informe.

Checkpoint final: `evidence/private/checkpoints/mision-final-20261115T054953Z/codigo.tar.gz`, sha256.json y RECUPERAR.md. No incluye datos oficiales, secretos, JSON privados, modelos ni volúmenes; evidencias y respaldos anteriores se conservan. No push ni entrega-lab2. Estado raíz/source y copia Git se revisan antes de publicar.

## Continuación exacta

Lee AGENTS y los cinco docs/progreso; luego inspecciona el informe nuevo de verificar_cierre.py si el usuario ejecutó el único comando Ubuntu. Si pytest falla, usar logs privados sin secretos y corregir solo la causa real. Si aprueba, revisar Git actualizado y preparar autorización de GitHub/tag; no repetir pruebas aprobadas ni iniciar recursos de nuevo por defecto. Mantener la limitación de promoción natural documentada. Guardar otro checkpoint al finalizar.

Cierre automático: pytest aprobado, {"tests": 167, "failures": 0, "errors": 0, "skipped": 0, "contratos_asgi": 10}; informe evidence/private/cierre/20261115T060616Z-0705ebbc/informe.json. No se repitió el arranque ni se tocó champion.
