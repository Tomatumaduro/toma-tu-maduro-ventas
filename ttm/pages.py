import io
import zipfile

import pandas as pd
import streamlit as st

from .auth import create_user, set_user_active
from .database import connect, is_integrity_error
from .parser import parse_smartcorp_pdf
from .invoice_parser import parse_invoice_pdf


DAY_NAMES = {0:"lunes",1:"martes",2:"miércoles",3:"jueves",4:"viernes",5:"sábado",6:"domingo"}
SOURCE_NAMES = {
    "delivery": "Delivery / Uber / Rappi / Pedidos Ya",
    "caja_chica": "Caja chica",
    "cuenta_bancaria": "Cuenta bancaria",
    "tarjeta_credito": "Tarjeta de crédito",
}
CATEGORIES = ["Por clasificar", "Arriendo", "Agua potable", "Bebidas", "Carnes", "Comisiones bancarias", "Comisiones plataformas", "Datafast", "Energía eléctrica", "Fondos de reserva", "Gas", "IESS", "Insumos", "Internet", "Maduro", "Otros gastos", "Queso", "Servicios contables", "Servicios prestados", "Sueldos", "Suministros", "Vegetales"]


def _sales_df():
    with connect() as con:
        rows = con.execute("SELECT * FROM daily_sales ORDER BY sale_date").fetchall()
        df = pd.DataFrame([dict(row) for row in rows])
    if not df.empty:
        df["sale_date"] = pd.to_datetime(df["sale_date"])
        df["día"] = df["sale_date"].dt.dayofweek.map(DAY_NAMES)
        df["ticket_promedio"] = df["total_sales"].div(df["tickets"].replace(0, pd.NA))
    return df


def render_dashboard():
    st.markdown('<h1 class="ttm-title">Evolutivo de ventas</h1>', unsafe_allow_html=True)
    df = _sales_df()
    if df.empty:
        st.info("Aún no hay reportes cargados. Pide al administrador cargar los cierres diarios.")
        return
    min_d, max_d = df.sale_date.min().date(), df.sale_date.max().date()
    selected = st.date_input("Periodo", (min_d, max_d), min_value=min_d, max_value=max_d)
    if isinstance(selected, tuple) and len(selected) == 2:
        df = df[(df.sale_date.dt.date >= selected[0]) & (df.sale_date.dt.date <= selected[1])]
    total, tickets = df.total_sales.sum(), int(df.tickets.sum())
    cols = st.columns(5)
    cols[0].metric("Venta total", f"${total:,.2f}")
    cols[1].metric("Tickets", f"{tickets:,}")
    cols[2].metric("Ticket promedio", f"${total/tickets:,.2f}" if tickets else "$0.00")
    cols[3].metric("Venta local", f"${df.local_sales.sum():,.2f}")
    cols[4].metric("Delivery", f"${df.delivery_sales.sum():,.2f}")
    st.subheader("Venta diaria")
    st.line_chart(df.set_index("sale_date")[["total_sales", "local_sales", "delivery_sales"]], color=["#d6532f", "#f6a21a", "#0b6375"])
    st.subheader("Comparación por día de la semana")
    base = df.groupby("día", as_index=False).agg(venta_promedio=("total_sales","mean"), tickets_promedio=("tickets","mean"), días=("sale_date","count"))
    order = list(DAY_NAMES.values())
    base["día"] = pd.Categorical(base["día"], order, ordered=True)
    st.dataframe(base.sort_values("día"), use_container_width=True, hide_index=True, column_config={"venta_promedio":st.column_config.NumberColumn(format="$%.2f"),"tickets_promedio":st.column_config.NumberColumn(format="%.1f")})
    show = df[["sale_date","día","total_sales","tickets","ticket_promedio","local_sales","delivery_sales"]].sort_values("sale_date", ascending=False)
    st.subheader("Detalle diario")
    st.dataframe(show, use_container_width=True, hide_index=True, column_config={"sale_date":st.column_config.DateColumn("Fecha"),"total_sales":st.column_config.NumberColumn("Venta total",format="$%.2f"),"ticket_promedio":st.column_config.NumberColumn("Ticket promedio",format="$%.2f"),"local_sales":st.column_config.NumberColumn("Local",format="$%.2f"),"delivery_sales":st.column_config.NumberColumn("Delivery",format="$%.2f")})
    st.download_button("Descargar detalle CSV", show.to_csv(index=False).encode("utf-8-sig"), "ventas_toma_tu_maduro.csv", "text/csv")


