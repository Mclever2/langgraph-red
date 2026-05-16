"""
Gestión del session_state de Streamlit.

Centraliza todos los valores por defecto, las funciones de reset y los
helpers de lectura del estado del grafo LangGraph.
"""

import uuid

import streamlit as st

from backend.graph.workflow import get_run_config
from .resources import graph

# ── Valores por defecto ───────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "thread_id":             None,
    "graph_status":          "initial",  # initial | rag_ready | paused | completed
    "vector_store":          None,       # ChromaDB ephemeral (tesis del estudiante)
    "pdf_hash":              None,
    "pdf_nombre":            None,
    "rubrica_dinamica":      None,       # dict parseado por rubric_parser (None = usa UPAO)
    "rubrica_hash":          None,
    "rubrica_nombre":        None,
    "error_msg":             None,
    "libro_subido_feedback": None,
    "estructura_toc":        None,   # dict {nombre_seccion: n_pagina} detectado del índice
}


def init_session() -> None:
    """Inicializa las claves del session_state con sus valores por defecto."""
    for k, v in _DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_todo() -> None:
    """Reinicia toda la sesión para comenzar una nueva evaluación desde cero."""
    st.session_state.thread_id       = str(uuid.uuid4())
    st.session_state.graph_status    = "initial"
    st.session_state.vector_store    = None
    st.session_state.pdf_hash        = None
    st.session_state.pdf_nombre      = None
    st.session_state.rubrica_dinamica = None
    st.session_state.rubrica_hash    = None
    st.session_state.rubrica_nombre  = None
    st.session_state.error_msg       = None
    st.session_state.estructura_toc  = None


def reset_solo_grafo() -> None:
    """Limpia el grafo y el error, pero conserva el PDF ya vectorizado."""
    st.session_state.thread_id    = str(uuid.uuid4())
    st.session_state.graph_status = "rag_ready"
    st.session_state.error_msg    = None


# ── Helpers de lectura del grafo ──────────────────────────────────────────────

def get_config() -> dict:
    """Devuelve la configuración de ejecución del grafo para el thread actual."""
    return get_run_config(st.session_state.thread_id)


def get_snapshot():
    """Lee el snapshot actual del grafo (estado pausado o completado)."""
    return graph.get_state(get_config())


def is_paused(snapshot) -> bool:
    """True si el grafo está pausado esperando la revisión del mentor."""
    return bool(snapshot.next) and "nodo_humano" in snapshot.next


# ── Helpers de presentación ───────────────────────────────────────────────────

def badge_puntaje(puntaje: int, puntaje_max: int) -> str:
    """Devuelve un emoji + texto para mostrar el puntaje con semáforo de color."""
    if puntaje_max == 0:
        return "—"
    pct = puntaje / puntaje_max
    if pct >= 0.8:
        return f"🟢 {puntaje}/{puntaje_max}"
    elif pct >= 0.5:
        return f"🟡 {puntaje}/{puntaje_max}"
    else:
        return f"🔴 {puntaje}/{puntaje_max}"
