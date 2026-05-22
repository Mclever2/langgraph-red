"""
Nodo Redactor — Pipeline de 2 subagentes secuencial con LoRA.

¿POR QUÉ 2 SUBAGENTES Y NO MÁS?
  El redactor opera en un pipeline de refinamiento, no en paralelo:
    Sub1 (corrector): aplica las correcciones específicas identificadas
    Sub2 (integrador): recibe el borrador de Sub1 y verifica coherencia global

  El 2do subagente ES EL ÁRBITRO — toma la versión del 1ro y la refina.
  Un 3er subagente añadiría costo sin beneficio: ¿qué haría que el 2do no haga?
  2 es el número correcto para este agente.

  El resultado final siempre es el texto de Sub2, que ya integró el trabajo de Sub1.

SUBAGENTES:
  1. redactor_corrector (temp 0.30)
     LoRA: editor de corrección dirigida
     MCP:  Tesis (contexto del documento para correcciones)
     → Aplica cada error del Auditor/Metodólogo con precisión quirúrgica

  2. redactor_integrador (temp 0.40)
     LoRA: editor de integración y coherencia
     MCP:  Tesis
     → Lee el borrador de Sub1 (en historial_panel) y verifica coherencia global
     → Produce la versión final limpia

NOTA:
  No hay consenso matemático en este nodo — la escritura no se mide con std_dev.
  El 2do subagente toma la decisión final al ver y refinar lo del 1ro.
"""

import logging
import os

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff
from ._rag_planner import obtener_contexto_dinamico
from ._panel_utils import ejecutar_panel, consolidar_panel_escritor, ResultadoSubagente

logger = logging.getLogger(__name__)


def make_nodo_redactor(llm: ChatGroq):
    """
    Construye el Nodo Redactor con pipeline de 2 subagentes (LoRA).
    """
    prompt_base = cargar_prompt("redactor_prompt.md")
    model_name  = getattr(llm, "model_name", "llama-3.3-70b-versatile")
    api_key_base = os.getenv("GROQ_KEY_REDACTOR") or os.getenv("GROQ_API_KEY", "")

    def nodo_redactor(state: MentoriaState) -> dict:
        iteracion_actual = state.get("numero_iteracion", 0) + 1
        universidad      = state.get("universidad", "upao")
        programa         = state.get("programa", "ingeniería de sistemas")
        seccion          = state["seccion_objetivo"]
        texto_base       = state.get("texto_iterado") or state["contexto_recuperado"]

        logger.info(
            f"[Redactor] Iteración #{iteracion_actual} | {seccion} | "
            f"Pipeline: corrector → integrador"
        )

        # ── Enriquecer contexto: el redactor decide qué secciones necesita ───
        # El corrector necesita ver otras secciones para escribir con coherencia
        # global (ej: si corrige Objetivos, debe ver Problema e Hipótesis).
        logger.info("[Redactor] Planificando contexto adicional con RAG dinámico…")
        contexto_dinamico = obtener_contexto_dinamico(
            llm          = llm,
            seccion      = seccion,
            texto_snippet= texto_base[:500],
            rol          = "redactor académico que mejora secciones de tesis universitaria",
        )

        # ── Inputs base ───────────────────────────────────────────────────────
        # Sintetizar el veredicto final del debate (para el prompt del redactor)
        historial_debate_lista = state.get("historial_debate") or []
        if historial_debate_lista:
            ultima = historial_debate_lista[-1]
            confirmados = ultima.get("items_confirmados", [])
            descartados = ultima.get("items_descartados", [])
            posicion    = ultima.get("respuesta_metodologico", "")[:600]
            veredicto_debate = (
                f"Tras {len(historial_debate_lista)} ronda(s) de debate:\n"
                f"- Ítems confirmados como errores reales: {confirmados}\n"
                f"- Ítems descartados (no son errores reales): {descartados}\n"
                f"Posición final del Metodólogo: {posicion}"
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
            # Placeholders MCP
            "contexto_secciones_relacionadas": "",
        }

        # ── Cargar LoRAs ──────────────────────────────────────────────────────
        from backend.lora.lora_configs import get_loras_para_agente, TIPO_REDACTOR
        from backend.mcp.tools import crear_fetch_para_lora

        loras = get_loras_para_agente(TIPO_REDACTOR, universidad, programa)

        # ── Construir sub_items ───────────────────────────────────────────────
        sub_items = []
        api_keys = _obtener_api_keys_redactor(api_key_base)

        for idx, lora in enumerate(loras):
            sub_llm = ChatGroq(
                api_key=api_keys[idx % len(api_keys)],
                model=model_name,
                temperature=lora.temperatura,
                max_retries=2,
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
                    "Responde ÚNICAMENTE con el texto mejorado, sin introducciones ni comentarios."
                )),
            ])
            chain = prompt | sub_llm

            mcp_fn = crear_fetch_para_lora(lora.fuentes_datos, lora.drive_folder_id)
            sub_items.append((chain, lora.id, mcp_fn))

        # ── Ejecutar pipeline secuencial ──────────────────────────────────────
        # Sub1 corrige → Sub2 ve el borrador en historial_panel y lo integra
        resultados = ejecutar_panel(
            sub_items,
            inputs_base,
            logger_prefix="Redactor",
            pausa_entre_subs=3.0,  # el redactor genera más tokens → más pausa
        )

        # ── Fallback ──────────────────────────────────────────────────────────
        if not any(r.exitoso for r in resultados):
            logger.warning("[Redactor] Pipeline falló — usando LLM base como fallback")
            prompt_fb = ChatPromptTemplate.from_messages([
                ("system", prompt_base),
                ("human", (
                    "Genera la versión mejorada del texto para la sección **{seccion}** "
                    "(iteración #{iteracion}).\n"
                    "Responde ÚNICAMENTE con el texto mejorado."
                )),
            ])
            chain_fb = prompt_fb | llm
            output_fb = invocar_con_backoff(chain_fb, inputs_base)
            resultados = [ResultadoSubagente(lora_id="fallback", output=output_fb)]

        # ── El texto final es siempre el del último subagente (integrador) ────
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


def _obtener_api_keys_redactor(api_key_base: str) -> list[str]:
    try:
        from config import Config
        keys = [Config.get_next_groq_key(i) for i in range(2)]
        return [k for k in keys if k] or [api_key_base]
    except Exception:
        return [api_key_base, api_key_base]
