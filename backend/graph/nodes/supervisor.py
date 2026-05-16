"""
Agente Supervisor Orquestador — Corazón de la red multiagente.

En la arquitectura de RED PURA, este nodo es el único que decide el flujo.
Lee el estado completo y elige dinámicamente qué agente ejecutar a continuación,
usando structured output (Pydantic) para garantizar una decisión válida.

Flujo:
  START → supervisor → [redactor | auditor | metodologico | debate | consenso | disenso | humano]
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
    siguiente: Literal[
        "redactor", "auditor", "metodologico",
        "debate", "consenso", "disenso", "humano"
    ] = Field(description="Nombre del agente a ejecutar a continuación")
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

        iter_auditada     = state.get("iter_auditada", 0)
        iter_metodologica = state.get("iter_metodologica", 0)
        iter_consenso     = state.get("iter_consenso", 0)
        iter_disenso      = state.get("iter_disenso", 0)
        ronda_debate      = state.get("ronda_debate", 0)
        max_rondas        = state.get("max_rondas_debate", 2)

        # iter_xxx = n_iter+1 tras cada ejecución → "corrió en este ciclo" = iter > n_iter
        auditor_ok      = iter_auditada > n_iter
        metodologico_ok = iter_metodologica > n_iter
        consenso_ok     = iter_consenso > n_iter
        disenso_ok      = iter_disenso > n_iter

        logger.info(
            f"[Supervisor] Paso {pasos + 1}/{max_pasos} | "
            f"Iter {n_iter}/{max_iter} | Errores={n_errores} | "
            f"Aud={'✓' if auditor_ok else '✗'} Met={'✓' if metodologico_ok else '✗'} "
            f"Debate={ronda_debate}/{max_rondas}"
        )

        # ── Protección anti-bucle (capa semántica) ────────────────────────────
        if pasos >= max_pasos:
            logger.warning(f"[Supervisor] Límite de pasos ({pasos}/{max_pasos}) → humano")
            resumen = (
                f"Límite de pasos alcanzado ({pasos}). "
                f"Iteraciones: {n_iter}/{max_iter}. Errores pendientes: {n_errores}."
            )
            return {
                "siguiente_nodo":           "humano",
                "instrucciones_supervisor": resumen,
                "plan_supervisor":          resumen,
                "pasos_ejecutados":         pasos + 1,
            }

        # ══════════════════════════════════════════════════════════════════════
        # ROUTING DETERMINISTA — Arquitectura de RED:
        #   Auditor → Metodólogo → Consenso → Disenso → Debate → Redactor
        #   El Redactor es la SÍNTESIS del ciclo, no el inicio.
        #   Condición: iter_xxx > n_iter significa "ya corrió en este ciclo".
        # ══════════════════════════════════════════════════════════════════════

        force       = None
        force_razon = ""
        force_inst  = ""

        seccion = state["seccion_objetivo"]

        if not auditor_ok:
            # Fase 1 — El Auditor evalúa el texto actual (original o mejorado)
            fuente = "texto mejorado" if state.get("texto_iterado") else "texto original del PDF"
            force       = "auditor"
            force_razon = f"Ciclo {n_iter}: Auditor evalúa el {fuente}"
            force_inst  = (
                f"Evalúa rigurosamente '{seccion}' contra todos los ítems de la rúbrica. "
                "Puntúa cada ítem 0-3 y señala errores bloqueantes (puntaje < 2)."
            )

        elif not metodologico_ok:
            # Fase 2 — El Metodólogo evalúa rigor y coherencia cruzada
            force       = "metodologico"
            force_razon = f"Ciclo {n_iter}: Metodólogo evalúa rigor científico"
            force_inst  = (
                "Evalúa el rigor metodológico y la coherencia con otras secciones. "
                "Identifica inconsistencias con el diseño, variables, hipótesis o instrumentos."
            )

        elif not consenso_ok:
            # Fase 3 — CONSENSO obligatorio: síntesis de acuerdos entre evaluadores
            force       = "consenso"
            force_razon = f"Ciclo {n_iter}: Consenso obligatorio — sintetiza acuerdos entre evaluadores"
            force_inst  = (
                "Identifica en qué puntos coinciden el Auditor y el Metodólogo. "
                "Prioriza los errores más críticos para el debate."
            )

        elif not disenso_ok:
            # Fase 4 — DISENSO obligatorio: identifica conflictos entre evaluadores
            force       = "disenso"
            force_razon = f"Ciclo {n_iter}: Disenso obligatorio — identifica conflictos entre evaluadores"
            force_inst  = (
                "Identifica contradicciones entre Auditor y Metodólogo. "
                "Señala ítems donde sus evaluaciones son opuestas y recomienda cómo resolverlos."
            )

        elif n_errores > 0 and ronda_debate < max_rondas:
            # Fase 5 — DEBATE obligatorio: todos evaluaron, hay errores, quedan rondas
            items_str = ", ".join(
                f"ítem {e['item_numero']}"
                for e in state.get("errores_rubrica", [])[:6]
            )
            force       = "debate"
            force_razon = (
                f"DEBATE OBLIGATORIO: {n_errores} errores · "
                f"Ronda {ronda_debate + 1}/{max_rondas}"
            )
            force_inst  = (
                f"El Redactor argumenta sus decisiones para: {items_str}. "
                "Los Evaluadores emiten veredicto ítem por ítem. "
                "Actualiza errores_rubrica: elimina los ítems aceptados."
            )

        elif n_iter < max_iter and (
            n_errores > 0 or not state.get("texto_iterado")
        ):
            # Fase 6 — REDACTOR:
            #   a) Hay errores que corregir, o
            #   b) El debate resolvió todos los errores conceptualmente pero el
            #      texto mejorado aún no se ha generado (texto_iterado vacío).
            if n_errores > 0:
                errores_crit = "; ".join(
                    f"ítem {e['item_numero']}: {e['descripcion'][:60]}"
                    for e in state.get("errores_rubrica", [])[:3]
                )
                force_inst = (
                    f"Mejora ÚNICAMENTE lo necesario para corregir: {errores_crit}. "
                    "NO inventes datos. Preserva el contenido y la voz del estudiante."
                )
                force_razon = (
                    f"Debate concluido. Ciclo {n_iter + 1}/{max_iter}: "
                    f"Redactor corrige {n_errores} error(es)"
                )
            else:
                # Debate aceptó todos los errores → Redactor aplica las correcciones al texto
                force_inst = (
                    "Aplica las correcciones propuestas en el debate al texto original. "
                    "Produce el texto mejorado final. NO inventes datos."
                )
                force_razon = (
                    "Debate resolvió todos los errores — Redactor genera el texto mejorado"
                )
            force = "redactor"

        elif n_errores == 0 or n_iter >= max_iter:
            # Fase 7 — HUMANO: sin errores o ciclos agotados
            if n_errores == 0:
                force_razon = (
                    f"Texto aprobado por rúbrica: 0 errores bloqueantes "
                    f"(puntaje {state.get('puntaje_estimado', 0)} pts)"
                )
                force_inst = "El texto cumple todos los ítems. Presentar al mentor para revisión final."
            else:
                force_razon = f"Ciclos agotados ({n_iter}/{max_iter}) — {n_errores} observaciones pendientes"
                force_inst  = (
                    f"Se completaron {n_iter} ciclos. "
                    f"Quedan {n_errores} observaciones para que el mentor decida."
                )
            force = "humano"

        # ── Si hay una decisión determinista, devolverla sin llamar al LLM ─────
        if force is not None:
            logger.info(f"[Supervisor] Fase determinista → {force.upper()} | {force_razon}")
            extra = {"ronda_debate": 0} if force == "redactor" else {}
            return {
                "siguiente_nodo":           force,
                "instrucciones_supervisor": force_inst,
                "plan_supervisor":          f"[{force.upper()}] {force_inst}",
                "pasos_ejecutados":         pasos + 1,
                **extra,
            }

        # ── Caso residual (no debería ocurrir en flujo normal) → LLM decide ────
        texto_generado_str  = "SÍ" if state.get("texto_iterado") else "NO"
        auditor_ok_str      = "SÍ" if auditor_ok else "NO"
        metodologico_ok_str = "SÍ" if metodologico_ok else "NO"
        consenso_ok_str     = "SÍ" if consenso_ok else "NO"
        disenso_ok_str      = "SÍ" if disenso_ok else "NO"

        decision: DecisionSupervisor = invocar_con_backoff(chain, {
            "seccion":                   state["seccion_objetivo"],
            "numero_iteracion":          n_iter,
            "max_iteraciones":           max_iter,
            "pasos_ejecutados":          pasos,
            "max_pasos_red":             max_pasos,
            "texto_generado":            texto_generado_str,
            "auditor_ok":                auditor_ok_str,
            "metodologico_ok":           metodologico_ok_str,
            "consenso_ok":               consenso_ok_str,
            "disenso_ok":                disenso_ok_str,
            "n_errores":                 n_errores,
            "ronda_debate":              ronda_debate,
            "max_rondas_debate":         max_rondas,
            "feedback_auditor":          state.get("feedback_auditor") or "Aún no disponible.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "Aún no disponible.",
            "resultado_consenso":        state.get("resultado_consenso") or "Sin análisis de consenso aún.",
            "resultado_disenso":         state.get("resultado_disenso") or "Sin análisis de disenso aún.",
            "veredicto_debate":          state.get("veredicto_debate") or "Sin debate aún.",
            "plan_anterior":             state.get("plan_supervisor") or "Primera decisión del ciclo.",
        })

        logger.info(
            f"[Supervisor] LLM decidió: {decision.siguiente.upper()} | {decision.razon[:80]}…"
        )

        extra = {"ronda_debate": 0} if decision.siguiente == "redactor" else {}
        return {
            "siguiente_nodo":           decision.siguiente,
            "instrucciones_supervisor": decision.instrucciones,
            "plan_supervisor":          f"[{decision.siguiente.upper()}] {decision.instrucciones}",
            "pasos_ejecutados":         pasos + 1,
            **extra,
        }

    return nodo_supervisor
