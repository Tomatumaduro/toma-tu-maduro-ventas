# Toma Tu Maduro — ventas y P&G

Aplicación Streamlit para conservar el histórico comercial y consultar el estado de pérdidas y ganancias por el periodo elegido.

## Funciones principales

- Usuarios administradores y usuarios de consulta.
- Carga de cierres diarios SMARTCORP en PDF.
- Carga del reporte mensual SMARTCORP en Excel (`.xls` o `.xlsx`).
- Vista previa antes de guardar: periodo, días, tickets, ingresos, local y delivery.
- Actualización por fecha sin duplicar las ventas existentes.
- Cuatro bandejas de facturas: delivery, caja chica, cuenta bancaria y tarjeta de crédito.
- Historial de facturas y descarga de los documentos originales.
- P&G por rango de fechas con ingresos, gastos, utilidad y margen.

## Carga del Excel mensual

En **Cargar ventas**, abre la pestaña **Excel mensual de ingresos**, selecciona el archivo original de SMARTCORP y revisa el resumen. Las filas identificadas como gastos no se suman a los ingresos, porque los egresos se obtienen de las facturas cargadas.

Si una fecha ya existe, sus totales diarios se actualizan. Así se puede volver a cargar un mes corregido sin crear días duplicados.

## Configuración

Instala las dependencias con `requirements.txt` y ejecuta `app.py`. En Streamlit Community Cloud, la conexión PostgreSQL/Supabase se configura mediante los secretos de la aplicación.
