"""
Nodo Exportador — Serializa el MentoriaState final a JSON y lo persiste.

Corre una sola vez, justo antes de END. No usa LLM.
Guarda localmente en ./outputs/run_{run_id}.json.
Si GCS_BUCKET_NAME está definido, también sube a Google Cloud Storage.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..state import MentoriaState

logger = logging.getLogger(__name__)

_OUTPUTS_DIR = Path("./outputs")


def _serializar_historial(historial: list) -> list[str]:
    """Convierte cada RondaDebate dict en un string legible."""
    turnos = []
    for ronda in historial:
        if isinstance(ronda, dict):
            n = ronda.get("ronda", "?")
            arg = ronda.get("argumento_auditor", "")
            resp = ronda.get("respuesta_metodologico", "")
            if arg:
                turnos.append(f"[Ronda {n} — Auditor] {arg}")
            if resp:
                turnos.append(f"[Ronda {n} — Metodólogo] {resp}")
        else:
            turnos.append(str(ronda))
    return turnos


def _subir_a_gcs(ruta_local: Path, blob_name: str) -> None:
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        return
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(ruta_local))
        logger.info(f"[Exportador] Subido a GCS: gs://{bucket_name}/{blob_name}")
    except Exception as exc:
        logger.warning(f"[Exportador] No se pudo subir a GCS ({blob_name}): {exc}")


def make_nodo_exportador():
    """Fábrica del Nodo Exportador. No recibe LLM."""

    def nodo_exportador(state: MentoriaState) -> dict:
        run_id = state.get("run_id") or "sin_id"
        logger.info(f"[Exportador] Serializando estado — run_id={run_id}")

        historial_raw = state.get("historial_debate") or []
        errores_raw = state.get("errores_rubrica") or []

        payload = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "universidad": state.get("universidad", ""),
            "programa": state.get("programa", ""),
            "arquitectura": "langgraph-hub-spoke",
            "texto_inicial": state.get("contexto_recuperado", ""),
            "texto_final": state.get("texto_iterado", ""),
            "puntaje_inicial": state.get("puntaje_inicial", 0.0),
            "puntaje_final": state.get("puntaje_estimado"),
            "iteraciones_realizadas": state.get("numero_iteracion", 0),
            "historial_debate": _serializar_historial(historial_raw),
            "errores_detectados": [
                e.get("descripcion", str(e)) if isinstance(e, dict) else str(e)
                for e in errores_raw
            ],
            "resultado_consenso": state.get("resultado_consenso", ""),
            "resultado_disenso": state.get("resultado_disenso", ""),
            "metadata": {
                "max_iterations": state.get("max_iteraciones"),
                "max_debate_rounds": state.get("max_rondas_debate"),
                "modelo_llm": "llama-3.3-70b-versatile",
                "temperatura_auditor": 0.1,
                "temperatura_redactor": 0.4,
            },
        }

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        ruta = _OUTPUTS_DIR / f"run_{run_id}.json"
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"[Exportador] Guardado en {ruta}")

        # Generar métricas NLP y reporte Markdown
        try:
            from evaluator.evaluator import evaluar_desde_archivo
            from evaluator.report import guardar_reporte
            evaluar_desde_archivo(str(ruta))
            ruta_eval = _OUTPUTS_DIR / f"eval_{run_id}.json"
            ruta_reporte = guardar_reporte(str(ruta_eval))
            logger.info(f"[Exportador] Métricas en {ruta_eval} | Reporte en {ruta_reporte}")
        except Exception as exc:
            logger.warning(f"[Exportador] No se pudieron generar métricas/reporte: {exc}")
            ruta_eval = None
            ruta_reporte = None

        _subir_a_gcs(ruta, f"runs/run_{run_id}.json")
        if ruta_eval and ruta_eval.exists():
            _subir_a_gcs(ruta_eval, f"runs/eval_{run_id}.json")
        if ruta_reporte and Path(ruta_reporte).exists():
            _subir_a_gcs(Path(ruta_reporte), f"runs/eval_{run_id}_reporte.md")

        return {}

    return nodo_exportador
