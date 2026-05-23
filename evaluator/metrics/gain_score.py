def calcular_gain_score(
    puntaje_inicial: float,
    puntaje_final: float,
    puntaje_maximo: float = 0.0,
) -> dict:
    """
    Gain Score normalizado: mejora relativa al máximo posible.
    Fórmula: (puntaje_final - puntaje_inicial) / (puntaje_maximo - puntaje_inicial)
    """
    if puntaje_maximo <= 0:
        return {"gain_score": None, "nota": "puntaje máximo no disponible"}
    if puntaje_maximo == puntaje_inicial:
        return {"gain_score": 1.0, "nota": "puntaje inicial ya era máximo"}

    gain = (puntaje_final - puntaje_inicial) / (puntaje_maximo - puntaje_inicial)
    gain = max(0.0, min(1.0, gain))
    return {
        "gain_score": round(gain, 4),
        "puntaje_inicial": puntaje_inicial,
        "puntaje_final": puntaje_final,
        "interpretacion": (
            "mejora alta" if gain > 0.6
            else "mejora moderada" if gain > 0.3
            else "mejora baja o sin mejora"
        ),
    }
