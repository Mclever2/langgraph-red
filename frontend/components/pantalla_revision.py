"""
Pantalla 3 — Revisión humana (grafo pausado en HITL).

Muestra métricas del ciclo automático, el informe del Auditor agrupado
por sección de la rúbrica activa, el debate y el texto mejorado.
El mentor puede aprobar (con ediciones) o rechazar y re-evaluar.
"""

import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..resources import graph
from ..session_manager import (
    get_config,
    get_snapshot,
    badge_puntaje,
)


def render_pantalla_revision() -> None:
    """Renderiza la pantalla de revisión y aprobación del mentor (HITL)."""
    snap = get_snapshot()
    v    = snap.values

    n_iter   = v.get("numero_iteracion", 0)
    errores  = v.get("errores_rubrica", [])
    feedback = v.get("feedback_auditor", "Sin feedback disponible.")
    seccion  = v.get("seccion_objetivo", "—")
    pts      = v.get("puntaje_estimado")
    rubrica  = v.get("rubrica_dinamica")

    # Puntaje máximo según rúbrica activa
    if rubrica:
        pts_max = rubrica.get("puntaje_maximo", 0)
    else:
        pts_max = len(SECCION_ITEMS_MAP.get(seccion, [])) * 3

    historial_debate   = v.get("historial_debate", [])
    plan_supervisor    = v.get("plan_supervisor", "")
    obs_metod          = v.get("observaciones_metodologicas", "")
    resultado_consenso = v.get("resultado_consenso", "")
    resultado_disenso  = v.get("resultado_disenso", "")

    st.title("Revisión del Mentor — Aprobación Final")
    st.markdown(
        f"El ciclo automático finalizó tras **{n_iter} iteración(es)**. "
        "Revisa el texto, edítalo si lo deseas y decide si lo apruebas."
    )
    st.divider()

    _render_metricas(n_iter, errores, pts, pts_max, rubrica)
    st.divider()
    _render_tabs_informe(
        v, errores, feedback, seccion, rubrica,
        historial_debate, plan_supervisor, obs_metod,
        resultado_consenso, resultado_disenso,
    )
    st.divider()

    texto_editado = _render_editor(v, seccion)
    st.divider()
    _render_decision(texto_editado)


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_metricas(n_iter: int, errores: list, pts, pts_max: int, rubrica) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Iteraciones", f"{n_iter}/3")
    c2.metric(
        "Errores finales",
        len(errores),
        delta="Sin errores" if len(errores) == 0 else None,
        delta_color="normal",
    )
    c3.metric("Puntaje sección", badge_puntaje(pts or 0, pts_max) if pts else "—")
    if pts and pts_max > 0:
        if rubrica and rubrica.get("tabla_vigesimal"):
            from backend.rag.rubric_parser import puntaje_a_nota_dinamico
            nota = puntaje_a_nota_dinamico(
                round(pts * rubrica["puntaje_maximo"] / pts_max),
                rubrica["tabla_vigesimal"],
            )
        else:
            nota = puntaje_a_nota(round(pts * 99 / pts_max))
        c4.metric("Nota estimada (vigesimal)", f"{nota}/20")


def _render_tabs_informe(
    v: dict, errores: list, feedback: str, seccion: str, rubrica,
    historial_debate: list, plan_supervisor: str, obs_metod: str,
    resultado_consenso: str, resultado_disenso: str,
) -> None:
    """Tabs con informe del Auditor (por sección), debate, consenso/disenso, supervisor, original, RAG."""
    historial_debate = historial_debate or []

    tabs = st.tabs([
        "Informe del Auditor",
        "Debate entre Agentes",
        "Consenso / Disenso",
        "Informe del Supervisor",
        "Texto Original",
        "Contexto RAG",
    ])

    with tabs[0]:
        _render_tab_auditor(errores, feedback, seccion, rubrica, obs_metod, v)

    with tabs[1]:
        _render_tab_debate(historial_debate, v)

    with tabs[2]:
        _render_tab_consenso_disenso(resultado_consenso, resultado_disenso)

    with tabs[3]:
        st.markdown("**Informe final del Supervisor:**")
        if plan_supervisor:
            st.markdown(plan_supervisor)
        else:
            st.info("Sin informe del Supervisor disponible.")

    with tabs[4]:
        st.markdown("**Contexto original extraído del PDF (sección evaluada):**")
        st.text(v.get("contexto_recuperado", "—"))

    with tabs[5]:
        st.markdown("**Fragmentos recuperados por ChromaDB (RAG):**")
        contexto_raw = v.get("contexto_recuperado", "—")
        for i, fragmento in enumerate(contexto_raw.split("---"), start=1):
            if fragmento.strip():
                with st.expander(f"Fragmento {i}"):
                    st.text(fragmento.strip())


