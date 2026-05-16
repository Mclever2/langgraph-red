"""
Pantalla 1 — Carga del PDF de tesis y (opcional) rúbrica de evaluación.

Paso 1: El estudiante sube el PDF de su proyecto de tesis.
         El sistema vectoriza el texto en ChromaDB ephemeral (RAG local).

Paso 2 (opcional): El estudiante sube su propia rúbrica de evaluación en PDF.
                   El sistema la parsea y la almacena en session_state.
                   Si no sube ninguna, el sistema usa la rúbrica UPAO por defecto.
"""

import hashlib
import uuid

import streamlit as st

from backend.rag import extraer_contenido_sin_indice, construir_vector_store, parse_rubrica_pdf

from ..resources import embeddings_model
from ..session_manager import reset_todo


def render_pantalla_upload() -> None:
    """Renderiza la pantalla de carga del PDF de tesis y rúbrica opcional."""
    st.title("Sistema de Mentoría Académica Multiagente")

    st.markdown("""
    **¿Cómo funciona este sistema?**
    1. **Sube el PDF** de tu proyecto de tesis borrador
    2. (Opcional) **Sube tu rúbrica de evaluación** — si no la subes, se usa la rúbrica UPAO por defecto
    3. **El sistema vectoriza** el documento (embeddings locales, sin enviar datos al exterior)
    4. **Elige una sección** y el sistema recupera solo ese fragmento (anti-token-burn)
    5. **Red multiagente** Redactor ↔ Auditor ↔ Metodólogo mejora el texto iterativamente
    6. **Tú revisas y apruebas** la versión final como mentor
    """)

    st.divider()

    # ── Paso 1: PDF de tesis ──────────────────────────────────────────────────
    st.subheader("Paso 1 — Carga el PDF de tu proyecto de tesis")

    archivo_pdf = st.file_uploader(
        label="Sube el borrador del proyecto de tesis (PDF)",
        type=["pdf"],
        key="uploader_tesis",
        help="El PDF se procesa localmente. Los embeddings se generan en tu máquina.",
    )

    if archivo_pdf is not None:
        pdf_bytes = archivo_pdf.getvalue()
        nuevo_hash = hashlib.md5(pdf_bytes).hexdigest()

        if st.session_state.pdf_hash == nuevo_hash:
            st.success(f"PDF '{st.session_state.pdf_nombre}' ya está vectorizado.")
            toc = st.session_state.get("estructura_toc") or {}
            if toc:
                with st.expander(f"Estructura detectada ({len(toc)} secciones)"):
                    for nombre_sec, pag in list(toc.items())[:20]:
                        st.markdown(f"- **{nombre_sec}** — pág. {pag}")
        else:
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.info(
                    f"**{archivo_pdf.name}** ({len(pdf_bytes) / 1024:.1f} KB)\n\n"
                    "Primera vectorización descarga el modelo multilingual-e5-small (~117 MB). "
                    "Las siguientes son instantáneas."
                )
            with col_btn:
                if st.button("Vectorizar PDF", type="primary", use_container_width=True):
                    _vectorizar_tesis(pdf_bytes, archivo_pdf.name, nuevo_hash)
                    return

    # ── Paso 2: Rúbrica opcional ──────────────────────────────────────────────
    if st.session_state.get("pdf_hash"):
        st.divider()
        st.subheader("Paso 2 — Rúbrica de evaluación (opcional)")

        col_rubrica, col_info_rubrica = st.columns([1, 2])

        with col_info_rubrica:
            if st.session_state.get("rubrica_dinamica"):
                r = st.session_state.rubrica_dinamica
                st.success(
                    f"Rúbrica cargada: **{st.session_state.rubrica_nombre}**  \n"
                    f"{r['total_items']} ítems · "
                    f"{len(r['secciones'])} secciones · "
                    f"puntaje máximo: {r['puntaje_maximo']} pts"
                )
                if st.button("Quitar rúbrica (usar UPAO por defecto)", type="secondary"):
                    st.session_state.rubrica_dinamica = None
                    st.session_state.rubrica_hash     = None
                    st.session_state.rubrica_nombre   = None
                    st.rerun()
            else:
                st.info(
                    "Sin rúbrica subida — se usará la **rúbrica oficial UPAO** (33 ítems).  \n"
                    "Puedes subir la rúbrica de tu jurado evaluador para obtener una evaluación personalizada."
                )

        with col_rubrica:
            archivo_rubrica = st.file_uploader(
                label="Sube la rúbrica de evaluación (PDF)",
                type=["pdf"],
                key="uploader_rubrica",
                help="La rúbrica debe tener ítems numerados (01, 02...) y secciones en mayúsculas.",
            )

            if archivo_rubrica is not None:
                rb_bytes = archivo_rubrica.getvalue()
                rb_hash  = hashlib.md5(rb_bytes).hexdigest()

                if st.session_state.get("rubrica_hash") != rb_hash:
                    if st.button("Cargar rúbrica", type="primary", use_container_width=True):
                        _cargar_rubrica(rb_bytes, archivo_rubrica.name, rb_hash)
                        return

        st.divider()

        # ── Botón continuar ───────────────────────────────────────────────────
        if st.button("Continuar a selección de sección →", type="primary", use_container_width=True):
            st.session_state.graph_status = "rag_ready"
            st.rerun()


