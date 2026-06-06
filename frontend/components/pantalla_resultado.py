import os
import json
import re

import streamlit as st

from backend.config import SECCION_ITEMS_MAP, puntaje_a_nota

from ..session_manager import get_snapshot, badge_puntaje, reset_solo_grafo, reset_todo


def render_pantalla_resultado() -> None:
    snap = get_snapshot()
    v    = snap.values

    seccion  = v.get("seccion_objetivo", "—")
    n_iter   = v.get("numero_iteracion", 0)
    max_iter = v.get("max_iteraciones", 3)
    pts      = v.get("puntaje_estimado")
    rubrica  = v.get("rubrica_dinamica")

    # Usar _puntaje_max del estado (establecido por el Auditor) como fuente primaria.
    pts_max = v.get("_puntaje_max")
    if not pts_max:
        if rubrica:
            pts_max = rubrica.get("puntaje_maximo", 0)
        else:
            pts_max = _buscar_pts_max(seccion)

    pts_ratio = (float(pts) / float(pts_max)) if (pts and pts_max and float(pts_max) > 0) else 0.0

    st.title("Mentoría Completada")
    if pts_ratio >= 0.50:
        st.success(
            f"El texto de la sección **{seccion}** fue **aprobado** "
            f"tras **{n_iter} iteración(es)** automática(s)."
        )
    else:
        st.warning(
            f"El ciclo de revisión de **{seccion}** finalizó tras **{n_iter} iteración(es)**. "
            f"Puntaje: **{int(float(pts)) if pts else '?'}/{pts_max}** — el texto requiere mejoras significativas."
        )

    puntaje_inicial = v.get("puntaje_inicial")
    _render_metricas_finales(n_iter, max_iter, pts, pts_max, rubrica, puntaje_inicial)
    st.divider()

    tab_eval, tab_debate, tab_rag, tab_reportes = st.tabs([
        "📋 Evaluación",
        "⚖️ Debate",
        "📄 Contexto RAG",
        "📊 Reportes",
    ])

    with tab_eval:
        _render_tab_evaluacion(v, seccion, rubrica, pts, pts_max)

    with tab_debate:
        _render_tab_debate(v)

    with tab_rag:
        _render_tab_rag(v)

    with tab_reportes:
        _render_tab_reportes(v)

    st.divider()
    _render_botones_finales()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _buscar_pts_max(seccion: str) -> int:
    """Busca pts_max por nombre exacto o por prefijo numérico."""
    direct = SECCION_ITEMS_MAP.get(seccion)
    if direct:
        return len(direct) * 3
    prefijo = re.match(r'^(\d[\d\.]*)', seccion.strip())
    if prefijo:
        p = prefijo.group(1).rstrip('.')
        for k, items in SECCION_ITEMS_MAP.items():
            m2 = re.match(r'^(\d[\d\.]*)', k.strip())
            if m2 and m2.group(1).rstrip('.') == p:
                return len(items) * 3
    return 0


# ── Métricas superiores ───────────────────────────────────────────────────────

def _render_metricas_finales(n_iter: int, max_iter: int, pts, pts_max: int, rubrica, puntaje_inicial) -> None:
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Iteraciones automáticas", f"{n_iter}/{max_iter}")

    if puntaje_inicial is not None and pts_max and pts_max > 0:
        mc2.metric("Puntaje UPAO Inicial", badge_puntaje(int(puntaje_inicial), pts_max))
    else:
        mc2.metric("Puntaje UPAO Inicial", "—")

    if pts is not None and pts_max and pts_max > 0:
        mc3.metric("Puntaje UPAO Sugerido", badge_puntaje(int(pts), pts_max))
    else:
        mc3.metric("Puntaje UPAO Sugerido", "—")


# ── Tab 1: Evaluación ─────────────────────────────────────────────────────────

