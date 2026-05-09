"""
Configuración central del sistema de mentoría académica UPAO.

Contiene:
  - RUBRICA_ITEMS_UPAO: Los 33 ítems exactos de la ficha oficial de evaluación
  - SECCION_ITEMS_MAP:  Qué ítems evaluar según la sección elegida
  - SECCIONES_TESIS:    Opciones del menú + query de búsqueda para ChromaDB
  - LIBRARY_CHROMA_PATH / BOOKS_PRELOAD_DIR: Paths para la biblioteca de libros
"""

import os

# ── Paths de la biblioteca de libros ─────────────────────────────────────────
# ChromaDB persistente: sobrevive reinicios del servidor
_ROOT = os.path.dirname(os.path.dirname(__file__))   # raíz del proyecto
LIBRARY_CHROMA_PATH = os.path.join(_ROOT, "chroma_db", "biblioteca")
# Carpeta opcional para pre-cargar PDFs sin pasar por el frontend
BOOKS_PRELOAD_DIR   = os.path.join(_ROOT, "books")

# ── Rúbrica oficial UPAO — 33 ítems ──────────────────────────────────────────
# Fuente: "Ficha de evaluación de proyecto de tesis" - Facultad de Ingeniería UPAO
# Escala: 3=Excelente | 2=Bueno | 1=Regular | 0=Insuficiente
# Puntaje máximo: 99 pts → equivale a nota vigesimal 20

RUBRICA_ITEMS_UPAO: dict[int, str] = {
    # ── TÍTULO (01-03) ────────────────────────────────────────────────────────
    1:  "El título es claro, conciso y refleja fielmente el contenido y el propósito de la investigación.",
    2:  "El título articula las variables, espacio y tiempo de la investigación.",
    3:  "El estudio se enmarca en la línea de investigación que promueve el programa de estudios.",

    # ── PLANTEAMIENTO DEL PROBLEMA (04-10) ────────────────────────────────────
    4:  "El problema central del estudio describe con claridad la realidad social, económica, cultural, científica o tecnológica que motiva la investigación.",
    5:  "El problema central del estudio recoge el estado de la investigación (antecedentes) de las variables de estudio.",
    6:  "El objetivo general guarda relación con el problema.",
    7:  "Los objetivos específicos derivan del objetivo general.",
    8:  "Se explica por qué el estudio es relevante y qué aportaciones hará al campo de investigación.",
    9:  "El problema está claramente formulado.",
    10: "Se detalla la justificación de la investigación, precisando cómo contribuirá al conocimiento existente y su impacto potencial.",

    # ── MARCO TEÓRICO (11-17) ─────────────────────────────────────────────────
    11: "Los antecedentes guardan relación con el problema de investigación.",
    12: "Las bases teóricas / científicas proporcionan una base sólida con teorías, modelos y conceptos relevantes.",
    13: "La definición de términos básicos define claramente términos técnicos y específicos para evitar confusiones.",
    14: "Las citas textuales o de paráfrasis son concordantes con la naturaleza de las variables.",
    15: "Los textos y autores citados se encuentran en las referencias bibliográficas.",
    16: "Los autores asumen una postura crítica y no solo copian las ideas de los autores citados.",
    17: "Se citan a los autores conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",

    # ── HIPÓTESIS Y VARIABLES (18-21) ─────────────────────────────────────────
    18: "Las hipótesis guardan relación con el problema de investigación.",
    19: "Si hay hipótesis específicas, éstas derivan de problemas derivados.",
    20: "Es clara la definición operacional de las variables: dimensiones o indicadores.",
    21: "La matriz de consistencia asegura que todos los elementos del estudio están alineados.",

    # ── MARCO METODOLÓGICO (22-27) ────────────────────────────────────────────
    22: "El tipo de investigación y el método de investigación guardan relación con el problema de investigación.",
    23: "Se presenta el esquema (gráfico) del diseño de investigación.",
    24: "Define claramente la población y muestra de estudio. Si fuera el caso, se hace uso del cálculo estadístico para el tamaño y selección de la muestra.",
    25: "Describe los instrumentos de recolección de datos de manera detallada en correspondencia con el problema y diseño metodológico.",
    26: "Especifica el procedimiento de ejecución del estudio.",
    27: "Especifica las técnicas de procesamiento y análisis de datos apropiadas conforme al problema y naturaleza de las variables.",

    # ── ASPECTOS ADMINISTRATIVOS (28-31) ──────────────────────────────────────
    28: "El cronograma detalla todas las actividades y plazos para el desarrollo del proyecto.",
    29: "Se detallan claramente los recursos humanos y materiales para ejecutar el proyecto.",
    30: "El presupuesto estima los costos de los bienes y servicios requeridos para ejecutar el proyecto.",
    31: "Se precisa las fuentes de financiamiento para ejecutar el proyecto: propia y/o externas.",

    # ── REFERENCIAS BIBLIOGRÁFICAS (32-33) ────────────────────────────────────
    32: "Se encuentran incorporados todos los autores citados.",
    33: "La redacción de las referencias bibliográficas es conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
}

