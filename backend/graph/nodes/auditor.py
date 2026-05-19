"""
Nodo Auditor — Panel de 3 subagentes que evalúan independientemente.

CAMBIO 4: usa ContextLoader para cargar rúbrica según universidad/programa.
CAMBIO 6: panel de 3 subagentes con temperatura variable → consenso matemático.

Fallback: si ContextLoader falla, usa la rúbrica UPAO de backend/config.py.
"""

import json
import logging
import os
import time
from typing import List

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from ..state import MentoriaState
from ._utils import cargar_prompt, invocar_con_backoff, calcular_consenso_matematico
from backend.config import get_items_texto_para_seccion, get_puntaje_maximo_seccion
from backend.rag.rubric_parser import rubrica_a_texto_prompt

logger = logging.getLogger(__name__)


# ── Modelos Pydantic para salida estructurada ─────────────────────────────────

class ItemEvaluado(BaseModel):
    item_numero: int = Field(ge=1, le=999, description="Número del ítem de la rúbrica")
    puntaje:     int = Field(ge=0, le=3,   description="0=Insuficiente 1=Regular 2=Bueno 3=Excelente")
    observacion: str = Field(description="Observación específica para este ítem")


class AuditorOutput(BaseModel):
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


# ── Sub-configuraciones del panel ─────────────────────────────────────────────

_SUBAGENT_CONFIGS = [
    {"id": "auditor_estricto",    "temperatura": 0.05, "enfasis": "errores formales y de estructura"},
    {"id": "auditor_equilibrado", "temperatura": 0.15, "enfasis": "balance entre rigor y contexto"},
    {"id": "auditor_contextual",  "temperatura": 0.25, "enfasis": "coherencia con objetivos del trabajo"},
]


def _make_sub_llm(index: int, model_name: str) -> ChatGroq:
    """Crea un ChatGroq para un subagente usando rotación de API keys."""
    cfg = _SUBAGENT_CONFIGS[index]
    try:
        from config import Config
        api_key = Config.get_next_groq_key(index)
    except Exception:
        api_key = (
            os.getenv("GROQ_KEY_AUDITOR")
            or os.getenv("GROQ_API_KEY", "")
        )
    return ChatGroq(
        api_key=api_key,
        model=model_name,
        temperature=cfg["temperatura"],
        max_retries=2,
    )


# ── Fábrica del nodo ──────────────────────────────────────────────────────────

