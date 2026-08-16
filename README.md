# Toma Tu Maduro - Evolutivo comercial

Primera etapa de la aplicación: usuarios, carga de cierres diarios SMARTCORP y dashboard de ventas local/delivery.

## Ejecutar

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

En el primer inicio, la aplicación solicita crear la cuenta administradora. El administrador puede crear usuarios de consulta y cargar un PDF diario. Si vuelve a cargar la misma fecha, el registro se actualiza sin duplicarse.

En producción, configure `DATABASE_URL` en los secretos de Streamlit con la conexión Session pooler de Supabase. Sin ese secreto, la aplicación utiliza SQLite únicamente para desarrollo local.

## Segunda etapa

La base ya incluye una tabla de gastos para incorporar el P&G: ingresos, costo de ventas, gastos operativos, utilidad y márgenes.
# Toma Tu Maduro - ventas y P&G

Aplicación Streamlit con usuarios, carga de cierres SMARTCORP, histórico de ventas y estado de pérdidas y ganancias.

## Segunda etapa

- Cuatro bandejas de facturas: plataformas, caja chica, cuenta bancaria y tarjeta de crédito.
- Lectura automática de fecha, proveedor, número, subtotal, IVA y total.
- Prevención de documentos duplicados mediante huella digital.
- Corrección manual de fecha, categoría y valor.
- Registro de gastos sin factura.
- P&G por rango de fechas, comparación con el periodo anterior e histórico mensual.
- Descarga del PDF original y exportación de tablas a CSV.

Los documentos y sus datos se almacenan en la misma base PostgreSQL/Supabase configurada mediante Streamlit Secrets.
