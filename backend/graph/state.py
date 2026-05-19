"""Estado global del grafo multiagente de mentoría académica."""

from typing import List, Optional, Any, Dict
from typing_extensions import TypedDict


class ErrorRubrica(TypedDict):
    item_numero:    int
    puntaje_actual: int
    descripcion:    str


class RondaDebate(TypedDict):
    ronda:                  int
    argumento_auditor:      str   # Auditor defiende sus hallazgos de rúbrica
    respuesta_metodologico: str   # Metodólogo evalúa y refuta/confirma
    items_confirmados:      List[int]  # errores que ambos confirman como reales
    items_descartados:      List[int]  # errores que el Metodólogo desestima


class MentoriaState(TypedDict):
    # ── Input desde Streamlit ─────────────────────────────────────────────────
    seccion_objetivo:       str
    contexto_recuperado:    str   # RAG tesis — sección objetivo
    contexto_dependencias:  str   # RAG tesis — secciones relacionadas
    contexto_teorico:       str   # RAG biblioteca de libros

    # ── Rúbrica dinámica (subida por el estudiante) ───────────────────────────
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

    # ── Debate inter-agente (Auditor y Metodólogo como nodos separados) ──────────
    ronda_debate:              int
    historial_debate:          List[RondaDebate]
    # Canal de comunicación entre nodos de debate — el Auditor escribe aquí,
    # el Metodólogo lee desde el estado (no se pasa como parámetro de función).
    argumento_debate_auditor:  str
    debate_auditor_ronda:      int   # ronda en que el Auditor argumentó por última vez
    debate_metodologo_ronda:   int   # ronda en que el Metodólogo respondió por última vez

    # ── Red multiagente — routing dinámico del Supervisor ────────────────────
    siguiente_nodo:           str
    instrucciones_supervisor: str
    pasos_ejecutados:         int
    max_pasos_red:            int

    # Rastreo por iteración
    iter_auditada:            int   # última iteración en que corrió el Auditor
    iter_metodologica:        int   # última iteración en que corrió el Metodólogo

    # ── Metadata ─────────────────────────────────────────────────────────────
    _puntaje_max:             Optional[int]

    # ── Identidad institucional (CAMBIO 4 — ContextLoader) ───────────────────
    universidad:              str   # "upao" por defecto; cualquier universidad
    programa:                 str   # "ingeniería de sistemas"
    modalidad:                str   # "tesis"

    # ── Trazabilidad de ejecución (CAMBIO 1 — exportador) ────────────────────
    run_id:                   str   # UUID generado al inicio del flujo
    puntaje_inicial:          Optional[float]  # score antes de la primera iteración

    # ── Consenso matemático global (CAMBIO 5 — nodo_consenso) ────────────────
    consenso_matematico:      Optional[Dict]

    # ── Panel de subagentes auditor (CAMBIO 6) ────────────────────────────────
    scores_subagentes:        Optional[List]   # scores de cada subagente
    consenso_matematico_auditor: Optional[Dict]
