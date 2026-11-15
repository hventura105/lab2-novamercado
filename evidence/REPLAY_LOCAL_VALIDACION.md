# Escenario de replay: prueba numérica local

Se ejecutó train_and_compare sobre las fuentes oficiales, con corte inicial 2025-11-08 y promociones ausentes en las observaciones de bloques posteriores. No se inventaron ventas ni se escribieron fuentes. No hubo PostgreSQL, MLflow, HTTP o DAG en esta prueba.

| Bloque terminado | Costo candidato | Costo vigente | Decisión de la regla |
| --- | ---: | ---: | --- |
| 2025-12-06 | 109601.60 | 109601.60 | No promover |
| 2026-01-03 | 137703.60 | 151281.60 | Promover |

MAE del segundo bloque: candidato65.536931, vigente65.556820. El criterio exige mejora de costo≥1% y MAE sin deterioro>5%; ambos se cumplieron en ese bloque. Duraciones locales: inicial10.98698s, primer candidato6.26066s, segundo6.60340s.

Esta evidencia valida solo el escenario temporal/numérico que usa el replay de integración. No sustituye la ejecución de checks/replay_integral.py con componentes reales ni demuestra promoción del champion productivo.
