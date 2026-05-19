"""
Pantalla 4 — Resultado final aprobado.

Muestra el texto final aprobado con métricas del proceso y el feedback
del Auditor agrupado por sección de la rúbrica activa.
"""

import os
import json

import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..session_manager import get_snapshot, badge_puntaje, reset_solo_grafo, reset_todo


def render_pantalla_resultado() -> None:
    snap = get_snapshot()
    v    = snap.values

    seccion  = v.get("seccion_objetivo", "—")
    n_iter   = v.get("numero_iteracion", 0)
    pts      = v.get("puntaje_estimado")
    rubrica  = v.get("rubrica_dinamica")

    if rubrica:
        pts_max = rubrica.get("puntaje_maximo", 0)
    else:
        pts_max = len(SECCION_ITEMS_MAP.get(seccion, [])) * 3

    st.title("Mentoría Completada")
    st.success(
        f"El texto de la sección **{seccion}** fue **aprobado** "
        f"tras **{n_iter} iteración(es)** automática(s)."
    )

    _render_metricas_finales(n_iter, pts, pts_max, rubrica)
    st.divider()
    _render_reportes_descarga(v)
    st.divider()
    _render_texto_final(v, seccion)
    st.divider()
    _render_metricas_nlp(st.session_state.get("thread_id", ""))
    st.divider()
    _render_resumen_proceso(v, rubrica)
    st.divider()
    _render_botones_finales()


# ── Secciones internas ────────────────────────────────────────────────────────

def _render_metricas_finales(n_iter: int, pts, pts_max: int, rubrica) -> None:
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Iteraciones automáticas", f"{n_iter}/3")
    mc2.metric("Puntaje de sección", badge_puntaje(pts or 0, pts_max) if pts else "—")
    if pts and pts_max > 0:
        if rubrica and rubrica.get("tabla_vigesimal"):
            from backend.rag.rubric_parser import puntaje_a_nota_dinamico
            nota = puntaje_a_nota_dinamico(
                round(pts * rubrica["puntaje_maximo"] / pts_max),
                rubrica["tabla_vigesimal"],
            )
        else:
            nota = puntaje_a_nota(round(pts * 99 / pts_max))
        mc3.metric("Nota vigesimal estimada", f"{nota}/20")


def _render_reportes_descarga(v: dict) -> None:
    """Sección de descarga de reportes y tabla de métricas computacionales."""
    st.subheader("Reportes del Ciclo Multiagente")

    rutas = v.get("rutas_reportes") or []

    # ── Tabla de métricas ────────────────────────────────────────────────────
    ruta_metricas = next((r for r in rutas if r and r.endswith(".json")), None)
    if ruta_metricas and os.path.isfile(ruta_metricas):
        try:
            with open(ruta_metricas, encoding="utf-8") as f:
                datos = json.load(f)
            metricas    = datos.get("metricas", {})
            m_debate    = datos.get("metricas_debate", {})
            score_comp  = datos.get("score_compuesto", {})
            datos_crudos = datos.get("datos_crudos", {})

            coherencia    = metricas.get("coherencia_semantica", {})
            mejora        = metricas.get("indice_mejora", {})
            acuerdo       = m_debate.get("acuerdo_multiagente", {})
            argumentativa = m_debate.get("calidad_argumentativa", {})

            st.markdown("#### Métricas Computacionales")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "TF-IDF — Fidelidad",
                f"{coherencia.get('valor', 0):.3f}",
                help="¿El agente preservó el trabajo del estudiante?",
            )
            col2.metric(
                "ROUGE-L — Cobertura",
                f"{argumentativa.get('valor', 0):.3f}",
                help="¿El agente respondió a las críticas recibidas?",
            )
            col3.metric(
                "Kappa proxy — Consistencia",
                f"{acuerdo.get('valor', 0):.3f}",
                help="¿El Auditor es consistente?",
            )
            col4.metric(
                "Normalized Gain — Mejora",
                f"{mejora.get('valor', 0):.3f}",
                help="¿El proceso realmente mejoró el texto?",
            )

            score_val = score_comp.get("valor", 0)
            interp    = score_comp.get("interpretacion", "")
            st.info(
                f"**Score compuesto:** {score_val:.4f} "
                f"(70% coherencia + 30% mejora) — {interp}  \n"
                f"Puntaje rúbrica: {datos_crudos.get('puntaje_inicial', 0)} → "
                f"{datos_crudos.get('puntaje_final', 0)} / {datos_crudos.get('puntaje_max', 0)}"
            )
        except Exception:
            st.warning("No se pudieron leer las métricas del archivo JSON.")

    # ── Botones de descarga ──────────────────────────────────────────────────
    if rutas:
        st.markdown("#### Descargar Reportes")
        col_d1, col_d2 = st.columns(2)

        ruta_debate = next((r for r in rutas if r and r.endswith(".md")), None)

        if ruta_metricas and os.path.isfile(ruta_metricas):
            with open(ruta_metricas, encoding="utf-8") as f:
                contenido_json = f.read()
            col_d1.download_button(
                label="Descargar métricas (.json)",
                data=contenido_json,
                file_name=os.path.basename(ruta_metricas),
                mime="application/json",
                use_container_width=True,
            )

        if ruta_debate and os.path.isfile(ruta_debate):
            with open(ruta_debate, encoding="utf-8") as f:
                contenido_md = f.read()
            col_d2.download_button(
                label="Descargar transcripción del debate (.md)",
                data=contenido_md,
                file_name=os.path.basename(ruta_debate),
                mime="text/markdown",
                use_container_width=True,
            )
    else:
        st.caption(
            "Los reportes se generan automáticamente al aprobar. "
            "También se guardan en `backend/logs/`."
        )