# Tabla de conversión de puntaje a nota vigesimal (UPAO oficial)
TABLA_VIGESIMAL: list[tuple[int, int, int]] = [
    # (puntaje_min, puntaje_max, nota)
    (96, 99, 20), (91, 95, 19), (86, 90, 18), (81, 85, 17),
    (76, 80, 16), (71, 75, 15), (66, 70, 14), (61, 65, 13),
    (56, 60, 12), (51, 55, 11), (46, 50, 10), (41, 45,  9),
    (36, 40,  8), (31, 35,  7), (26, 30,  6), (21, 25,  5),
    (0,  20,  0),
]


def puntaje_a_nota(puntaje: int) -> int:
    """Convierte puntaje 0-99 a nota vigesimal 0-20 según tabla UPAO."""
    for pmin, pmax, nota in TABLA_VIGESIMAL:
        if pmin <= puntaje <= pmax:
            return nota
    return 0


# ── Mapa sección → ítems de rúbrica relevantes ────────────────────────────────
SECCION_ITEMS_MAP: dict[str, list[int]] = {
    "1. Título del proyecto":                    [1, 2, 3],
    "1.1 Descripción y delimitación":            [4, 5],
    "1.1.2 Problema central (formulación)":      [4, 5, 9],
    "1.2 Objetivos (General y Específicos)":     [6, 7],
    "1.3 Importancia del estudio":               [8],
    "1.4 Justificación del estudio":             [10],
    "2.2 Investigaciones antecedentes":          [11, 15],
    "2.3 Base teórica (Variables)":              [12, 14, 16, 17],
    "2.4 Definición de términos básicos":        [13],
    "3.1–3.2 Hipótesis":                         [18, 19],
    "3.3 Variables (Operacionalización)":        [20],
    "3.4 Matriz de consistencia":                [21],
    "4.1–4.3 Tipo, Método y Diseño":             [22, 23],
    "4.4 Población y muestra":                   [24],
    "4.5 Instrumentos de recolección de datos":  [25],
    "4.6 Procedimiento de ejecución":            [26],
    "4.7 Análisis de datos":                     [27],
    "5. Aspectos administrativos":               [28, 29, 30, 31],
    "III. Referencias bibliográficas":           [32, 33],
}

# ── Secciones del menú con query de búsqueda semántica para ChromaDB ──────────
SECCIONES_TESIS: list[dict] = [
    {
        "nombre": "1. Título del proyecto",
        "query":  "título proyecto investigación variables espacio tiempo línea investigación",
    },
    {
        "nombre": "1.1 Descripción y delimitación",
        "query":  "descripción problema central delimitación realidad antecedentes variables",
    },
    {
        "nombre": "1.1.2 Problema central (formulación)",
        "query":  "formulación problema central estudio planteamiento pregunta investigación",
    },
    {
        "nombre": "1.2 Objetivos (General y Específicos)",
        "query":  "objetivo general específicos investigación derivan problema",
    },
    {
        "nombre": "1.3 Importancia del estudio",
        "query":  "importancia relevancia aportaciones campo investigación estudio",
    },
    {
        "nombre": "1.4 Justificación del estudio",
        "query":  "justificación teórica práctica metodológica social investigación",
    },
    {
        "nombre": "2.2 Investigaciones antecedentes",
        "query":  "antecedentes investigaciones previas estudios relacionados citados",
    },
    {
        "nombre": "2.3 Base teórica (Variables)",
        "query":  "base teórica científica modelos teorías conceptos citas paráfrasis",
    },
    {
        "nombre": "2.4 Definición de términos básicos",
        "query":  "definición términos básicos técnicos específicos glosario",
    },
    {
        "nombre": "3.1–3.2 Hipótesis",
        "query":  "hipótesis general específicas supuestos básicos problema relación",
    },
    {
        "nombre": "3.3 Variables (Operacionalización)",
        "query":  "variables definición operacional dimensiones indicadores ítems escala",
    },
    {
        "nombre": "3.4 Matriz de consistencia",
        "query":  "matriz de consistencia alineación elementos problema objetivo hipótesis variable",
    },
    {
        "nombre": "4.1–4.3 Tipo, Método y Diseño",
        "query":  "tipo investigación método diseño esquema gráfico investigación",
    },
    {
        "nombre": "4.4 Población y muestra",
        "query":  "población muestra estudio cálculo estadístico selección criterios",
    },
    {
        "nombre": "4.5 Instrumentos de recolección de datos",
        "query":  "instrumentos técnicas recolección datos correspondencia diseño",
    },
    {
        "nombre": "4.6 Procedimiento de ejecución",
        "query":  "procedimiento ejecución estudio pasos etapas actividades",
    },
    {
        "nombre": "4.7 Análisis de datos",
        "query":  "técnicas procesamiento análisis datos estadísticas naturaleza variables",
    },
    {
        "nombre": "5. Aspectos administrativos",
        "query":  "cronograma actividades recursos humanos materiales presupuesto financiamiento",
    },
    {
        "nombre": "III. Referencias bibliográficas",
        "query":  "referencias bibliográficas autores citados normas APA VANCOUVER HARVARD",
    },
]


