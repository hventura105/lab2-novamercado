# Arranque limpio: aprobado y diagnóstico resuelto

El informe existente evidence/private/arranque-limpio/20261115t011732z-4299dce5/informe.json acredita **74.4243s** hasta GET /health HTTP200/estado ok, límite600s excluyendo build. No se volvió a ejecutar ni se reutilizaron sus almacenes. Datos oficiales importados83052/10/12/12/61; primer modelo y promoción1; MLflow/artefacto/linaje/imagen comprobados. Principal idéntico antes/después. SHA-256 e inventario en evidence/AUDITORIA_FINAL.md.

## FileNotFoundError concreto

Se reprodujo la traza en ColdStart→load_plan→read_text: no existía la ruta con `20261115T011732Z-4299dce5/plan.json`. La inspección DIRECTA confirmó que el directorio real es `20261115t011732z-4299dce5`, con plan.json, prueba.env, Compose privado e informe aprobado. No faltaba el plan real. La traza original está en evidence/private/diagnostico-final/20261115T053839Z/file_not_found_original.txt.

Corrección: resolver exclusivamente una coincidencia única de mayúsculas entre hermanos; rechazar ambigüedad, carpeta fuera del proyecto y archivos ausentes con mensaje controlado. No cambiar credenciales ni copiar el plan por encima de otro. Diecinueve pruebas específicas aprobadas, incluidas cuatro regresiones nuevas.

Diagnóstico seguro, incluso para la variante utilizada por el usuario:

```bash
python3 scripts/prueba_arranque_limpio.py diagnosticar --plan evidence/private/arranque-limpio/20261115T011732Z-4299dce5
```

Devuelve el directorio real, presencia de fuentes/env/Compose, imágenes configuradas y resultado/hash del informe. No imprime credenciales. Las imágenes se identifican por tags e IDs Docker registrados, no por rutas del sistema de archivos. El diagnóstico sin daemon no acredita que sigan ejecutándose ahora.

**No volver a ejecutar ese plan:** informe.json existente bloquea reutilización deliberadamente. La aprobación es evidencia, no permiso para llamarlo vacío otra vez.

## Procedimiento para otro checkout o un intento nuevo necesario

```bash
python3 scripts/prueba_arranque_limpio.py preparar
python3 scripts/prueba_arranque_limpio.py validar --plan <carpeta-impresa>
python3 scripts/prueba_arranque_limpio.py ejecutar --plan <carpeta-impresa> --autorizar-recursos
```

La misión vigente autoriza recursos exclusivos de estas pruebas; no hace falta pedir esa autorización otra vez. Cada plan genera credenciales propias0600, proyecto único, nueve contenedores, dos redes y cinco volúmenes nuevos. PostgreSQL y MLflow locales por DNS; cero puertos publicados; datos/scripts read-only. Se bloquean recursos previos, volúmenes externos, montajes escribibles, host network y privilegios. No se incluyen modelos previos.

Antes de cronometrar se validan Compose e imágenes ya disponibles y se capturan contenedores/huellasSQL/modelo/alias del principal, sin entrenamiento activo. Desde ANTES de compose up -d --no-build --pull never --no-recreate hasta health ok se cuentan creación, inicialización, importación, entrenamiento y registro. Las sondas no ayudan al bootstrap: solo leen. Después se verifican counts/hashes/Registry/artefactos/código y principal antes/después. Cualquier discrepancia o duración>600s impide aprobar.

No hay borrado ni parada automáticos, tampoco después de un timeout; se conservan recursos y evidencias. Nuevos recursos consumen memoria/CPU/disco. No ejecutar por repetición si ya existe evidencia aprobada suficiente.

## Único pendiente operativo actual

No repetir arranque, resiliencia ni persistencia. Desde Ubuntu ejecutar `python3 scripts/verificar_cierre.py` para pytest aislado y exportación Git revisada. La promoción productiva natural queda limitada por falta de observaciones auténticas posteriores al champion, no por este problema de rutas.
