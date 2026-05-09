"""
Agente Supervisor — Coordinador de la red multiagente.

Dos roles:
  - nodo_supervisor_inicio:    Analiza la sección, el contexto y prepara el plan
                               para que el Redactor sepa exactamente qué mejorar.
  - nodo_supervisor_veredicto: Tras el debate, decide si el ciclo debe repetirse
                               o si el texto puede pasar a revisión humana.
"""

import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_supervisor_inicio(llm: ChatGroq):
    plantilla = cargar_prompt("supervisor_inicio_prompt.md")
    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human", "Genera el plan de trabajo para la iteración #{numero_iteracion} de la sección '{seccion}'."),
    ])
    chain = prompt | llm

    def nodo_supervisor_inicio(state: MentoriaState) -> dict:
        iter_actual = state.get("numero_iteracion", 0)
        logger.info(f"[Supervisor] Inicio iteración #{iter_actual + 1} | {state['seccion_objetivo']}")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                  state["seccion_objetivo"],
            "contexto_recuperado":      state["contexto_recuperado"],
            "contexto_dependencias":    state.get("contexto_dependencias") or "No hay secciones relacionadas disponibles.",
            "contexto_teorico":         state.get("contexto_teorico") or "",
            "feedback_previo":          state.get("feedback_auditor") or "Primera iteración — sin feedback previo.",
            "observaciones_previas":    state.get("observaciones_metodologicas") or "",
            "veredicto_debate_previo":  state.get("veredicto_debate") or "",
            "numero_iteracion":         iter_actual + 1,
            "max_iteraciones":          state.get("max_iteraciones", 3),
        })

        return {
            "plan_supervisor":  respuesta.content.strip(),
            "ronda_debate":     0,   # resetear debate para esta iteración
        }

    return nodo_supervisor_inicio


def make_nodo_supervisor_veredicto(llm: ChatGroq):
    plantilla = cargar_prompt("supervisor_veredicto_prompt.md")
    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human", "Emite tu veredicto tras revisar el debate de la iteración #{numero_iteracion}."),
    ])
    chain = prompt | llm

    def nodo_supervisor_veredicto(state: MentoriaState) -> dict:
        logger.info(
            f"[Supervisor] Veredicto iteración #{state.get('numero_iteracion', 1)} | "
            f"Errores={len(state.get('errores_rubrica', []))} | "
            f"Rondas debate={state.get('ronda_debate', 0)}"
        )

        respuesta = invocar_con_backoff(chain, {
            "seccion":                       state["seccion_objetivo"],
            "texto_iterado":                 state["texto_iterado"],
            "errores_rubrica":               str(state.get("errores_rubrica", [])),
            "observaciones_metodologicas":   state.get("observaciones_metodologicas", ""),
            "veredicto_debate":              state.get("veredicto_debate", ""),
            "numero_iteracion":              state.get("numero_iteracion", 1),
            "max_iteraciones":               state.get("max_iteraciones", 3),
        })

        return {"plan_supervisor": respuesta.content.strip()}

    return nodo_supervisor_veredicto
