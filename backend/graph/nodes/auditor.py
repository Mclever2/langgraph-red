"""
Nodo Auditor — Evalúa el texto contra los ítems REALES de la rúbrica oficial UPAO.

Usa with_structured_output(AuditorOutput) para garantizar JSON válido y tipado.
Incluye sleep(3) obligatorio anti-rate-limit para la API gratuita de Groq.
"""

import time
import logging
from typing import List

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff
from backend.config import get_items_texto_para_seccion, get_puntaje_maximo_seccion

logger = logging.getLogger(__name__)


# ── Modelos Pydantic para la salida estructurada ──────────────────────────────

class ItemEvaluado(BaseModel):
    """Evaluación de un ítem individual de la rúbrica UPAO."""
    item_numero: int = Field(ge=1, le=33, description="Número del ítem (01-33)")
    puntaje:     int = Field(ge=0, le=3,  description="0=Insuficiente 1=Regular 2=Bueno 3=Excelente")
    observacion: str = Field(description="Observación específica para este ítem")


class AuditorOutput(BaseModel):
    """Salida estructurada completa del Nodo Auditor."""
    items_evaluados:  List[ItemEvaluado] = Field(
        description="Evaluación de cada ítem relevante para la sección"
    )
    aprobado:         bool = Field(
        description="True SOLO si todos los ítems evaluados tienen puntaje >= 2"
    )
    feedback_general: str = Field(
        description="Retroalimentación detallada y accionable para el Redactor"
    )
    puntaje_total:    int = Field(
        ge=0, description="Suma total de puntajes de los ítems evaluados"
    )


# ── Fábrica del nodo ──────────────────────────────────────────────────────────

def make_nodo_auditor(llm: ChatGroq):
    """
    Fábrica del Nodo Auditor.

    Evalúa el texto del Redactor contra los ítems EXACTOS de la rúbrica oficial
    UPAO (Ficha de Evaluación de Proyecto de Tesis — Facultad de Ingeniería).

    Usa with_structured_output(AuditorOutput) para garantizar JSON válido.
    Incluye sleep(3) obligatorio para no saturar los TPM de la API gratuita de Groq.
    """
    plantilla_sistema = cargar_prompt("auditor_prompt.md")
    llm_estructurado  = llm.with_structured_output(AuditorOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", "Evalúa el texto y devuelve tu evaluación estructurada según la rúbrica UPAO."),
    ])
    chain = prompt | llm_estructurado

    def nodo_auditor(state: MentoriaState) -> dict:
        # ── Pausa obligatoria anti-rate-limit ─────────────────────────────────
        logger.info("[Auditor] Pausa 3 s anti-rate-limit...")
        time.sleep(3)

        seccion = state["seccion_objetivo"]
        logger.info(
            f"[Auditor] Evaluando iteración #{state.get('numero_iteracion', 1)} "
            f"| Sección: {seccion}"
        )

        # Construir la tabla de ítems relevantes para esta sección
        items_texto = get_items_texto_para_seccion(seccion)
        puntaje_max = get_puntaje_maximo_seccion(seccion)

        resultado: AuditorOutput = invocar_con_backoff(chain, {
            "seccion":                  seccion,
            "texto_iterado":            state["texto_iterado"],
            "items_rubrica":            items_texto,
            "puntaje_max":              puntaje_max,
            "contexto_dependencias":    state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
        })

        # Solo ítems con puntaje < 2 se consideran "errores" a corregir
        errores = [
            {
                "item_numero":    item.item_numero,
                "puntaje_actual": item.puntaje,
                "descripcion":    item.observacion,
            }
            for item in resultado.items_evaluados
            if item.puntaje < 2
        ]

        logger.info(
            f"[Auditor] Aprobado={resultado.aprobado} | "
            f"Puntaje={resultado.puntaje_total}/{puntaje_max} | "
            f"Errores={len(errores)}"
        )

        return {
            "feedback_auditor": resultado.feedback_general,
            "errores_rubrica":  errores,
            "puntaje_estimado": resultado.puntaje_total,
            # Informa al Supervisor que el Auditor ya corrió en esta iteración
            "iter_auditada":    state.get("numero_iteracion", 1),
        }

    return nodo_auditor
