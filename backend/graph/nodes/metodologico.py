"""
Agente Metodólogo — Rigor científico y coherencia cruzada entre secciones.

Corre en PARALELO con el Auditor (fork-join). Evalúa:
  - Si la investigación tiene consistencia lógica interna
  - Si las secciones dependientes son coherentes entre sí
  - Aspectos de rigor que la rúbrica formal no captura
"""

import time
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_metodologico(llm: ChatGroq):
    plantilla = cargar_prompt("metodologico_prompt.md")
    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla),
        ("human", "Evalúa el rigor metodológico y la coherencia cruzada del texto para la sección '{seccion}'."),
    ])
    chain = prompt | llm

    def nodo_metodologico(state: MentoriaState) -> dict:
        logger.info(f"[Metodólogo] Pausa 5s anti-rate-limit (paralelo con Auditor)...")
        time.sleep(5)

        seccion = state["seccion_objetivo"]
        logger.info(f"[Metodólogo] Evaluando coherencia | Sección: {seccion}")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                  seccion,
            "texto_iterado":            state["texto_iterado"],
            "contexto_dependencias":    state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_recuperado":      state["contexto_recuperado"],
            "numero_iteracion":         state.get("numero_iteracion", 1),
        })

        logger.info(f"[Metodólogo] Evaluación completada ({len(respuesta.content)} chars)")
        return {
            "observaciones_metodologicas": respuesta.content.strip(),
            # Informa al Supervisor que el Metodólogo ya corrió en esta iteración
            "iter_metodologica": state.get("numero_iteracion", 1),
        }

    return nodo_metodologico
