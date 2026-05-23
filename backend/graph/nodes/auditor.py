"""
Nodo Auditor — Panel de 3 subagentes especializados con LoRA + MCP.

ARQUITECTURA:
  3 subagentes con roles especializados (LoRA):
    1. auditor_formal     (temp 0.05) — criterios formales y estructura
    2. auditor_equilibrado (temp 0.15) — balance rigor/contexto
    3. auditor_contextual  (temp 0.25) — coherencia global con objetivos

  Cada subagente ve los outputs anteriores (memoria compartida intra-nodo).
  El consenso se calcula ALGORÍTMICAMENTE con std_dev (no por LLM).
  Los errores consolidados requieren ≥ 2 de 3 subagentes de acuerdo.

  Fuentes MCP por subagente:
    - auditor_formal:      Drive (rúbrica institucional) + Biblioteca
    - auditor_equilibrado: Drive + Biblioteca + Tesis
    - auditor_contextual:  Tesis + Biblioteca

  Configuración por universidad/programa cargada desde:
    backend/lora/university_configs/{universidad}.yaml
"""

import logging
import os
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff
from ._rag_planner import obtener_contexto_dinamico
from ._panel_utils import (
    ejecutar_panel,
    consolidar_panel_evaluador,
    ResultadoSubagente,
)
from backend.config import get_items_texto_para_seccion, get_puntaje_maximo_seccion
from backend.rag.rubric_parser import rubrica_a_texto_prompt

logger = logging.getLogger(__name__)


# ── Modelos Pydantic de salida estructurada ───────────────────────────────────

class ItemEvaluado(BaseModel):
    item_numero: int = Field(ge=1, le=999, description="Número del ítem de la rúbrica")
    puntaje:     int = Field(ge=0, le=3,   description="0=Insuficiente 1=Regular 2=Bueno 3=Excelente")
    observacion: str = Field(description="Observación específica para este ítem")


class AuditorOutput(BaseModel):
    items_evaluados:  List[ItemEvaluado] = Field(description="Evaluación de cada ítem relevante")
    aprobado:         bool               = Field(description="True SOLO si todos los ítems >= 2")
    feedback_general: str                = Field(description="Retroalimentación accionable para el Redactor")
    puntaje_total:    int                = Field(ge=0, description="Suma total de puntajes")


# ── Helpers de extracción para consolidar_panel_evaluador ────────────────────

def _extraer_score(output: AuditorOutput) -> float:
    return float(output.puntaje_total)

def _extraer_items_error(output: AuditorOutput) -> list:
    return [
        {
            "item_numero":    i.item_numero,
            "puntaje_actual": i.puntaje,
            "descripcion":    i.observacion,
        }
        for i in output.items_evaluados
        if i.puntaje < 2
    ]


# ── Construcción de rúbrica desde estado ─────────────────────────────────────

def _construir_rubrica(state: MentoriaState, seccion: str) -> tuple[str, int, str]:
    """Retorna (items_texto, puntaje_max, descripcion_fuente)."""
    universidad = state.get("universidad", "upao")
    programa    = state.get("programa", "ingeniería de sistemas")

    try:
        from context.context_loader import ContextLoader
        loader  = ContextLoader()
        ctx     = loader.get(universidad=universidad, programa=programa)
        crit    = ctx.get("criterios", [])
        lineas  = [
            "| N° | Criterio | Peso | Puntaje (0-3) |",
            "|----|----------|------|--------------|",
        ]
        for i, c in enumerate(crit, 1):
            lineas.append(f"| {i:02d} | {c['nombre']}: {c['descripcion']} | {c.get('peso', '')} | ___ |")
        items_texto = "\n".join(lineas)
        puntaje_max = int(ctx.get("escala_maxima", 3) * len(crit))
        return items_texto, puntaje_max, f"rúbrica dinámica — {ctx['universidad']}"
    except Exception:
        pass

    rubrica = state.get("rubrica_dinamica")
    if rubrica:
        return (
            rubrica_a_texto_prompt(rubrica),
            rubrica.get("puntaje_maximo", len(rubrica.get("items", [])) * 3),
            "rúbrica subida por el estudiante",
        )

    return (
        get_items_texto_para_seccion(seccion),
        get_puntaje_maximo_seccion(seccion),
        "rúbrica oficial UPAO",
    )


# ── Fábrica del nodo ──────────────────────────────────────────────────────────