def render_upload():
    st.markdown('<h1 class="ttm-title">Cargar reportes</h1>', unsafe_allow_html=True)
    st.write("Sube el cierre diario tal como lo genera SMARTCORP. Si esa fecha ya existe, se actualizará sin duplicarla.")
    file = st.file_uploader("Seleccionar PDF diario", type=["pdf"], accept_multiple_files=False)
    if file and st.button("Procesar PDF", type="primary"):
        imported, errors = 0, []
        try:
            row = parse_smartcorp_pdf(file.getvalue(), file.name)
            products = row.pop("products")
            # Un producto puede aparecer en varias secciones del mismo cierre.
            # Se consolida antes de insertarlo porque la tabla guarda una sola
            # fila por fecha y texto original del producto.
            consolidated_products = {}
            for product in products:
                key = product["product_raw"]
                if key in consolidated_products:
                    consolidated_products[key]["quantity"] += product["quantity"]
                else:
                    consolidated_products[key] = product.copy()
            products = list(consolidated_products.values())
            cols = list(row)
            with connect() as con:
                updates = ",".join(f"{col}=excluded.{col}" for col in cols if col != "sale_date")
                con.execute(f"INSERT INTO daily_sales ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(sale_date) DO UPDATE SET {updates}", tuple(row.values()))
                con.execute("DELETE FROM product_sales WHERE sale_date=?", (row["sale_date"],))
                con.executemany(
                    """INSERT INTO product_sales(
                           sale_date,product_raw,product_name,channel,quantity,source_file
                       ) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(sale_date,product_raw) DO UPDATE SET
                           quantity=product_sales.quantity + excluded.quantity,
                           product_name=excluded.product_name,
                           channel=excluded.channel,
                           source_file=excluded.source_file""",
                    [(row["sale_date"],p["product_raw"],p["product_name"],p["channel"],p["quantity"],file.name) for p in products],
                )
            imported = 1
            st.success(f"Reporte del {row['sale_date']} cargado correctamente: ${row['total_sales']:,.2f} y {row['tickets']} tickets.")
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")
        for err in errors:
            st.error(err)


def _invoice_files(uploaded):
    for item in uploaded or []:
        data = item.getvalue()
        if item.name.lower().endswith(".pdf"):
            yield item.name, data
        elif item.name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if not info.is_dir() and info.filename.lower().endswith(".pdf"):
                        yield info.filename.rsplit("/", 1)[-1], archive.read(info)


def render_invoice_upload():
    st.markdown('<h1 class="ttm-title">Facturas y gastos</h1>', unsafe_allow_html=True)
    st.write("Guarda las facturas en su forma de pago. Puedes subir varios PDF o una carpeta comprimida en ZIP.")
    source = st.radio("Forma de pago", list(SOURCE_NAMES), horizontal=True, format_func=SOURCE_NAMES.get)
    files = st.file_uploader("Seleccionar facturas", type=["pdf", "zip"], accept_multiple_files=True, key=f"inv_{source}")
    if files and st.button("Guardar facturas", type="primary"):
        saved = duplicates = 0
        errors = []
        for filename, data in _invoice_files(files):
            try:
                row = parse_invoice_pdf(data, filename)
                values = {**row, "source_bucket": source, "pdf_data": data}
                cols = list(values)
                with connect() as con:
                    result = con.execute(
                        f"INSERT INTO invoice_documents ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(document_hash) DO NOTHING",
                        tuple(values.values()),
                    )
                    if getattr(result, "rowcount", 0) == 0:
                        duplicates += 1
                    else:
                        saved += 1
            except Exception as exc:
                errors.append(f"{filename}: {exc}")
        st.success(f"{saved} factura(s) guardada(s). {duplicates} duplicada(s) omitida(s).")
        for error in errors:
            st.error(error)

    st.divider()
    st.subheader("Registrar gasto sin factura")
    with st.form("manual_expense"):
        c1, c2, c3 = st.columns(3)
        expense_date = c1.date_input("Fecha")
        category = c2.selectbox("Categoría", CATEGORIES[1:])
        amount = c3.number_input("Valor", min_value=0.0, step=1.0, format="%.2f")
        description = st.text_input("Descripción")
        if st.form_submit_button("Guardar gasto"):
            with connect() as con:
                con.execute("INSERT INTO expenses(expense_date,category,description,amount,source_file) VALUES(?,?,?,?,?)", (expense_date, category, description, amount, "Registro manual"))
            st.success("Gasto guardado.")


