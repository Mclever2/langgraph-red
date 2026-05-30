"""
Nodo Redactor — Dos modos según el puntaje de la sección.

MODO SUGERENCIAS (puntaje >= 80 % del máximo):
  Un único subagente especializado produce recomendaciones numeradas.
  El texto original del estudiante NO se reescribe — se devuelven
  sugerencias puntuales que el estudiante puede aplicar por su cuenta.
  El texto_iterado contendrá las recomendaciones, no una nueva versión.

MODO REESCRITURA (puntaje < 80 % del máximo):
  Pipeline de 2 subagentes secuencial con LoRA (comportamiento original):
    Sub1 (corrector):   aplica los errores confirmados con precisión quirúrgica
    Sub2 (integrador):  recibe el borrador de Sub1, verifica coherencia global
  El texto_iterado contendrá el texto mejorado completo.

El umbral del 80 % es universal: funciona para cualquier sección y
cualquier universidad porque usa el porcentaje del puntaje de sección,
no un número absoluto (que varía según cuántos ítems evalúa la sección).
"""

import logging
import os

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff
from ._rag_planner import obtener_contexto_dinamico
from ._panel_utils import ejecutar_panel, consolidar_panel_escritor, ResultadoSubagente

logger = logging.getLogger(__name__)

_UMBRAL_SUGERENCIAS = 0.8667  # >= 86.67 % (13/15) → modo sugerencias

# ── Prompt del subagente de sugerencias ──────────────────────────────────────
_PROMPT_SUGERENCIAS = """\
Eres un asesor académico experto en tesis universitarias de pregrado.
La sección evaluada ya alcanzó una calidad BUENA o MUY BUENA (≥ 86.67 % de la rúbrica).

Tu tarea es identificar SOLO las mejoras puntuales que elevarían esta sección al máximo.
NO reescribas el texto — el estudiante conserva su propia redacción.

REGLAS OBLIGATORIAS:
- Cada recomendación debe ser específica: indica qué cambiar, dónde y cómo.
- Cita entre corchetes el número del ítem de rúbrica que mejora ([Ítem N]).
- Máximo 5 recomendaciones. Si hay menos errores confirmados, da menos.
- Si no quedan errores confirmados, declara que la sección está lista para entregar.

FORMATO DE SALIDA OBLIGATORIO:

ESTADO DE LA SECCIÓN: [Buena calidad | Muy buena calidad | Excelente — lista para entregar]

RECOMENDACIONES PUNTUALES:
1. [Ítem N] Descripción exacta: qué agregar, modificar o precisar, y en qué parte del texto.
2. [Ítem N] ...
(omite este bloque si no hay recomendaciones)

VEREDICTO: LISTA PARA ENTREGAR | REQUIERE AJUSTES MENORES\
"""