def make_nodo_auditor(llm: ChatOpenAI):
    """
    Construye el Nodo Auditor con panel de 3 subagentes (LoRA + MCP).
    Cada subagente usa el mismo modelo base pero con rol especializado distinto.
    """
    prompt_base = cargar_prompt("auditor_prompt.md")
    model_name  = getattr(llm, "model_name", "llama-3.3-70b-versatile")

    def nodo_auditor(state: MentoriaState) -> dict:
        logger.info("[Auditor] Iniciando panel de 3 subagentes (LoRA + MCP)...")

        seccion     = state["seccion_objetivo"]
        n_iter      = state.get("numero_iteracion", 0)
        universidad = state.get("universidad", "upao")
        programa    = state.get("programa", "ingeniería de sistemas")

        texto_a_evaluar = state.get("texto_iterado") or state.get("contexto_recuperado", "")
        fuente_texto    = "mejorado" if state.get("texto_iterado") else "original del PDF"

        # ── Enriquecer contexto: el auditor decide qué secciones necesita ver ─
        logger.info("[Auditor] Planificando contexto adicional con RAG dinámico…")
        contexto_dinamico = obtener_contexto_dinamico(
            llm          = llm,
            seccion      = seccion,
            texto_snippet= texto_a_evaluar[:500],
            rol          = "auditor especializado en rúbricas universitarias",
        )

        puntaje_previo = state.get("puntaje_estimado")
        puntaje_inicial_calc = (
            float(puntaje_previo)
            if puntaje_previo and float(puntaje_previo) > 0.0 and n_iter > 0
            else float(state.get("puntaje_inicial") or 0.0)
        )

        items_texto, puntaje_max, rubrica_desc = _construir_rubrica(state, seccion)

        logger.info(
            f"[Auditor] Ciclo {n_iter} | {seccion} | {fuente_texto} | "
            f"Rúbrica: {rubrica_desc} | Universidad: {universidad}"
        )

        # ── Inputs base comunes a todos los subagentes ────────────────────────
        inputs_base = {
            "seccion":               seccion,
            "texto_iterado":         texto_a_evaluar,
            "items_rubrica":         items_texto,
            "puntaje_max":           puntaje_max,
            "rubrica_descripcion":   rubrica_desc,
            "contexto_dependencias": contexto_dinamico or state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":      state.get("contexto_teorico") or "",
            "universidad":           universidad,
            "programa":              programa,
            # Drive y biblioteca se añaden dinámicamente via MCP fetch
            "rubrica_institucional_drive": "",
            "contexto_biblioteca_disponible": "",
            "contexto_secciones_relacionadas": "",
        }

        # ── Cargar LoRAs para esta universidad/programa ───────────────────────
        from backend.lora.lora_configs import get_loras_para_agente, TIPO_AUDITOR
        from backend.mcp.tools import crear_fetch_para_lora

        loras = get_loras_para_agente(TIPO_AUDITOR, universidad, programa)

        # ── Construir sub_items: (chain, lora_id, mcp_fetch_fn) ──────────────
        sub_items = []
        for lora in loras:
            sub_llm = ChatOpenAI(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model=model_name,
                temperature=lora.temperatura,
                max_retries=2,
            ).with_structured_output(AuditorOutput)

            # Prompt = base + modificador LoRA (con universidad embebida)
            system_prompt = lora.system_prompt_completo(prompt_base)

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", (
                    "Evalúa el texto para la sección '{seccion}' y devuelve tu evaluación estructurada.\n\n"
                    "**HISTORIAL DEL PANEL (evaluadores anteriores):**\n{historial_panel}\n\n"
                    "{rubrica_institucional_drive}"
                    "{contexto_biblioteca_disponible}"
                )),
            ])
            chain = prompt | sub_llm

            # MCP fetch según fuentes declaradas en el LoRA
            mcp_fn = crear_fetch_para_lora(lora.fuentes_datos, lora.drive_folder_id)

            sub_items.append((chain, lora.id, mcp_fn))

        # ── Ejecutar panel con memoria compartida ─────────────────────────────
        resultados = ejecutar_panel(sub_items, inputs_base, logger_prefix="Auditor")

        # ── Fallback: si el panel falla completamente, usar LLM base ─────────
        if not any(r.exitoso for r in resultados):
            logger.warning("[Auditor] Panel completo falló — usando LLM base como fallback")
            llm_struct = llm.with_structured_output(AuditorOutput)
            prompt_fallback = ChatPromptTemplate.from_messages([
                ("system", prompt_base),
                ("human", "Evalúa el texto y devuelve tu evaluación estructurada."),
            ])
            chain_fallback = prompt_fallback | llm_struct
            output_fb = invocar_con_backoff(chain_fallback, inputs_base)
            resultados = [ResultadoSubagente(lora_id="fallback", output=output_fb)]

        # ── Consolidar resultados algorítmicamente ────────────────────────────
        consolidado = consolidar_panel_evaluador(
            resultados=resultados,
            extraer_score=_extraer_score,
            extraer_items=_extraer_items_error,
            puntaje_max=puntaje_max,
        )

        # Feedback del subagente con puntaje más cercano al consenso
        score_consenso = consolidado["consenso_matematico"].get("score_consenso", 0)
        mejor = min(
            (r for r in resultados if r.exitoso),
            key=lambda r: abs(_extraer_score(r.output) - score_consenso),
            default=None,
        )
        feedback = mejor.output.feedback_general if mejor else "Sin feedback disponible."

        loras_usadas = [lora.id for lora in loras]

        return {
            "feedback_auditor":            feedback,
            "errores_rubrica":             consolidado["errores_consensuados"],
            "puntaje_estimado":            consolidado["score_final"],
            "puntaje_inicial":             puntaje_inicial_calc,
            "iter_auditada":               n_iter + 1,
            "_puntaje_max":                puntaje_max,
            "scores_subagentes":           consolidado["scores_subagentes"],
            "consenso_matematico_auditor": consolidado["consenso_matematico"],
            "loras_activas":               loras_usadas,
        }

    return nodo_auditor


