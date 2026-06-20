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

    # 1. Rúbrica dinámica subida por el estudiante
    rubrica = state.get("rubrica_dinamica")
    if rubrica:
        return (
            rubrica_a_texto_prompt(rubrica),
            rubrica.get("puntaje_maximo", len(rubrica.get("items", [])) * 3),
            "rúbrica subida por el estudiante",
        )

    # 2. Si es UPAO, preferir evaluación fine-grained por ítem de rúbrica
    # CONFIRMACIÓN FIX 4: Esta asignación es 100% DINÁMICA y no hardcodeada.
    # No contiene números de ítems hardcodeados; los lee en tiempo real a través de
    # _buscar_items_seccion(seccion) y los asocia a RUBRICA_ITEMS_UPAO definidos en backend/config.py.
    from backend.config import _buscar_items_seccion, RUBRICA_ITEMS_UPAO
    items_seccion = _buscar_items_seccion(seccion)
    univ_lower = str(universidad).lower()
    if ("upao" in univ_lower or "antenor orrego" in univ_lower) and items_seccion:
        lineas = [
            "| N° | Ítem de la Rúbrica UPAO | Puntaje (0-3) |",
            "|----|-----------------------------|--------------|",
        ]
        for num in items_seccion:
            desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
            lineas.append(f"| {num:02d} | {desc} | ___ |")
        items_texto = "\n".join(lineas)
        puntaje_max = len(items_seccion) * 3
        return items_texto, puntaje_max, "rúbrica oficial UPAO (por ítems)"

    # 3. Fallback a ContextLoader (para otras universidades o si no hay items_seccion)
    try:
        from context.context_loader import ContextLoader
        loader  = ContextLoader()
        ctx     = loader.get(universidad=universidad, programa=programa)
        crit    = ctx.get("criterios", [])

        # Filtrar criterios si la sección tiene ítems específicos asignados
        if items_seccion:
            criterios_filtrados = []
            for c in crit:
                items_c = c.get("items_rubrica", [])
                if items_c:
                    if any(item in items_seccion for item in items_c):
                        criterios_filtrados.append(c)
                else:
                    criterios_filtrados.append(c)
            if criterios_filtrados:
                crit = criterios_filtrados

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
        if n_iter > 0 and not state.get("texto_iterado"):
            logger.warning("[Auditor] ¡Alerta! n_iter > 0 pero 'texto_iterado' está vacío. Usando 'contexto_recuperado' como fallback.")
        
        fuente_texto = "mejorado" if (n_iter > 0 and state.get("texto_iterado")) else "original"
        logger.info(f"[Auditor] Evaluando texto de {len(texto_a_evaluar)} chars | fuente: {fuente_texto}")

        items_texto, puntaje_max, rubrica_desc = _construir_rubrica(state, seccion)

        # ── Enriquecer contexto: el auditor decide qué secciones necesita ver ─
        logger.info("[Auditor] Planificando contexto adicional con RAG dinámico…")
        contexto_dinamico = obtener_contexto_dinamico(
            llm              = llm,
            seccion          = seccion,
            texto_snippet    = texto_a_evaluar[:500],
            rol              = "auditor especializado en rúbricas universitarias",
            criterios        = items_texto,
            feedback_auditor = "",
        )

        logger.info(
            f"[Auditor] Ciclo {n_iter} | {seccion} | {fuente_texto} | "
            f"Rúbrica: {rubrica_desc} | Universidad: {universidad}"
        )

        # ── Contexto de iteración para que el Auditor reconozca el texto mejorado ──
        if n_iter > 0:
            errores_previos = state.get("errores_rubrica", [])
            texto_errores = ""
            for e in errores_previos:
                texto_errores += f"- Ítem {e.get('item_numero', '?')}: {e.get('descripcion', '')}\n"
                
            contexto_iteracion = f"""
---
## CONTEXTO DE ITERACIÓN (¡IMPORTANTE!)

Estás evaluando una VERSIÓN MEJORADA del texto (Iteración {n_iter}).
En la iteración anterior, se encontraron los siguientes errores:
{texto_errores}

Tu tarea principal ahora es VERIFICAR SI ESTOS ERRORES FUERON CORREGIDOS en el nuevo texto.
- Si el texto nuevo incorpora los elementos solicitados (ej. citas, aclaraciones, referencias, formato), ELEVA EL PUNTAJE de esos ítems a 2 o 3.
- Reconoce el esfuerzo de mejora. No busques excusas para mantener el puntaje en 1 si el estudiante corrigió lo indicado.
- NO crees nuevos errores para ítems que ya habían sido aprobados.
---
"""
        else:
            contexto_iteracion = ""

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
            "contexto_iteracion":    contexto_iteracion,
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
                max_retries=3,
                timeout=600.0,
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

        # ── Fallback errores: si score es bajo pero no hay consenso de errores ──
        # Ocurre cuando el LLM no lista todos los ítems (pese al prompt) y los
        # subagentes flaggean ítems distintos sin alcanzar la mayoría.
        # También cubre el caso en que el LLM lista solo ítems con puntaje ≥ 2
        # (ej. 3 ítems × 2 pts = 6/21) omitiendo los ítems con puntuación baja.
        score_pct = consolidado["score_final"] / puntaje_max if puntaje_max > 0 else 1.0
        if not consolidado["errores_consensuados"] and score_pct < 0.50 and mejor and mejor.output:
            # Paso 1: errores del auditor principal (puntaje < 2)
            errores_directos = _extraer_items_error(mejor.output)
            if errores_directos:
                consolidado["errores_consensuados"] = errores_directos
                logger.info(
                    f"[Auditor] Fallback score bajo ({score_pct:.0%}): "
                    f"{len(errores_directos)} errores del auditor principal (sin consenso)"
                )
            else:
                # Paso 2: buscar en TODOS los auditores items con puntaje ≤ 1
                items_bajos = []
                for r in resultados:
                    if r.exitoso and r.output:
                        for item in r.output.items_evaluados:
                            if item.puntaje <= 1:
                                items_bajos.append({
                                    "item_numero":    item.item_numero,
                                    "puntaje_actual": item.puntaje,
                                    "descripcion":    item.observacion,
                                })
                if items_bajos:
                    # Tomar el item con menor puntaje encontrado en cualquier auditor
                    consolidado["errores_consensuados"] = [
                        min(items_bajos, key=lambda x: x["puntaje_actual"])
                    ]
                    logger.info(
                        f"[Auditor] Fallback individual ({score_pct:.0%}): "
                        "1 error encontrado en auditor individual"
                    )
                else:
                    # Paso 3: error sintético — el LLM omitió ítems bajos pese al prompt.
                    # Inyectar el feedback general como error para que el Redactor
                    # tenga guidance en la siguiente iteración.
                    if n_iter == 0 and score_pct < 0.15:
                        feedback_text = mejor.output.feedback_general or "El texto requiere mejoras generales según la rúbrica."
                        consolidado["errores_consensuados"] = [{
                            "item_numero":    1,
                            "puntaje_actual": 0,
                            "descripcion":    feedback_text[:600],
                        }]
                        logger.info(
                            f"[Auditor] Fallback sintético ({score_pct:.0%}): "
                            "el LLM omitió ítems bajos — error generado desde feedback general"
                        )
                    else:
                        logger.info(
                            f"[Auditor] Omitiendo fallback sintético en ciclo {n_iter} | score: {score_pct:.0%}"
                        )

        loras_usadas = [lora.id for lora in loras]

        # ── Consolidar todos los ítems evaluados (incluyendo aciertos y errores) ──
        todos_items_subagentes = []
        for r in resultados:
            if r.exitoso and r.output and hasattr(r.output, "items_evaluados"):
                for it in r.output.items_evaluados:
                    todos_items_subagentes.append({
                        "item_numero": it.item_numero,
                        "puntaje": it.puntaje,
                        "observacion": it.observacion,
                    })

        # Agrupar por item_numero
        conteo_items = {}
        for it in todos_items_subagentes:
            num = it["item_numero"]
            conteo_items.setdefault(num, []).append(it)

        items_consolidados = []
        for num in sorted(conteo_items.keys()):
            grupo = conteo_items[num]
            puntajes = [g["puntaje"] for g in grupo]
            puntaje_promedio = round(sum(puntajes) / len(puntajes)) if puntajes else 0
            
            # Buscar observación para este ítem
            obs_elegida = grupo[0]["observacion"]
            for g in grupo:
                if g["puntaje"] == puntaje_promedio:
                    obs_elegida = g["observacion"]
                    break
            
            items_consolidados.append({
                "item_numero": num,
                "puntaje": puntaje_promedio,
                "observacion": obs_elegida,
            })

        # Puntaje total programático recalculado desde los ítems consolidados para consistencia matemática
        puntaje_total_consolidado = sum(it["puntaje"] for it in items_consolidados) if items_consolidados else consolidado["score_final"]

        # ── Puntaje inicial para métricas de Hake ────────────────────────────
        # Ciclo 0: guardamos el score recién computado como baseline pre-test.
        # Ciclos >0: preservamos el baseline original (nunca lo sobreescribimos),
        # para que Gain Score use siempre (ciclo_0_score, ciclo_N_score).
        if n_iter == 0:
            puntaje_inicial_calc = float(puntaje_total_consolidado)
        else:
            puntaje_inicial_calc = float(state.get("puntaje_inicial") or puntaje_total_consolidado)

        ret_dict = {
            "feedback_auditor":            feedback,
            "errores_rubrica":             consolidado["errores_consensuados"],
            "puntaje_estimado":            puntaje_total_consolidado,
            "puntaje_inicial":             puntaje_inicial_calc,
            "iter_auditada":               n_iter + 1,
            "_puntaje_max":                puntaje_max,
            "scores_subagentes":           consolidado["scores_subagentes"],
            "consenso_matematico_auditor": consolidado["consenso_matematico"],
            "loras_activas":               loras_usadas,
            "auditor_ejecutado":           True,
            "evaluacion_upao_final":       items_consolidados,
        }

        if n_iter == 0:
            ret_dict["evaluacion_upao_inicial"] = items_consolidados
        else:
            ret_dict["evaluacion_upao_inicial"] = state.get("evaluacion_upao_inicial") or items_consolidados

        return ret_dict


    return nodo_auditor


