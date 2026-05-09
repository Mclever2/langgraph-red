"""Estado global del grafo multiagente de mentoría académica UPAO."""

from typing import List, Optional
from typing_extensions import TypedDict


class ErrorRubrica(TypedDict):
    item_numero:    int
    puntaje_actual: int
    descripcion:    str


class RondaDebate(TypedDict):
    ronda:                  int
    argumento_redactor:     str
    veredicto_evaluadores:  str
    items_aceptados:        List[int]
    items_mantenidos:       List[int]


class MentoriaState(TypedDict):
    # ── Input desde Streamlit ─────────────────────────────────────────────────
    seccion_objetivo:       str
    contexto_recuperado:    str   # RAG tesis — sección objetivo
    contexto_dependencias:  str   # RAG tesis — secciones relacionadas (cruzado)
    contexto_teorico:       str   # RAG biblioteca de libros

    # ── Configuración del ciclo (inyectada por Streamlit) ─────────────────────
    max_iteraciones:        int   # Límite de ciclos principales (default 3)
    max_rondas_debate:      int   # Límite de rondas de debate por ciclo (default 2)

    # ── Supervisor ────────────────────────────────────────────────────────────
    plan_supervisor:        str   # Análisis del Supervisor al inicio del ciclo

    # ── Redactor ──────────────────────────────────────────────────────────────
    texto_iterado:          str
    numero_iteracion:       int

    # ── Auditor (evaluación rúbrica) ──────────────────────────────────────────
    feedback_auditor:       str
    errores_rubrica:        List[ErrorRubrica]
    puntaje_estimado:       Optional[int]

    # ── Metodólogo (rigor científico + coherencia cruzada) ────────────────────
    observaciones_metodologicas: str

    # ── Debate ────────────────────────────────────────────────────────────────
    ronda_debate:           int
    historial_debate:       List[RondaDebate]
    argumento_redactor:     str
    veredicto_debate:       str

    # ── HITL ──────────────────────────────────────────────────────────────────
    aprobacion_humana:      Optional[str]

    # ── Red multiagente — routing dinámico del Supervisor ────────────────────
    siguiente_nodo:           str   # decisión del Supervisor → siguiente agente
    instrucciones_supervisor: str   # nota del Supervisor para el siguiente agente
    pasos_ejecutados:         int   # contador total de pasos (anti-bucle)
    max_pasos_red:            int   # techo de pasos (inyectado por Streamlit)

    # Rastreo por iteración (el Supervisor los lee para decidir quién ya corrió)
    iter_auditada:            int   # numero_iteracion cuando el Auditor ejecutó por última vez
    iter_metodologica:        int   # numero_iteracion cuando el Metodólogo ejecutó por última vez