def _render_tab_evaluacion(v: dict, seccion: str, rubrica, pts, pts_max: int) -> None:
    pts_ratio = (float(pts) / float(pts_max)) if (pts and pts_max and float(pts_max) > 0) else 0.0

    # Texto aprobado
    texto_iterado = v.get("texto_iterado") or ""
    texto_final = texto_iterado if texto_iterado.strip() else (v.get("contexto_recuperado") or "")
    n_iter = v.get("numero_iteracion", 0)

    st.subheader(f"Texto Final — {seccion}")
    if texto_final:
        if texto_iterado.strip():
            if n_iter > 0:
                st.caption("Texto generado por el Redactor automático.")
            else:
                st.caption("Contexto original del PDF (el Redactor no fue necesario).")
        else:
            st.caption(f"📄 Texto original — aprobado sin modificaciones (Puntaje: {int(float(pts)) if pts else '?'}/{pts_max})")
        st.code(texto_final, language=None, wrap_lines=True)
        st.caption("Usa el ícono de copia para exportar el texto.")
        if "[COMPLETAR:" in texto_final:
            st.warning(
                "El texto contiene `[COMPLETAR: …]`. "
                "El estudiante debe completar esas secciones con contenido real."
            )
    else:
        st.info(
            "El texto fue evaluado en la primera pasada sin reescritura automática. "
            "El contexto recuperado del PDF fue evaluado directamente."
        )

    st.divider()

    # ── Recomendaciones de Pulido (Subagente 3 - Redactor) ────────────────────
    sug_mejoras = v.get("redactor_sugerencias_mejoras")
    if sug_mejoras and sug_mejoras.strip():
        st.subheader("💡 Recomendaciones de Pulido (Subagente 3 - Redactor)")
        st.info(sug_mejoras)
        st.divider()

    # ── Rúbrica UPAO Evaluada del Texto de Entrada (Original) ─────────────────
    eval_upao_inicial = v.get("evaluacion_upao_inicial")
    if eval_upao_inicial:
        st.subheader("📋 Rúbrica UPAO Evaluada del Texto de Entrada (Original)")
        from backend.config import RUBRICA_ITEMS_UPAO
        tabla_markdown = [
            "| Ítem ID | Criterio de la Rúbrica UPAO | Puntaje | Observación del Evaluador |",
            "| :--- | :--- | :--- | :--- |"
        ]
        for it in eval_upao_inicial:
            num = it.get("item_numero")
            desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
            pts_ob = it.get("puntaje", 0)
            tabla_markdown.append(
                f"| **{num:02d}** | {desc} | **{pts_ob}/3** | {it.get('observacion', '')} |"
            )
        st.markdown("\n".join(tabla_markdown))
        st.divider()

    # ── Rúbrica UPAO Evaluada del Texto Sugerido / Final ──────────────────────
    eval_upao_final = v.get("evaluacion_upao_final")
    if eval_upao_final and n_iter > 0:
        st.subheader("📋 Rúbrica UPAO Evaluada del Texto Sugerido / Final")
        from backend.config import RUBRICA_ITEMS_UPAO
        tabla_markdown_final = [
            "| Ítem ID | Criterio de la Rúbrica UPAO | Puntaje | Observación del Evaluador |",
            "| :--- | :--- | :--- | :--- |"
        ]
        for it in eval_upao_final:
            num = it.get("item_numero")
            desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
            pts_ob = it.get("puntaje", 0)
            tabla_markdown_final.append(
                f"| **{num:02d}** | {desc} | **{pts_ob}/3** | {it.get('observacion', '')} |"
            )
        st.markdown("\n".join(tabla_markdown_final))
        st.divider()


    # Feedback del auditor
    st.subheader("Feedback del Auditor")
    feedback = v.get("feedback_auditor", "—")
    st.info(feedback)

    # Qué haría el Redactor (si hubiera iterado)
    with st.expander("💡 ¿Qué recomendaría el Redactor?", expanded=False):
        errores = v.get("errores_rubrica", [])
        if errores:
            st.markdown("El Redactor aplicaría las siguientes correcciones:")
            for err in errores:
                st.markdown(
                    f"- **Ítem {err['item_numero']:02d}** "
                    f"(puntaje actual={err['puntaje_actual']}): {err['descripcion']}"
                )
        elif pts_ratio < 0.50:
            st.warning(
                "El puntaje es bajo pero el panel de auditores no alcanzó consenso sobre "
                "errores específicos. Revisa el **Feedback del Auditor** y las "
                "**Recomendaciones generales** para orientación de mejora."
            )
        else:
            st.success("No se detectaron observaciones de mejora bloqueantes en la rúbrica.")

    st.divider()

    # Observaciones restantes
    errores_finales = v.get("errores_rubrica", [])
    if errores_finales:
        _render_observaciones(errores_finales, rubrica)
    elif pts_ratio < 0.50:
        st.warning(
            f"Puntaje final: **{int(float(pts)) if pts else '?'}/{pts_max}**. "
            "No se consolidaron errores específicos con consenso del panel, pero el texto "
            "requiere mejoras significativas. Consulta el feedback del Auditor y el Metodólogo."
        )
    else:
        tipo = "la rúbrica personalizada" if rubrica else "la rúbrica UPAO"
        st.success(f"El texto cumple todos los ítems evaluados de {tipo}.")

    st.divider()

    # Recomendaciones generales (siempre visibles)
    st.subheader("Recomendaciones generales")
    _render_recomendaciones(v, pts, pts_max)