def make_nodo_auditor(llm: ChatGroq):
    """
    Fábrica del Nodo Auditor.

    Crea un panel de 3 subagentes con temperaturas distintas.
    El score final es el consenso matemático entre los 3.
    """
    plantilla_sistema = cargar_prompt("auditor_prompt.md")
    model_name = getattr(llm, "model_name", "llama-3.3-70b-versatile")

    # Pre-crear los 3 sub-LLMs con structured output
    sub_chains = []
    for i, cfg in enumerate(_SUBAGENT_CONFIGS):
        sub_llm = _make_sub_llm(i, model_name)
        sub_llm_struct = sub_llm.with_structured_output(AuditorOutput)
        prompt = ChatPromptTemplate.from_messages([
            ("system", plantilla_sistema + f"\n\nTu enfoque específico: {cfg['enfasis']}"),
            ("human", "Evalúa el texto y devuelve tu evaluación estructurada según la rúbrica."),
        ])
        sub_chains.append(prompt | sub_llm_struct)

    # También mantener chain principal (fallback o uso directo)
    llm_estructurado = llm.with_structured_output(AuditorOutput)
    prompt_principal = ChatPromptTemplate.from_messages([
        ("system", plantilla_sistema),
        ("human", "Evalúa el texto y devuelve tu evaluación estructurada según la rúbrica."),
    ])
    chain_principal = prompt_principal | llm_estructurado

    def _construir_inputs_rubrica(state: MentoriaState, seccion: str) -> tuple[str, int, str]:
        """Retorna (items_texto, puntaje_max, rubrica_desc)."""
        # Intentar ContextLoader primero
        universidad = state.get("universidad", "upao")
        programa = state.get("programa", "ingeniería de sistemas")
        try:
            from context.context_loader import ContextLoader
            loader = ContextLoader()
            contexto = loader.get(universidad=universidad, programa=programa)
            criterios = contexto.get("criterios", [])
            items_lineas = ["| N° | Criterio | Peso | Puntaje (0-3) |",
                            "|----|----------|------|--------------|"]
            for i, c in enumerate(criterios, 1):
                items_lineas.append(
                    f"| {i:02d} | {c['nombre']}: {c['descripcion']} | {c.get('peso', '')} | ___ |"
                )
            items_texto = "\n".join(items_lineas)
            puntaje_max = int(contexto.get("escala_maxima", 3) * len(criterios))
            rubrica_desc = f"rúbrica dinámica — {contexto['universidad']}"
            return items_texto, puntaje_max, rubrica_desc
        except Exception:
            pass

        # Fallback: rúbrica dinámica del estudiante
        rubrica = state.get("rubrica_dinamica")
        if rubrica:
            return (
                rubrica_a_texto_prompt(rubrica),
                rubrica.get("puntaje_maximo", len(rubrica.get("items", [])) * 3),
                "rúbrica subida por el estudiante",
            )

        # Fallback final: UPAO hardcoded
        return (
            get_items_texto_para_seccion(seccion),
            get_puntaje_maximo_seccion(seccion),
            "rúbrica oficial UPAO",
        )

    def nodo_auditor(state: MentoriaState) -> dict:
        logger.info("[Auditor] Pausa 3 s anti-rate-limit...")
        time.sleep(3)

        seccion = state["seccion_objetivo"]
        n_iter  = state.get("numero_iteracion", 0)
        texto_a_evaluar = state.get("texto_iterado") or state.get("contexto_recuperado", "")
        fuente_texto    = "mejorado" if state.get("texto_iterado") else "original del PDF"

        # Capturar puntaje_inicial real entre iteraciones para que el Gain Score
        # mida la mejora desde la evaluación anterior, no siempre desde cero.
        puntaje_previo = state.get("puntaje_estimado")
        if puntaje_previo is not None and float(puntaje_previo) > 0.0 and n_iter > 0:
            puntaje_inicial_calculado = float(puntaje_previo)
        else:
            puntaje_inicial_calculado = float(state.get("puntaje_inicial") or 0.0)

        items_texto, puntaje_max, rubrica_desc = _construir_inputs_rubrica(state, seccion)

        logger.info(
            f"[Auditor] Ciclo {n_iter} | Sección: {seccion} | "
            f"Texto: {fuente_texto} | Rúbrica: {rubrica_desc}"
        )

        inputs_base = {
            "seccion":               seccion,
            "texto_iterado":         texto_a_evaluar,
            "items_rubrica":         items_texto,
            "puntaje_max":           puntaje_max,
            "rubrica_descripcion":   rubrica_desc,
            "contexto_dependencias": state.get("contexto_dependencias") or "Sin contexto de secciones relacionadas.",
            "contexto_teorico":      state.get("contexto_teorico") or "",
        }

        # ── Panel de 3 subagentes ─────────────────────────────────────────────
        resultados_subagentes: list[AuditorOutput] = []
        for i, chain in enumerate(sub_chains):
            cfg = _SUBAGENT_CONFIGS[i]
            try:
                resultado: AuditorOutput = invocar_con_backoff(chain, inputs_base)
                resultados_subagentes.append(resultado)
                logger.info(
                    f"[Auditor/{cfg['id']}] puntaje={resultado.puntaje_total} "
                    f"aprobado={resultado.aprobado}"
                )
            except Exception as exc:
                logger.warning(f"[Auditor/{cfg['id']}] Falló: {exc}")

        if not resultados_subagentes:
            # Todos los subagentes fallaron → usar chain principal
            logger.warning("[Auditor] Panel falló, usando chain principal como fallback")
            resultado_fallback: AuditorOutput = invocar_con_backoff(chain_principal, inputs_base)
            resultados_subagentes.append(resultado_fallback)

        # ── Consenso matemático entre subagentes ──────────────────────────────
        scores = [r.puntaje_total for r in resultados_subagentes]
        consenso = calcular_consenso_matematico(scores, umbral_std=0.4 * puntaje_max / 3)
        puntaje_consenso = int(round(consenso["score_consenso"]))

        # Consolidar errores: los que aparecen en ≥ 2 de 3 subagentes
        todos_items_errores = [
            item
            for r in resultados_subagentes
            for item in r.items_evaluados
            if item.puntaje < 2
        ]
        conteo_items: dict[int, list] = {}
        for item in todos_items_errores:
            conteo_items.setdefault(item.item_numero, []).append(item)

        errores_consensuados = [
            {
                "item_numero":    num,
                "puntaje_actual": round(sum(i.puntaje for i in items) / len(items)),
                "descripcion":    items[0].observacion,
            }
            for num, items in conteo_items.items()
            if len(items) >= max(2, len(resultados_subagentes) - 1)
        ]

        # Feedback: del subagente con puntaje más cercano al consenso
        mejor_resultado = min(
            resultados_subagentes,
            key=lambda r: abs(r.puntaje_total - consenso["score_consenso"]),
        )

        logger.info(
            f"[Auditor] Consenso={puntaje_consenso}/{puntaje_max} | "
            f"Errores={len(errores_consensuados)} | {consenso['motivo']}"
        )

        return {
            "feedback_auditor":            mejor_resultado.feedback_general,
            "errores_rubrica":             errores_consensuados,
            "puntaje_estimado":            puntaje_consenso,
            "puntaje_inicial":             puntaje_inicial_calculado,
            "iter_auditada":               n_iter + 1,
            "_puntaje_max":                puntaje_max,
            "scores_subagentes":           scores,
            "consenso_matematico_auditor": consenso,
        }

    return nodo_auditor
