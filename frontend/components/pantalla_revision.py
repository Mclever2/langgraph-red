"""
Pantalla 3 — Revisión humana (grafo pausado en HITL).

Muestra las métricas del ciclo automático, el informe del Auditor y
el editor del texto mejorado. El mentor puede aprobar (con ediciones)
o rechazar y re-evaluar.
"""

import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..resources import graph
from ..session_manager import (
    get_config,
    get_snapshot,
    reset_solo_grafo,
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
    pts_max  = len(SECCION_ITEMS_MAP.get(seccion, [])) * 3

    historial_debate = v.get("historial_debate", [])
    plan_supervisor  = v.get("plan_supervisor", "")
    obs_metod        = v.get("observaciones_metodologicas", "")

    st.title("📋 Revisión del Mentor — Aprobación Final")
    st.markdown(
        f"El ciclo automático finalizó tras **{n_iter} iteración(es)**. "
        "Revisa el texto, edítalo si lo deseas y decide si lo apruebas."
    )
    st.divider()

    _render_metricas(n_iter, errores, pts, pts_max)
    st.divider()
    _render_tabs_informe(v, errores, feedback, seccion, historial_debate, plan_supervisor, obs_metod)
    st.divider()

    texto_editado = _render_editor(v, seccion)
    st.divider()
    _render_decision(texto_editado)


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_metricas(n_iter: int, errores: list, pts, pts_max: int) -> None:
    """Métricas del proceso en 4 columnas."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Iteraciones", f"{n_iter}/3")
    c2.metric(
        "Errores finales",
        len(errores),
        delta="✅ Sin errores" if len(errores) == 0 else None,
        delta_color="normal",
    )
    c3.metric("Puntaje sección", badge_puntaje(pts or 0, pts_max) if pts else "—")
    if pts and pts_max > 0:
        nota = puntaje_a_nota(round(pts * 99 / pts_max))
        c4.metric("Nota estimada (vigesimal)", f"{nota}/20")


def _render_tabs_informe(
    v: dict,
    errores: list,
    feedback: str,
    seccion: str,
    historial_debate: list = None,
    plan_supervisor: str = "",
    obs_metod: str = "",
) -> None:
    """Tabs con el informe del Auditor, debate, informe supervisor, texto original y contexto RAG."""
    historial_debate = historial_debate or []

    tab_audit, tab_debate, tab_super, tab_orig, tab_ctx = st.tabs([
        "📊 Informe del Auditor",
        "🗣️ Debate entre Agentes",
        "🧠 Informe del Supervisor",
        "📄 Texto Original del Estudiante",
        "🔍 Contexto Recuperado (RAG)",
    ])

    with tab_audit:
        if not errores:
            st.success(
                "✅ **El Auditor declaró el texto conforme a la rúbrica UPAO** "
                f"para la sección *{seccion}*. Se solicitó revisión humana para aprobación final."
            )
        else:
            st.warning(
                f"⚠️ El Auditor detectó **{len(errores)} ítem(s)** con puntaje 0–1 "
                f"al terminar la iteración #{v.get('numero_iteracion', 0)}."
            )
            for err in errores:
                puntaje_lbl = (
                    "🔴 Insuficiente (0)" if err["puntaje_actual"] == 0 else "🟡 Regular (1)"
                )
                with st.container(border=True):
                    st.markdown(
                        f"**Ítem {err['item_numero']:02d}** &nbsp; {puntaje_lbl}\n\n"
                        f"{err['descripcion']}"
                    )

        st.divider()
        st.markdown("**Feedback general del Auditor:**")
        st.info(feedback)

        if obs_metod:
            st.divider()
            st.markdown("**Observaciones del Metodólogo (rigor científico):**")
            st.info(obs_metod)

    with tab_debate:
        if not historial_debate:
            st.info("No hubo rondas de debate en este ciclo (sin errores detectados o proceso omitido).")
        else:
            st.markdown(
                f"Se realizaron **{len(historial_debate)} ronda(s) de debate** entre el Redactor y el panel evaluador."
            )
            for ronda in historial_debate:
                n_ronda = ronda.get("ronda", "?")
                items_acep = ronda.get("items_aceptados", [])
                items_mant = ronda.get("items_mantenidos", [])
                with st.expander(
                    f"Ronda {n_ronda} — "
                    f"✅ {len(items_acep)} aceptados · "
                    f"⚠️ {len(items_mant)} mantenidos",
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
                            st.info("Sin ítems aceptados en esta ronda")
                    with col_m:
                        if items_mant:
                            st.error(f"Ítems mantenidos: {', '.join(str(i) for i in items_mant)}")
                        else:
                            st.success("Sin ítems mantenidos — todos resueltos")

    with tab_super:
        st.markdown("**Informe final del Supervisor:**")
        if plan_supervisor:
            st.markdown(plan_supervisor)
        else:
            st.info("Sin informe del Supervisor disponible.")

    with tab_orig:
        st.markdown("**Contexto original extraído del PDF (sección evaluada):**")
        st.text(v.get("contexto_recuperado", "—"))

    with tab_ctx:
        st.markdown("**Fragmentos recuperados por ChromaDB (RAG):**")
        contexto_raw = v.get("contexto_recuperado", "—")
        for i, fragmento in enumerate(contexto_raw.split("---"), start=1):
            if fragmento.strip():
                with st.expander(f"Fragmento {i}"):
                    st.text(fragmento.strip())


def _render_editor(v: dict, seccion: str) -> str:
    """Área de edición del texto mejorado. Devuelve el valor editado."""
    st.subheader(f"✏️ Texto mejorado — Sección: *{seccion}*")
    st.caption(
        "El sistema generó esta versión en base al formato y rúbrica UPAO. "
        "Puedes editarla antes de aprobar."
    )
    return st.text_area(
        label="Texto para aprobación:",
        value=v.get("texto_iterado", ""),
        height=450,
        key="editor_texto_hitl",
        label_visibility="collapsed",
    )


def _render_decision(texto_editado: str) -> None:
    """Botones de decisión del mentor: Aprobar o Rechazar."""
    st.subheader("Decisión del Mentor")
    col_ap, col_re = st.columns(2)

    with col_ap:
        st.markdown("**✅ Aprobar:** El texto (con tus ediciones) queda como versión final.")
        if st.button("✅ Aprobar Texto Final", type="primary", use_container_width=True):
            config = get_config()
            graph.update_state(
                config,
                {
                    "aprobacion_humana": "aprobado",
                    "texto_iterado":     texto_editado,
                },
            )
            with st.spinner("Registrando aprobación y cerrando el proceso…"):
                try:
                    graph.invoke(None, config)
                except Exception as exc:
                    st.session_state.error_msg = f"Error al reanudar el grafo: {exc}"
                    st.rerun()
            st.session_state.graph_status = "completed"
            st.rerun()

    with col_re:
        st.markdown(
            "**❌ Rechazar:** Descarta este resultado. "
            "Puedes evaluar la misma sección de nuevo."
        )
        if st.button("❌ Rechazar y Re-evaluar", type="secondary", use_container_width=True):
            reset_solo_grafo()
            st.rerun()