def _render_observaciones(errores: list, rubrica) -> None:
    st.subheader(f"Observaciones ({len(errores)} ítems, no bloqueantes)")
    if rubrica:
        secciones_rubrica = rubrica.get("secciones", {})
        item_a_seccion = {
            n: sec
            for sec, nums in secciones_rubrica.items()
            for n in nums
        }
        errores_por_seccion: dict = {}
        for err in errores:
            sec = item_a_seccion.get(err["item_numero"], "General")
            errores_por_seccion.setdefault(sec, []).append(err)
        for sec_nombre, errs in errores_por_seccion.items():
            st.markdown(f"**{sec_nombre}**")
            for err in errs:
                st.markdown(
                    f"- Ítem **{err['item_numero']:02d}** "
                    f"(puntaje={err['puntaje_actual']}): {err['descripcion']}"
                )
    else:
        for err in errores:
            st.markdown(
                f"- Ítem **{err['item_numero']:02d}** "
                f"(puntaje={err['puntaje_actual']}): {err['descripcion']}"
            )


def _render_recomendaciones(v: dict, pts, pts_max: int) -> None:
    obs_met = v.get("observaciones_metodologicas", "")
    if obs_met:
        st.markdown(obs_met)
    else:
        if pts and pts_max and pts_max > 0 and (pts / pts_max) >= 0.8:
            st.markdown(
                "**El texto tiene un nivel alto.** Considera estos aspectos para perfeccionarlo:\n"
                "- Verifica que cada objetivo específico comience con un verbo en infinitivo "
                "(establecer, determinar, analizar…)\n"
                "- Asegúrate de que la numeración de los objetivos sea correlativa con las "
                "hipótesis y variables\n"
                "- Revisa que el alcance temporal y espacial esté explicitado"
            )
        else:
            st.markdown(
                "**Áreas de mejora detectadas:**\n"
                "- Revisa la alineación entre el objetivo general y los específicos\n"
                "- Comprueba que cada objetivo sea medible y alcanzable\n"
                "- Verifica la coherencia con el problema de investigación planteado"
            )


# ── Tab 2: Debate ─────────────────────────────────────────────────────────────

_ICONOS_SUBAGENTE = {
    "perspectiva_formal":       "🏛️",
    "perspectiva_metodologica": "🔬",
    "perspectiva_contextual":   "🌎",
    "sintetizador_debate":      "⚖️",
}

_COLORES_SUBAGENTE = {
    "perspectiva_formal":       "info",
    "perspectiva_metodologica": "warning",
    "perspectiva_contextual":   "info",
    "sintetizador_debate":      "success",
}


