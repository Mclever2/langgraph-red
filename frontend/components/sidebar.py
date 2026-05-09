"""
Sidebar de la aplicación — Estado del proceso + Panel de Biblioteca Metodológica.

Renderiza:
  - Indicador de estado del grafo (semáforo)
  - Métricas rápidas (iteraciones, errores, puntaje) cuando el grafo está activo
  - Botones de navegación (nueva evaluación / otra sección)
  - Panel completo de gestión de la biblioteca de libros PDF
  - Pie con el stack técnico
"""

import os

import streamlit as st

from backend.config import SECCION_ITEMS_MAP
from backend.rag import agregar_libro, listar_libros, eliminar_libro

from ..resources import biblioteca
from ..session_manager import (
    get_snapshot,
    badge_puntaje,
    reset_todo,
    reset_solo_grafo,
)


def render_sidebar() -> None:
    """Renderiza el sidebar completo de la aplicación."""
    with st.sidebar:
        st.title("🎓 Mentoría UPAO")
        st.caption("PoC #2 · LangGraph + RAG + Groq")
        st.divider()

        _render_estado()
        st.divider()
        _render_botones_navegacion()
        st.divider()
        _render_biblioteca()
        st.divider()
        _render_stack_tecnico()


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_estado() -> None:
    """Muestra el estado del proceso y métricas rápidas."""
    STATUS_UI = {
        "initial":   ("⚪", "Sin PDF cargado"),
        "rag_ready": ("🔵", "PDF listo — elige sección"),
        "paused":    ("🟡", "Esperando revisión del mentor"),
        "completed": ("🟢", "Proceso completado"),
    }
    icono, etiqueta = STATUS_UI.get(st.session_state.graph_status, ("⚫", "Desconocido"))
    st.markdown(f"**Estado:** {icono} {etiqueta}")

    if st.session_state.pdf_nombre:
        st.caption(f"📄 Tesis: `{st.session_state.pdf_nombre}`")
    if st.session_state.thread_id:
        st.caption(f"Thread: `{st.session_state.thread_id[:12]}…`")

    if st.session_state.graph_status in ("paused", "completed"):
        snap = get_snapshot()
        v    = snap.values
        n_it = v.get("numero_iteracion", 0)
        n_er = len(v.get("errores_rubrica", []))
        pts  = v.get("puntaje_estimado")
        sec  = v.get("seccion_objetivo", "—")
        pts_max = len(SECCION_ITEMS_MAP.get(sec, [])) * 3

        st.markdown("**Resumen del proceso:**")
        c1, c2 = st.columns(2)
        c1.metric("Iteraciones", f"{n_it}/3")
        c2.metric("Errores", n_er)
        if pts is not None:
            st.metric("Puntaje", badge_puntaje(pts, pts_max))
        st.caption(f"*{sec}*")


def _render_botones_navegacion() -> None:
    """Botones de reset y navegación entre pantallas."""
    if st.button("🔄 Nueva evaluación", use_container_width=True):
        reset_todo()
        st.rerun()

    if st.session_state.graph_status in ("paused", "completed", "rag_ready"):
        if st.button("📄 Otra sección (mismo PDF)", use_container_width=True):
            reset_solo_grafo()
            st.rerun()


def _render_biblioteca() -> None:
    """Panel de gestión de la biblioteca de libros metodológicos."""
    st.subheader("📚 Biblioteca Metodológica")
    st.caption(
        "Sube libros de metodología de la investigación (PDF). "
        "Se guardan en disco y enriquecen las sugerencias del Redactor."
    )

    # Feedback temporal tras operaciones
    if st.session_state.libro_subido_feedback:
        msg_tipo, msg_texto = st.session_state.libro_subido_feedback
        if msg_tipo == "ok":
            st.success(msg_texto)
        else:
            st.error(msg_texto)
        st.session_state.libro_subido_feedback = None

    _render_agregar_libro()
    _render_lista_libros()


def _render_agregar_libro() -> None:
    """Expander para subir e indexar un nuevo libro."""
    with st.expander("➕ Agregar libro", expanded=False):
        archivo_libro = st.file_uploader(
            "Selecciona un PDF de metodología:",
            type=["pdf"],
            key="uploader_libro",
            label_visibility="collapsed",
        )
        nombre_custom = st.text_input(
            "Nombre del libro (para identificarlo):",
            placeholder="Ej: Hernández Sampieri 2014 — Metodología",
            key="nombre_libro_input",
        )

        if archivo_libro is not None:
            nombre_final = nombre_custom.strip() or os.path.splitext(archivo_libro.name)[0]
            libros_existentes = [l["nombre"] for l in listar_libros(biblioteca)]

            if nombre_final in libros_existentes:
                st.warning(
                    f"Ya existe un libro con el nombre **{nombre_final}**. "
                    "Cambia el nombre o elimina el anterior."
                )
            else:
                if st.button(
                    "📥 Indexar libro",
                    type="primary",
                    use_container_width=True,
                    key="btn_indexar",
                ):
                    with st.spinner(f"Vectorizando '{nombre_final}'…"):
                        try:
                            n_frags = agregar_libro(
                                biblioteca,
                                archivo_libro.getvalue(),
                                nombre_final,
                            )
                            st.session_state.libro_subido_feedback = (
                                "ok",
                                f"✅ '{nombre_final}' indexado ({n_frags} fragmentos).",
                            )
                        except Exception as exc:
                            st.session_state.libro_subido_feedback = (
                                "err",
                                f"❌ Error: {exc}",
                            )
                    st.rerun()


def _render_lista_libros() -> None:
    """Muestra los libros indexados con opción de eliminar cada uno."""
    libros = listar_libros(biblioteca)
    if libros:
        total_frags = sum(l["fragmentos"] for l in libros)
        st.caption(f"**{len(libros)} libro(s)** · {total_frags} fragmentos indexados")

        for libro in libros:
            col_nombre, col_btn = st.columns([3, 1])
            with col_nombre:
                st.markdown(
                    f"📖 **{libro['nombre']}**  \n"
                    f"<span style='font-size:0.78rem;color:#888'>"
                    f"{libro['fragmentos']} fragmentos</span>",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    "🗑️",
                    key=f"del_{libro['nombre']}",
                    help=f"Eliminar '{libro['nombre']}' de la biblioteca",
                ):
                    n_eliminados = eliminar_libro(biblioteca, libro["nombre"])
                    st.session_state.libro_subido_feedback = (
                        "ok",
                        f"🗑️ '{libro['nombre']}' eliminado ({n_eliminados} fragmentos).",
                    )
                    st.rerun()
    else:
        st.info(
            "La biblioteca está vacía. Sube libros de metodología para "
            "enriquecer las sugerencias del Redactor.",
            icon="💡",
        )
        st.caption(
            "**Sugerencias:** Hernández Sampieri, Ñaupas Paitán, Tam Malaga, Bernal Torres"
        )


def _render_stack_tecnico() -> None:
    """Pie del sidebar con información del stack tecnológico."""
    st.caption("**Stack técnico:**")
    st.caption("• LLM: `llama-3.3-70b-versatile` (Groq)")
    st.caption("• Embeddings: `all-MiniLM-L6-v2` (local)")
    st.caption("• VectorDB tesis: ChromaDB ephemeral")
    st.caption("• VectorDB libros: ChromaDB persistente")
    st.caption("• Framework: LangGraph + Streamlit")
