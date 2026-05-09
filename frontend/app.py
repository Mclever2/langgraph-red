"""
PoC #2 (v3 — modularizada) — Sistema Multiagente de Mentoría Académica
=======================================================================
Stack: LangGraph · Groq (llama-3.3-70b-versatile) · ChromaDB · HuggingFace · Streamlit

Punto de entrada minimal: configura la página, inicializa la sesión
y delega el renderizado a los módulos de componentes.

Estructura del proyecto:
  frontend/
    app.py                          ← este archivo (router principal)
    resources.py                    ← singletons @st.cache_resource
    session_manager.py              ← session_state helpers
    components/
      sidebar.py                    ← sidebar + biblioteca metodológica
      pantalla_upload.py            ← Pantalla 1: carga y vectorización del PDF
      pantalla_seleccion.py         ← Pantalla 2: selección de sección + inicio del grafo
      pantalla_revision.py          ← Pantalla 3: revisión HITL del mentor
      pantalla_resultado.py         ← Pantalla 4: resultado final aprobado
"""

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

logging.basicConfig(level=logging.INFO)

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
