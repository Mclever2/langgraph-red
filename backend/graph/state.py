"""Estado global del grafo multiagente de mentoría académica."""

from typing import List, Optional, Any
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
    contexto_dependencias:  str   # RAG tesis — secciones relacionadas
    contexto_teorico:       str   # RAG biblioteca de libros

    # ── Rúbrica dinámica (subida por el estudiante) ───────────────────────────
    # Si es None, el Auditor usa la rúbrica UPAO hardcodeada en config.py
    rubrica_dinamica:       Optional[Any]   # dict parseado por rubric_parser.py

    # ── Configuración del ciclo ───────────────────────────────────────────────
    max_iteraciones:        int
    max_rondas_debate:      int

    # ── Supervisor ────────────────────────────────────────────────────────────
    plan_supervisor:        str

    # ── Redactor ──────────────────────────────────────────────────────────────
    texto_iterado:          str
    numero_iteracion:       int

    # ── Auditor (evaluación rúbrica) ──────────────────────────────────────────
    feedback_auditor:       str
    errores_rubrica:        List[ErrorRubrica]
    puntaje_estimado:       Optional[int]

    # ── Metodólogo (rigor científico + coherencia cruzada) ────────────────────
    observaciones_metodologicas: str

    # ── Consenso / Disenso ────────────────────────────────────────────────────
    resultado_consenso:     str   # síntesis de acuerdos entre evaluadores
    resultado_disenso:      str   # conflictos entre evaluadores
    iter_consenso:          int   # iteración en que corrió el nodo consenso
    iter_disenso:           int   # iteración en que corrió el nodo disenso

    # ── Debate ────────────────────────────────────────────────────────────────
    ronda_debate:           int
    historial_debate:       List[RondaDebate]
    argumento_redactor:     str
    veredicto_debate:       str

    # ── HITL ──────────────────────────────────────────────────────────────────
    aprobacion_humana:      Optional[str]

    # ── Red multiagente — routing dinámico del Supervisor ────────────────────
    siguiente_nodo:           str
    instrucciones_supervisor: str
    pasos_ejecutados:         int
    max_pasos_red:            int

    # Rastreo por iteración
    iter_auditada:            int   # última iteración en que corrió el Auditor
    iter_metodologica:        int   # última iteración en que corrió el Metodólogo

    # ── Reportes generados al aprobar ────────────────────────────────────────
    rutas_reportes:           Optional[List[str]]  # [ruta_metricas.json, ruta_debate.md]
    _puntaje_max:             Optional[int]         # puntaje máximo de la rúbrica activa
