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
        logger.info(f"[Metodólogo] Pausa 5s anti-rate-limit...")
        time.sleep(5)

        seccion = state["seccion_objetivo"]
        n_iter  = state.get("numero_iteracion", 0)

        # Evalúa el texto actual: mejorado si existe, original del PDF si no
        texto_a_evaluar = state.get("texto_iterado") or state.get("contexto_recuperado", "")
        fuente_texto    = "mejorado" if state.get("texto_iterado") else "original del PDF"
        logger.info(f"[Metodólogo] Ciclo {n_iter} | Texto: {fuente_texto} | Sección: {seccion}")

        respuesta = invocar_con_backoff(chain, {
            "seccion":                  seccion,
            "texto_iterado":            texto_a_evaluar,
            "contexto_dependencias":    state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_recuperado":      state.get("contexto_recuperado", ""),
            "contexto_teorico":         state.get("contexto_teorico") or "",
            "numero_iteracion":         n_iter,
        })

        logger.info(f"[Metodólogo] Evaluación completada ({len(respuesta.content)} chars)")
        return {
            "observaciones_metodologicas": respuesta.content.strip(),
            "iter_metodologica":           n_iter + 1,
        }

    return nodo_metodologico
