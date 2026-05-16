"""Pantalla 2 — Selección de sección y lanzamiento del grafo multiagente."""

import streamlit as st

from backend.config import (
    SECCIONES_TESIS, SECCION_ITEMS_MAP, DEPENDENCIAS_SECCIONES,
    MAX_RONDAS_DEBATE_DEFAULT,
)
from backend.rag import recuperar_contexto, recuperar_contexto_teorico, listar_libros

from ..resources import graph, biblioteca
from ..session_manager import get_config, get_snapshot, is_paused


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

    nombres_secciones = [s["nombre"] for s in SECCIONES_TESIS]
    col_form, col_config = st.columns([2, 1])

    with col_form:
        seccion_elegida = st.selectbox(
            "Sección del proyecto de tesis:",
            options=nombres_secciones,
            help="El sistema buscará en el PDF los fragmentos relevantes para esta sección y sus dependencias.",
        )

        # Mostrar ítems según la rúbrica activa
        if rubrica_activa:
            # Mostrar ítems de la rúbrica dinámica (todos, ya que aplican globalmente)
            secciones_rubrica = rubrica_activa.get("secciones", {})
            if secciones_rubrica:
                primer_grupo = next(iter(secciones_rubrica.values()), [])
                total = rubrica_activa["total_items"]
                st.caption(
                    f"Rúbrica personalizada: **{total} ítems** en "
                    f"{len(secciones_rubrica)} secciones · "
                    f"puntaje máx: {rubrica_activa['puntaje_maximo']} pts"
                )
        else:
            items_de_seccion = SECCION_ITEMS_MAP.get(seccion_elegida, [])
            if items_de_seccion:
                st.caption(
                    f"Ítems UPAO a evaluar: **{', '.join(str(i) for i in items_de_seccion)}** "
                    f"(máx. {len(items_de_seccion) * 3} pts)"
                )

        deps = DEPENDENCIAS_SECCIONES.get(seccion_elegida, [])
        if deps:
            st.caption(f"Secciones relacionadas consultadas: {', '.join(deps)}")

    with col_config:
        with st.expander("Configuración avanzada", expanded=False):
            max_debate = st.slider(
                "Rondas máximas de debate:",
                min_value=1, max_value=3,
                value=MAX_RONDAS_DEBATE_DEFAULT,
                help="Rondas de argumentación Redactor ↔ Evaluadores por ciclo",
            )

    st.divider()

    max_iter  = 1
    # Flujo real: Aud+Met+Con+Dis+(Debate×max_debate)+Red+Aud2 = 7+max_debate agentes
    # Cada agente tiene su Supervisor antes → ×2 + holgura
    max_pasos = (7 + max_debate) * 2 + 4

    tiempo_est_min = (6 + max_debate) * 6 // 60
    tiempo_est_max = (6 + max_debate) * 10 // 60
    st.info(
        f"1 ciclo de evaluación · {max_debate} ronda(s) de debate · "
        f"Tiempo estimado: {tiempo_est_min}–{tiempo_est_max} min · "
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
    with st.spinner("Recuperando contexto inteligente (sección + dependencias)…"):
        contexto_tesis = recuperar_contexto(vs, seccion_elegida)

        deps = DEPENDENCIAS_SECCIONES.get(seccion_elegida, [])
        partes_deps = []
        for dep in deps:
            ctx_dep = recuperar_contexto(vs, dep)
            if ctx_dep and ctx_dep.strip():
                partes_deps.append(f"### {dep}\n{ctx_dep}")
        contexto_dependencias = "\n\n---\n\n".join(partes_deps) if partes_deps else ""

        contexto_teoria = recuperar_contexto_teorico(biblioteca, seccion_elegida)

    if not contexto_tesis.strip():
        st.warning(
            "No se encontró contenido en el PDF para esta sección. "
            "Prueba con otra sección o verifica que el PDF tenga texto seleccionable."
        )
        st.stop()

    n_libros = len(listar_libros(biblioteca))
    col_i1, col_i2 = st.columns(2)
    col_i1.success("Contexto principal recuperado")
    if contexto_dependencias:
        col_i2.success(f"{len(deps)} sección(es) relacionada(s) recuperadas")
    else:
        col_i2.info("Sin contexto cruzado (secciones aún no escritas)")

    # ── Estado inicial para el grafo ──────────────────────────────────────────
    estado_inicial = {
        "seccion_objetivo":            seccion_elegida,
        "contexto_recuperado":         contexto_tesis,
        "contexto_dependencias":       contexto_dependencias,
        "contexto_teorico":            contexto_teoria,
        "rubrica_dinamica":            st.session_state.get("rubrica_dinamica"),
        "max_iteraciones":             max_iter,
        "max_rondas_debate":           max_debate,
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
        "ronda_debate":                0,
        "historial_debate":            [],
        "argumento_redactor":          "",
        "veredicto_debate":            "",
        "aprobacion_humana":           None,
    }

    config = get_config()

    with st.status("Red multiagente trabajando…", expanded=True) as status_run:
        st.write("**Supervisor** orquesta la red — decide dinámicamente el siguiente agente…")
        st.write("Redactor → Auditor → Metodólogo → Consenso/Disenso → Debate (orden dinámico)")
        st.write("Cada agente regresa al Supervisor para que decida el siguiente paso…")
        try:
            graph.invoke(estado_inicial, config)
        except Exception as exc:
            st.session_state.error_msg = f"Error en el grafo: {exc}"
            st.rerun()

        snap = get_snapshot()
        if is_paused(snap):
            st.write("Listo para revisión del mentor")
            st.session_state.graph_status = "paused"
            status_run.update(label="Evaluación completada — pendiente revisión", state="complete")
        else:
            st.session_state.graph_status = "completed"
            status_run.update(label="Completado", state="complete")

    st.rerun()
