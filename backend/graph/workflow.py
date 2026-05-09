"""
Grafo multiagente de mentoría académica — topología de red fork-join.

Topología:
  START → Supervisor_inicio → Redactor
                                  ↓ (FORK — paralelo)
                        Auditor ──┤
                     Metodólogo ──┘ (JOIN)
                                  ↓
                              Debate ←── (bucle propio ronda_debate)
                                  ↓
                      Supervisor_veredicto
                                  ↓
          (errores y < max_iter) → Redactor  (ciclo principal)
          (ok o límite)          → Humano → END
"""

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq

from .state import MentoriaState
from .nodes import (
    make_nodo_supervisor_inicio,
    make_nodo_supervisor_veredicto,
    make_nodo_redactor,
    make_nodo_auditor,
    make_nodo_metodologico,
    make_nodo_debate,
    nodo_humano,
)
from .edges import routing_debate, routing_post_supervisor

load_dotenv()


def _llm(env_key: str, temperatura: float = 0.3) -> ChatGroq:
    """Crea un ChatGroq con la clave de API específica del agente."""
    api_key = os.getenv(env_key) or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            f"No se encontró la variable de entorno '{env_key}' ni 'GROQ_API_KEY'. "
            "Configura tu .env con las claves de Groq."
        )
    return ChatGroq(
        api_key=api_key,
        model="llama-3.3-70b-versatile",
        temperature=temperatura,
        max_retries=2,
    )


# Límite de supersteps:
# Cada iteración principal = ~6 supersteps (ver comentario abajo)
# Con 5 iter max × 6 steps + overhead → 40 es seguro
# Supersteps por iteración:
#   1. supervisor_inicio
#   2. redactor
#   3. auditor + metodologico (paralelo = 1 superstep)
#   4. debate ronda 1
#   5. debate ronda 2  (max_rondas_debate=2)
#   6. supervisor_veredicto
RECURSION_LIMIT = 40


def create_graph():
    """Construye y compila el StateGraph multiagente de red fork-join."""

    # ── Un LLM por agente (clave API propia) ─────────────────────────────────
    llm_supervisor   = _llm("GROQ_KEY_SUPERVISOR",   temperatura=0.2)
    llm_redactor     = _llm("GROQ_KEY_REDACTOR",     temperatura=0.4)
    llm_auditor      = _llm("GROQ_KEY_AUDITOR",      temperatura=0.1)
    llm_metodologico = _llm("GROQ_KEY_METODOLOGICO", temperatura=0.2)

    builder = StateGraph(MentoriaState)

    # ── Registrar nodos ───────────────────────────────────────────────────────
    builder.add_node("nodo_supervisor_inicio",    make_nodo_supervisor_inicio(llm_supervisor))
    builder.add_node("nodo_redactor",             make_nodo_redactor(llm_redactor))
    builder.add_node("nodo_auditor",              make_nodo_auditor(llm_auditor))
    builder.add_node("nodo_metodologico",         make_nodo_metodologico(llm_metodologico))
    builder.add_node("nodo_debate",               make_nodo_debate(llm_redactor, llm_auditor))
    builder.add_node("nodo_supervisor_veredicto", make_nodo_supervisor_veredicto(llm_supervisor))
    builder.add_node("nodo_humano",               nodo_humano)

    # ── Flujo principal ───────────────────────────────────────────────────────
    builder.set_entry_point("nodo_supervisor_inicio")
    builder.add_edge("nodo_supervisor_inicio", "nodo_redactor")

    # FORK → paralelo (Auditor y Metodólogo corren simultáneamente)
    builder.add_edge("nodo_redactor", "nodo_auditor")
    builder.add_edge("nodo_redactor", "nodo_metodologico")

    # JOIN → debate espera a que ambos terminen
    builder.add_edge("nodo_auditor",      "nodo_debate")
    builder.add_edge("nodo_metodologico", "nodo_debate")

    # Bucle propio del debate
    builder.add_conditional_edges(
        "nodo_debate",
        routing_debate,
        {
            "continuar_debate":     "nodo_debate",
            "supervisor_veredicto": "nodo_supervisor_veredicto",
        },
    )

    # Bucle principal (Supervisor decide iterar o pasar al humano)
    builder.add_conditional_edges(
        "nodo_supervisor_veredicto",
        routing_post_supervisor,
        {
            "nodo_redactor": "nodo_supervisor_inicio",   # nuevo ciclo → pasa por Supervisor primero
            "nodo_humano":   "nodo_humano",
        },
    )
    builder.add_edge("nodo_humano", END)

    checkpointer = MemorySaver()
    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["nodo_humano"],
    )
    return graph


def get_run_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }
