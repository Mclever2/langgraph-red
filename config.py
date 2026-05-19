"""
Configuración global Cloud-ready para el sistema LangGraph.

Lee todas las variables desde el entorno (.env o variables del sistema).
Usado por los nodos del grafo y por la API FastAPI.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── API Keys Groq en rotación (un LLM por agente → rate limits distribuidos) ─
    GROQ_KEYS: list[str] = [
        v for k, v in sorted(os.environ.items())
        if k.startswith("GROQ_API_KEY") and v
    ]

    # ── Storage ───────────────────────────────────────────────────────────────
    GCS_BUCKET_NAME: str | None = os.environ.get("GCS_BUCKET_NAME")
    CONTEXT_SOURCE: str = os.environ.get("CONTEXT_SOURCE", "local")
    GDRIVE_RUBRIC_MAP: str = os.environ.get("GDRIVE_RUBRIC_MAP", "{}")

    # ── Parámetros del flujo ──────────────────────────────────────────────────
    MAX_ITERATIONS: int = int(os.environ.get("MAX_ITERATIONS", 3))
    MAX_DEBATE_ROUNDS: int = int(os.environ.get("MAX_DEBATE_ROUNDS", 2))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def get_next_groq_key(cls, index: int = 0) -> str:
        if not cls.GROQ_KEYS:
            raise EnvironmentError(
                "No hay GROQ_API_KEY_* configuradas. "
                "Agrega al menos una en el archivo .env o como variable de entorno."
            )
        return cls.GROQ_KEYS[index % len(cls.GROQ_KEYS)]
