"""Pantalla 2 — Selección de sección y lanzamiento del grafo multiagente."""

import re
import logging
import traceback

import streamlit as st

logger = logging.getLogger(__name__)

from backend.config import (
    SECCIONES_TESIS, SECCION_ITEMS_MAP, DEPENDENCIAS_SECCIONES,
)
from config import Config
from backend.rag import (
    recuperar_contexto, recuperar_contexto_cruzado, recuperar_vista_general,
    recuperar_contexto_teorico, listar_libros,
)
from backend.rag.rag_context import set_vector_store

from ..resources import graph, biblioteca
from ..session_manager import get_config, get_snapshot, is_paused


OPCION_VISTA_GENERAL = "Vista general del proyecto (panorama completo)"


def _buscar_seccion_upao(nombre_pdf: str) -> str | None:
    """
    Intenta encontrar la sección UPAO cuyo prefijo numérico coincide con el del PDF.
    Ejemplo: '1.2. Objetivos de la investigación' → '1.2 Objetivos (General y Específicos)'
    """
    m = re.match(r'^(\d[\d\.]*)', nombre_pdf.strip())
    if not m:
        return None
    prefijo_pdf = m.group(1).rstrip('.')
    for s in SECCIONES_TESIS:
        m2 = re.match(r'^(\d[\d\.]*)', s["nombre"].strip())
        if m2 and m2.group(1).rstrip('.') == prefijo_pdf:
            return s["nombre"]
    return None


