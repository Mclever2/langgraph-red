import streamlit as st

from backend.config import SECCION_ITEMS_MAP
from backend.rag import listar_libros

from ..resources import biblioteca
from ..session_manager import (
    get_snapshot,
    badge_puntaje,
    reset_todo,
    reset_solo_grafo,
)

# Opciones disponibles: (etiqueta visible) → (codigo_universidad, nombre_programa)
_UNIVERSIDADES: dict[str, tuple[str, str]] = {
    "UPAO · Ingeniería de Sistemas":    ("upao", "ingeniería de sistemas"),
    "Cayetano Heredia · Investigación": ("upch", "investigacion"),
}

_TITULOS_SIDEBAR: dict[str, str] = {
    "upao": "🎓 Mentoría UPAO",
    "upch": "🎓 Mentoría UPCH",
}


def render_sidebar() -> None:
    """Renderiza el sidebar completo de la aplicación."""
    with st.sidebar:
        titulo = _TITULOS_SIDEBAR.get(st.session_state.get("universidad", "upao"), "🎓 Mentoría")
        st.title(titulo)
        st.caption("PoC #2 · LangGraph + RAG + OpenAI")
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
    """Botones de reset, selector de universidad y navegación entre pantallas."""
    if st.button("🔄 Nueva evaluación", use_container_width=True):
        reset_todo()
        st.rerun()

    _render_selector_universidad()

    if st.session_state.graph_status in ("paused", "completed", "rag_ready"):
        if st.button("📄 Otra sección (mismo PDF)", use_container_width=True):
            reset_solo_grafo()
            st.rerun()


def _render_selector_universidad() -> None:
    """Dropdown para seleccionar la universidad / rúbrica activa."""
    opciones = list(_UNIVERSIDADES.keys())

    # Determinar la opción actualmente seleccionada según session_state
    univ_actual = st.session_state.get("universidad", "upao")
    prog_actual  = st.session_state.get("programa", "ingeniería de sistemas")
    idx_actual   = 0
    for i, (univ, prog) in enumerate(_UNIVERSIDADES.values()):
        if univ == univ_actual and prog == prog_actual:
            idx_actual = i
            break

    # Bloquear el selector si ya hay un proceso activo para evitar cambios a mitad de evaluación
    bloqueado = st.session_state.graph_status in ("paused", "completed")

    seleccion = st.selectbox(
        "Universidad / Rúbrica:",
        options=opciones,
        index=idx_actual,
        disabled=bloqueado,
        help=(
            "Selecciona la institución para cargar su rúbrica y contexto de evaluación. "
            "Cada universidad usa sus propios criterios y escala de puntuación."
            if not bloqueado
            else "Completa o reinicia la evaluación actual antes de cambiar de universidad."
        ),
    )

    nueva_univ, nuevo_prog = _UNIVERSIDADES[seleccion]
    if nueva_univ != st.session_state.get("universidad") or nuevo_prog != st.session_state.get("programa"):
        st.session_state.universidad = nueva_univ
        st.session_state.programa    = nuevo_prog
        st.rerun()


def _render_biblioteca() -> None:
    """Panel informativo de la biblioteca de libros metodológicos."""
    st.subheader("📚 Biblioteca Metodológica")
    _render_lista_libros()


def _render_lista_libros() -> None:
    """Muestra los libros indexados en la biblioteca."""
    libros = listar_libros(biblioteca)
    if libros:
        total_frags = sum(l["fragmentos"] for l in libros)
        st.caption(f"**{len(libros)} libro(s)** · {total_frags} fragmentos indexados")
        for libro in libros:
            st.markdown(
                f"📖 **{libro['nombre']}**  \n"
                f"<span style='font-size:0.78rem;color:#888'>"
                f"{libro['fragmentos']} fragmentos</span>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Sin libros de referencia cargados.", icon="📚")


def _render_stack_tecnico() -> None:
    """Pie del sidebar con información del stack tecnológico."""
    st.caption("**Stack técnico:**")
    st.caption("• LLM: `llama-3.3-70b-versatile` (Groq)")
    st.caption("• Embeddings: `all-MiniLM-L6-v2` (local)")
    st.caption("• VectorDB tesis: ChromaDB ephemeral")
    st.caption("• VectorDB libros: ChromaDB (precargado)")
    st.caption("• Framework: LangGraph + Streamlit")
