"""
Pantalla 4 — Resultado final aprobado.

Muestra el texto final aprobado con métricas del proceso, el feedback
del Auditor y las observaciones residuales (no bloqueantes).
Ofrece opciones para evaluar otra sección o comenzar una nueva evaluación.
"""

import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..session_manager import get_snapshot, badge_puntaje, reset_solo_grafo, reset_todo


def render_pantalla_resultado() -> None:
    """Renderiza la pantalla de resultado final aprobado."""
    snap = get_snapshot()
    v    = snap.values

    seccion  = v.get("seccion_objetivo", "—")
    n_iter   = v.get("numero_iteracion", 0)
    pts      = v.get("puntaje_estimado")
    pts_max  = len(SECCION_ITEMS_MAP.get(seccion, [])) * 3

    st.title("✅ Mentoría Completada")
    st.success(
        f"El texto de la sección **{seccion}** fue **aprobado** "
        f"tras **{n_iter} iteración(es)** automática(s)."
    )

    _render_metricas_finales(n_iter, pts, pts_max)
    st.divider()
    _render_texto_final(v, seccion)
    st.divider()
    _render_resumen_proceso(v)
    st.divider()
    _render_botones_finales()


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_metricas_finales(n_iter: int, pts, pts_max: int) -> None:
    """Métricas finales del proceso en 3 columnas."""
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Iteraciones automáticas", f"{n_iter}/3")
    mc2.metric("Puntaje de sección", badge_puntaje(pts or 0, pts_max) if pts else "—")
    if pts and pts_max > 0:
        nota = puntaje_a_nota(round(pts * 99 / pts_max))
        mc3.metric("Nota vigesimal estimada", f"{nota}/20")


def _render_texto_final(v: dict, seccion: str) -> None:
    """Muestra el texto final con estilo y botón de copia."""
    st.subheader(f"📄 Texto Final Aprobado — {seccion}")
    texto_final = v.get("texto_iterado", "")

    st.markdown(
        f"""
        <div style="
            background:#f0faf0;
            border-left:4px solid #28a745;
            padding:1.2rem 1.5rem;
            border-radius:6px;
            line-height:1.8;
            font-size:0.96rem;
        ">{texto_final.replace(chr(10), "<br>")}</div>
        """,
        unsafe_allow_html=True,
    )
    st.code(texto_final, language=None)
    st.caption("☝️ Usa el ícono de copia para exportar el texto aprobado.")


def _render_resumen_proceso(v: dict) -> None:
    """Expander con el resumen completo del proceso de mentoría."""
    with st.expander("📊 Resumen completo del proceso de mentoría"):
        col_r1, col_r2 = st.columns(2)

        with col_r1:
            st.markdown("**Feedback final del Auditor:**")
            st.info(v.get("feedback_auditor", "—"))

        with col_r2:
            errores_finales = v.get("errores_rubrica", [])
            if errores_finales:
                st.markdown(
                    f"**Observaciones restantes ({len(errores_finales)} ítems, no bloqueantes):**"
                )
                for err in errores_finales:
                    st.markdown(
                        f"- Ítem **{err['item_numero']:02d}** "
                        f"(puntaje={err['puntaje_actual']}): {err['descripcion']}"
                    )
            else:
                st.success("El texto cumple todos los ítems evaluados de la rúbrica UPAO.")

        st.divider()
        st.markdown("**Contexto original recuperado del PDF:**")
        st.text(v.get("contexto_recuperado", "—")[:1200] + "…")


def _render_botones_finales() -> None:
    """Botones para evaluar otra sección o comenzar nueva evaluación."""
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("📄 Evaluar otra sección (mismo PDF)", use_container_width=True):
            reset_solo_grafo()
            st.rerun()
    with col_b2:
        if st.button(
            "🔄 Nueva evaluación (nuevo PDF)",
            type="primary",
            use_container_width=True,
        ):
            reset_todo()
            st.rerun()
