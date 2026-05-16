"""
ChromaDB efímero para el PDF del estudiante.

Ciclo de vida: se crea por sesión y se destruye al cerrar el navegador.
Responsabilidad única: indexar la tesis y recuperar contexto por sección.

Estrategia de chunking:
  Si el PDF tiene índice (TOC) detectado, se divide el contenido por secciones
  usando los números de página del TOC. Cada sección queda como uno o varios
  documentos con metadata {"seccion": nombre}. Esto evita que fragmentos fijos
  corten secciones a la mitad y permite recuperar la sección correcta de forma
  más precisa.

  Si no hay TOC, se aplica el splitter clásico de tamaño fijo como fallback.
"""

import logging

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import SECCIONES_TESIS

logger = logging.getLogger(__name__)

CHUNK_SIZE    = 600
CHUNK_OVERLAP = 80
K_RESULTADOS  = 4        # solo para fallback sin metadata de sección
K_INICIAL     = 6        # cuántos resultados top usar para detectar la sección dominante
MAX_FRAGMENTOS_SECCION = 20  # límite de fragmentos por sección (~12 000 chars máx)


# ── Agrupación por TOC ────────────────────────────────────────────────────────

def _agrupar_por_toc(
    paginas: list[tuple[int, str]],
    estructura_toc: dict[str, int],
) -> list[tuple[str, str, int]]:
    """
    Agrupa las páginas de contenido en secciones según el TOC.

    Algoritmo "last-start-wins": cada página se asigna a la sección cuyo
    número de inicio es el mayor que sea <= número de esa página. Esto garantiza
    que TODAS las páginas queden asignadas a exactamente una sección, incluso
    cuando varias secciones comparten la misma página de inicio.

    Returns:
        Lista de (nombre_seccion, texto_seccion, pagina_inicio), solo secciones
        con contenido no vacío. Si no hay TOC o no hay coincidencias, retorna
        un único grupo con todo el texto.
    """
    if not estructura_toc or not paginas:
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    # Ordenar secciones por página de inicio (ascendente)
    secciones_ord = sorted(estructura_toc.items(), key=lambda x: x[1])

    # Acumular texto por sección
    acumulado: dict[str, list[str]] = {nombre: [] for nombre, _ in secciones_ord}
    paginas_asignadas = 0

    for pag, texto in sorted(paginas):
        # Encontrar la sección más reciente cuyo inicio sea <= pag
        seccion_actual: str | None = None
        for nombre, pag_inicio in reversed(secciones_ord):
            if pag_inicio <= pag:
                seccion_actual = nombre
                break
        if seccion_actual is not None:
            acumulado[seccion_actual].append(texto)
            paginas_asignadas += 1

    if paginas_asignadas == 0:
        logger.warning(
            "TOC detectado pero ninguna página coincide con sus números de página. "
            "Fallback a chunking por tamaño fijo."
        )
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    grupos: list[tuple[str, str, int]] = []
    for nombre, pag_inicio in secciones_ord:
        texto = "\n\n".join(acumulado[nombre])
        if texto.strip():
            grupos.append((nombre, texto.strip(), pag_inicio))

    logger.info(
        f"TOC: {len(grupos)} secciones con contenido "
        f"({paginas_asignadas}/{len(paginas)} páginas asignadas)"
    )
    return grupos