def make_nodo_redactor(llm: ChatOpenAI):
    """
    Construye el Nodo Redactor con modo dual según puntaje de sección.
    """
    prompt_base = cargar_prompt("redactor_prompt.md")
    model_name  = getattr(llm, "model_name", "gpt-4o-mini")

    def nodo_redactor(state: MentoriaState) -> dict:
        iteracion_actual = state.get("numero_iteracion", 0) + 1
        universidad      = state.get("universidad", "upao")
        programa         = state.get("programa", "ingeniería de sistemas")
        seccion          = state["seccion_objetivo"]
        texto_base       = state.get("texto_iterado") or state["contexto_recuperado"]

        # ── Calcular porcentaje del puntaje para decidir el modo ─────────────
        puntaje_estimado = float(state.get("puntaje_estimado") or 0.0)
        puntaje_max      = float(state.get("_puntaje_max") or 0.0)
        porcentaje       = (puntaje_estimado / puntaje_max) if puntaje_max > 0 else 0.0
        modo_sugerencias = porcentaje >= _UMBRAL_SUGERENCIAS

        logger.info(
            f"[Redactor] Iteración #{iteracion_actual} | {seccion} | "
            f"Puntaje: {puntaje_estimado}/{puntaje_max} ({porcentaje:.0%}) | "
            f"Modo: {'SUGERENCIAS' if modo_sugerencias else 'REESCRITURA'}"
        )

        # ════════════════════════════════════════════════════════════════════════
        # MODO SUGERENCIAS — puntaje >= 80 %
        # ════════════════════════════════════════════════════════════════════════
        if modo_sugerencias:
            prompt_sug = ChatPromptTemplate.from_messages([
                ("system", _PROMPT_SUGERENCIAS),
                ("human", (
                    "Sección evaluada: **{seccion}** (iteración #{iteracion})\n\n"
                    "**PUNTAJE:** {puntaje_estimado}/{puntaje_max} ({porcentaje})\n\n"
                    "**ERRORES CONFIRMADOS POR EL PANEL:**\n{errores_confirmados}\n\n"
                    "**FEEDBACK DEL AUDITOR:**\n{feedback_auditor}\n\n"
                    "**TEXTO ACTUAL DEL ESTUDIANTE:**\n{texto_actual}\n\n"
                    "Genera las recomendaciones puntuales."
                )),
            ])
            chain_sug = prompt_sug | llm

            try:
                output = invocar_con_backoff(chain_sug, {
                    "seccion":            seccion,
                    "iteracion":          iteracion_actual,
                    "puntaje_estimado":   int(puntaje_estimado),
                    "puntaje_max":        int(puntaje_max),
                    "porcentaje":         f"{porcentaje:.0%}",
                    "errores_confirmados": _formatear_errores(state.get("errores_rubrica") or []),
                    "feedback_auditor":   state.get("feedback_auditor") or "Sin feedback específico.",
                    "texto_actual":       texto_base,
                })
                texto_final = output.content.strip()
            except Exception as exc:
                logger.warning(f"[Redactor/Sugerencias] Falló: {exc} — usando fallback")
                texto_final = (
                    f"No se pudieron generar sugerencias automáticas.\n"
                    f"Revisa el feedback del auditor para mejorar la sección.\n"
                    f"Puntaje actual: {int(puntaje_estimado)}/{int(puntaje_max)}"
                )

            logger.info(f"[Redactor] Sugerencias generadas ({len(texto_final)} chars)")

            return {
                "texto_iterado":    texto_final,
                "numero_iteracion": iteracion_actual,
                "loras_activas":    ["redactor_sugerencias"],
            }

        # ════════════════════════════════════════════════════════════════════════
        # MODO REESCRITURA — puntaje < 80 %
        # ════════════════════════════════════════════════════════════════════════

        # ── Enriquecer contexto con RAG dinámico ─────────────────────────────
        logger.info("[Redactor] Planificando contexto adicional con RAG dinámico…")
        contexto_dinamico = obtener_contexto_dinamico(
            llm          = llm,
            seccion      = seccion,
            texto_snippet= texto_base[:500],
            rol          = "redactor académico que mejora secciones de tesis universitaria",
        )

        # ── Sintetizar veredicto del debate ───────────────────────────────────
        historial_debate_lista = state.get("historial_debate") or []
        if historial_debate_lista:
            ultima = historial_debate_lista[-1]
            confirmados = ultima.get("items_confirmados", [])
            descartados = ultima.get("items_descartados", [])
            veredicto_debate = (
                f"Tras {len(historial_debate_lista)} ronda(s) de debate:\n"
                f"- Ítems confirmados como errores reales: {confirmados}\n"
                f"- Ítems descartados (no son errores reales): {descartados}"
            )
        else:
            veredicto_debate = "No hubo debate previo en esta iteración."

        inputs_base = {
            "seccion":                  seccion,
            "iteracion":                iteracion_actual,
            "max_iteraciones":          state.get("max_iteraciones", 3),
            "contexto_recuperado":      state["contexto_recuperado"],
            "contexto_dependencias":    contexto_dinamico or state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":         state.get("contexto_teorico") or "",
            "texto_actual":             texto_base,
            "plan_supervisor":          state.get("plan_supervisor") or "Sin plan previo.",
            "feedback_auditor":         state.get("feedback_auditor") or "Primera iteración.",
            "observaciones_metodologicas": state.get("observaciones_metodologicas") or "",
            "veredicto_debate":         veredicto_debate,
            "errores_confirmados":      _formatear_errores(state.get("errores_rubrica") or []),
            "universidad":              universidad,
            "programa":                 programa,
            "contexto_secciones_relacionadas": "",
        }

        # ── Cargar LoRAs ──────────────────────────────────────────────────────
        from backend.lora.lora_configs import get_loras_para_agente, TIPO_REDACTOR
        from backend.mcp.tools import crear_fetch_para_lora

        loras = get_loras_para_agente(TIPO_REDACTOR, universidad, programa)

        # ── Construir sub_items ───────────────────────────────────────────────
        sub_items = []

        for idx, lora in enumerate(loras):
            sub_llm = ChatOpenAI(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model=model_name,
                temperature=lora.temperatura,
                max_retries=3,
                timeout=600.0,
            )

            system_prompt = lora.system_prompt_completo(prompt_base)

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", (
                    "Genera la versión mejorada del texto para la sección **{seccion}** "
                    "(iteración #{iteracion}).\n\n"
                    "**ERRORES CONFIRMADOS POR EL PANEL:**\n{errores_confirmados}\n\n"
                    "**LO QUE HIZO EL SUBAGENTE ANTERIOR DEL PANEL:**\n"
                    "{historial_panel}\n\n"
                    "{contexto_secciones_relacionadas}\n\n"
                    "INSTRUCCIONES DE ESCRITURA — OBLIGATORIAS:\n"
                    "- El contexto RAG y las referencias bibliográficas son SOLO orientación "
                    "para ti. NUNCA copies frases, dimensiones o criterios del contexto RAG "
                    "al texto generado.\n"
                    "- Mantén el mismo registro académico y longitud aproximada del texto original. "
                    "No extiendas el texto más de 1.5x su longitud original salvo necesidad real.\n"
                    "- Para OBJETIVOS GENERALES: redacta UNA sola oración con esta estructura:\n"
                    "  [verbo infinitivo] + [variable independiente] + \"en\" + [variable dependiente] "
                    "+ \"de\" + [unidad de análisis] + \"en\" + [horizonte temporal].\n"
                    "  No añadas sub-dimensiones, instrumentos ni metodología dentro del objetivo general.\n"
                    "- Para OBJETIVOS ESPECÍFICOS: cada uno debe ser una oración independiente "
                    "que se derive lógicamente del objetivo general.\n"
                    "- Si la estructura del texto original es correcta, mejora SOLO la precisión "
                    "de la redacción, no la estructura.\n\n"
                    "Responde ÚNICAMENTE con el texto mejorado, sin introducciones ni comentarios."
                )),
            ])
            chain = prompt | sub_llm

            mcp_fn = crear_fetch_para_lora(lora.fuentes_datos, lora.drive_folder_id)
            sub_items.append((chain, lora.id, mcp_fn))

        # ── Ejecutar pipeline secuencial ──────────────────────────────────────
        resultados = ejecutar_panel(
            sub_items,
            inputs_base,
            logger_prefix="Redactor",
            pausa_entre_subs=0.5,
        )

        # ── Fallback ──────────────────────────────────────────────────────────
        if not any(r.exitoso for r in resultados):
            logger.warning("[Redactor] Pipeline falló — usando LLM base como fallback")
            prompt_fb = ChatPromptTemplate.from_messages([
                ("system", prompt_base),
                ("human", (
                    "Genera la versión mejorada del texto para la sección **{seccion}** "
                    "(iteración #{iteracion}).\n\n"
                    "INSTRUCCIONES DE ESCRITURA — OBLIGATORIAS:\n"
                    "- El contexto RAG y las referencias bibliográficas son SOLO orientación "
                    "para ti. NUNCA copies frases, dimensiones o criterios del contexto RAG "
                    "al texto generado.\n"
                    "- Mantén el mismo registro académico y longitud aproximada del texto original. "
                    "No extiendas el texto más de 1.5x su longitud original salvo necesidad real.\n"
                    "- Para OBJETIVOS GENERALES: redacta UNA sola oración con esta estructura:\n"
                    "  [verbo infinitivo] + [variable independiente] + \"en\" + [variable dependiente] "
                    "+ \"de\" + [unidad de análisis] + \"en\" + [horizonte temporal].\n"
                    "  No añadas sub-dimensiones, instrumentos ni metodología dentro del objetivo general.\n"
                    "- Para OBJETIVOS ESPECÍFICOS: cada uno debe ser una oración independiente "
                    "que se derive lógicamente del objetivo general.\n"
                    "- Si la estructura del texto original es correcta, mejora SOLO la precisión "
                    "de la redacción, no la estructura.\n\n"
                    "Responde ÚNICAMENTE con el texto mejorado, sin introducciones ni comentarios."
                )),
            ])
            chain_fb = prompt_fb | llm
            output_fb = invocar_con_backoff(chain_fb, inputs_base)
            resultados = [ResultadoSubagente(lora_id="fallback", output=output_fb)]

        texto_final = consolidar_panel_escritor(resultados)

        loras_usadas = [lora.id for lora in loras]
        logger.info(
            f"[Redactor] Texto generado ({len(texto_final)} chars) | LoRAs: {loras_usadas}"
        )

        return {
            "texto_iterado":    texto_final,
            "numero_iteracion": iteracion_actual,
            "loras_activas":    loras_usadas,
        }

    return nodo_redactor


def _formatear_errores(errores: list) -> str:
    """Formatea la lista de errores confirmados para el prompt del redactor."""
    if not errores:
        return "No hay errores específicos confirmados — revisa el feedback general del Auditor."
    lineas = []
    for e in errores:
        if isinstance(e, dict):
            lineas.append(
                f"- Ítem {e.get('item_numero', '?')}: {e.get('descripcion', '')} "
                f"(puntaje actual: {e.get('puntaje_actual', '?')}/3)"
            )
    return "\n".join(lineas) if lineas else "Sin errores específicos."
