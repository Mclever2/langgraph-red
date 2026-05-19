"""
Nodo Debate — Turno del Auditor.

El Auditor lee errores_rubrica y feedback_auditor del estado compartido,
construye su argumento defensivo y lo escribe en `argumento_debate_auditor`.

El Metodólogo leerá ese campo en su propio nodo (debate_metodologo.py),
completando el ciclo de debate real inter-agente a través del estado.
"""

import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_debate_auditor(llm_auditor: ChatGroq):
    """Fábrica del nodo de debate del Auditor."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_auditor_prompt.md")),
        ("human", "Defiende tus hallazgos en la ronda {ronda} del debate sobre '{seccion}'."),
    ])
    chain = prompt | llm_auditor

    def nodo_debate_auditor(state: MentoriaState) -> dict:
        ronda_siguiente = state.get("ronda_debate", 0) + 1
        logger.info(
            f"[Debate-Auditor] Argumentando ronda {ronda_siguiente} | "
            f"Sección: {state['seccion_objetivo']}"
        )

        respuesta = invocar_con_backoff(chain, {
            "seccion":          state["seccion_objetivo"],
            "texto_iterado":    state.get("texto_iterado") or state.get("contexto_recuperado", ""),
            "errores_rubrica":  str(state.get("errores_rubrica", [])),
            "feedback_auditor": state.get("feedback_auditor", ""),
            "historial_debate": str(state.get("historial_debate", [])),
            "ronda":            ronda_siguiente,
        })

        argumento = respuesta.content.strip()
        logger.info(f"[Debate-Auditor] Argumento escrito al estado ({len(argumento)} chars)")

        return {
            "argumento_debate_auditor": argumento,
            "debate_auditor_ronda":     ronda_siguiente,
        }

    return nodo_debate_auditor
