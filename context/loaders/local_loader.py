import unicodedata
from pathlib import Path

import yaml


def _normalizar(texto: str) -> str:
    """Quita acentos y pasa a minúsculas para comparación de nombres de archivo."""
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def cargar_local(key: str) -> dict:
    """
    Lee una rúbrica YAML desde ./rubrics/{key}.yaml.
    Intenta con el key exacto, luego con key sin acentos, luego búsqueda por prefijo.
    """
    base = Path("./rubrics")

    # Intento 1: coincidencia exacta
    ruta = base / f"{key}.yaml"
    if ruta.exists():
        with open(ruta, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Intento 2: key sin acentos
    key_sin_acentos = _normalizar(key)
    ruta2 = base / f"{key_sin_acentos}.yaml"
    if ruta2.exists():
        with open(ruta2, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Intento 3: buscar por prefijo (primera palabra del key)
    prefijo = key.split("_")[0]
    candidatos = list(base.glob(f"*{prefijo}*.yaml"))
    if not candidatos:
        # Fallback: prefijo sin acentos
        candidatos = list(base.glob(f"*{_normalizar(prefijo)}*.yaml"))
    if not candidatos:
        raise FileNotFoundError(
            f"No se encontró rúbrica para '{key}' en {base.resolve()}"
        )
    with open(candidatos[0], "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
