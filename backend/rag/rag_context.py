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

    Si la query coincide con una sección o sus proximidades,
    recupera TODOS los fragmentos pertenecientes a esa sección
    en su orden de lectura original (orden cronológico por chunk_index).
    Retorna "" si no hay vector store disponible o no hay resultados.
    """
    if _vector_store is None:
        logger.debug("[rag_context] Sin vector store activo — búsqueda omitida")
        return ""
    try:
        n_total = _vector_store._collection.count()
        if n_total == 0:
            return ""

        # 1. Obtener todos los documentos ordenados por relevancia para identificar la sección
        todos_docs = _vector_store.similarity_search(query, k=n_total)
        if not todos_docs:
            return ""

        # 2. Obtener las secciones de los top-6 resultados más relevantes
        top_meta = [d.metadata.get("seccion") for d in todos_docs[:6]
                    if d.metadata.get("seccion")]

        if not top_meta:
            # Fallback: usar los top k por similitud
            docs = todos_docs[:k]
            # Ordenar por el orden de lectura original si existe chunk_index
            docs.sort(key=lambda d: d.metadata.get("chunk_index", 0))
        else:
            from collections import Counter
            from backend.rag.tesis_store import _extraer_prefijo, _es_subseccion

            # Identificar la sección dominante de los resultados de búsqueda
            seccion_dominante = Counter(top_meta).most_common(1)[0][0]
            prefijo_dom = _extraer_prefijo(seccion_dominante)

            if prefijo_dom:
                # Filtrar todos los que pertenezcan a la sección dominante o sus subsecciones
                docs = [d for d in todos_docs
                        if _es_subseccion(d.metadata.get("seccion", ""), prefijo_dom)]
            else:
                docs = [d for d in todos_docs
                        if d.metadata.get("seccion") == seccion_dominante]

            # Ordenar por el orden de lectura original
            docs.sort(key=lambda d: d.metadata.get("chunk_index", 0))
            # Limitar a 50 fragmentos para no desbordar el contexto
            docs = docs[:50]

        partes = []
        for i, doc in enumerate(docs, 1):
            seccion = doc.metadata.get("seccion", "")
            prefijo = f"[{i} — {seccion}]" if seccion else f"[{i}]"
            partes.append(f"{prefijo}\n{doc.page_content}")
        return "\n\n".join(partes)
    except Exception as exc:
        logger.warning(f"[rag_context] Error en búsqueda: {exc}")
        return ""
