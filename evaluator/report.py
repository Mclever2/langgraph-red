"""Genera un reporte Markdown legible a partir del JSON de métricas del evaluador."""

import json
from pathlib import Path


def generar_reporte(ruta_eval_json: str) -> str:
    """Lee eval_{run_id}.json y devuelve un string Markdown."""
    with open(ruta_eval_json, "r", encoding="utf-8") as f:
        datos = json.load(f)

    metricas = datos.get("metricas", {})
    run_id = datos.get("run_id", "?")
    universidad = datos.get("universidad", "?")

    lineas = [
        f"# Reporte de Evaluación — {run_id}",
        f"",
        f"**Universidad:** {universidad}  ",
        f"**Arquitectura:** {datos.get('arquitectura', '?')}  ",
        f"",
        f"## Métricas de Calidad",
        f"",
        f"| Métrica | Valor | Interpretación |",
        f"|---------|-------|----------------|",
        f"| ROUGE-1 F | {metricas.get('rouge1_f', 'N/A')} | Solapamiento de unigramas |",
        f"| ROUGE-2 F | {metricas.get('rouge2_f', 'N/A')} | Solapamiento de bigramas |",
        f"| ROUGE-L F | {metricas.get('rougeL_f', 'N/A')} | Subsecuencia común más larga |",
        f"| BLEU | {metricas.get('bleu_score', 'N/A')} | Precisión n-gram ponderada |",
        f"| Similitud coseno | {metricas.get('similitud_coseno', 'N/A')} | {metricas.get('interpretacion', '')} |",
        f"| Cohen's Kappa | {metricas.get('kappa', 'N/A')} | {metricas.get('interpretacion', '')} |",
        f"| Gain Score | {metricas.get('gain_score', 'N/A')} | {metricas.get('interpretacion', '')} |",
        f"",
    ]

    if metricas.get("puntaje_inicial") is not None:
        lineas += [
            f"**Puntaje inicial:** {metricas['puntaje_inicial']}  ",
            f"**Puntaje final:** {metricas['puntaje_final']}  ",
            f"",
        ]

    return "\n".join(lineas)


def guardar_reporte(ruta_eval_json: str, ruta_salida: str | None = None) -> str:
    md = generar_reporte(ruta_eval_json)
    if ruta_salida is None:
        ruta_salida = ruta_eval_json.replace(".json", "_reporte.md")
    Path(ruta_salida).write_text(md, encoding="utf-8")
    return ruta_salida
