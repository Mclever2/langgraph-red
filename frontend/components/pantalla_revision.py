import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..session_manager import (
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

    st.title("Resultados de la Evaluación Multiagente")
    st.markdown(
        f"El ciclo automático finalizó tras **{n_iter} iteración(es)**. "
        "El sistema procesó el texto de forma autónoma."
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

    _render_editor(v, seccion)


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_metricas(n_iter: int, errores: list, pts, pts_max: int, rubrica) -> None:
    c1, c2, c3, c4 = st.columns(4)
    max_iter_config = v.get("max_iteraciones", 1)
    c1.metric("Iteraciones", f"{n_iter}/{max_iter_config}")
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

    st.markdown(f"Se realizaron **{len(historial_debate)} ronda(s) de debate** (Auditor vs Metodólogo).")
    for ronda in historial_debate:
        n_ronda       = ronda.get("ronda", "?")
        items_conf    = ronda.get("items_confirmados", [])
        items_desc    = ronda.get("items_descartados", [])
        with st.expander(
            f"Ronda {n_ronda} — "
            f"{len(items_conf)} confirmados · {len(items_desc)} descartados",
            expanded=(n_ronda == len(historial_debate)),
        ):
            st.markdown("**Argumento del Auditor** (defiende sus hallazgos de rúbrica):")
            st.info(ronda.get("argumento_auditor", "—"))
            st.markdown("**Respuesta del Metodólogo** (evalúa si los errores son reales):")
            st.warning(ronda.get("respuesta_metodologico", "—"))
            col_c, col_d = st.columns(2)
            with col_c:
                if items_conf:
                    st.error(f"Ítems confirmados (debe corregir): {', '.join(str(i) for i in items_conf)}")
                else:
                    st.success("Sin ítems confirmados")
            with col_d:
                if items_desc:
                    st.success(f"Ítems descartados (no eran reales): {', '.join(str(i) for i in items_desc)}")
                else:
                    st.info("Sin ítems descartados")


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


def _render_editor(v: dict, seccion: str) -> None:
    st.subheader(f"Texto mejorado — Sección: *{seccion}*")
    st.caption(
        "Texto generado por el Redactor basándose en el contenido original del estudiante y la rúbrica activa. "
        "Los placeholders [COMPLETAR: ...] indican elementos que el estudiante debe completar."
    )
    st.text_area(
        label="Texto resultado:",
        value=v.get("texto_iterado", ""),
        height=450,
        key="editor_texto_resultado",
        label_visibility="collapsed",
        disabled=True,
    )
