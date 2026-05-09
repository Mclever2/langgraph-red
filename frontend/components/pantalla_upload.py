"""
Pantalla 1 — Carga del PDF y vectorización (RAG).

Permite al usuario subir el borrador de su proyecto de tesis en PDF.
Extrae el texto, genera embeddings locales con HuggingFace y construye
el ChromaDB ephemeral para la sesión actual (anti-token-burn).
"""

import hashlib
import uuid

import streamlit as st

from backend.rag import extraer_texto_pdf, construir_vector_store

from ..resources import embeddings_model
from ..session_manager import reset_todo


def render_pantalla_upload() -> None:
    """Renderiza la pantalla de carga y vectorización del PDF de tesis."""
    st.title("🎓 Sistema de Mentoría Académica — UPAO Ingeniería")

    st.markdown("""
    **¿Cómo funciona este sistema?**
    1. 📤 **Sube el PDF** de tu proyecto de tesis borrador
    2. 🔍 **El sistema vectoriza** el documento en ChromaDB (embeddings locales, gratis)
    3. 🧠 **Elige una sección** y el sistema recupera solo ese fragmento (anti-token-burn)
    4. 🤖 **Ciclo automático** Redactor ↔ Auditor mejora el texto (máx. 3 rondas)
    5. 👨‍🏫 **Tú revisas y apruebas** la versión final como mentor
    """)

    st.divider()
    st.subheader("Paso 1 — Carga el PDF de tu proyecto de tesis")

    archivo_pdf = st.file_uploader(
        label="Sube el borrador del proyecto de tesis (PDF)",
        type=["pdf"],
        help="El PDF se procesa localmente. No se envía a ningún servidor externo para embeddings.",
    )

    if archivo_pdf is None:
        return

    pdf_bytes = archivo_pdf.getvalue()
    nuevo_hash = hashlib.md5(pdf_bytes).hexdigest()

    # Solo vectorizar si es un PDF diferente al que ya está en sesión
    if st.session_state.pdf_hash == nuevo_hash:
        st.success(f"✅ PDF '{st.session_state.pdf_nombre}' ya está vectorizado.")
        if st.button("Continuar →", type="primary"):
            st.session_state.graph_status = "rag_ready"
            st.rerun()
        return

    col_btn, col_info = st.columns([1, 3])
    with col_info:
        st.info(
            f"📄 **{archivo_pdf.name}** ({len(pdf_bytes) / 1024:.1f} KB)\n\n"
            "La primera vez que vectorizas descarga el modelo de embeddings (~80 MB). "
            "Las siguientes veces es instantáneo."
        )
    with col_btn:
        btn_vectorizar = st.button(
            "🔍 Vectorizar PDF",
            type="primary",
            use_container_width=True,
        )

    if not btn_vectorizar:
        return

    try:
        with st.status("Procesando PDF...", expanded=True) as status:
            st.write("📄 Extrayendo texto del PDF...")
            texto = extraer_texto_pdf(pdf_bytes)

            if len(texto.strip()) < 100:
                raise ValueError(
                    "El PDF parece estar vacío o ser un escaneo sin texto seleccionable. "
                    "Asegúrate de que el PDF sea nativo (no solo imágenes)."
                )

            st.write(f"✅ Texto extraído: {len(texto):,} caracteres")
            st.write("🔢 Generando embeddings locales (HuggingFace all-MiniLM-L6-v2)...")

            collection_name = f"tesis_{nuevo_hash[:8]}"
            vector_store = construir_vector_store(
                texto, embeddings_model, collection_name=collection_name
            )

            st.session_state.vector_store = vector_store
            st.session_state.pdf_hash     = nuevo_hash
            st.session_state.pdf_nombre   = archivo_pdf.name
            st.session_state.graph_status = "rag_ready"
            st.session_state.thread_id    = str(uuid.uuid4())

            status.update(label="✅ PDF vectorizado correctamente", state="complete")

        st.rerun()

    except Exception as exc:
        st.session_state.error_msg = str(exc)
        st.rerun()