def _render_panel_debate(panel: list, veredicto: dict, idx: int) -> None:
    """Renderiza una sesión de debate del panel de 4 subagentes."""
    vered_gen   = veredicto.get("veredicto_general", "—")
    confirmados = veredicto.get("items_confirmados", [])
    descartados = veredicto.get("items_descartados", [])
    matizados   = veredicto.get("items_matizados", [])

    etiqueta = f"Sesión {idx} — Veredicto: {vered_gen} | ✓ {confirmados} | ✗ {descartados} | ~ {matizados}"
    with st.expander(etiqueta, expanded=(idx == 1)):
        justificacion = veredicto.get("justificacion", "")
        if justificacion:
            st.markdown(f"**Justificación del sintetizador:** {justificacion}")
            st.divider()

        for item in panel:
            nombre   = item.get("subagente", "desconocido")
            contenido = item.get("contenido", "—")
            icono    = _ICONOS_SUBAGENTE.get(nombre, "💬")
            color    = _COLORES_SUBAGENTE.get(nombre, "info")

            st.markdown(f"**{icono} {nombre.replace('_', ' ').title()}**")
            if color == "info":
                st.info(contenido)
            elif color == "warning":
                st.warning(contenido)
            elif color == "success":
                st.success(contenido)
            else:
                st.markdown(contenido)


def _render_tab_debate(v: dict) -> None:
    historial = v.get("historial_debate", [])

    if not historial:
        # Fallback: leer directamente debate_memory si historial vacío
        debate_memory = v.get("debate_memory", [])
        if debate_memory:
            _render_panel_debate(debate_memory, v.get("debate_veredicto", {}), idx=1)
        else:
            st.info("No se realizaron sesiones de debate en esta evaluación.")
    else:
        st.subheader(f"Historial de Debate ({len(historial)} sesión(es))")
        for idx, entrada in enumerate(historial, 1):
            if not isinstance(entrada, dict):
                continue
            if entrada.get("tipo") == "panel":
                _render_panel_debate(
                    panel=entrada.get("panel", []),
                    veredicto=entrada.get("veredicto", {}),
                    idx=idx,
                )
            else:
                # Formato anterior (compatibilidad)
                n           = entrada.get("ronda", idx)
                confirmados = entrada.get("items_confirmados", [])
                descartados = entrada.get("items_descartados", [])
                with st.expander(
                    f"Ronda {n} — Confirmados: {confirmados} | Descartados: {descartados}",
                    expanded=(idx == 1),
                ):
                    st.markdown("**Auditor:**")
                    st.info(entrada.get("argumento_auditor", "—"))
                    st.markdown("**Metodólogo:**")
                    st.warning(entrada.get("respuesta_metodologico", "—"))

    st.divider()

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("Consenso")
        if v.get("resultado_consenso"):
            st.markdown(v["resultado_consenso"])
        else:
            st.caption("Sin análisis de consenso disponible.")

    with col_d:
        st.subheader("Disenso")
        if v.get("resultado_disenso"):
            st.markdown(v["resultado_disenso"])
        else:
            st.caption("Sin análisis de disenso disponible.")


# ── Tab 3: Contexto RAG ───────────────────────────────────────────────────────

def _render_tab_rag(v: dict) -> None:
    st.subheader("Fragmentos recuperados")

    ctx_pdf  = v.get("contexto_recuperado", "")
    ctx_libs = v.get("contexto_teorico", "")
    ctx_deps = v.get("contexto_dependencias", "")

    rag_tabs = st.tabs(["📄 Del PDF de tesis", "📚 De libros de referencia", "🔗 Contexto cruzado"])

    with rag_tabs[0]:
        if ctx_pdf and ctx_pdf.strip():
            st.caption("Fragmentos recuperados del PDF del estudiante para la sección evaluada.")
            # Separar fragmentos por el delimitador "---"
            fragmentos = [f.strip() for f in ctx_pdf.split("---") if f.strip()]
            for i, frag in enumerate(fragmentos, 1):
                with st.expander(f"Fragmento {i}", expanded=(i == 1)):
                    st.code(frag, language=None, wrap_lines=True)
        else:
            st.info("No se recuperaron fragmentos del PDF para esta sección.")

    with rag_tabs[1]:
        if ctx_libs and ctx_libs.strip():
            st.caption("Fragmentos de libros de referencia metodológica.")
            fragmentos_lib = [f.strip() for f in ctx_libs.split("---") if f.strip()]
            for i, frag in enumerate(fragmentos_lib, 1):
                with st.expander(f"Referencia {i}", expanded=(i == 1)):
                    st.code(frag, language=None, wrap_lines=True)
        else:
            st.info("No se recuperaron fragmentos de libros de referencia.")

    with rag_tabs[2]:
        if ctx_deps and ctx_deps.strip():
            st.caption("Fragmentos de otras secciones del proyecto (contexto cruzado para coherencia).")
            fragmentos_dep = [f.strip() for f in ctx_deps.split("---") if f.strip()]
            for i, frag in enumerate(fragmentos_dep, 1):
                with st.expander(f"Sección relacionada {i}", expanded=(i == 1)):
                    st.markdown(frag)
        else:
            st.info("No se recuperó contexto cruzado de otras secciones.")


