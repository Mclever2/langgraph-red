"""Paquete nodes — exporta todos los nodos del grafo multiagente de red."""

from .supervisor  import make_nodo_supervisor
from .redactor    import make_nodo_redactor
from .auditor     import make_nodo_auditor
from .metodologico import make_nodo_metodologico
from .debate      import make_nodo_debate
from .human       import nodo_humano

__all__ = [
    "make_nodo_supervisor",
    "make_nodo_redactor",
    "make_nodo_auditor",
    "make_nodo_metodologico",
    "make_nodo_debate",
    "nodo_humano",
]
