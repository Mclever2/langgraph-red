"""
Nodo Debate — Turno del Metodólogo.

El Metodólogo lee `argumento_debate_auditor` DESDE EL ESTADO compartido —
no recibe el texto como parámetro de función. Así el debate es real:
dos nodos separados que se comunican exclusivamente a través del estado
del grafo LangGraph (MentoriaState), sin acoplamiento directo entre ellos.

Flujo de una ronda completa:
  nodo_supervisor → nodo_debate_auditor → nodo_supervisor → nodo_debate_metodologo → nodo_supervisor

Después de esta respuesta, el Supervisor evalúa errores_rubrica actualizado
y decide si debate continúa (otra ronda) o si va al Redactor.
"""

import logging
from typing import List

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ..state import MentoriaState, ErrorRubrica, RondaDebate
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


class ItemResolucion(BaseModel):
    item_numero: int = Field(description="Número del ítem de la rúbrica")
    decision: str = Field(
        description="'confirmado' si el error es real y debe corregirse, "
                    "'descartado' si el argumento del Auditor no tiene base metodológica suficiente"
    )
    razon: str = Field(description="Razón metodológica de la decisión (1-2 oraciones)")


class ResolucionDebate(BaseModel):
    items_resolucion: List[ItemResolucion] = Field(
        description="Resolución ítem por ítem de todos los errores argumentados"
    )
    posicion_metodologica: str = Field(
        description="Respuesta narrativa completa del Metodólogo al argumento del Auditor"
    )
    items_confirmados: List[int] = Field(
        description="Números de ítems confirmados como errores reales que el Redactor debe corregir"
    )
    items_descartados: List[int] = Field(
        description="Números de ítems descartados — no son errores reales o no tienen base suficiente"
    )


def make_nodo_debate_metodologo(llm_metodologico: ChatGroq):
    """Fábrica del nodo de debate del Metodólogo."""
    llm_estructurado = llm_metodologico.with_structured_output(ResolucionDebate)
    prompt = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_metodologico_prompt.md")),
        ("human", "Emite tu resolución sobre los argumentos del Auditor en la ronda {ronda}."),
    ])
    chain = prompt | llm_estructurado

    def nodo_debate_metodologo(state: MentoriaState) -> dict:
        ronda_actual = state.get("debate_auditor_ronda", 1)
        logger.info(
            f"[Debate-Metodologo] Respondiendo ronda {ronda_actual} | "
            f"Sección: {state['seccion_objetivo']}"
        )

        # Lee el argumento del Auditor exclusivamente desde el estado compartido
        argumento_auditor = state.get("argumento_debate_auditor", "")
        if not argumento_auditor:
            logger.warning("[Debate-Metodologo] argumento_debate_auditor vacío en el estado.")

        resolucion: ResolucionDebate = invocar_con_backoff(chain, {
            "seccion":                     state["seccion_objetivo"],
            "texto_iterado":               state.get("texto_iterado") or state.get("contexto_recuperado", ""),
            "argumento_auditor":           argumento_auditor,
            "errores_rubrica":             str(state.get("errores_rubrica", [])),
            "observaciones_metodologicas": state.get("observaciones_metodologicas", ""),
            "feedback_auditor":            state.get("feedback_auditor", ""),
            "ronda":                       ronda_actual,
        })

        # Actualizar errores_rubrica: eliminar los que el Metodólogo descarta
        errores_actuales: List[ErrorRubrica] = state.get("errores_rubrica", [])
        items_descartados = set(resolucion.items_descartados)
        errores_actualizados = [
            e for e in errores_actuales
            if e["item_numero"] not in items_descartados
        ]

        logger.info(
            f"[Debate-Metodologo] Ronda {ronda_actual} cerrada: "
            f"{len(items_descartados)} descartados · "
            f"{len(errores_actualizados)} errores pendientes"
        )

        # Registrar la ronda completa en el historial
        historial: List[RondaDebate] = list(state.get("historial_debate", []))
        historial.append({
            "ronda":                  ronda_actual,
            "argumento_auditor":      argumento_auditor,
            "respuesta_metodologico": resolucion.posicion_metodologica,
            "items_confirmados":      list(resolucion.items_confirmados),
            "items_descartados":      list(resolucion.items_descartados),
        })

        return {
            "ronda_debate":           ronda_actual,
            "debate_metodologo_ronda": ronda_actual,
            "historial_debate":       historial,
            "errores_rubrica":        errores_actualizados,
        }

    return nodo_debate_metodologo
