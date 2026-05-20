"""
Agente Supervisor Orquestador — Corazón de la red multiagente.

En la arquitectura de RED PURA, este nodo es el único que decide el flujo.
El LLM analiza el estado completo y elige el siguiente agente a ejecutar.
Si el LLM falla o devuelve un valor inválido, se aplica un fallback determinista.

Flujo:
  START → supervisor → [redactor | auditor | metodologico | debate | consenso | disenso | fin]
              ↑______________________________________________|
  (todos los agentes regresan al supervisor tras su ejecución)

Protección anti-bucle infinito:
  - pasos_ejecutados se incrementa en cada llamada al supervisor
  - Si pasos_ejecutados >= max_pasos_red → fuerza "fin" sin llamar al LLM
  - Capa adicional: recursion_limit en workflow.py
"""

import logging

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)

NODOS_VALIDOS = {
    "auditor", "metodologico", "consenso", "disenso",
    "debate_auditor", "debate_metodologo", "redactor", "fin"
}


def _fallback_routing(state: MentoriaState) -> str:
    """
    Fallback determinista SOLO si el LLM falla o devuelve valor inválido.
    Este es el último recurso, no el camino normal.
    """
    n_iter     = state.get("numero_iteracion", 0)
    max_iter   = state.get("max_iteraciones", 3)
    n_errores  = len(state.get("errores_rubrica") or [])
    ronda      = state.get("ronda_debate", 0)
    max_rondas = state.get("max_rondas_debate", 2)
    pasos      = state.get("pasos_ejecutados", 0)
    max_pasos  = state.get("max_pasos_red", 40)

    if pasos >= max_pasos:
        return "fin"
    if not state.get("iter_auditada"):
        return "auditor"
    if not state.get("iter_metodologica"):
        return "metodologico"
    if not state.get("iter_consenso"):
        return "consenso"
    if not state.get("iter_disenso"):
        return "disenso"
    if n_errores > 0 and ronda < max_rondas:
        if state.get("debate_auditor_ronda", 0) <= ronda:
            return "debate_auditor"
        if state.get("debate_metodologo_ronda", 0) <= ronda:
            return "debate_metodologo"
    if state.get("texto_iterado") is None or (n_errores > 0 and n_iter < max_iter):
        return "redactor"
    return "fin"


def _validar_decision_semantica(siguiente: str, state: MentoriaState) -> str | None:
    """
    Valida que la decisión del LLM sea semánticamente coherente con el estado.
    Retorna None si es válida, o un string con el motivo del rechazo si no lo es.
    """
    n_iter     = state.get("numero_iteracion", 0)
    max_iter   = state.get("max_iteraciones", 3)
    n_errores  = len(state.get("errores_rubrica") or [])
    ronda      = state.get("ronda_debate", 0)
    max_rondas = state.get("max_rondas_debate", 2)
    iter_auditada           = state.get("iter_auditada", 0)
    iter_metodologica       = state.get("iter_metodologica", 0)
    iter_consenso           = state.get("iter_consenso", 0)
    iter_disenso            = state.get("iter_disenso", 0)
    debate_auditor_ronda    = state.get("debate_auditor_ronda", 0)

    auditor_ok      = iter_auditada > n_iter
    metodologico_ok = iter_metodologica > n_iter
    consenso_ok     = iter_consenso > n_iter
    disenso_ok      = iter_disenso > n_iter

    if siguiente == "fin":
        if not auditor_ok:
            return "fin sin auditor ejecutado"
        if n_errores > 0 and n_iter < max_iter:
            return f"fin con {n_errores} errores y {max_iter - n_iter} iteraciones restantes"
        if not state.get("texto_iterado"):
            return "fin sin texto mejorado generado"

    if siguiente == "redactor":
        if not consenso_ok:
            return "redactor sin consenso ejecutado"
        if not disenso_ok:
            return "redactor sin disenso ejecutado"

    if siguiente == "consenso" and (not auditor_ok or not metodologico_ok):
        return "consenso sin auditor y metodólogo completos"

    if siguiente == "disenso" and (not auditor_ok or not metodologico_ok):
        return "disenso sin auditor y metodólogo completos"

    if siguiente == "debate_metodologo" and debate_auditor_ronda <= ronda:
        return "debate_metodologo sin debate_auditor previo en esta ronda"

    if siguiente == "debate_auditor" and n_errores == 0:
        return "debate_auditor sin errores activos"

    return None  # decisión válida