def _invoice_df():
    with connect() as con:
        rows = con.execute("SELECT id,source_bucket,original_filename,invoice_date,supplier_name,supplier_tax_id,invoice_number,subtotal,tax,total,expense_category,description,review_status,imported_at FROM invoice_documents ORDER BY invoice_date DESC, id DESC").fetchall()
    df = pd.DataFrame([dict(row) for row in rows])
    if not df.empty:
        df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
        for col in ["subtotal", "tax", "total"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def render_invoice_history():
    st.markdown('<h1 class="ttm-title">Historial de facturas</h1>', unsafe_allow_html=True)
    df = _invoice_df()
    if df.empty:
        st.info("Aún no hay facturas guardadas.")
        return
    c1, c2 = st.columns(2)
    sources = c1.multiselect("Forma de pago", list(SOURCE_NAMES), default=list(SOURCE_NAMES), format_func=SOURCE_NAMES.get)
    categories = c2.multiselect("Categoría", sorted(df.expense_category.unique()), default=sorted(df.expense_category.unique()))
    view = df[df.source_bucket.isin(sources) & df.expense_category.isin(categories)].copy()
    view["forma_pago"] = view.source_bucket.map(SOURCE_NAMES)
    st.metric("Facturas encontradas", len(view), f"${view.total.sum():,.2f}")
    st.dataframe(view[["id","invoice_date","supplier_name","invoice_number","expense_category","forma_pago","total","review_status"]], use_container_width=True, hide_index=True,
        column_config={"invoice_date": st.column_config.DateColumn("Fecha"), "supplier_name":"Proveedor", "invoice_number":"Factura", "expense_category":"Categoría", "forma_pago":"Forma de pago", "total":st.column_config.NumberColumn("Total",format="$%.2f"), "review_status":"Estado"})
    st.subheader("Revisar o corregir una factura")
    selected = st.selectbox("Factura", view.id.tolist(), format_func=lambda i: f"#{i} - {view.loc[view.id==i,'supplier_name'].iloc[0]}")
    current = df[df.id == selected].iloc[0]
    with st.form("edit_invoice"):
        e1, e2, e3 = st.columns(3)
        date_value = current.invoice_date.date() if pd.notna(current.invoice_date) else pd.Timestamp.today().date()
        new_date = e1.date_input("Fecha", date_value)
        new_category = e2.selectbox("Categoría", CATEGORIES, index=CATEGORIES.index(current.expense_category) if current.expense_category in CATEGORIES else 0)
        new_total = e3.number_input("Total", min_value=0.0, value=float(current.total), format="%.2f")
        new_description = st.text_input("Descripción", value=current.description or "")
        if st.form_submit_button("Guardar corrección"):
            with connect() as con:
                con.execute("UPDATE invoice_documents SET invoice_date=?,expense_category=?,total=?,description=?,review_status='Revisado' WHERE id=?", (new_date, new_category, new_total, new_description, int(selected)))
            st.success("Factura actualizada.")
            st.rerun()
    with connect() as con:
        pdf = con.execute("SELECT original_filename,pdf_data FROM invoice_documents WHERE id=?", (int(selected),)).fetchone()
    if pdf and pdf["pdf_data"]:
        st.download_button("Descargar PDF original", bytes(pdf["pdf_data"]), pdf["original_filename"], "application/pdf")
    st.download_button("Descargar historial CSV", view.drop(columns=["source_bucket"]).to_csv(index=False).encode("utf-8-sig"), "historial_facturas.csv", "text/csv")


def render_profit_loss():
    st.markdown('<h1 class="ttm-title">Pérdidas y ganancias</h1>', unsafe_allow_html=True)
    sales = _sales_df()
    invoices = _invoice_df()
    with connect() as con:
        manual_rows = con.execute("SELECT expense_date,category,description,amount FROM expenses ORDER BY expense_date").fetchall()
    manual = pd.DataFrame([dict(row) for row in manual_rows])
    dates = []
    if not sales.empty: dates += sales.sale_date.dt.date.tolist()
    if not invoices.empty: dates += invoices.invoice_date.dropna().dt.date.tolist()
    if not manual.empty: dates += pd.to_datetime(manual.expense_date).dt.date.tolist()
    if not dates:
        st.info("Primero carga ventas y facturas para construir el P&G.")
        return
    selected = st.date_input("Periodo del P&G", (min(dates), max(dates)), min_value=min(dates), max_value=max(dates))
    start, end = selected if isinstance(selected, tuple) and len(selected) == 2 else (min(dates), max(dates))
    sales_view = sales[(sales.sale_date.dt.date >= start) & (sales.sale_date.dt.date <= end)] if not sales.empty else sales
    inv_view = invoices[(invoices.invoice_date.dt.date >= start) & (invoices.invoice_date.dt.date <= end)] if not invoices.empty else invoices
    if not manual.empty:
        manual["expense_date"] = pd.to_datetime(manual.expense_date)
        manual = manual[(manual.expense_date.dt.date >= start) & (manual.expense_date.dt.date <= end)]
    income = float(sales_view.total_sales.sum()) if not sales_view.empty else 0.0
    invoice_expenses = float(inv_view.total.sum()) if not inv_view.empty else 0.0
    manual_expenses = float(manual.amount.sum()) if not manual.empty else 0.0
    expenses = invoice_expenses + manual_expenses
    profit = income - expenses
    margin = profit / income * 100 if income else 0.0
    days = (end - start).days + 1
    previous_end = start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=days - 1)
    previous_income = 0.0
    if not sales.empty:
        previous_income = float(sales[(sales.sale_date.dt.date >= previous_start) & (sales.sale_date.dt.date <= previous_end)].total_sales.sum())
    previous_expenses = 0.0
    if not invoices.empty:
        previous_expenses += float(invoices[(invoices.invoice_date.dt.date >= previous_start) & (invoices.invoice_date.dt.date <= previous_end)].total.sum())
    if not manual_rows == []:
        all_manual = pd.DataFrame([dict(row) for row in manual_rows])
        if not all_manual.empty:
            all_manual["expense_date"] = pd.to_datetime(all_manual.expense_date)
            previous_expenses += float(all_manual[(all_manual.expense_date.dt.date >= previous_start) & (all_manual.expense_date.dt.date <= previous_end)].amount.sum())
    previous_profit = previous_income - previous_expenses
    cols = st.columns(4)
    cols[0].metric("Ingresos", f"${income:,.2f}", f"${income-previous_income:,.2f} vs. periodo anterior")
    cols[1].metric("Gastos", f"${expenses:,.2f}", f"${expenses-previous_expenses:,.2f} vs. periodo anterior", delta_color="inverse")
    cols[2].metric("Utilidad / pérdida", f"${profit:,.2f}", f"${profit-previous_profit:,.2f} vs. periodo anterior")
    cols[3].metric("Margen", f"{margin:,.1f}%")
    category_frames = []
    if not inv_view.empty: category_frames.append(inv_view.groupby("expense_category", as_index=False).total.sum().rename(columns={"expense_category":"Categoría","total":"Gasto"}))
    if not manual.empty: category_frames.append(manual.groupby("category", as_index=False).amount.sum().rename(columns={"category":"Categoría","amount":"Gasto"}))
    if category_frames:
        categories = pd.concat(category_frames).groupby("Categoría", as_index=False).Gasto.sum().sort_values("Gasto", ascending=False)
        st.subheader("Gastos por categoría")
        st.bar_chart(categories.set_index("Categoría"))
        st.dataframe(categories, use_container_width=True, hide_index=True, column_config={"Gasto":st.column_config.NumberColumn(format="$%.2f")})
    if not inv_view.empty:
        by_source = inv_view.groupby("source_bucket", as_index=False).total.sum()
        by_source["Forma de pago"] = by_source.source_bucket.map(SOURCE_NAMES)
        st.subheader("Gastos por forma de pago")
        st.dataframe(by_source[["Forma de pago","total"]], use_container_width=True, hide_index=True, column_config={"total":st.column_config.NumberColumn("Total",format="$%.2f")})
    monthly_parts = []
    if not sales.empty:
        sales_month = sales.assign(Mes=sales.sale_date.dt.to_period("M").astype(str)).groupby("Mes", as_index=False).total_sales.sum().rename(columns={"total_sales":"Ingresos"})
        monthly_parts.append(sales_month.set_index("Mes"))
    if not invoices.empty:
        invoice_month = invoices.dropna(subset=["invoice_date"]).assign(Mes=invoices.dropna(subset=["invoice_date"]).invoice_date.dt.to_period("M").astype(str)).groupby("Mes", as_index=False).total.sum().rename(columns={"total":"Gastos_facturas"})
        monthly_parts.append(invoice_month.set_index("Mes"))
    if not manual_rows == []:
        all_manual = pd.DataFrame([dict(row) for row in manual_rows])
        if not all_manual.empty:
            all_manual["expense_date"] = pd.to_datetime(all_manual.expense_date)
            manual_month = all_manual.assign(Mes=all_manual.expense_date.dt.to_period("M").astype(str)).groupby("Mes", as_index=False).amount.sum().rename(columns={"amount":"Gastos_manuales"})
            monthly_parts.append(manual_month.set_index("Mes"))
    if monthly_parts:
        monthly = pd.concat(monthly_parts, axis=1).fillna(0).reset_index()
        monthly["Gastos"] = monthly.get("Gastos_facturas", 0) + monthly.get("Gastos_manuales", 0)
        monthly["Utilidad"] = monthly.get("Ingresos", 0) - monthly["Gastos"]
        st.subheader("Historial mensual")
        st.dataframe(monthly[["Mes","Ingresos","Gastos","Utilidad"]].sort_values("Mes", ascending=False), use_container_width=True, hide_index=True, column_config={c:st.column_config.NumberColumn(format="$%.2f") for c in ["Ingresos","Gastos","Utilidad"]})
    summary = pd.DataFrame([{"Concepto":"Ingresos","Valor":income},{"Concepto":"Gastos","Valor":expenses},{"Concepto":"Utilidad / pérdida","Valor":profit},{"Concepto":"Margen %","Valor":margin}])
    st.download_button("Descargar P&G CSV", summary.to_csv(index=False).encode("utf-8-sig"), f"pyg_{start}_{end}.csv", "text/csv")


