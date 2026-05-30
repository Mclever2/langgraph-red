import sys
import os
import logging

# Añadir el directorio raíz del proyecto al path para importar backend y frontend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from frontend.session_manager import init_session, reset_todo
from frontend.components.sidebar          import render_sidebar
from frontend.components.pantalla_upload  import render_pantalla_upload
from frontend.components.pantalla_seleccion import render_pantalla_seleccion
from frontend.components.pantalla_revision  import render_pantalla_revision
from frontend.components.pantalla_resultado import render_pantalla_resultado

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── Configuración de la página ────────────────────────────────────────────────
st.set_page_config(
    page_title="Mentoría Académica UPAO",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inicialización del session_state ─────────────────────────────────────────
init_session()

# ── Sidebar (siempre visible) ─────────────────────────────────────────────────
render_sidebar()

# ── Manejo de errores ─────────────────────────────────────────────────────────
if st.session_state.error_msg:
    st.error(f"**⚠️ Error:** {st.session_state.error_msg}")
    if st.button("← Volver al inicio"):
        reset_todo()
        st.rerun()
    st.stop()

# ── Router de pantallas ───────────────────────────────────────────────────────
_STATUS = st.session_state.graph_status

if _STATUS == "initial":
    render_pantalla_upload()
elif _STATUS == "rag_ready":
    render_pantalla_seleccion()
elif _STATUS == "paused":
    render_pantalla_revision()
elif _STATUS == "completed":
    render_pantalla_resultado()
