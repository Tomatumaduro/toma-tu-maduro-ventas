import io
import unicodedata

import pandas as pd


LOCAL_COLUMNS = [
    "efectivo", "tarjeta", "cheque", "credito", "retencion",
    "payphone", "deuna", "t.afiliado", "canjes", "transferencia",
    "anticipo",
]
DELIVERY_COLUMNS = ["uber", "pedidos ya", "togo", "rappi"]


def _clean(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().lower().split())


def _number_column(frame, name):
    if name not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[name], errors="coerce").fillna(0.0)


def parse_smartcorp_sales_excel(data, filename):
    """Convierte el Cuadre de Caja Detallado de SMARTCORP en ventas diarias."""
    suffix = filename.lower().rsplit(".", 1)[-1]
    engine = "xlrd" if suffix == "xls" else "openpyxl"
    engine_kwargs = {"ignore_workbook_corruption": True} if engine == "xlrd" else None
    frame = pd.read_excel(
        io.BytesIO(data), sheet_name=0, header=4, engine=engine,
        engine_kwargs=engine_kwargs,
    )
    frame.columns = [_clean(column) for column in frame.columns]

    required = {"fecha", "tipo doc"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "El Excel no parece ser el Cuadre de Caja Detallado de SMARTCORP. "
            f"Faltan columnas: {', '.join(sorted(missing))}."
        )

    # SMARTCORP exporta fechas ISO (AAAA-MM-DD). No usar dayfirst aquí,
    # porque convertiría 2026-07-01 en 7 de enero.
    parsed_dates = pd.to_datetime(frame["fecha"], errors="coerce")
    missing_dates = parsed_dates.isna()
    if missing_dates.any():
        parsed_dates.loc[missing_dates] = pd.to_datetime(
            frame.loc[missing_dates, "fecha"], errors="coerce", dayfirst=True
        )
    frame["fecha"] = parsed_dates
    document_type = frame["tipo doc"].map(_clean)
    sales = frame[document_type.eq("f.venta") & frame["fecha"].notna()].copy()
    if sales.empty:
        raise ValueError("No se encontraron filas F.VENTA con fecha en el archivo.")

    payment_columns = LOCAL_COLUMNS + DELIVERY_COLUMNS
    for column in payment_columns:
        sales[column] = _number_column(sales, column)

    sales["local_sales"] = sales[LOCAL_COLUMNS].sum(axis=1)
    sales["delivery_sales"] = sales[DELIVERY_COLUMNS].sum(axis=1)
    sales["total_sales"] = sales["local_sales"] + sales["delivery_sales"]
    sales["local_ticket"] = sales["local_sales"].gt(0).astype(int)
    sales["delivery_ticket"] = sales["delivery_sales"].gt(0).astype(int)
    sales["card"] = sales["tarjeta"] + sales["t.afiliado"]
    sales["transfer"] = sales[
        ["transferencia", "payphone", "deuna", "cheque", "credito",
         "retencion", "canjes", "anticipo"]
    ].sum(axis=1)

    grouped = sales.groupby(sales["fecha"].dt.date, sort=True)
    rows = []
    for sale_date, day in grouped:
        rows.append({
            "sale_date": sale_date,
            "total_sales": round(float(day["total_sales"].sum()), 2),
            "local_sales": round(float(day["local_sales"].sum()), 2),
            "delivery_sales": round(float(day["delivery_sales"].sum()), 2),
            "tickets": int(len(day)),
            "local_tickets": int(day["local_ticket"].sum()),
            "delivery_tickets": int(day["delivery_ticket"].sum()),
            "cash": round(float(day["efectivo"].sum()), 2),
            "card": round(float(day["card"].sum()), 2),
            "transfer": round(float(day["transfer"].sum()), 2),
            "pedidos_ya": round(float(day["pedidos ya"].sum()), 2),
            "uber_eats": round(float(day["uber"].sum()), 2),
            "rappi": round(float(day["rappi"].sum()), 2),
            "other_delivery": round(float(day["togo"].sum()), 2),
            "source_file": filename,
        })

    expenses = frame[document_type.eq("gasto")].copy()
    expense_total = 0.0
    if not expenses.empty:
        for column in payment_columns:
            expenses[column] = _number_column(expenses, column)
        expense_total = float(expenses[payment_columns].sum(axis=1).sum())

    metadata = {
        "start_date": rows[0]["sale_date"],
        "end_date": rows[-1]["sale_date"],
        "days": len(rows),
        "tickets": len(sales),
        "total_sales": round(sum(row["total_sales"] for row in rows), 2),
        "local_sales": round(sum(row["local_sales"] for row in rows), 2),
        "delivery_sales": round(sum(row["delivery_sales"] for row in rows), 2),
        "excluded_expenses": len(expenses),
        "excluded_expense_total": round(expense_total, 2),
    }
    return rows, metadata
