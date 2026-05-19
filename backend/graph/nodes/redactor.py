"""
Agente Redactor — Produce el texto mejorado aplicando las correcciones confirmadas.

Recibe el plan del Supervisor, el feedback del Auditor, las observaciones del
Metodólogo y el historial del debate (errores confirmados) para generar la versión
corregida del texto. El Redactor no participa en el debate.
"""

import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_redactor(llm: ChatGroq):
    plantilla_sistema = cargar_prompt("redactor_prompt.md")
    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", (
            "Genera la versión mejorada del texto para la sección **{seccion}** "
            "(iteración #{iteracion}).\n"
            "Responde ÚNICAMENTE con el texto mejorado, sin introducciones ni comentarios."
        )),
    ])
    chain = prompt | llm

    def nodo_redactor(state: MentoriaState) -> dict:
        iteracion_actual = state.get("numero_iteracion", 0) + 1
        texto_base = state.get("texto_iterado") or state["contexto_recuperado"]

        logger.info(f"[Redactor] Iteración #{iteracion_actual} | {state['seccion_objetivo']}")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                  state["seccion_objetivo"],
            "iteracion":                iteracion_actual,
            "max_iteraciones":          state.get("max_iteraciones", 3),
            "contexto_recuperado":      state["contexto_recuperado"],
            "contexto_dependencias":    state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":         state.get("contexto_teorico") or "",
            "texto_actual":             texto_base,
            "plan_supervisor":          state.get("plan_supervisor") or "Sin plan previo.",
            "feedback_auditor":         state.get("feedback_auditor") or "Primera iteración.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "",
            "historial_debate":          str(state.get("historial_debate") or []),
        })

        return {
            "texto_iterado":    respuesta.content.strip(),
            "numero_iteracion": iteracion_actual,
        }

    return nodo_redactor
