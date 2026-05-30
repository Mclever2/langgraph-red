"""
API FastAPI — punto de entrada para Cloud Run.

Endpoints:
  POST /evaluar  — recibe PDF + parámetros institucionales, devuelve métricas
  GET  /health   — health check para Cloud Run
"""

import uuid
import logging

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="LangGraph Thesis Evaluator API",
    description="Evaluación automática de tesis mediante sistema multiagente LangGraph.",
    version="1.0.0",
)


def _extraer_texto_pdf(contenido: bytes, seccion: str) -> str:
    """Extrae texto del PDF usando pdfplumber (ya instalado en el proyecto)."""
    import io
    import pdfplumber

    texto_completo = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text()
            if t:
                texto_completo.append(t)
    return "\n\n".join(texto_completo)


def _ejecutar_grafo(estado_inicial: dict) -> dict:
    """Compila el grafo LangGraph y lo ejecuta con el estado inicial."""
    from backend.graph.workflow import create_graph, get_run_config

    graph = create_graph()
    run_config = get_run_config(thread_id=estado_inicial["run_id"])
    estado_final = graph.invoke(estado_inicial, config=run_config)
    return estado_final


@app.post("/evaluar")
async def evaluar_tesis(
    archivo_pdf: UploadFile = File(...),
    universidad: str = Form(...),
    programa: str = Form(...),
    seccion: str = Form(..., description="Nombre de la sección a evaluar"),
    modalidad: str = Form(default="tesis"),
):
    """
    Recibe un PDF y parámetros institucionales.
    Ejecuta el flujo LangGraph completo y retorna métricas NLP.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"[API] Nueva evaluación run_id={run_id} | {universidad} | {programa} | {seccion}")

    try:
        contenido_pdf = await archivo_pdf.read()
        texto_seccion = _extraer_texto_pdf(contenido_pdf, seccion)

        from config import Config

        estado_inicial = {
            "run_id":                   run_id,
            "universidad":              universidad,
            "programa":                 programa,
            "modalidad":                modalidad,
            "seccion_objetivo":         seccion,
            "contexto_recuperado":      texto_seccion,
            "contexto_dependencias":    "",
            "contexto_teorico":         "",
            "rubrica_dinamica":         None,
            "max_iteraciones":          Config.MAX_ITERATIONS,
            "plan_supervisor":          "",
            "texto_iterado":            "",
            "numero_iteracion":         0,
            "feedback_auditor":         "",
            "errores_rubrica":          [],
            "puntaje_estimado":         None,
            "puntaje_inicial":          0.0,
            "observaciones_metodologicas": "",
            "resultado_consenso":       "",
            "resultado_disenso":        "",
            "iter_consenso":            0,
            "iter_disenso":             0,
            "debate_memory":            [],
            "debate_veredicto":         None,
            "debate_completado":        False,
            "historial_debate":         [],
            "siguiente_nodo":           "",
            "instrucciones_supervisor": "",
            "pasos_ejecutados":         0,
            "max_pasos_red":            Config.get_max_pasos(Config.MAX_ITERATIONS),
            "consenso_ejecutado":       False,
            "disenso_ejecutado":        False,
            "auditor_ejecutado":        False,
            "metodologo_ejecutado":     False,
            "debate_ejecutado":         False,
            "iter_auditada":            0,
            "iter_metodologica":        0,
            "_puntaje_max":             None,
            "consenso_matematico":      {},
            "scores_subagentes":        [],
            "consenso_matematico_auditor": {},
        }

        estado_final = _ejecutar_grafo(estado_inicial)

        ruta_json = f"./outputs/run_{run_id}.json"

        from evaluator.evaluator import evaluar_desde_archivo
        metricas = evaluar_desde_archivo(ruta_json)

        return JSONResponse(content={
            "run_id":            run_id,
            "texto_mejorado":    estado_final.get("texto_iterado"),
            "puntaje_final":     estado_final.get("puntaje_estimado"),
            "metricas":          metricas["metricas"],
            "resultado_consenso": estado_final.get("resultado_consenso"),
        })

    except Exception as exc:
        logger.exception(f"[API] Error en run_id={run_id}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health():
    return {"status": "ok"}
