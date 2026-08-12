import streamlit as st

from ttm.auth import bootstrap_admin, login, logout, require_login
from ttm.database import init_db
from ttm.pages import render_admin, render_dashboard, render_upload


st.set_page_config(page_title="Toma Tu Maduro | Ventas", page_icon="🍌", layout="wide")
init_db()

st.markdown(
    """
    <style>
    [data-testid="stMetric"] {background:#fff8ed;border:1px solid #ffd19a;border-radius:14px;padding:14px}
    .ttm-title {color:#d6532f;font-weight:800;letter-spacing:-.03em}
    </style>
    """,
    unsafe_allow_html=True,
)

if bootstrap_admin():
    st.stop()
if not require_login():
    login()
    st.stop()

with st.sidebar:
    st.markdown("## 🍌 Toma Tu Maduro")
    user = st.session_state.user
    st.caption(f"Sesión: {user['username']} · {user['role']}")
    pages = ["Evolutivo de ventas"]
    if user["role"] == "admin":
        pages += ["Cargar reportes", "Administrar usuarios"]
    page = st.radio("Navegación", pages)
    st.divider()
    if st.button("Cerrar sesión", use_container_width=True):
        logout()

if page == "Evolutivo de ventas":
    render_dashboard()
elif page == "Cargar reportes":
    render_upload()
else:
    render_admin()
