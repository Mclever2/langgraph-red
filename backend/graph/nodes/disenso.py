"""
Nodo Disenso — Identifica conflictos entre Auditor y Metodólogo.

En la arquitectura de RED PURA, el Supervisor activa este nodo cuando
detecta señales contradictorias entre los evaluadores y necesita
una síntesis de los conflictos para decidir la siguiente acción.

Entrada:  feedback_auditor + observaciones_metodologicas + texto_iterado + n_errores
Salida:   resultado_disenso (conflictos detectados + recomendación)
Regresa:  al Supervisor
"""

import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_disenso(llm: ChatGroq):
    """Fábrica del Nodo Disenso."""
    plantilla = cargar_prompt("disenso_prompt.md")
    prompt    = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human",  "Analiza las evaluaciones y produce el análisis de disenso."),
    ])
    chain = prompt | llm

    def nodo_disenso(state: MentoriaState) -> dict:
        n_iter   = state.get("numero_iteracion", 1)
        seccion  = state["seccion_objetivo"]
        n_errores = len(state.get("errores_rubrica", []))
        logger.info(f"[Disenso] Iteración #{n_iter} | Errores={n_errores} | {seccion}")

        texto_actual = state.get("texto_iterado") or state.get("contexto_recuperado", "")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                   seccion,
            "numero_iteracion":          n_iter,
            "n_errores":                 n_errores,
            "feedback_auditor":          state.get("feedback_auditor") or "Sin feedback del Auditor.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "Sin observaciones del Metodólogo.",
            "texto_iterado":             texto_actual,
        })

        resultado = respuesta.content.strip()
        logger.info(f"[Disenso] Análisis completado ({len(resultado)} chars)")

        return {
            "resultado_disenso": resultado,
            "iter_disenso":      n_iter + 1,
        }

    return nodo_disenso