def _render_tab_auditor(errores, feedback, seccion, rubrica, obs_metod, v) -> None:
    """Muestra el informe del Auditor, agrupando errores por sección de la rúbrica."""
    if not errores:
        tipo = "la rúbrica subida" if rubrica else "la rúbrica UPAO"
        st.success(
            f"El Auditor declaró el texto conforme a {tipo} "
            f"para la sección *{seccion}*."
        )
    else:
        st.warning(f"El Auditor detectó **{len(errores)} ítem(s)** con puntaje 0–1.")

        # Agrupar errores por sección de la rúbrica activa
        if rubrica:
            secciones_rubrica = rubrica.get("secciones", {})
            # Crear mapa item_numero → seccion
            item_a_seccion = {}
            for sec_nombre, nums in secciones_rubrica.items():
                for n in nums:
                    item_a_seccion[n] = sec_nombre

            # Agrupar errores
            errores_por_seccion: dict = {}
            for err in errores:
                sec = item_a_seccion.get(err["item_numero"], "General")
                errores_por_seccion.setdefault(sec, []).append(err)

            for sec_nombre, errs in errores_por_seccion.items():
                st.markdown(f"**{sec_nombre}**")
                for err in errs:
                    _render_error_card(err)
        else:
            # Sin rúbrica dinámica — lista plana
            for err in errores:
                _render_error_card(err)

    st.divider()
    st.markdown("**Feedback general del Auditor:**")
    st.info(feedback)

    if obs_metod:
        st.divider()
        st.markdown("**Observaciones del Metodólogo (rigor científico):**")
        st.info(obs_metod)


def _render_error_card(err: dict) -> None:
    puntaje_lbl = (
        "Insuficiente (0)" if err["puntaje_actual"] == 0 else "Regular (1)"
    )
    with st.container(border=True):
        st.markdown(
            f"**Ítem {err['item_numero']:02d}** &nbsp; {puntaje_lbl}\n\n"
            f"{err['descripcion']}"
        )


def _render_tab_debate(historial_debate: list, v: dict) -> None:
    if not historial_debate:
        st.info("No hubo rondas de debate en este ciclo.")
        return

    st.markdown(f"Se realizaron **{len(historial_debate)} ronda(s) de debate**.")
    for ronda in historial_debate:
        n_ronda    = ronda.get("ronda", "?")
        items_acep = ronda.get("items_aceptados", [])
        items_mant = ronda.get("items_mantenidos", [])
        with st.expander(
            f"Ronda {n_ronda} — "
            f"{len(items_acep)} aceptados · {len(items_mant)} mantenidos",
            expanded=(n_ronda == len(historial_debate)),
        ):
            st.markdown("**Argumento del Redactor:**")
            st.info(ronda.get("argumento_redactor", "—"))
            st.markdown("**Veredicto de los Evaluadores:**")
            st.warning(ronda.get("veredicto_evaluadores", "—"))
            col_a, col_m = st.columns(2)
            with col_a:
                if items_acep:
                    st.success(f"Ítems aceptados: {', '.join(str(i) for i in items_acep)}")
                else:
                    st.info("Sin ítems aceptados")
            with col_m:
                if items_mant:
                    st.error(f"Ítems mantenidos: {', '.join(str(i) for i in items_mant)}")
                else:
                    st.success("Sin ítems mantenidos")


def _render_tab_consenso_disenso(resultado_consenso: str, resultado_disenso: str) -> None:
    """Muestra los análisis de consenso y disenso entre agentes evaluadores."""
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("**Análisis de Consenso**")
        st.caption("Puntos de acuerdo entre Auditor y Metodólogo")
        if resultado_consenso:
            st.info(resultado_consenso)
        else:
            st.caption("El nodo de Consenso no fue activado en este ciclo.")

    with col_d:
        st.markdown("**Análisis de Disenso**")
        st.caption("Conflictos entre Auditor y Metodólogo")
        if resultado_disenso:
            st.warning(resultado_disenso)
        else:
            st.caption("El nodo de Disenso no fue activado en este ciclo.")


def _render_editor(v: dict, seccion: str) -> str:
    st.subheader(f"Texto mejorado — Sección: *{seccion}*")
    st.caption(
        "El sistema mejoró el texto del estudiante basándose en su contenido original y la rúbrica activa. "
        "Puedes editarlo antes de aprobar. Los placeholders [COMPLETAR: ...] indican secciones que el estudiante debe completar."
    )
    return st.text_area(
        label="Texto para aprobación:",
        value=v.get("texto_iterado", ""),
        height=450,
        key="editor_texto_hitl",
        label_visibility="collapsed",
    )


def _render_decision(texto_editado: str) -> None:
    st.subheader("Decisión del Mentor")
    st.markdown("**Aprobar:** El texto (con tus ediciones) queda como versión final de esta iteración.")
    if st.button("Aprobar Texto Final", type="primary", use_container_width=True):
        config = get_config()
        graph.update_state(
            config,
            {
                "aprobacion_humana": "aprobado",
                "texto_iterado":     texto_editado,
            },
        )
        with st.spinner("Registrando aprobación y calculando métricas…"):
            try:
                graph.invoke(None, config)
            except Exception as exc:
                st.session_state.error_msg = f"Error al reanudar el grafo: {exc}"
                st.rerun()
        st.session_state.graph_status = "completed"
        st.rerun()