def _secciones_a_documentos(
    grupos: list[tuple[str, str, int]],
    collection_name: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """
    Convierte grupos de sección en documentos para ChromaDB.

    Secciones cortas → un documento.
    Secciones largas → múltiples chunks preservando el nombre de sección en metadata.
    """
    docs: list[Document] = []
    for nombre, texto, pag_inicio in grupos:
        metadata = {
            "source":        collection_name,
            "tipo":          "proyecto_tesis",
            "seccion":       nombre,
            "pagina_inicio": pag_inicio,
        }

        if len(texto) <= CHUNK_SIZE:
            docs.append(Document(page_content=texto, metadata=metadata))
        else:
            chunks = splitter.create_documents([texto], metadatas=[metadata])
            docs.extend(chunks)

    return docs


# ── API pública ───────────────────────────────────────────────────────────────

def construir_vector_store(
    paginas: list[tuple[int, str]],
    estructura_toc: dict[str, int],
    embeddings: HuggingFaceEmbeddings,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Divide el contenido de la tesis en fragmentos y los indexa en ChromaDB en memoria.

    Estrategia:
      - Con TOC: agrupa páginas por sección → cada sección es uno o varios documentos.
      - Sin TOC: splitter clásico de tamaño fijo sobre el texto completo.

    Args:
        paginas:         Lista de (numero_pagina_1indexed, texto_pagina).
        estructura_toc:  Dict {nombre_seccion: pagina_inicio} del índice del PDF.
        embeddings:      Modelo de embeddings ya cargado.
        collection_name: Nombre único de la colección (evita colisiones entre PDFs).

    Returns:
        Chroma vector store listo para búsqueda de similitud.
    """
    if not paginas:
        raise ValueError("El texto extraído del PDF está vacío.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )

    if estructura_toc:
        grupos = _agrupar_por_toc(paginas, estructura_toc)
        documentos = _secciones_a_documentos(grupos, collection_name, splitter)
        n_secciones = len(grupos)
        logger.info(
            f"Chunking por TOC: {n_secciones} secciones → {len(documentos)} fragmentos"
        )
    else:
        # Fallback: texto plano + splitter fijo
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        documentos = splitter.create_documents(
            [texto_total],
            metadatas=[{"source": collection_name, "tipo": "proyecto_tesis"}],
        )
        logger.info(f"Chunking fijo (sin TOC): {len(documentos)} fragmentos")

    logger.info(f"Tesis dividida en {len(documentos)} fragmentos")

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
    Recupera el contexto del PDF del estudiante para la sección indicada.

    Estrategia de recuperación en dos pasos:
      1. Obtiene los K_INICIAL fragmentos más similares a la query para
         identificar cuál sección del TOC es la dominante (via metadata).
      2. Devuelve TODOS los fragmentos de esa sección (hasta MAX_FRAGMENTOS_SECCION),
         ordenados por relevancia semántica.

    Si los fragmentos no tienen metadata de sección (chunking antiguo), cae
    back al top-k clásico.
    """
    from collections import Counter

    query = seccion  # fallback si no hay entrada en SECCIONES_TESIS
    for sec in SECCIONES_TESIS:
        if sec["nombre"] == seccion:
            query = sec["query"]
            break

    logger.info(f"RAG tesis → '{seccion}' | query: '{query[:55]}…'")

    try:
        n_total = vector_store._collection.count()
        # Paso 1: rankeamos todos los fragmentos por similitud a la query
        todos_docs = vector_store.similarity_search(query, k=n_total)
    except Exception as exc:
        logger.error(f"Error en similarity_search tesis: {exc}")
        return f"[Error en búsqueda RAG: {exc}]"

    if not todos_docs:
        return (
            f"No se encontró contenido relevante en el PDF para '{seccion}'.\n"
            "El estudiante puede no haber redactado aún esta sección."
        )

    # Paso 2: detectar sección dominante en los primeros K_INICIAL resultados
    top_meta = [d.metadata.get("seccion") for d in todos_docs[:K_INICIAL]
                if d.metadata.get("seccion")]

    if top_meta:
        seccion_dominante = Counter(top_meta).most_common(1)[0][0]
        # Devolver TODOS los fragmentos de esa sección (en orden de relevancia)
        docs = [d for d in todos_docs
                if d.metadata.get("seccion") == seccion_dominante]
        docs = docs[:MAX_FRAGMENTOS_SECCION]
        logger.info(
            f"RAG tesis: sección '{seccion_dominante}' → "
            f"{len(docs)} fragmentos devueltos"
        )
    else:
        # Sin metadata de sección (chunking fijo antiguo): top-k clásico
        docs = todos_docs[:k]
        logger.info(f"RAG tesis: {len(docs)} fragmentos (sin metadata de sección)")

    fragmentos = [f"[Fragmento {i + 1}]\n{d.page_content}" for i, d in enumerate(docs)]
    resultado = "\n\n" + "\n\n---\n\n".join(fragmentos) + "\n"
    logger.info(f"RAG tesis: {len(resultado)} chars totales recuperados")
    return resultado
