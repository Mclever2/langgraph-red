"""
Contexto RAG activo para la sesión en curso.

Singleton de módulo — se establece desde pantalla_seleccion.py antes de
invocar el grafo y lo usan los nodos de los agentes en tiempo de ejecución.

Por qué un singleton y no el estado del grafo:
  El vector store (Chroma EphemeralClient) no es serializable por MemorySaver,
  así que no puede vivir en MentoriaState. El singleton es seguro en Streamlit
  porque cada sesión de usuario corre en un solo hilo.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_chroma import Chroma

logger = logging.getLogger(__name__)

_vector_store: Optional["Chroma"] = None


def set_vector_store(vs: "Chroma") -> None:
    """Registra el vector store de la sesión actual antes de invocar el grafo."""
    global _vector_store
    _vector_store = vs
    logger.info("[rag_context] Vector store registrado para la sesión actual")


def get_vector_store() -> Optional["Chroma"]:
    return _vector_store


def buscar_fragmentos(query: str, k: int = 4) -> str:
    """
    Búsqueda semántica libre en el vector store activo.

    No está limitada a SECCIONES_TESIS — acepta cualquier query que
    el agente decida plantear. Retorna "" si no hay vector store disponible.
    """
    if _vector_store is None:
        logger.debug("[rag_context] Sin vector store activo — búsqueda omitida")
        return ""
    try:
        docs = _vector_store.similarity_search(query, k=k)
        if not docs:
            return ""
        partes = []
        for i, doc in enumerate(docs, 1):
            seccion = doc.metadata.get("seccion", "")
            prefijo = f"[{i} — {seccion}]" if seccion else f"[{i}]"
            partes.append(f"{prefijo}\n{doc.page_content}")
        return "\n\n".join(partes)
    except Exception as exc:
        logger.warning(f"[rag_context] Error en búsqueda: {exc}")
        return ""
