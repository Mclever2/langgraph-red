"""
Nodo Humano (HITL pasarela) — Punto de revisión y aprobación del mentor.

El grafo se PAUSA automáticamente ANTES de ejecutar este nodo
gracias a `interrupt_before=["nodo_humano"]` en workflow.py.

Flujo HITL en Streamlit:
  1. graph.invoke() llega aquí y el grafo se detiene
  2. Streamlit lee el estado con graph.get_state(config)
  3. El mentor revisa, edita y aprueba/rechaza
  4. Streamlit llama a graph.update_state(config, {aprobacion_humana, texto_iterado})
  5. graph.invoke(None, config) reanuda → este nodo ejecuta → END

Este nodo NO modifica el estado: la decisión ya fue inyectada por Streamlit.
"""

import logging

from ..state import MentoriaState

logger = logging.getLogger(__name__)


def nodo_humano(state: MentoriaState) -> dict:
    """
    Nodo de revisión humana (Human-in-the-Loop).

    No realiza ninguna transformación: solo registra la decisión que
    Streamlit ya inyectó con graph.update_state() antes de reanudar.
    """
    aprobacion = state.get("aprobacion_humana", "aprobado")
    logger.info(f"[Humano] Decisión registrada: {aprobacion}")
    return {"aprobacion_humana": aprobacion}