# ── Tab 4: Reportes ───────────────────────────────────────────────────────────

def _render_tab_reportes(v: dict) -> None:
    _render_reportes_descarga(v)


def _render_reportes_descarga(v: dict) -> None:
    st.subheader("Reportes del Ciclo Multiagente")
    rutas = v.get("rutas_reportes") or []

    if not rutas:
        st.info(
            "Los reportes se generan al finalizar el análisis. "
            "Si ves este mensaje tras la evaluación, reinicia el análisis — "
            "puede haberse interrumpido por límite de API."
        )
        return

    # Clasificar archivos por nombre de base
    ruta_run    = next((r for r in rutas if r and os.path.basename(r).startswith("run_") and r.endswith(".json")), None)
    ruta_eval   = next((r for r in rutas if r and os.path.basename(r).startswith("eval_") and r.endswith(".json")), None)
    ruta_debate = next((r for r in rutas if r and r.endswith(".md")), None)

    # ── Métricas NLP (solo si existe el eval JSON con clave "metricas") ────────
    if ruta_eval and os.path.isfile(ruta_eval):
        try:
            with open(ruta_eval, encoding="utf-8") as f:
                datos = json.load(f)
            metricas = datos.get("metricas", {})
            if metricas:
                st.markdown("### 📊 Métricas de Proceso y Calidad (Rúbrica Especializada)")
                
                # Renderizar métricas principales en columnas
                col1, col2, col3, col4 = st.columns(4)
                
                # 1. LLM-as-Judge
                llm_score = metricas.get("llm_judge_score", 0.0)
                llm_max = metricas.get("llm_judge_max", 0.0)
                col1.metric("LLM-as-Judge (G-Eval)", f"{llm_score} / {llm_max}")
                
                # 2. Gain Score
                gain_val = metricas.get("gain_score", 0.0)
                col2.metric("Gain Score (Hake)", f"{gain_val:+.4f}", help=f"Pre: {metricas.get('gain_score_pre', 0.0)} → Post: {metricas.get('gain_score_post', 0.0)}\nInterpretación: {metricas.get('gain_score_interpretacion', '')}")
                
                # 3. Cosine Similarity
                sim_cos = metricas.get("similitud_coseno", 0.0)
                col3.metric("Similitud Coseno (e5)", f"{sim_cos:.4f}", help=metricas.get("similitud_coseno_interpretacion", ""))
                
                # 4. Context Precision
                ctx_prec = metricas.get("context_precision", 0.0)
                col4.metric("Context Precision", f"{ctx_prec:.4f}", help=metricas.get("context_precision_interpretacion", ""))
                
                # 5. Iterative Consistency (Trajectory)
                if metricas.get("iterative_consistency_has_iter"):
                    trajectory = metricas.get("iterative_consistency", [])
                    st.markdown("#### 📈 Iterative Consistency (Trayectoria del Juez Externo)")
                    trajectory_str = " ➔ ".join(f"**{s}**" for s in trajectory)
                    st.info(f"Trayectoria de puntuaciones del Juez Externo: {trajectory_str}")
                
                st.divider()
                
                # Mostrar los detalles del Juez LLM
                st.markdown("### 📋 Evaluación Detallada del Juez LLM (G-Eval)")
                secciones_sel = metricas.get("llm_judge_secciones", [])
                if secciones_sel:
                    st.markdown(f"**Secciones de la Rúbrica Seleccionadas:** {', '.join(secciones_sel)}")
                    
                items_eval = metricas.get("llm_judge_items", [])
                if items_eval:
                    tabla_markdown = [
                        "| Ítem | Criterio de la Rúbrica | Puntaje | Justificación Académica |",
                        "| :--- | :--- | :--- | :--- |"
                    ]
                    for it in items_eval:
                        pts_ob = it.get("pts_obtenido", 0.0)
                        pts_mx = it.get("pts_max", 0.0)
                        tabla_markdown.append(
                            f"| **{it.get('item_id', '?')}** | {it.get('descripcion', '')} | **{pts_ob}/{pts_mx}** | {it.get('razon', '')} |"
                        )
                    st.markdown("\n".join(tabla_markdown))
                
                st.divider()
        except Exception as exc:
            st.error(f"Error cargando métricas: {exc}")

    # ── Botones de descarga (siempre que los archivos existan) ────────────────
    st.markdown("#### Descargar Reportes")

    col_d1, col_d2, col_d3 = st.columns(3)

    # Estado del ciclo (run JSON — siempre generado)
    if ruta_run and os.path.isfile(ruta_run):
        with open(ruta_run, encoding="utf-8") as f:
            contenido_run = f.read()
        col_d1.download_button(
            label="📥 Estado del ciclo (.json)",
            data=contenido_run,
            file_name=os.path.basename(ruta_run),
            mime="application/json",
            use_container_width=True,
        )

    # Transcripción del debate (MD — siempre generado)
    if ruta_debate and os.path.isfile(ruta_debate):
        with open(ruta_debate, encoding="utf-8") as f:
            contenido_md = f.read()
        col_d2.download_button(
            label="📝 Transcripción debate (.md)",
            data=contenido_md,
            file_name=os.path.basename(ruta_debate),
            mime="text/markdown",
            use_container_width=True,
        )

    # Métricas (eval JSON)
    if ruta_eval and os.path.isfile(ruta_eval):
        with open(ruta_eval, encoding="utf-8") as f:
            contenido_eval = f.read()
        col_d3.download_button(
            label="📊 Métricas Académicas (.json)",
            data=contenido_eval,
            file_name=os.path.basename(ruta_eval),
            mime="application/json",
            use_container_width=True,
        )
    else:
        col_d3.caption("Métricas no disponibles para esta sesión.")


