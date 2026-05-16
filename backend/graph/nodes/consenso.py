"""
Nodo Consenso — Identifica acuerdos entre Auditor y Metodólogo.

En la arquitectura de RED PURA, el Supervisor activa este nodo cuando
ambos evaluadores ya corrieron en la iteración actual y sus salidas
necesitan ser sintetizadas para informar la siguiente decisión.

Entrada:  feedback_auditor + observaciones_metodologicas + texto_iterado
Salida:   resultado_consenso (síntesis de acuerdos)
Regresa:  al Supervisor
"""

import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_consenso(llm: ChatGroq):
    """Fábrica del Nodo Consenso."""
    plantilla = cargar_prompt("consenso_prompt.md")
    prompt    = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human",  "Analiza las evaluaciones y produce el análisis de consenso."),
    ])
    chain = prompt | llm

    def nodo_consenso(state: MentoriaState) -> dict:
        n_iter  = state.get("numero_iteracion", 1)
        seccion = state["seccion_objetivo"]
        logger.info(f"[Consenso] Iteración #{n_iter} | {seccion}")

        texto_actual = state.get("texto_iterado") or state.get("contexto_recuperado", "")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                   seccion,
            "numero_iteracion":          n_iter,
            "feedback_auditor":          state.get("feedback_auditor") or "Sin feedback del Auditor.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "Sin observaciones del Metodólogo.",
            "texto_iterado":             texto_actual,
        })

        resultado = respuesta.content.strip()
        logger.info(f"[Consenso] Análisis completado ({len(resultado)} chars)")

        return {
            "resultado_consenso": resultado,
            "iter_consenso":      n_iter + 1,
        }

    return nodo_consenso
