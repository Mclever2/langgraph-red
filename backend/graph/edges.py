"""Funciones de routing del grafo multiagente."""

from .state import MentoriaState


def routing_debate(state: MentoriaState) -> str:
    """Decide si el debate necesita otra ronda o ya puede pasar al Supervisor."""
    ronda_actual   = state.get("ronda_debate", 0)
    max_rondas     = state.get("max_rondas_debate", 2)
    hay_errores    = len(state.get("errores_rubrica", [])) > 0

    # Si no quedan errores, no tiene sentido más debate
    if not hay_errores:
        return "supervisor_veredicto"

    # Si aún hay rondas disponibles y hay errores → continuar debate
    if ronda_actual < max_rondas:
        return "continuar_debate"

    return "supervisor_veredicto"


def routing_post_supervisor(state: MentoriaState) -> str:
    """Decide si el ciclo principal itera de nuevo o pasa al mentor humano."""
    tiene_errores    = len(state.get("errores_rubrica", [])) > 0
    limite_alcanzado = state.get("numero_iteracion", 0) >= state.get("max_iteraciones", 3)

    if tiene_errores and not limite_alcanzado:
        return "nodo_redactor"
    return "nodo_humano"
