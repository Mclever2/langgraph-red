"""
Grafo multiagente de mentoría académica — ARQUITECTURA DE RED PURA.

Topología:
  START → nodo_supervisor ←─────────────────────────────────────────────────────┐
               │  (conditional edge: lee state["siguiente_nodo"])               │
               ├──────────────→ nodo_redactor ────────────────────────────────┤ │
               ├──────────────→ nodo_auditor ─────────────────────────────────┤ │
               ├──────────────→ nodo_metodologico ───────────────────────────┤ │
               ├──────────────→ nodo_debate_auditor ──────────────────────────┤ │
               │                  (escribe argumento al estado)               │ │
               ├──────────────→ nodo_debate_metodologo ─────────────────────┤ │
               │                  (lee argumento del estado, emite veredicto) │ │
               ├──────────────→ nodo_consenso ────────────────────────────────┤ │
               ├──────────────→ nodo_disenso ─────────────────────────────────┘ │
               └──────────────→ END  (cuando siguiente_nodo == "fin")            │
  Todos los nodos regresan al Supervisor via edge fijo ──────────────────────────┘

Debate inter-agente real:
  Supervisor → debate_auditor (escribe al estado) → Supervisor
  Supervisor → debate_metodologo (lee del estado) → Supervisor
  Los agentes se comunican exclusivamente a través de MentoriaState,
  no por parámetros de función. Cada uno es un nodo independiente del grafo.

Protección anti-bucle:
  1. Semántica:  pasos_ejecutados >= max_pasos_red → Supervisor fuerza "fin"
  2. Sistémica:  recursion_limit = 80 supersteps (capa de seguridad de LangGraph)
"""

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq

from .state import MentoriaState
from .nodes import (
    make_nodo_supervisor,
    make_nodo_redactor,
    make_nodo_auditor,
    make_nodo_metodologico,
    make_nodo_debate_auditor,
    make_nodo_debate_metodologo,
    make_nodo_consenso,
    make_nodo_disenso,
    make_nodo_exportador,
)
from .edges import routing_supervisor

load_dotenv()

RECURSION_LIMIT = 80


def _llm(env_key: str, temperatura: float = 0.3) -> ChatGroq:
    """Crea un ChatGroq con la clave de API específica del agente."""
    api_key = os.getenv(env_key) or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            f"No se encontró '{env_key}' ni 'GROQ_API_KEY'. "
            "Configura tu .env con las claves de Groq."
        )
    return ChatGroq(
        api_key=api_key,
        model="llama-3.3-70b-versatile",
        temperature=temperatura,
        max_retries=2,
    )


def create_graph():
    """Construye y compila el StateGraph de red multiagente pura."""

    # ── Un LLM por agente (clave API propia → rate limits distribuidos) ───────
    llm_supervisor   = _llm("GROQ_KEY_SUPERVISOR",   temperatura=0.2)
    llm_redactor     = _llm("GROQ_KEY_REDACTOR",     temperatura=0.4)
    llm_auditor      = _llm("GROQ_KEY_AUDITOR",      temperatura=0.1)
    llm_metodologico = _llm("GROQ_KEY_METODOLOGICO", temperatura=0.2)
    llm_consenso     = _llm("GROQ_KEY_CONSENSO",     temperatura=0.2)
    llm_disenso      = _llm("GROQ_KEY_DISENSO",      temperatura=0.2)

    builder = StateGraph(MentoriaState)

    # ── Registrar todos los nodos ──────────────────────────────────────────────
    builder.add_node("nodo_supervisor",        make_nodo_supervisor(llm_supervisor))
    builder.add_node("nodo_redactor",          make_nodo_redactor(llm_redactor))
    builder.add_node("nodo_auditor",           make_nodo_auditor(llm_auditor))
    builder.add_node("nodo_metodologico",      make_nodo_metodologico(llm_metodologico))
    # Debate inter-agente real: dos nodos separados que se comunican por estado
    builder.add_node("nodo_debate_auditor",    make_nodo_debate_auditor(llm_auditor))
    builder.add_node("nodo_debate_metodologo", make_nodo_debate_metodologo(llm_metodologico))
    builder.add_node("nodo_consenso",          make_nodo_consenso(llm_consenso))
    builder.add_node("nodo_disenso",           make_nodo_disenso(llm_disenso))
    # Exportador: serializa el estado final antes de END (no usa LLM)
    builder.add_node("nodo_exportador",        make_nodo_exportador())

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.set_entry_point("nodo_supervisor")

    # ── Supervisor decide dinámicamente (RED PURA) ─────────────────────────────
    builder.add_conditional_edges(
        "nodo_supervisor",
        routing_supervisor,
        {
            "redactor":          "nodo_redactor",
            "auditor":           "nodo_auditor",
            "metodologico":      "nodo_metodologico",
            "debate_auditor":    "nodo_debate_auditor",    # Turno 1: Auditor escribe al estado
            "debate_metodologo": "nodo_debate_metodologo", # Turno 2: Metodólogo lee del estado
            "consenso":          "nodo_consenso",
            "disenso":           "nodo_disenso",
            "fin":               "nodo_exportador",
        },
    )

    # ── Todos los agentes regresan al Supervisor ──────────────────────────────
    builder.add_edge("nodo_redactor",          "nodo_supervisor")
    builder.add_edge("nodo_auditor",           "nodo_supervisor")
    builder.add_edge("nodo_metodologico",      "nodo_supervisor")
    builder.add_edge("nodo_debate_auditor",    "nodo_supervisor")
    builder.add_edge("nodo_debate_metodologo", "nodo_supervisor")
    builder.add_edge("nodo_consenso",          "nodo_supervisor")
    builder.add_edge("nodo_disenso",           "nodo_supervisor")
    builder.add_edge("nodo_exportador",        END)

    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


def get_run_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }
