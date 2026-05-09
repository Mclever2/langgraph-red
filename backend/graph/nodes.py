"""
ARCHIVO OBSOLETO — Reemplazado por el paquete backend/graph/nodes/

Python 3 usa el paquete nodes/ (directorio con __init__.py) en lugar de
este archivo cuando ambos existen en el mismo directorio. Este archivo
es ignorado por el sistema de imports y se mantiene solo como referencia.

La lógica ha sido dividida en:
  - backend/graph/nodes/redactor.py  → make_nodo_redactor()
  - backend/graph/nodes/auditor.py   → make_nodo_auditor(), ItemEvaluado, AuditorOutput
  - backend/graph/nodes/human.py     → nodo_humano()
  - backend/graph/nodes/_utils.py    → cargar_prompt(), invocar_con_backoff()
  - backend/graph/nodes/__init__.py  → re-exporta todos los símbolos públicos
"""

import os
import time
import random
import logging
from typing import List

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .state import MentoriaState
from backend.config import get_items_texto_para_seccion, get_puntaje_maximo_seccion

logger = logging.getLogger(__name__)

# ── Ruta a los archivos de prompts ────────────────────────────────────────────
_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def _cargar_prompt(nombre_archivo: str) -> str:
    ruta = os.path.join(_PROMPTS_DIR, nombre_archivo)
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


# ── Modelos Pydantic para la salida estructurada del Auditor ──────────────────

class ItemEvaluado(BaseModel):
    """Evaluación de un ítem individual de la rúbrica UPAO."""
    item_numero:  int = Field(ge=1, le=33, description="Número del ítem (01-33)")
    puntaje:      int = Field(ge=0, le=3,  description="0=Insuficiente 1=Regular 2=Bueno 3=Excelente")
    observacion:  str = Field(description="Observación específica para este ítem")


class AuditorOutput(BaseModel):
    """Salida estructurada completa del Nodo Auditor."""
    items_evaluados:  List[ItemEvaluado] = Field(
        description="Evaluación de cada ítem relevante para la sección"
    )
    aprobado:         bool = Field(
        description="True SOLO si todos los ítems evaluados tienen puntaje >= 2"
    )
    feedback_general: str = Field(
        description="Retroalimentación detallada y accionable para el Redactor"
    )
    puntaje_total:    int = Field(
        ge=0, description="Suma total de puntajes de los ítems evaluados"
    )


# ── Utilidad: reintentos con backoff exponencial (anti HTTP 429) ──────────────

def _invocar_con_backoff(chain, inputs: dict, max_reintentos: int = 3):
    """
    Reintenta la llamada al LLM con espera exponencial ante errores 429 (rate limit).
    Base: 5 s × 2^intento + jitter aleatorio hasta 2 s.
    """
    for intento in range(max_reintentos):
        try:
            return chain.invoke(inputs)
        except Exception as exc:
            es_rate_limit = "429" in str(exc) or "rate_limit" in str(exc).lower()
            if es_rate_limit and intento < max_reintentos - 1:
                espera = (2 ** intento) * 5 + random.uniform(0, 2)
                logger.warning(
                    f"⚠️  Rate limit Groq (intento {intento + 1}/{max_reintentos}). "
                    f"Esperando {espera:.1f}s..."
                )
                time.sleep(espera)
            else:
                raise
    raise RuntimeError("Se agotaron los reintentos por rate-limit de Groq.")


# ══════════════════════════════════════════════════════════════════════════════
# NODO REDACTOR
# ══════════════════════════════════════════════════════════════════════════════

def make_nodo_redactor(llm: ChatGroq):
    """
    Fábrica del Nodo Redactor.

    Recibe el contexto recuperado del PDF del estudiante (vía RAG) y el
    feedback del Auditor, y genera una versión mejorada que cumple la rúbrica UPAO.

    RESTRICCIÓN ABSOLUTA (incrustada en el prompt):
      No debe usar lenguaje complejo ni tecnicismos innecesarios.
      El texto debe ser académico pero claro y directo.
    """
    plantilla_sistema = _cargar_prompt("redactor_prompt.md")

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", (
            "Genera ahora la versión mejorada del texto para la sección **{seccion}**.\n"
            "Responde ÚNICAMENTE con el texto mejorado, sin introducciones ni comentarios."
        )),
    ])
    chain = prompt | llm

    def nodo_redactor(state: MentoriaState) -> dict:
        iteracion_actual = state.get("numero_iteracion", 0) + 1
        texto_base = state.get("texto_iterado") or state["contexto_recuperado"]
        feedback = (
            state.get("feedback_auditor")
            or "Primera iteración: no hay feedback previo. Mejora el texto con base en la rúbrica."
        )

        logger.info(f"[Redactor] Iteración #{iteracion_actual} | Sección: {state['seccion_objetivo']}")

        respuesta = _invocar_con_backoff(chain, {
            "seccion":              state["seccion_objetivo"],
            "contexto_recuperado":  state["contexto_recuperado"],
            "contexto_teorico":     state.get("contexto_teorico") or "",
            "texto_actual":         texto_base,
            "feedback":             feedback,
            "iteracion":            iteracion_actual,
        })

        return {
            "texto_iterado":   respuesta.content.strip(),
            "numero_iteracion": iteracion_actual,
        }

    return nodo_redactor


# ══════════════════════════════════════════════════════════════════════════════
# NODO AUDITOR
# ══════════════════════════════════════════════════════════════════════════════

def make_nodo_auditor(llm: ChatGroq):
    """
    Fábrica del Nodo Auditor.

    Evalúa el texto del Redactor contra los ítems EXACTOS de la rúbrica oficial
    UPAO (Ficha de Evaluación de Proyecto de Tesis — Facultad de Ingeniería).

    Usa with_structured_output(AuditorOutput) para garantizar JSON válido.
    Incluye sleep(3) obligatorio para no saturar los TPM de la API gratuita de Groq.
    """
    plantilla_sistema = _cargar_prompt("auditor_prompt.md")
    llm_estructurado = llm.with_structured_output(AuditorOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", "Evalúa el texto y devuelve tu evaluación estructurada según la rúbrica UPAO."),
    ])
    chain = prompt | llm_estructurado

    def nodo_auditor(state: MentoriaState) -> dict:
        # ── Pausa obligatoria anti-rate-limit ─────────────────────────────────
        logger.info(f"[Auditor] Pausa 3 s anti-rate-limit...")
        time.sleep(3)

        seccion = state["seccion_objetivo"]
        logger.info(f"[Auditor] Evaluando iteración #{state.get('numero_iteracion', 1)} | Sección: {seccion}")

        # Construir la tabla de ítems relevantes para esta sección
        items_texto = get_items_texto_para_seccion(seccion)
        puntaje_max = get_puntaje_maximo_seccion(seccion)

        resultado: AuditorOutput = _invocar_con_backoff(chain, {
            "seccion":        seccion,
            "texto_iterado":  state["texto_iterado"],
            "items_rubrica":  items_texto,
            "puntaje_max":    puntaje_max,
        })

        # Convertir a formato del estado (solo ítems con puntaje < 2 → "errores")
        errores = [
            {
                "item_numero":    item.item_numero,
                "puntaje_actual": item.puntaje,
                "descripcion":    item.observacion,
            }
            for item in resultado.items_evaluados
            if item.puntaje < 2
        ]

        logger.info(
            f"[Auditor] Aprobado={resultado.aprobado} | "
            f"Puntaje={resultado.puntaje_total}/{puntaje_max} | "
            f"Errores={len(errores)}"
        )

        return {
            "feedback_auditor": resultado.feedback_general,
            "errores_rubrica":  errores,
            "puntaje_estimado": resultado.puntaje_total,
        }

    return nodo_auditor


# ══════════════════════════════════════════════════════════════════════════════
# NODO HUMANO (HITL pasarela)
# ══════════════════════════════════════════════════════════════════════════════

def nodo_humano(state: MentoriaState) -> dict:
    """
    Nodo de revisión humana (Human-in-the-Loop).

    El grafo se PAUSA automáticamente ANTES de ejecutar este nodo
    gracias a `interrupt_before=["nodo_humano"]` en workflow.py.

    Flujo HITL en Streamlit:
      1. graph.invoke() llega aquí y el grafo se detiene
      2. Streamlit lee el estado con graph.get_state(config)
      3. El mentor revisa, edita y aprueba/rechaza
      4. Streamlit llama a graph.update_state(config, {aprobacion_humana, texto_iterado})
      5. graph.invoke(None, config) reanuda → este nodo ejecuta → END

    Este nodo NO modifica el estado: la decisión ya fue inyectada por Streamlit.
    """
    aprobacion = state.get("aprobacion_humana", "aprobado")
    logger.info(f"[Humano] Decisión registrada: {aprobacion}")
    return {"aprobacion_humana": aprobacion}
