"""
Planificador de contexto RAG dinámico para los agentes evaluadores.

Flujo de cada agente que lo usa:
  1. El agente lee la sección objetivo (ya en state["contexto_recuperado"])
  2. Este módulo hace UNA llamada LLM para decidir qué secciones adicionales buscar
  3. Ejecuta esas queries contra el vector store activo (rag_context.py)
  4. Devuelve el contexto enriquecido para inyectarlo en inputs_base

Por qué una llamada de planificación y no tool calling directo:
  Groq no permite bind_tools + with_structured_output simultáneamente de forma
  limpia. La separación en dos fases (planificación libre → evaluación estructurada)
  es compatible con todos los modelos y evita conflictos de output schema.
"""

from __future__ import annotations

import logging
import time

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from backend.rag.rag_context import get_vector_store, buscar_fragmentos

logger = logging.getLogger(__name__)

_PAUSA_POST_PLANIFICACION = 2.0  # segundos anti-rate-limit tras la llamada de planificación

_PROMPT_PLANNER = """\
Eres {rol} y estás a punto de evaluar la sección "{seccion}" de un proyecto de tesis universitaria.

Antes de iniciar tu evaluación, decide qué secciones adicionales del documento necesitas consultar
para hacer una evaluación coherente (verificar consistencia, detectar contradicciones, confirmar alineación).

Devuelve EXACTAMENTE 2 o 3 queries de búsqueda, una por línea, sin numeración ni explicaciones.
Cada query debe ser corta (5-10 palabras) y representar una sección estructural clave de una tesis.

Queries válidas (ejemplos):
objetivos general específicos investigación
hipótesis variables relación dependiente independiente
metodología tipo diseño investigación
problema realidad formulación pregunta investigación
marco teórico conceptos antecedentes base teórica
operacionalización variables dimensiones indicadores
población muestra técnica instrumento recolección datos"""


def obtener_contexto_dinamico(
    llm: ChatGroq,
    seccion: str,
    texto_snippet: str,
    rol: str,
    k_por_query: int = 3,
) -> str:
    """
    Hace UNA llamada LLM para planificar qué buscar, luego ejecuta las queries.

    Args:
        llm:           Instancia ChatGroq del agente (usa su propia API key).
        seccion:       Nombre de la sección bajo evaluación.
        texto_snippet: Extracto del texto a evaluar (primeros ~400 chars).
        rol:           Descripción del rol del agente (para el prompt).
        k_por_query:   Fragmentos a recuperar por cada query.

    Returns:
        Contexto adicional recuperado (string con fragmentos etiquetados),
        o "" si el vector store no está disponible o la planificación falla.
    """
    if get_vector_store() is None:
        logger.info(f"[RAGPlanner/{rol}] Vector store no disponible — sin enriquecimiento")
        return ""

    # ── Llamada de planificación ──────────────────────────────────────────────
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", _PROMPT_PLANNER),
            ("human", "Extracto del texto a evaluar:\n{texto}"),
        ])
        respuesta = (prompt | llm).invoke({
            "rol":     rol,
            "seccion": seccion,
            "texto":   texto_snippet[:400],
        })
        lineas = [l.strip() for l in respuesta.content.strip().split("\n") if l.strip()]
        queries = lineas[:3]
        logger.info(f"[RAGPlanner/{rol}] Queries planificadas: {queries}")
    except Exception as exc:
        logger.warning(f"[RAGPlanner/{rol}] Falló la planificación: {exc}")
        return ""

    time.sleep(_PAUSA_POST_PLANIFICACION)

    # ── Ejecución de queries ──────────────────────────────────────────────────
    prefijo_excluido = _extraer_prefijo_numerico(seccion)
    partes: list[str] = []
    vistas: set[str] = set()

    for query in queries:
        resultado = buscar_fragmentos(query, k=k_por_query)
        if not resultado:
            continue

        # Filtrar fragmentos de la propia sección objetivo (evitar duplicados)
        fragmentos_filtrados = _filtrar_seccion_principal(resultado, prefijo_excluido, vistas)
        if fragmentos_filtrados:
            partes.append(f"**[Contexto buscado: {query}]**\n{fragmentos_filtrados}")

    if not partes:
        logger.info(f"[RAGPlanner/{rol}] Sin contexto adicional recuperado")
        return ""

    contexto = "\n\n---\n\n".join(partes)
    logger.info(
        f"[RAGPlanner/{rol}] Contexto dinámico: {len(partes)} bloques, "
        f"{len(contexto)} chars totales"
    )
    return contexto


# ── Helpers internos ──────────────────────────────────────────────────────────

def _extraer_prefijo_numerico(seccion: str) -> str:
    """Extrae el prefijo numérico de una sección: '2.1. Título' → '2.1'"""
    import re
    m = re.match(r'^(\d[\d\.]*)', seccion.strip())
    return m.group(1).rstrip('.') if m else ""


def _filtrar_seccion_principal(
    resultado: str,
    prefijo_excluido: str,
    vistas: set[str],
) -> str:
    """
    Del resultado de buscar_fragmentos, descarta los fragmentos que
    pertenecen a la sección principal (ya en contexto_recuperado) o
    ya fueron incluidos en una query anterior.
    """
    import re

    partes_filtradas = []
    for bloque in resultado.split("\n\n"):
        if not bloque.strip():
            continue

        # Extraer etiqueta de sección del formato "[N — Sección]"
        m = re.match(r'^\[(\d+)\s*[—-]\s*([^\]]+)\]', bloque)
        seccion_bloque = m.group(2).strip() if m else ""
        prefijo_bloque = _extraer_prefijo_numerico(seccion_bloque)

        # Excluir si es la misma sección principal
        if prefijo_excluido and prefijo_bloque and (
            prefijo_bloque == prefijo_excluido
            or prefijo_bloque.startswith(prefijo_excluido + ".")
        ):
            continue

        # Deduplicar secciones ya recuperadas en queries anteriores
        clave = prefijo_bloque or seccion_bloque[:30]
        if clave and clave in vistas:
            continue
        if clave:
            vistas.add(clave)

        partes_filtradas.append(bloque)

    return "\n\n".join(partes_filtradas)
