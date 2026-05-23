"""
Evaluador determinístico — lee el JSON del exportador y calcula métricas NLP.

No importa nada de LangGraph. Puede ejecutarse de forma independiente:
  python -m evaluator.evaluator ./outputs/run_<uuid>.json
"""

import json
import sys
from pathlib import Path

from .metrics.rouge_bleu import calcular_rouge, calcular_bleu
from .metrics.cosine_sim import calcular_similitud_coseno
from .metrics.kappa import calcular_kappa
from .metrics.gain_score import calcular_gain_score


def evaluar_desde_archivo(ruta_json: str) -> dict:
    with open(ruta_json, "r", encoding="utf-8") as f:
        datos = json.load(f)
    return evaluar(datos)


def evaluar(datos: dict) -> dict:
    texto_inicial = datos.get("texto_inicial", "")
    texto_final = datos.get("texto_final", "")
    puntaje_final = float(datos.get("puntaje_final") or 0.0)
    puntaje_inicial = float(datos.get("puntaje_inicial") or 0.0)
    puntaje_maximo = float(datos.get("puntaje_maximo") or 0.0)
    historial_debate = datos.get("historial_debate", [])

    resultado = {
        "run_id": datos.get("run_id"),
        "arquitectura": datos.get("arquitectura"),
        "universidad": datos.get("universidad"),
        "metricas": {
            **calcular_rouge(texto_inicial, texto_final),
            **calcular_bleu(texto_inicial, texto_final),
            **calcular_similitud_coseno(texto_inicial, texto_final),
            **calcular_kappa(historial_debate),
            **calcular_gain_score(puntaje_inicial, puntaje_final, puntaje_maximo),
        },
    }

    ruta_salida = Path("./outputs") / f"eval_{datos.get('run_id', 'sin_id')}.json"
    ruta_salida.parent.mkdir(exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    return resultado


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m evaluator.evaluator <ruta_json>")
        sys.exit(1)
    resultado = evaluar_desde_archivo(sys.argv[1])
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
