"""
ChromaDB efímero para el PDF del estudiante.

Ciclo de vida: se crea por sesión y se destruye al cerrar el navegador.
Responsabilidad única: indexar la tesis y recuperar contexto por sección.
"""

import logging

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import SECCIONES_TESIS

logger = logging.getLogger(__name__)

CHUNK_SIZE    = 600
CHUNK_OVERLAP = 80
K_RESULTADOS  = 4


def construir_vector_store(
    texto: str,
    embeddings: HuggingFaceEmbeddings,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Divide el texto de la tesis en fragmentos y los indexa en ChromaDB en memoria.

    Args:
        texto:           Texto completo extraído del PDF del estudiante.
        embeddings:      Modelo de embeddings ya cargado.
        collection_name: Nombre único de la colección (evita colisiones entre PDFs).

    Returns:
        Chroma vector store listo para búsqueda de similitud.
    """
    if not texto.strip():
        raise ValueError("El texto extraído del PDF está vacío.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )
    documentos = splitter.create_documents(
        [texto],
        metadatas=[{"source": collection_name, "tipo": "proyecto_tesis"}],
    )
    logger.info(f"Tesis dividida en {len(documentos)} fragmentos")

    # EphemeralClient = solo en RAM, no escribe en disco
    cliente = chromadb.EphemeralClient()
    store = Chroma(
        client=cliente,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    store.add_documents(documentos)

    n = store._collection.count()
    logger.info(f"ChromaDB tesis listo: {n} fragmentos en '{collection_name}'")
    return store


def recuperar_contexto(
    vector_store: Chroma,
    seccion: str,
    k: int = K_RESULTADOS,
) -> str:
    """
    Recupera los k fragmentos más relevantes del PDF del estudiante para la sección.

    Usa la query semántica definida en SECCIONES_TESIS (config.py).
    """
    query = seccion  # fallback
    for sec in SECCIONES_TESIS:
        if sec["nombre"] == seccion:
            query = sec["query"]
            break

    logger.info(f"RAG tesis → '{seccion}' | query: '{query[:55]}…'")

    try:
        docs = vector_store.similarity_search(query, k=k)
    except Exception as exc:
        logger.error(f"Error en similarity_search tesis: {exc}")
        return f"[Error en búsqueda RAG: {exc}]"

    if not docs:
        return (
            f"No se encontró contenido relevante en el PDF para '{seccion}'.\n"
            "El estudiante puede no haber redactado aún esta sección."
        )

    fragmentos = [f"[Fragmento {i + 1}]\n{d.page_content}" for i, d in enumerate(docs)]
    resultado = "\n\n" + "\n\n---\n\n".join(fragmentos) + "\n"
    logger.info(f"RAG tesis: {len(docs)} fragmentos recuperados ({len(resultado)} chars)")
    return resultado