def get_items_texto_para_seccion(seccion: str) -> str:
    """Genera la tabla de ítems relevantes para un sección, lista para inyectar en el prompt."""
    items_nums = SECCION_ITEMS_MAP.get(seccion, list(RUBRICA_ITEMS_UPAO.keys()))
    lineas = ["| N° | Ítem de la Rúbrica UPAO | Puntaje (0-3) |",
              "|----|-----------------------------|--------------|"]
    for num in items_nums:
        desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
        lineas.append(f"| {num:02d} | {desc} | ___ |")
    return "\n".join(lineas)


def get_puntaje_maximo_seccion(seccion: str) -> int:
    """Puntaje máximo posible para la sección (nro. de ítems × 3)."""
    return len(SECCION_ITEMS_MAP.get(seccion, [])) * 3


# ── Dependencias cruzadas entre secciones ────────────────────────────────────
# Cada sección necesita fragmentos RAG de estas otras secciones para evaluarse
# correctamente. El Título usa TODAS las secciones (coherencia global).
DEPENDENCIAS_SECCIONES: dict[str, list[str]] = {
    "1. Título del proyecto": [          # Título = coherencia global → TODAS
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
        "3.1–3.2 Hipótesis",
        "2.3 Base teórica (Variables)",
        "4.1–4.3 Tipo, Método y Diseño",
    ],
    "1.1 Descripción y delimitación": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
    ],
    "1.1.2 Problema central (formulación)": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
        "3.1–3.2 Hipótesis",
    ],
    "1.2 Objetivos (General y Específicos)": [
        "1.1.2 Problema central (formulación)",
        "3.1–3.2 Hipótesis",
        "3.3 Variables (Operacionalización)",
    ],
    "1.3 Importancia del estudio": [
        "1.1.2 Problema central (formulación)",
    ],
    "1.4 Justificación del estudio": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
    ],
    "2.2 Investigaciones antecedentes": [
        "1.1.2 Problema central (formulación)",
        "3.3 Variables (Operacionalización)",
    ],
    "2.3 Base teórica (Variables)": [
        "3.3 Variables (Operacionalización)",
        "1. Título del proyecto",
    ],
    "2.4 Definición de términos básicos": [
        "3.3 Variables (Operacionalización)",
        "2.3 Base teórica (Variables)",
    ],
    "3.1–3.2 Hipótesis": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
    ],
    "3.3 Variables (Operacionalización)": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
        "3.1–3.2 Hipótesis",
    ],
    "3.4 Matriz de consistencia": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.1–3.2 Hipótesis",
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
    ],
    "4.1–4.3 Tipo, Método y Diseño": [
        "1.1.2 Problema central (formulación)",
        "3.1–3.2 Hipótesis",
        "3.3 Variables (Operacionalización)",
    ],
    "4.4 Población y muestra": [
        "4.1–4.3 Tipo, Método y Diseño",
        "3.3 Variables (Operacionalización)",
    ],
    "4.5 Instrumentos de recolección de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
    ],
    "4.6 Procedimiento de ejecución": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
    ],
    "4.7 Análisis de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "3.1–3.2 Hipótesis",
    ],
    "5. Aspectos administrativos": [
        "1.2 Objetivos (General y Específicos)",
    ],
    "III. Referencias bibliográficas": [
        "2.2 Investigaciones antecedentes",
        "2.3 Base teórica (Variables)",
    ],
}

# ── Límites configurables por defecto ────────────────────────────────────────
MAX_ITERACIONES_DEFAULT  = 3   # Ciclos Redactor ↔ Agentes
MAX_RONDAS_DEBATE_DEFAULT = 2  # Rondas de debate por iteración
