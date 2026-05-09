"""
Agente Supervisor Orquestador — Corazón de la red multiagente.

En la arquitectura de RED PURA, este nodo es el único que decide el flujo.
Lee el estado completo y elige dinámicamente qué agente ejecutar a continuación,
usando structured output (Pydantic) para garantizar una decisión válida.

Flujo:
  START → supervisor → [redactor | auditor | metodologico | debate | humano]
              ↑______________________________________________|
  (todos los agentes regresan al supervisor tras su ejecución)

Protección anti-bucle infinito:
  - pasos_ejecutados se incrementa en cada llamada al supervisor
  - Si pasos_ejecutados >= max_pasos_red → fuerza "humano" sin llamar al LLM
  - Capa adicional: recursion_limit en workflow.py
"""

import logging
from typing import Literal

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


# ── Modelo de decisión estructurada ──────────────────────────────────────────

class DecisionSupervisor(BaseModel):
    """Decisión de routing del Supervisor."""
    siguiente: Literal["redactor", "auditor", "metodologico", "debate", "humano"] = Field(
        description="Nombre del agente a ejecutar a continuación"
    )
    razon: str = Field(
        description="Explicación técnica breve de por qué se eligió este agente (máx. 2 oraciones)"
    )
    instrucciones: str = Field(
        description="Instrucciones específicas y accionables para el agente elegido"
    )


# ── Fábrica del nodo ──────────────────────────────────────────────────────────

def make_nodo_supervisor(llm: ChatGroq):
    """
    Fábrica del Supervisor Orquestador.

    Devuelve un nodo que:
      1. Verifica el límite de pasos (anti-bucle)
      2. Llama al LLM con el estado completo
      3. Retorna la decisión de routing + actualizaciones de estado
    """
    plantilla = cargar_prompt("supervisor_red_prompt.md")
    llm_struct = llm.with_structured_output(DecisionSupervisor)

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human", "Analiza el estado actual y decide el siguiente paso de la red."),
    ])
    chain = prompt | llm_struct

    def nodo_supervisor(state: MentoriaState) -> dict:
        pasos      = state.get("pasos_ejecutados", 0)
        max_pasos  = state.get("max_pasos_red", 30)
        n_iter     = state.get("numero_iteracion", 0)
        max_iter   = state.get("max_iteraciones", 3)
        n_errores  = len(state.get("errores_rubrica", []))

        logger.info(
            f"[Supervisor] Paso {pasos + 1}/{max_pasos} | "
            f"Iter {n_iter}/{max_iter} | Errores={n_errores}"
        )

        # ── Protección anti-bucle (capa semántica) ────────────────────────────
        if pasos >= max_pasos:
            logger.warning(
                f"[Supervisor] Límite de pasos alcanzado ({pasos}/{max_pasos}) "
                "→ forzando revisión humana"
            )
            resumen = (
                f"Límite de pasos de la red alcanzado ({pasos} pasos). "
                f"Iteraciones completadas: {n_iter}/{max_iter}. "
                f"Errores pendientes: {n_errores}. "
                "Se pasa a revisión humana por seguridad."
            )
            return {
                "siguiente_nodo":           "humano",
                "instrucciones_supervisor": resumen,
                "plan_supervisor":          resumen,
                "pasos_ejecutados":         pasos + 1,
            }

        # ── Construir señales de estado para el prompt ────────────────────────
        iter_auditada     = state.get("iter_auditada", 0)
        iter_metodologica = state.get("iter_metodologica", 0)
        ronda_debate      = state.get("ronda_debate", 0)
        max_rondas        = state.get("max_rondas_debate", 2)
        texto_generado    = "SÍ" if state.get("texto_iterado") else "NO"
        auditor_ok        = "SÍ" if iter_auditada >= n_iter and n_iter > 0 else "NO"
        metodologico_ok   = "SÍ" if iter_metodologica >= n_iter and n_iter > 0 else "NO"

        # ── Llamada al LLM ────────────────────────────────────────────────────
        decision: DecisionSupervisor = invocar_con_backoff(chain, {
            "seccion":                   state["seccion_objetivo"],
            "numero_iteracion":          n_iter,
            "max_iteraciones":           max_iter,
            "pasos_ejecutados":          pasos,
            "max_pasos_red":             max_pasos,
            "texto_generado":            texto_generado,
            "auditor_ok":                auditor_ok,
            "metodologico_ok":           metodologico_ok,
            "n_errores":                 n_errores,
            "ronda_debate":              ronda_debate,
            "max_rondas_debate":         max_rondas,
            "feedback_auditor":          state.get("feedback_auditor") or "Aún no disponible.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "Aún no disponible.",
            "veredicto_debate":          state.get("veredicto_debate") or "Sin debate aún.",
            "plan_anterior":             state.get("plan_supervisor") or "Primera decisión del ciclo.",
        })

        logger.info(
            f"[Supervisor] Decisión: {decision.siguiente.upper()} | "
            f"Razón: {decision.razon[:80]}…"
        )

        # Cuando el Supervisor decide ir al Redactor (nueva iteración),
        # resetea el contador de rondas de debate
        extra = {}
        if decision.siguiente == "redactor":
            extra["ronda_debate"] = 0

        return {
            "siguiente_nodo":           decision.siguiente,
            "instrucciones_supervisor": decision.instrucciones,
            "plan_supervisor":          f"[{decision.siguiente.upper()}] {decision.instrucciones}",
            "pasos_ejecutados":         pasos + 1,
            **extra,
        }

    return nodo_supervisor
