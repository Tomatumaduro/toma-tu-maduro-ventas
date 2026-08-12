import sqlite3
import pandas as pd
import streamlit as st

from .auth import create_user, set_user_active
from .database import connect
from .parser import parse_smartcorp_pdf


DAY_NAMES = {0:"lunes",1:"martes",2:"miércoles",3:"jueves",4:"viernes",5:"sábado",6:"domingo"}


def _sales_df():
    with connect() as con:
        df = pd.read_sql_query("SELECT * FROM daily_sales ORDER BY sale_date", con)
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
            cols = list(row)
            with connect() as con:
                con.execute(f"INSERT OR REPLACE INTO daily_sales ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(row.values()))
                con.execute("DELETE FROM product_sales WHERE sale_date=?", (row["sale_date"],))
                con.executemany("INSERT INTO product_sales(sale_date,product_raw,product_name,channel,quantity,source_file) VALUES(?,?,?,?,?,?)", [(row["sale_date"],p["product_raw"],p["product_name"],p["channel"],p["quantity"],file.name) for p in products])
            imported = 1
            st.success(f"Reporte del {row['sale_date']} cargado correctamente: ${row['total_sales']:,.2f} y {row['tickets']} tickets.")
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")
        for err in errors:
            st.error(err)


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
        except (sqlite3.IntegrityError, ValueError) as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else "Ese usuario ya existe.")
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