# ── Funciones internas ────────────────────────────────────────────────────────

def _vectorizar_tesis(pdf_bytes: bytes, nombre: str, nuevo_hash: str) -> None:
    """Extrae texto (omitiendo índices), genera embeddings y construye ChromaDB para la tesis."""
    try:
        with st.status("Procesando PDF de tesis...", expanded=True) as status:
            st.write("Analizando estructura del PDF (separando índice del contenido)...")
            paginas, estructura_toc = extraer_contenido_sin_indice(pdf_bytes)

            total_chars = sum(len(t) for _, t in paginas)
            if total_chars < 100:
                raise ValueError(
                    "El PDF parece estar vacío o ser un escaneo sin texto seleccionable. "
                    "Asegúrate de que el PDF sea nativo (no solo imágenes)."
                )

            st.write(f"Texto de contenido extraído: {total_chars:,} caracteres en {len(paginas)} páginas")

            if estructura_toc:
                secciones_detectadas = list(estructura_toc.keys())[:8]
                st.write(
                    f"Estructura detectada: **{len(estructura_toc)} secciones** en el índice  \n"
                    + "  \n".join(f"- {s}" for s in secciones_detectadas)
                    + ("  \n- …" if len(estructura_toc) > 8 else "")
                )
                st.write("Dividiendo contenido por secciones del índice (chunking semántico)...")
            else:
                st.write("No se detectó índice formal — se aplica chunking por tamaño fijo.")

            st.write("Generando embeddings locales (multilingual-e5-small)...")

            collection_name = f"tesis_{nuevo_hash[:8]}"
            vector_store = construir_vector_store(
                paginas, estructura_toc, embeddings_model, collection_name=collection_name
            )

            st.session_state.vector_store  = vector_store
            st.session_state.pdf_hash      = nuevo_hash
            st.session_state.pdf_nombre    = nombre
            st.session_state.thread_id     = str(uuid.uuid4())
            st.session_state.estructura_toc = estructura_toc

            status.update(label="PDF vectorizado correctamente (índice excluido)", state="complete")

        st.rerun()

    except Exception as exc:
        st.session_state.error_msg = str(exc)
        st.rerun()


def _cargar_rubrica(rb_bytes: bytes, nombre: str, rb_hash: str) -> None:
    """Parsea el PDF de rúbrica y lo almacena en session_state."""
    with st.spinner(f"Parseando rúbrica '{nombre}'..."):
        rubrica = parse_rubrica_pdf(rb_bytes)

    if rubrica is None:
        st.error(
            "No se pudo parsear la rúbrica. Asegúrate de que el PDF tenga "
            "ítems numerados (01, 02...) y secciones visibles. "
            "Se seguirá usando la rúbrica UPAO por defecto."
        )
        return

    st.session_state.rubrica_dinamica = rubrica
    st.session_state.rubrica_hash     = rb_hash
    st.session_state.rubrica_nombre   = nombre

    st.success(
        f"Rúbrica cargada: {rubrica['total_items']} ítems en "
        f"{len(rubrica['secciones'])} secciones."
    )
    st.rerun()
