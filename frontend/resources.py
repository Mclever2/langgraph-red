import logging

import streamlit as st

from backend.rag import (
    cargar_modelo_embeddings,
    cargar_o_crear_biblioteca,
    listar_libros,
    precargar_libros_desde_carpeta,
)
from backend.graph.workflow import create_graph

logger = logging.getLogger(__name__)


@st.cache_resource(show_spinner="Cargando modelo de embeddings multilingual-e5-small (primera vez ~117 MB)…")
def _get_embeddings():
    """Carga el modelo HuggingFace UNA sola vez (~80 MB en la primera ejecución)."""
    return cargar_modelo_embeddings()


@st.cache_resource(show_spinner="Compilando grafo de mentoría…")
def _get_graph():
    """Compila el grafo LangGraph con MemorySaver UNA sola vez."""
    return create_graph()


@st.cache_resource(show_spinner="Cargando biblioteca metodológica…")
def _get_biblioteca(_embeddings):
    """
    Carga o crea la biblioteca persistente de libros de metodología.

    PersistentClient → datos en disco, sobreviven reinicios del servidor.
    Pre-carga automáticamente cualquier PDF de la carpeta ./books/
    """
    vs = cargar_o_crear_biblioteca(_embeddings)
    libros_existentes = [l["nombre"] for l in listar_libros(vs)]
    nuevos = precargar_libros_desde_carpeta(vs, libros_existentes)
    if nuevos:
        logger.info(f"Pre-cargados {len(nuevos)} libro(s) desde ./books/: {nuevos}")
    return vs


# ── Instancias globales (se crean una vez al importar este módulo) ────────────
# Envuelto en try/except para que cualquier error interno sea visible en lugar
# de quedar oculto tras "ImportError: cannot import name 'init_session'".
try:
    embeddings_model = _get_embeddings()
    graph            = _get_graph()
    biblioteca       = _get_biblioteca(embeddings_model)
except Exception as _startup_err:
    import traceback
    logger.error(
        f"[resources] Error crítico al inicializar singletons:\n"
        f"{traceback.format_exc()}"
    )
    raise