def _render_metricas_nlp(run_id: str) -> None:
    if not run_id:
        st.caption("Métricas no disponibles para esta sesión.")
        return
    ruta = f"./outputs/run_{run_id}.json"
    if not os.path.isfile(ruta):
        st.caption("Métricas no disponibles para esta sesión.")
        return
    try:
        from evaluator.evaluator import evaluar_desde_archivo
        resultado = evaluar_desde_archivo(ruta)
        m = resultado.get("metricas", {})
        st.subheader("Métricas de Proceso y Calidad")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("LLM-as-Judge (G-Eval)", f"{m.get('llm_judge_score', 0)} / {m.get('llm_judge_max', 0)}")
        col2.metric("Gain Score", f"{m.get('gain_score', 0):.4f}")
        col3.metric("Similitud Coseno (e5)", f"{m.get('similitud_coseno', 0):.4f}")
        col4.metric("Context Precision", f"{m.get('context_precision', 0):.4f}")
    except Exception:
        st.caption("Métricas no disponibles para esta sesión.")


# ── Botones finales ───────────────────────────────────────────────────────────

def _render_botones_finales() -> None:
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Evaluar otra sección (mismo PDF)", use_container_width=True):
            reset_solo_grafo()
            st.rerun()
    with col_b2:
        if st.button("Nueva evaluación (nuevo PDF)", type="primary", use_container_width=True):
            reset_todo()
            st.rerun()
