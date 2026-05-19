"""
ARCHIVO OBSOLETO — Reemplazado por debate_auditor.py y debate_metodologo.py

El debate ahora es inter-agente real: dos nodos separados en el grafo
que se comunican exclusivamente a través del estado compartido (MentoriaState).

  - debate_auditor.py   → nodo_debate_auditor   (Auditor escribe al estado)
  - debate_metodologo.py → nodo_debate_metodologo (Metodólogo lee del estado)

Flujo en el grafo:
  Supervisor → nodo_debate_auditor  → Supervisor
  Supervisor → nodo_debate_metodologo → Supervisor

Este archivo ya no es importado por nodes/__init__.py ni por workflow.py.
"""

import time
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


def make_nodo_debate(llm_auditor: ChatGroq, llm_metodologico: ChatGroq):
    """
    Fábrica del Nodo Debate.
    El Auditor argumenta sus hallazgos; el Metodólogo responde con veredicto estructurado.
    """
    prompt_auditor = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_auditor_prompt.md")),
        ("human", "Defiende tus hallazgos en la ronda {ronda} del debate sobre '{seccion}'."),
    ])
    chain_auditor = prompt_auditor | llm_auditor

    llm_metod_estructurado = llm_metodologico.with_structured_output(ResolucionDebate)
    prompt_metodologico = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_metodologico_prompt.md")),
        ("human", "Emite tu resolución sobre los argumentos del Auditor en la ronda {ronda}."),
    ])
    chain_metodologico = prompt_metodologico | llm_metod_estructurado

    def nodo_debate(state: MentoriaState) -> dict:
        ronda_actual = state.get("ronda_debate", 0) + 1
        logger.info(
            f"[Debate] Ronda {ronda_actual}/{state.get('max_rondas_debate', 2)} | "
            f"Sección: {state['seccion_objetivo']}"
        )

        texto_actual = state.get("texto_iterado") or state.get("contexto_recuperado", "")

        # ── PASO 1: Auditor defiende sus hallazgos ────────────────────────────
        arg = invocar_con_backoff(chain_auditor, {
            "seccion":          state["seccion_objetivo"],
            "texto_iterado":    texto_actual,
            "errores_rubrica":  str(state.get("errores_rubrica", [])),
            "feedback_auditor": state.get("feedback_auditor", ""),
            "historial_debate": str(state.get("historial_debate", [])),
            "ronda":            ronda_actual,
        })
        argumento_auditor = arg.content.strip()
        logger.info(f"[Debate] Auditor argumentó ({len(argumento_auditor)} chars)")

        # ── Pausa anti-rate-limit ─────────────────────────────────────────────
        time.sleep(5)

        # ── PASO 2: Metodólogo responde con resolución estructurada ──────────
        resolucion: ResolucionDebate = invocar_con_backoff(chain_metodologico, {
            "seccion":                       state["seccion_objetivo"],
            "texto_iterado":                 texto_actual,
            "argumento_auditor":             argumento_auditor,
            "errores_rubrica":               str(state.get("errores_rubrica", [])),
            "observaciones_metodologicas":   state.get("observaciones_metodologicas", ""),
            "feedback_auditor":              state.get("feedback_auditor", ""),
            "ronda":                         ronda_actual,
        })

        # ── Actualizar errores_rubrica (eliminar los descartados) ─────────────
        errores_actuales: List[ErrorRubrica] = state.get("errores_rubrica", [])
        items_descartados = set(resolucion.items_descartados)
        errores_actualizados = [
            e for e in errores_actuales
            if e["item_numero"] not in items_descartados
        ]

        logger.info(
            f"[Debate] Ronda {ronda_actual}: "
            f"{len(items_descartados)} descartados · "
            f"{len(errores_actualizados)} errores pendientes"
        )

        # ── Registrar ronda en historial ──────────────────────────────────────
        historial: List[RondaDebate] = list(state.get("historial_debate", []))
        historial.append({
            "ronda":                  ronda_actual,
            "argumento_auditor":      argumento_auditor,
            "respuesta_metodologico": resolucion.posicion_metodologica,
            "items_confirmados":      list(resolucion.items_confirmados),
            "items_descartados":      list(resolucion.items_descartados),
        })

        return {
            "ronda_debate":     ronda_actual,
            "historial_debate": historial,
            "errores_rubrica":  errores_actualizados,
        }

    return nodo_debate
