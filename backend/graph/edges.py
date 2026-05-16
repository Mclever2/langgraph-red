"""
Routing de la red multiagente.

En la arquitectura de RED PURA el Supervisor escribe `siguiente_nodo`
en el estado y este router lo lee. No hay lógica aquí: toda la inteligencia
de routing vive en el LLM del Supervisor (nodes/supervisor.py).
"""

from .state import MentoriaState

# Destinos válidos que el Supervisor puede elegir
DESTINOS_VALIDOS = {
    "redactor",
    "auditor",
    "metodologico",
    "debate",
    "consenso",
    "disenso",
    "humano",
}


def routing_supervisor(state: MentoriaState) -> str:
    """
    Lee la decisión del Supervisor y devuelve el nombre del siguiente nodo.

    Si por algún motivo el valor no es válido (fallo del LLM),
    cae a 'humano' como destino seguro.
    """
    destino = state.get("siguiente_nodo", "humano")
    if destino not in DESTINOS_VALIDOS:
        return "humano"
    return destino
