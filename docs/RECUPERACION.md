# Recuperar y continuar sin perder trabajo

Leer AGENTS.md y los cinco docs/progreso/. El primer arranque YA aprobó en74.4243s: no repetirlo ni reutilizar el plan ejecutado. Los informes originales y respaldos anteriores se conservan. La última misión autoriza operaciones reversibles y recursos exclusivos, pero no borrados, push o tag.

## Respaldo de código

Último checkpoint previsto/completado: `evidence/private/checkpoints/mision-final-20261115T054953Z/codigo.tar.gz`, manifiesto sha256.json y RECUPERAR.md. Verificar antes de restaurar:

```bash
python3 - <<'PYVERIFY'
from pathlib import Path
import hashlib,json,tarfile
backup=Path('evidence/private/checkpoints/mision-final-20261115T054953Z')
m=json.loads((backup/'sha256.json').read_text())
assert hashlib.sha256((backup/'codigo.tar.gz').read_bytes()).hexdigest()==m['archive_sha256']
with tarfile.open(backup/'codigo.tar.gz') as archive:
    for name,expected in m['archivos'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==expected,name
print('Integridad verificada; no se sobrescribió ningún archivo.')
PYVERIFY
```

Extraer solo en un directorio NUEVO dentro del proyecto con protección de rutas, revisar diferencias y copiar cambios revisados. No restaurar sobre .env, datos, .git ni volúmenes. El respaldo contiene código/config/docs, NO credenciales, CSV oficiales, JSON privados, modelos ni bases. No sustituye un backup de datos; estos recursos se conservan en el entorno existente.

## Git local independiente

Repositorio final preparado: `evidence/private/entrega/final-20261115T054953Z/repositorio`. Es un checkout normal con su .git propio; manifest.json/git.json junto a él registran archivos, hashes, commit y revisión. Root .git estaba vacío/protegido y permanece intacto. No mover ni sobrescribirlo para recuperar. Para publicar usar el repositorio exportado revisado, únicamente cuando el usuario lo autorice. No tiene remotos/tags.

Para otra máquina, copiar/clonar el código, obtener CSV/catálogos/ejemplos oficiales en data/entrada/, generar secretos propios con scripts/infra.py init-env y seguir README. No depende del escritorio Windows ni de rutas personales para operar; scripts usan raíz relativa. No copiar secretos por Git.

## Siguiente paso exacto

Desde Ubuntu: `python3 scripts/verificar_cierre.py`. Es el único comando pendiente para pytest real en Python3.12 sin red, evidencia y Git actualizado. No reinicia servicios ni cambia champion. En Codex Docker está denegado y pip no obtuvo paquetes; no repetir intentos idénticos ni pedir privilegios globales.

Nueva sesión: «Lee AGENTS y docs/progreso. Arranque74.4243s y demás integrales ya aprobados: no repetir. Revisa el informe nuevo de scripts/verificar_cierre.py cuando exista; si pytest falla, usa sus trazas privadas y corrige solamente causas comprobadas. Conserva la limitación de promoción natural por falta de datos nuevos, los volúmenes/champion1 y respaldos. No publiques ni crees entrega-lab2 sin autorización. Usa el Git independiente revisado y guarda otro checkpoint».
