"""
Nodo Debate — Intercambio argumentativo entre el Redactor y los Evaluadores.

Flujo de una ronda:
  1. Redactor argumenta sus decisiones y responde las críticas del Auditor y Metodólogo
  2. Evaluadores (Auditor + Metodólogo, en una sola llamada conjunta) emiten veredicto:
     - Aceptan o mantienen cada crítica con razones explícitas
     - Actualizan la lista de errores bloqueantes

El nodo se ejecuta en BUCLE PROPIO controlado por ronda_debate < max_rondas_debate.
Este bucle es independiente del bucle principal de iteraciones.
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


class ItemVeredicto(BaseModel):
    item_numero:  int = Field(description="Número del ítem de la rúbrica")
    decision:     str = Field(description="'aceptado' si el argumento es válido, 'mantenido' si el error persiste")
    razon:        str = Field(description="Razón de la decisión")


class VeredictoEvaluadores(BaseModel):
    items_veredicto:    List[ItemVeredicto] = Field(description="Veredicto ítem por ítem")
    respuesta_narrativa: str = Field(description="Respuesta narrativa completa al argumento del Redactor")
    errores_resueltos:  List[int] = Field(description="Números de ítems que se dan por resueltos tras el argumento")
    errores_mantenidos: List[int] = Field(description="Números de ítems que siguen siendo errores bloqueantes")


def make_nodo_debate(llm_redactor: ChatGroq, llm_evaluadores: ChatGroq):
    # Prompt del Redactor argumentando
    prompt_redactor = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_redactor_prompt.md")),
        ("human", "Argumenta tus decisiones para la ronda {ronda} del debate sobre la sección '{seccion}'."),
    ])
    chain_redactor = prompt_redactor | llm_redactor

    # Prompt de los Evaluadores respondiendo (Pydantic structured output)
    llm_eval_estructurado = llm_evaluadores.with_structured_output(VeredictoEvaluadores)
    prompt_evaluadores = ChatPromptTemplate.from_messages([
        ("system", cargar_prompt("debate_evaluadores_prompt.md")),
        ("human", "Emite el veredicto conjunto sobre el argumento del Redactor en la ronda {ronda}."),
    ])
    chain_evaluadores = prompt_evaluadores | llm_eval_estructurado

    def nodo_debate(state: MentoriaState) -> dict:
        ronda_actual = state.get("ronda_debate", 0) + 1
        logger.info(
            f"[Debate] Ronda {ronda_actual}/{state.get('max_rondas_debate', 2)} | "
            f"Sección: {state['seccion_objetivo']}"
        )

        # ── PASO 1: Redactor argumenta ────────────────────────────────────────
        arg = invocar_con_backoff(chain_redactor, {
            "seccion":                       state["seccion_objetivo"],
            "texto_iterado":                 state["texto_iterado"],
            "feedback_auditor":              state.get("feedback_auditor", ""),
            "observaciones_metodologicas":   state.get("observaciones_metodologicas", ""),
            "errores_rubrica":               str(state.get("errores_rubrica", [])),
            "historial_debate":              str(state.get("historial_debate", [])),
            "ronda":                         ronda_actual,
        })
        argumento_redactor = arg.content.strip()
        logger.info(f"[Debate] Redactor argumentó ({len(argumento_redactor)} chars)")

        # ── Pausa anti-rate-limit ─────────────────────────────────────────────
        time.sleep(5)

        # ── PASO 2: Evaluadores responden con veredicto estructurado ─────────
        veredicto: VeredictoEvaluadores = invocar_con_backoff(chain_evaluadores, {
            "seccion":                       state["seccion_objetivo"],
            "texto_iterado":                 state["texto_iterado"],
            "argumento_redactor":            argumento_redactor,
            "errores_rubrica":               str(state.get("errores_rubrica", [])),
            "observaciones_metodologicas":   state.get("observaciones_metodologicas", ""),
            "feedback_auditor":              state.get("feedback_auditor", ""),
            "ronda":                         ronda_actual,
        })

        # ── Actualizar errores_rubrica (eliminar los aceptados) ───────────────
        errores_actuales: List[ErrorRubrica] = state.get("errores_rubrica", [])
        errores_resueltos = set(veredicto.errores_resueltos)
        errores_actualizados = [
            e for e in errores_actuales
            if e["item_numero"] not in errores_resueltos
        ]

        logger.info(
            f"[Debate] Ronda {ronda_actual}: "
            f"{len(errores_resueltos)} errores aceptados, "
            f"{len(errores_actualizados)} mantenidos"
        )

        # ── Actualizar historial ──────────────────────────────────────────────
        historial: List[RondaDebate] = list(state.get("historial_debate", []))
        historial.append({
            "ronda":                 ronda_actual,
            "argumento_redactor":    argumento_redactor,
            "veredicto_evaluadores": veredicto.respuesta_narrativa,
            "items_aceptados":       list(veredicto.errores_resueltos),
            "items_mantenidos":      list(veredicto.errores_mantenidos),
        })

        return {
            "ronda_debate":       ronda_actual,
            "historial_debate":   historial,
            "argumento_redactor": argumento_redactor,
            "veredicto_debate":   veredicto.respuesta_narrativa,
            "errores_rubrica":    errores_actualizados,
        }

    return nodo_debate