def _render_texto_final(v: dict, seccion: str) -> None:
    st.subheader(f"Texto Final Aprobado — {seccion}")
    # Si el Redactor nunca corrió (texto aprobado en primera evaluación), usa el original
    texto_final = v.get("texto_iterado") or v.get("contexto_recuperado", "")

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
    st.caption("Usa el ícono de copia para exportar el texto aprobado.")

    if "[COMPLETAR:" in texto_final:
        st.warning(
            "El texto contiene placeholders `[COMPLETAR: ...]`. "
            "Estos indican secciones que **el estudiante debe completar** con contenido real de su investigación."
        )


def _render_resumen_proceso(v: dict, rubrica) -> None:
    with st.expander("Resumen completo del proceso de mentoría"):
        col_r1, col_r2 = st.columns(2)

        with col_r1:
            st.markdown("**Feedback final del Auditor:**")
            st.info(v.get("feedback_auditor", "—"))

            if v.get("resultado_consenso"):
                st.markdown("**Análisis de Consenso:**")
                st.info(v.get("resultado_consenso"))

            if v.get("resultado_disenso"):
                st.markdown("**Análisis de Disenso:**")
                st.warning(v.get("resultado_disenso"))

        with col_r2:
            errores_finales = v.get("errores_rubrica", [])
            if errores_finales:
                # Agrupar por sección si hay rúbrica dinámica
                if rubrica:
                    secciones_rubrica = rubrica.get("secciones", {})
                    item_a_seccion = {
                        n: sec
                        for sec, nums in secciones_rubrica.items()
                        for n in nums
                    }
                    errores_por_seccion: dict = {}
                    for err in errores_finales:
                        sec = item_a_seccion.get(err["item_numero"], "General")
                        errores_por_seccion.setdefault(sec, []).append(err)

                    st.markdown(f"**Observaciones restantes ({len(errores_finales)} ítems, no bloqueantes):**")
                    for sec_nombre, errs in errores_por_seccion.items():
                        st.markdown(f"*{sec_nombre}*")
                        for err in errs:
                            st.markdown(
                                f"- Ítem **{err['item_numero']:02d}** "
                                f"(puntaje={err['puntaje_actual']}): {err['descripcion']}"
                            )
                else:
                    st.markdown(f"**Observaciones restantes ({len(errores_finales)} ítems, no bloqueantes):**")
                    for err in errores_finales:
                        st.markdown(
                            f"- Ítem **{err['item_numero']:02d}** "
                            f"(puntaje={err['puntaje_actual']}): {err['descripcion']}"
                        )
            else:
                tipo = "la rúbrica personalizada" if rubrica else "la rúbrica UPAO"
                st.success(f"El texto cumple todos los ítems evaluados de {tipo}.")

        st.divider()
        st.markdown("**Contexto original recuperado del PDF:**")
        st.text(v.get("contexto_recuperado", "—")[:1200] + "…")

        st.caption(
            "Los archivos JSON y Markdown también están disponibles en `backend/logs/`."
        )


def _render_metricas_nlp(run_id: str) -> None:
    """Muestra métricas NLP del evaluador determinístico (ROUGE, BLEU, coseno, kappa, gain)."""
    if not run_id:
        st.caption("Métricas NLP no disponibles para esta sesión.")
        return

    ruta = f"./outputs/run_{run_id}.json"
    if not os.path.isfile(ruta):
        st.caption("Métricas NLP no disponibles para esta sesión.")
        return

    try:
        from evaluator.evaluator import evaluar_desde_archivo
        resultado = evaluar_desde_archivo(ruta)
        m = resultado.get("metricas", {})

        st.subheader("Métricas NLP del Proceso")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ROUGE-1 F", f"{m.get('rouge1_f', 0):.4f}", help="Solapamiento de unigramas entre texto inicial y mejorado")
        col2.metric("ROUGE-2 F", f"{m.get('rouge2_f', 0):.4f}", help="Solapamiento de bigramas")
        col3.metric("ROUGE-L F", f"{m.get('rougeL_f', 0):.4f}", help="Subsecuencia común más larga")
        col4.metric("BLEU", f"{m.get('bleu_score', 0):.4f}", help="Precisión n-grama ponderada")

        col5, col6, col7 = st.columns(3)
        col5.metric("Similitud Coseno", f"{m.get('similitud_coseno', 0):.4f}", help="Coherencia temática TF-IDF entre versiones")
        kappa_val = m.get("kappa")
        col6.metric("Kappa", f"{kappa_val:.4f}" if kappa_val is not None else "N/A", help="Acuerdo entre agentes en el debate")
        col7.metric("Gain Score", f"{m.get('gain_score', 0):.4f}", help="Mejora normalizada del puntaje (0–1)")

    except Exception:
        st.caption("Métricas NLP no disponibles para esta sesión.")


def _render_botones_finales() -> None:
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Evaluar otra sección (mismo PDF)", use_container_width=True):
            reset_solo_grafo()
            st.rerun()
    with col_b2:
        if st.button(
            "Nueva evaluación (nuevo PDF)",
            type="primary",
            use_container_width=True,
        ):
            reset_todo()
            st.rerun()