def make_nodo_supervisor(llm: ChatGroq):
    """
    Fábrica del Supervisor Orquestador.

    Devuelve un nodo que:
      1. Verifica el límite de pasos (anti-bucle)
      2. Llama al LLM con el estado completo para decidir el siguiente nodo
      3. Valida la respuesta y aplica fallback si es inválida
      4. Retorna la decisión de routing + actualizaciones de estado
    """
    plantilla = cargar_prompt("supervisor_red_prompt.md")

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human", "Decide el siguiente nodo."),
    ])
    chain = prompt | llm

    def nodo_supervisor(state: MentoriaState) -> dict:
        pasos      = state.get("pasos_ejecutados", 0)
        max_pasos  = state.get("max_pasos_red", 30)
        n_iter     = state.get("numero_iteracion", 0)
        max_iter   = state.get("max_iteraciones", 3)
        n_errores  = len(state.get("errores_rubrica") or [])
        ronda      = state.get("ronda_debate", 0)
        max_rondas = state.get("max_rondas_debate", 2)

        iter_auditada           = state.get("iter_auditada", 0)
        iter_metodologica       = state.get("iter_metodologica", 0)
        iter_consenso           = state.get("iter_consenso", 0)
        iter_disenso            = state.get("iter_disenso", 0)
        debate_auditor_ronda    = state.get("debate_auditor_ronda", 0)
        debate_metodologo_ronda = state.get("debate_metodologo_ronda", 0)

        auditor_ok      = iter_auditada > n_iter
        metodologico_ok = iter_metodologica > n_iter
        consenso_ok     = iter_consenso > n_iter
        disenso_ok      = iter_disenso > n_iter

        logger.info(
            f"[Supervisor] Paso {pasos + 1}/{max_pasos} | "
            f"Iter {n_iter}/{max_iter} | Errores={n_errores} | "
            f"Aud={'✓' if auditor_ok else '✗'} Met={'✓' if metodologico_ok else '✗'} "
            f"Debate={ronda}/{max_rondas}"
        )

        # ── Protección anti-bucle (capa semántica) ────────────────────────────
        if pasos >= max_pasos:
            logger.warning(f"[Supervisor] Límite de pasos ({pasos}/{max_pasos}) → fin")
            return {
                "siguiente_nodo":           "fin",
                "instrucciones_supervisor": f"Límite de pasos alcanzado ({pasos}). Fin forzado.",
                "plan_supervisor":          "[FIN] Límite de pasos alcanzado",
                "pasos_ejecutados":         pasos + 1,
            }

        # ── Construir contexto para el LLM ────────────────────────────────────
        llm_input = {
            "seccion":              state.get("seccion_objetivo", ""),
            "numero_iteracion":     n_iter,
            "max_iteraciones":      max_iter,
            "auditor_ok":           auditor_ok,
            "metodologico_ok":      metodologico_ok,
            "consenso_ok":          consenso_ok,
            "disenso_ok":           disenso_ok,
            "n_errores":            n_errores,
            "ronda_debate":         ronda,
            "max_rondas_debate":    max_rondas,
            "debate_auditor_ok":    debate_auditor_ronda > ronda,
            "debate_metodologo_ok": debate_metodologo_ronda > ronda,
            "puntaje_estimado":     state.get("puntaje_estimado"),
            "tiene_texto_iterado":  bool(state.get("texto_iterado")),
        }

        # ── El LLM decide el siguiente nodo ───────────────────────────────────
        try:
            respuesta = invocar_con_backoff(chain, llm_input)
            siguiente = respuesta.content.strip().lower().strip(".,;:")
            if siguiente not in NODOS_VALIDOS:
                logger.warning(f"[Supervisor] LLM devolvió '{siguiente}' inválido → fallback")
                siguiente = _fallback_routing(state)
            else:
                motivo_rechazo = _validar_decision_semantica(siguiente, state)
                if motivo_rechazo:
                    logger.warning(
                        f"[Supervisor] LLM dijo '{siguiente}' pero es semánticamente inválido "
                        f"({motivo_rechazo}) → fallback"
                    )
                    siguiente = _fallback_routing(state)
                else:
                    logger.info(f"[Supervisor] LLM decidió → {siguiente}")
        except Exception as exc:
            logger.warning(f"[Supervisor] LLM falló ({exc}) → fallback")
            siguiente = _fallback_routing(state)

        # ── Resetear contadores de debate al enrutar al Redactor ─────────────
        extra = {
            "ronda_debate":             0,
            "debate_auditor_ronda":     0,
            "debate_metodologo_ronda":  0,
            "argumento_debate_auditor": "",
        } if siguiente == "redactor" else {}

        return {
            "siguiente_nodo":           siguiente,
            "instrucciones_supervisor": f"LLM → {siguiente}",
            "plan_supervisor":          f"[{siguiente.upper()}] decisión LLM",
            "pasos_ejecutados":         pasos + 1,
            **extra,
        }

    return nodo_supervisor
