"""
Nodo Auditor — Evalúa el texto contra la rúbrica activa.

Si el estudiante subió su propia rúbrica (state["rubrica_dinamica"]),
la usa para evaluar. De lo contrario, usa la rúbrica oficial UPAO de config.py.

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
from backend.rag.rubric_parser import rubrica_a_texto_prompt

logger = logging.getLogger(__name__)


# ── Modelos Pydantic para salida estructurada ─────────────────────────────────

class ItemEvaluado(BaseModel):
    """Evaluación de un ítem individual de la rúbrica."""
    item_numero: int = Field(ge=1, le=999, description="Número del ítem de la rúbrica")
    puntaje:     int = Field(ge=0, le=3,   description="0=Insuficiente 1=Regular 2=Bueno 3=Excelente")
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

    Evalúa el texto contra la rúbrica activa:
    - Rúbrica dinámica del estudiante (si fue subida)
    - Rúbrica UPAO hardcodeada (fallback)

    Usa with_structured_output(AuditorOutput) para garantizar JSON válido.
    """
    plantilla_sistema = cargar_prompt("auditor_prompt.md")
    llm_estructurado  = llm.with_structured_output(AuditorOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", "Evalúa el texto y devuelve tu evaluación estructurada según la rúbrica."),
    ])
    chain = prompt | llm_estructurado

    def nodo_auditor(state: MentoriaState) -> dict:
        logger.info("[Auditor] Pausa 3 s anti-rate-limit...")
        time.sleep(3)

        seccion  = state["seccion_objetivo"]
        n_iter   = state.get("numero_iteracion", 0)
        rubrica  = state.get("rubrica_dinamica")

        # Evalúa texto_iterado si existe, sino el texto original del PDF
        texto_a_evaluar = state.get("texto_iterado") or state.get("contexto_recuperado", "")
        fuente_texto    = "mejorado" if state.get("texto_iterado") else "original del PDF"

        logger.info(
            f"[Auditor] Ciclo {n_iter} | Sección: {seccion} | "
            f"Texto: {fuente_texto} | Rúbrica: {'dinámica' if rubrica else 'UPAO'}"
        )

        # ── Construir tabla de ítems y puntaje máximo ─────────────────────────
        if rubrica:
            items_texto  = rubrica_a_texto_prompt(rubrica)
            puntaje_max  = rubrica.get("puntaje_maximo", len(rubrica.get("items", [])) * 3)
            rubrica_desc = "rúbrica subida por el estudiante"
        else:
            items_texto  = get_items_texto_para_seccion(seccion)
            puntaje_max  = get_puntaje_maximo_seccion(seccion)
            rubrica_desc = "rúbrica oficial UPAO"

        resultado: AuditorOutput = invocar_con_backoff(chain, {
            "seccion":               seccion,
            "texto_iterado":         texto_a_evaluar,
            "items_rubrica":         items_texto,
            "puntaje_max":           puntaje_max,
            "rubrica_descripcion":   rubrica_desc,
            "contexto_dependencias": state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":      state.get("contexto_teorico") or "",
        })

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
            # iter_auditada = n_iter + 1 para que auditor_ok = iter > n_iter
            "iter_auditada":    n_iter + 1,
            "_puntaje_max":     puntaje_max,
        }

    return nodo_auditor
