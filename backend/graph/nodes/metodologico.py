"""
Agente Metodólogo — Rigor científico y coherencia cruzada entre secciones.

CAMBIO 4: usa ContextLoader para obtener instrucciones institucionales dinámicas.
Fallback: si ContextLoader falla, usa el prompt UPAO del archivo metodologico_prompt.md.

Corre en PARALELO con el Auditor (fork-join).
"""

import time
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff

logger = logging.getLogger(__name__)


def make_nodo_metodologico(llm: ChatGroq):
    plantilla_base = cargar_prompt("metodologico_prompt.md")
    prompt_base = ChatPromptTemplate.from_messages([
        ("system", plantilla_base),
        ("human", "Evalúa el rigor metodológico y la coherencia cruzada del texto para la sección '{seccion}'."),
    ])
    chain_base = prompt_base | llm

    def nodo_metodologico(state: MentoriaState) -> dict:
        logger.info("[Metodólogo] Pausa 5s anti-rate-limit...")
        time.sleep(5)

        seccion = state["seccion_objetivo"]
        n_iter  = state.get("numero_iteracion", 0)
        universidad = state.get("universidad", "upao")
        programa    = state.get("programa", "ingeniería de sistemas")

        texto_a_evaluar = state.get("texto_iterado") or state.get("contexto_recuperado", "")
        fuente_texto    = "mejorado" if state.get("texto_iterado") else "original del PDF"
        logger.info(f"[Metodólogo] Ciclo {n_iter} | Texto: {fuente_texto} | Sección: {seccion}")

        # Intentar enriquecer el system prompt con instrucciones institucionales
        chain = chain_base
        try:
            from context.context_loader import ContextLoader
            loader = ContextLoader()
            contexto = loader.get(universidad=universidad, programa=programa)
            instrucciones = loader.construir_system_prompt_metodologo(contexto)
            prompt_enriquecido = ChatPromptTemplate.from_messages([
                ("system", instrucciones + "\n\n---\n\n" + plantilla_base),
                ("human", "Evalúa el rigor metodológico y la coherencia cruzada del texto para la sección '{seccion}'."),
            ])
            chain = prompt_enriquecido | llm
            logger.info(f"[Metodólogo] ContextLoader OK — {contexto.get('universidad', '?')}")
        except Exception as exc:
            logger.debug(f"[Metodólogo] ContextLoader no disponible ({exc}), usando prompt base")

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