def render_pantalla_seleccion() -> None:
    st.title("Sistema de Mentoría Académica Multiagente")
    st.success(f"PDF cargado: **{st.session_state.pdf_nombre}**")

    # Mostrar rúbrica activa
    rubrica_activa = st.session_state.get("rubrica_dinamica")
    if rubrica_activa:
        st.info(
            f"Rúbrica activa: **{st.session_state.get('rubrica_nombre', 'Rúbrica personalizada')}** "
            f"({rubrica_activa['total_items']} ítems)"
        )
    else:
        st.caption("Rúbrica activa: UPAO oficial (33 ítems) — puedes subir tu propia rúbrica en el paso anterior.")

    st.subheader("Paso 2 — Configura y lanza la evaluación")

    # ── Determinar opciones del dropdown ─────────────────────────────────────
    # Si el PDF tiene TOC detectado, usamos sus secciones reales (ordenadas por página).
    # Esto le permite al usuario ver el documento completo y seleccionar cualquier sección.
    # Si no hay TOC, se usan las secciones fijas de la rúbrica UPAO como fallback.
    estructura_toc = st.session_state.get("estructura_toc") or {}
    if estructura_toc:
        secciones_ordenadas = sorted(estructura_toc.items(), key=lambda x: x[1])
        # "Vista general" como primera opción para evaluar coherencia global
        opciones_dropdown  = [OPCION_VISTA_GENERAL] + [nombre for nombre, _ in secciones_ordenadas]
        usando_pdf         = True
    else:
        opciones_dropdown = [s["nombre"] for s in SECCIONES_TESIS]
        usando_pdf        = False

    col_form, col_config = st.columns([2, 1])

    with col_form:
        seccion_elegida = st.selectbox(
            "Sección del proyecto de tesis:",
            options=opciones_dropdown,
            help=(
                "Secciones extraídas del índice de tu PDF. "
                "'Vista general' evalúa coherencia global del documento completo. "
                "Al seleccionar una sección padre (ej. '2. MARCO TEÓRICO'), "
                "se recuperarán automáticamente todas sus subsecciones."
            ) if usando_pdf else (
                "Secciones de la rúbrica UPAO. El sistema buscará en el PDF "
                "los fragmentos relevantes para esta sección y sus dependencias."
            ),
        )

        # Mostrar ítems de rúbrica según la sección seleccionada
        if rubrica_activa:
            secciones_rubrica = rubrica_activa.get("secciones", {})
            if secciones_rubrica:
                total = rubrica_activa["total_items"]
                st.caption(
                    f"Rúbrica personalizada: **{total} ítems** en "
                    f"{len(secciones_rubrica)} secciones · "
                    f"puntaje máx: {rubrica_activa['puntaje_maximo']} pts"
                )
        else:
            # Si usamos secciones del PDF, intentar mapear a sección UPAO para los ítems
            seccion_upao = seccion_elegida if not usando_pdf else _buscar_seccion_upao(seccion_elegida)
            items_de_seccion = SECCION_ITEMS_MAP.get(seccion_upao or "", [])
            if items_de_seccion:
                st.caption(
                    f"Ítems UPAO a evaluar: **{', '.join(str(i) for i in items_de_seccion)}** "
                    f"(máx. {len(items_de_seccion) * 3} pts)"
                )
            elif usando_pdf and seccion_upao is None:
                st.caption("Esta sección del PDF no tiene un mapeo directo a ítems UPAO — se evaluará con todos los criterios relevantes.")

        # Dependencias: solo para secciones UPAO (las del PDF usan contexto cruzado inteligente)
        if not usando_pdf:
            deps = DEPENDENCIAS_SECCIONES.get(seccion_elegida, [])
            if deps:
                st.caption(f"Secciones relacionadas consultadas: {', '.join(deps)}")
        elif seccion_elegida == OPCION_VISTA_GENERAL:
            st.caption("Recuperará un fragmento representativo de cada capítulo del documento para evaluar coherencia global.")
        else:
            st.caption("Contexto: subsecciones de la sección seleccionada + secciones estructuralmente clave del proyecto.")

    with col_config:
        with st.expander("Configuración avanzada", expanded=False):
            max_iter = st.slider(
                "Iteraciones de mejora automática:",
                min_value=1, max_value=3,
                value=2,
                help=(
                    "Ciclos automáticos Redactor → Auditor → Metodólogo. "
                    "1 = una pasada (rápido). 2-3 = el Redactor mejora el texto "
                    "varias veces basándose en el feedback acumulado (más tiempo, texto más refinado)."
                ),
            )

    st.divider()

    # Flujo por iteración: Supervisor×8 + Aud + Met + Con + Dis + Debate + Red
    # + 1 auditoría final post-reescritura + 2 supervisores extra (margen)
    max_pasos = Config.get_max_pasos(max_iter)

    tiempo_est_min = 7 * max_iter * 6 // 60
    tiempo_est_max = 7 * max_iter * 10 // 60
    st.info(
        f"{max_iter} iteración(es) · panel de debate (4 subagentes) · "
        f"Tiempo estimado: {max(1, tiempo_est_min)}–{max(2, tiempo_est_max)} min · "
        "Agentes: Supervisor, Auditor, Metodólogo, Consenso, Disenso, Debate, Redactor",
        icon="ℹ️",
    )

    btn_iniciar = st.button("Iniciar Evaluación Multiagente", type="primary", use_container_width=True)
    if not btn_iniciar:
        return

    vs = st.session_state.vector_store
    if vs is None:
        st.error("Vector store no disponible. Sube el PDF nuevamente.")
        st.stop()

    # ── RAG cruzado ───────────────────────────────────────────────────────────
    es_vista_general = usando_pdf and (seccion_elegida == OPCION_VISTA_GENERAL)

    with st.spinner(
        "Recuperando panorama del documento…" if es_vista_general
        else "Recuperando contexto principal y contexto cruzado de otras secciones…"
    ):
        if es_vista_general:
            # Vista general: un fragmento representativo de cada capítulo
            contexto_tesis = recuperar_vista_general(vs)
            contexto_dependencias = ""
            seccion_para_estado  = "Vista general del proyecto"
        else:
            # Recuperación normal: sección principal + subsecciones
            contexto_tesis = recuperar_contexto(vs, seccion_elegida)
            seccion_para_estado  = seccion_elegida
            # Contexto cruzado: fragmentos de otras secciones estructuralmente
            # relevantes (objetivos, hipótesis, variables, metodología…).
            # Se pre-fetcha aquí para que todos los agentes lo tengan disponible
            # y para mostrarlo en la pestaña "Contexto cruzado" de la UI.
            contexto_dependencias = recuperar_contexto_cruzado(vs, seccion_elegida)

        contexto_teoria = recuperar_contexto_teorico(biblioteca, seccion_elegida if not es_vista_general else "metodología investigación")

    if not contexto_tesis.strip():
        st.warning(
            "No se encontró contenido en el PDF para esta sección. "
            "Prueba con otra sección o verifica que el PDF tenga texto seleccionable."
        )
        st.stop()

    n_libros = len(listar_libros(biblioteca))
    col_i1, col_i2 = st.columns(2)
    col_i1.success(
        "Panorama del documento recuperado" if es_vista_general
        else "Contexto principal recuperado (sección + subsecciones)"
    )
    if es_vista_general:
        col_i2.info("Modo vista general: un fragmento representativo por capítulo")
    else:
        n_cruzado = len([p for p in contexto_dependencias.split("---") if p.strip()]) if contexto_dependencias else 0
        col_i2.info(f"Contexto cruzado recuperado: {n_cruzado} sección(es) relacionadas")

    # ── Estado inicial para el grafo ──────────────────────────────────────────
    estado_inicial = {
        "run_id":                      st.session_state.thread_id,
        "universidad":                 st.session_state.get("universidad", "upao"),
        "programa":                    st.session_state.get("programa", "ingeniería de sistemas"),
        "modalidad":                   st.session_state.get("modalidad", "tesis"),
        "puntaje_inicial":             0.0,
        "seccion_objetivo":            seccion_para_estado,
        "contexto_recuperado":         contexto_tesis,
        "contexto_dependencias":       contexto_dependencias,
        "contexto_teorico":            contexto_teoria,
        "rubrica_dinamica":            st.session_state.get("rubrica_dinamica"),
        "max_iteraciones":             max_iter,
        "siguiente_nodo":              "",
        "instrucciones_supervisor":    "",
        "pasos_ejecutados":            0,
        "max_pasos_red":               max_pasos,
        "iter_auditada":               0,
        "iter_metodologica":           0,
        "iter_consenso":               0,
        "iter_disenso":                0,
        "plan_supervisor":             "",
        "texto_iterado":               "",
        "feedback_auditor":            "",
        "numero_iteracion":            0,
        "errores_rubrica":             [],
        "puntaje_estimado":            None,
        "observaciones_metodologicas": "",
        "resultado_consenso":          "",
        "resultado_disenso":           "",
        "debate_memory":               [],
        "debate_veredicto":            None,
        "debate_completado":           False,
        "historial_debate":            [],
        "_puntaje_max":                None,
        "consenso_matematico":         {},
        "scores_subagentes":           [],
        "consenso_matematico_auditor": {},
        "loras_activas":               [],
        "consenso_ejecutado":          False,
        "disenso_ejecutado":           False,
        "auditor_ejecutado":           False,
        "metodologo_ejecutado":        False,
        "debate_ejecutado":            False,
    }

    config = get_config()

    # Registrar el vector store activo para que los agentes puedan consultarlo
    # dinámicamente durante la ejecución del grafo (Auditor, Metodólogo, Redactor).
    set_vector_store(vs)

    _NODO_LABELS = {
        "nodo_supervisor":   "Supervisor",
        "nodo_redactor":     "Redactor",
        "nodo_auditor":      "Auditor",
        "nodo_metodologico": "Metodólogo",
        "nodo_debate":       "Debate (panel 4 subagentes)",
        "nodo_consenso":     "Consenso",
        "nodo_disenso":      "Disenso",
        "nodo_exportador":   "Exportador",
    }

    nodos_completados: list[str] = []

    with st.status("Red multiagente trabajando…", expanded=True) as status_run:
        st.write("**Supervisor** orquesta la red — decide dinámicamente el siguiente agente…")
        try:
            for chunk in graph.stream(estado_inicial, config, stream_mode="updates"):
                for nodo, _ in chunk.items():
                    label = _NODO_LABELS.get(nodo, nodo)
                    nodos_completados.append(nodo)
                    st.write(f"✓ **{label}** completado")
        except Exception as exc:
            tb = traceback.format_exc()
            ultimo_nodo = nodos_completados[-1] if nodos_completados else "ninguno"
            # Log completo para Cloud Run logs (visible con `gcloud run services logs tail`)
            logger.error(
                "[GRAFO] Excepción después de %d nodos. Último completado: %s\n"
                "Tipo: %s — Mensaje: %s\n%s",
                len(nodos_completados), ultimo_nodo,
                type(exc).__name__, exc, tb,
            )
            msg = (
                f"[{type(exc).__name__}] {exc} "
                f"| Último nodo: {ultimo_nodo} "
                f"| Nodos ok: {len(nodos_completados)}"
            )
            st.session_state.error_msg = f"Error en el grafo: {msg}"
            st.rerun()

        st.session_state.graph_status = "completed"
        status_run.update(label="Evaluación completada — resultado listo", state="complete")

    st.rerun()
