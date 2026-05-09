"""
Paquete RAG — re-exporta todos los símbolos públicos.

Permite importar desde backend.rag directamente sin conocer la estructura interna:
    from backend.rag import extraer_texto_pdf, construir_vector_store, ...
"""

from .extractor     import extraer_texto_pdf
from .embeddings    import cargar_modelo_embeddings, MODELO_EMBEDDING
from .tesis_store   import construir_vector_store, recuperar_contexto
from .library_store import (
    cargar_o_crear_biblioteca,
    agregar_libro,
    listar_libros,
    eliminar_libro,
    precargar_libros_desde_carpeta,
    recuperar_contexto_teorico,
)

__all__ = [
    "extraer_texto_pdf",
    "cargar_modelo_embeddings",
    "MODELO_EMBEDDING",
    "construir_vector_store",
    "recuperar_contexto",
    "cargar_o_crear_biblioteca",
    "agregar_libro",
    "listar_libros",
    "eliminar_libro",
    "precargar_libros_desde_carpeta",
    "recuperar_contexto_teorico",
]
