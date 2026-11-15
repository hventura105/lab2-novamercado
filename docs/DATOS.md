# Validación de fuentes oficiales

Se verificaron tamaños y SHA-256 de las 18 fuentes recibidas: cinco CSV, catálogo de errores y 12 ejemplos JSON. No se modificaron los originales. El manifiesto y el perfil detallado quedan privados en `data/entrada/`.

| Archivo | Filas | Estructura real |
| --- | ---: | --- |
| tiendas.csv | 10 | tienda_id, nombre, ciudad, departamento, tipo, fecha_apertura |
| familias.csv | 12 | familia_id, nombre |
| historico_ventas.csv | 83 052 | fecha, tienda_id, familia_id, ventas, en_promocion |
| feriados.csv | 61 | fecha, nombre, tipo, ambito |
| costos.csv | 12 | familia_id, costo_faltante, costo_sobrante |

El histórico abarca **2024-03-01–2026-02-28**, 730 días. No hay vacíos, claves repetidas, ventas/promociones negativas, referencias desconocidas ni ventas anteriores a la apertura. Todas las tiendas tienen las 12 familias. Las tiendas 1–9 cubren los 730 días; la tienda 10 abrió el **2025-03-15** y cubre 351 días. Las 4 548 combinaciones ausentes del producto cartesiano completo pertenecen a días anteriores a esa apertura. No son ventas cero ni datos por imputar. No hay huecos después de la apertura.

Los costos cubren exactamente las familias del catálogo y ambos costos son positivos. Los eventos van de **2024-03-28 a 2026-12-31**: 38 feriados, 11 comerciales, 6 de pago y 6 medios días. Los ámbitos locales coinciden con ciudades de tiendas. El archivo contiene eventos, no una fila por cada día; dentro de la cobertura publicada un día sin evento se trata como día sin evento listado. Fuera del límite superior se rechaza un pronóstico porque no se conoce el calendario.

La evaluación comienza después del histórico, por tanto la primera fecha posible de pronóstico es **2026-03-01**, sin fijar la duración del periodo oculto. Los JSON oficiales usan **2025-11-17** como ejemplo de formato, que pertenece al histórico real: no deben convertirse en una excepción a la regla de fechas futuras. Se prueban sus reparaciones de forma separada y el contrato con fechas válidas derivadas de los límites reales.

Para D solo se usan ventas con fecha < D. Las promociones de D vienen de la solicitud. Las observaciones no traen promociones; se mantiene esa ausencia, sin inventar cero. Las particiones temporales se hacen por días completos, nunca aleatorias. La selección del corte no consulta el reloj del sistema.