def render_admin():
    st.markdown('<h1 class="ttm-title">Administrar usuarios</h1>', unsafe_allow_html=True)
    with st.form("new_user"):
        username = st.text_input("Nuevo usuario")
        password = st.text_input("Contraseña temporal", type="password")
        role = st.selectbox("Rol", ["viewer", "admin"], format_func=lambda x: "Consulta" if x == "viewer" else "Administrador")
        submit = st.form_submit_button("Crear usuario")
    if submit:
        try:
            if len(username.strip()) < 3 or len(password) < 8:
                raise ValueError("Usuario mínimo 3 caracteres; contraseña mínimo 8.")
            create_user(username, password, role)
            st.success("Usuario creado.")
        except Exception as exc:
            if isinstance(exc, ValueError):
                st.error(str(exc))
            elif is_integrity_error(exc):
                st.error("Ese usuario ya existe.")
            else:
                st.error("No se pudo crear el usuario.")
    with connect() as con:
        users = con.execute("SELECT id,username,role,active,created_at FROM users ORDER BY username").fetchall()
    st.subheader("Usuarios")
    for user in users:
        a, b, c = st.columns([3,2,2])
        a.write(f"**{user['username']}**")
        b.write("Administrador" if user["role"] == "admin" else "Consulta")
        if user["id"] != st.session_state.user["id"]:
            label = "Desactivar" if user["active"] else "Activar"
            if c.button(label, key=f"u{user['id']}"):
                set_user_active(user["id"], not user["active"])
                st.rerun()
