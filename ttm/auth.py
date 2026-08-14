import hashlib
import hmac
import secrets
import streamlit as st

from .database import connect


def _hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000)
    return f"{salt}${digest.hex()}"


def _verify(password, stored):
    salt, expected = stored.split("$", 1)
    actual = _hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def bootstrap_admin():
    with connect() as con:
        count = con.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if count:
        return False
    st.markdown('<h1 class="ttm-title">Configurar Toma Tu Maduro</h1>', unsafe_allow_html=True)
    st.write("Crea la primera cuenta administradora.")
    with st.form("bootstrap"):
        username = st.text_input("Usuario administrador")
        password = st.text_input("Contraseña", type="password")
        confirm = st.text_input("Confirmar contraseña", type="password")
        submitted = st.form_submit_button("Crear administrador")
    if submitted:
        if len(username.strip()) < 3 or len(password) < 8:
            st.error("Usa un usuario de al menos 3 caracteres y una contraseña de al menos 8.")
        elif password != confirm:
            st.error("Las contraseñas no coinciden.")
        else:
            with connect() as con:
                con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", (username.strip().lower(), _hash_password(password), "admin"))
            st.success("Administrador creado. Recarga para iniciar sesión.")
    return True


def require_login():
    return bool(st.session_state.get("user"))


def login():
    st.markdown('<h1 class="ttm-title">Toma Tu Maduro</h1>', unsafe_allow_html=True)
    st.subheader("Evolutivo comercial")
    with st.form("login"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)
    if submitted:
        with connect() as con:
            row = con.execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip().lower(),)).fetchone()
        if row and _verify(password, row["password_hash"]):
            st.session_state.user = {"id": row["id"], "username": row["username"], "role": row["role"]}
            st.rerun()
        st.error("Usuario o contraseña incorrectos.")


def logout():
    st.session_state.clear()
    st.rerun()


def create_user(username, password, role):
    with connect() as con:
        con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", (username.strip().lower(), _hash_password(password), role))


def set_user_active(user_id, active):
    with connect() as con:
        con.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))
