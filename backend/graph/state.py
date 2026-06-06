"""Estado global del grafo multiagente de mentoría académica."""

from typing import List, Optional, Any, Dict
from typing_extensions import TypedDict


class ErrorRubrica(TypedDict):
    item_numero:    int
    puntaje_actual: int
    descripcion:    str


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

    # ── Debate — panel de 4 subagentes con memoria compartida ────────────────
    debate_memory:          list          # historial del panel: [{"subagente": str, "contenido": str}, ...]
    debate_veredicto:       Optional[Dict]  # output estructurado del sintetizador
    debate_completado:      bool          # True tras ejecutar el nodo debate en la iteración actual
    historial_debate:       list          # registro acumulado de sesiones de debate (compatible exportador)

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

    # ── Identidad institucional ───────────────────────────────────────────────
    universidad:              str   # "upao" por defecto; cualquier universidad
    programa:                 str   # "ingeniería de sistemas"
    modalidad:                str   # "tesis"

    # ── Trazabilidad de ejecución ─────────────────────────────────────────────
    run_id:                   str   # UUID generado al inicio del flujo
    puntaje_inicial:          Optional[float]  # score antes de la primera iteración

    # ── Consenso matemático global ────────────────────────────────────────────
    consenso_matematico:      Optional[Dict]

    # ── Panel de subagentes auditor ───────────────────────────────────────────
    scores_subagentes:        Optional[List]   # scores de cada subagente
    consenso_matematico_auditor: Optional[Dict]

    # ── Trazabilidad LoRA + MCP (subagentes por nodo) ─────────────────────────
    loras_activas:            Optional[List]   # IDs de LoRAs del último nodo ejecutado

    # ── Exportador — rutas de archivos generados ──────────────────────────────
    rutas_reportes:           Optional[List]   # paths a run_*.json, debate_*.md, eval_*.json

    # ── Flags de ejecución por iteración ─────────────────────────────────────
    consenso_ejecutado:       Optional[bool]
    disenso_ejecutado:        Optional[bool]
    auditor_ejecutado:        Optional[bool]
    metodologo_ejecutado:     Optional[bool]
    debate_ejecutado:         Optional[bool]

    # ── Nuevos campos para métricas y subagentes de redactor ─────────────────
    redactor_evaluacion_rubrica: Optional[Dict]
    redactor_sugerencias_mejoras: Optional[str]
    historial_textos:            Optional[List[str]]

