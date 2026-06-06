import os
import logging
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

class ItemRubricaEvaluado(BaseModel):
    item_id: str = Field(description="ID del ítem en la rúbrica (ej. '4.1', '2.3')")
    descripcion: str = Field(description="Descripción del criterio de la rúbrica")
    pts_max: float = Field(description="Puntaje máximo asignable a este ítem")
    pts_obtenido: float = Field(description="Puntaje asignado (0, 50% de pts_max, o pts_max)")
    razon: str = Field(description="Explicación detallada de por qué se asignó esta calificación")

class EvaluacionSeccion(BaseModel):
    secciones_seleccionadas: List[str] = Field(description="Secciones de la rúbrica especializada seleccionadas")
    items: List[ItemRubricaEvaluado] = Field(description="Lista de ítems evaluados")
    puntaje_total: float = Field(description="Suma total de los puntajes obtenidos")
    puntaje_maximo: float = Field(description="Suma total de los puntajes máximos de los ítems seleccionados")

def cargar_rubrica_metodologica() -> str:
    """Lee el archivo rubrica.md de la carpeta del proyecto."""
    # Buscar rubrica.md
    for pos in ["rubrica.md", "../rubrica.md", "poc_langgraph_mentoria/rubrica.md"]:
        if os.path.isfile(pos):
            with open(pos, "r", encoding="utf-8") as f:
                return f.read()
    
    # Intento de path absoluto
    abs_path = r"c:\Users\Administrador\Downloads\langgraph-red\poc_langgraph_mentoria\rubrica.md"
    if os.path.isfile(abs_path):
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()
            
    return "Rúbrica metodológica no encontrada en el sistema."

_PROMPT_JUEZ_LLM = """
Eres un Juez Metodológico de tesis de Ingeniería (estilo G-Eval). Evaluador de alta precisión.
Tu tarea es evaluar la calidad metodológica de la sección de tesis del estudiante utilizando la RÚBRICA DE EVALUACIÓN DE CALIDAD METODOLÓGICA especializada adjunta.

REGLAS DE SELECCIÓN DE SECCIONES DE LA RÚBRICA:
1. Debes analizar la "Sección Objetivo de la Tesis" y el "Texto a Evaluar".
2. Selecciona ÚNICAMENTE las secciones y criterios de la rúbrica que son directamente aplicables a esa Sección Objetivo. 
   - Por ejemplo, si se evalúa "1.2 Objetivos (General y Específicos)", debes seleccionar únicamente la sección "4. Objetivos de la investigación".
   - Si se evalúa "3.3 Variables (Operacionalización)", selecciona únicamente "9. Variables y operacionalización".
   - Si es "Vista general del proyecto", puedes seleccionar varias secciones representativas (como Título, Problema, Objetivos, Hipótesis y Metodología).
   - De nada sirve evaluar ítems de "Referencias bibliográficas" si el estudiante está consultando "Formulación del problema". Sé lógico y selectivo.

RÚBRICA COMPLETA DE REFERENCIA:
{rubrica}

---

ENTRADAS A EVALUAR:
- Sección Objetivo de la Tesis: **{seccion_objetivo}**
- Texto a Evaluar:
{texto}

---

REGLAS DE CALIFICACIÓN POR ÍTEM:
- Para cada ítem aplicable en las secciones seleccionadas de la rúbrica, asigna:
  * Puntaje máximo (pts_max) si se cumple COMPLETAMENTE.
  * 50% de pts_max si se cumple PARCIALMENTE.
  * 0 si NO SE CUMPLE.
- Escribe una justificación académica clara para cada ítem en "razon".

Responde en formato estructurado de JSON.
"""

def _ejecutar_un_juez(
    model_name: str,
    temperature: float,
    seccion_objetivo: str,
    texto: str,
    rubrica_content: str,
    api_key: str
) -> Optional[EvaluacionSeccion]:
    """Ejecuta una llamada de evaluación a un modelo/configuración específica."""
    try:
        llm = ChatOpenAI(
            api_key=api_key,
            model=model_name,
            temperature=temperature,
            max_retries=2,
            timeout=180.0
        ).with_structured_output(EvaluacionSeccion)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", _PROMPT_JUEZ_LLM)
        ])
        
        chain = prompt | llm
        resultado = chain.invoke({
            "rubrica": rubrica_content,
            "seccion_objetivo": seccion_objetivo,
            "texto": texto
        })
        return resultado
    except Exception as exc:
        logger.warning(f"Juez LLM con modelo {model_name} y temp {temperature} falló: {exc}")
        return None

def evaluar_con_juez_llm(seccion_objetivo: str, texto: str, es_panel: bool = True) -> EvaluacionSeccion:
    """
    Evalúa un texto con el Juez LLM (G-Eval).
    Si es_panel es True, usa un panel de hasta 3 configuraciones/modelos de LLM y calcula el consenso.
    """
    if not texto.strip():
        return EvaluacionSeccion(
            secciones_seleccionadas=[],
            items=[],
            puntaje_total=0.0,
            puntaje_maximo=1.0
        )
        
    rubrica_content = cargar_rubrica_metodologica()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    
    if not es_panel:
        # Modo rápido: un solo juez (gpt-4o-mini con temp 0.0)
        res = _ejecutar_un_juez("gpt-4o-mini", 0.0, seccion_objetivo, texto, rubrica_content, api_key)
        if res:
            return res
        raise ValueError("El Juez LLM único falló al evaluar el texto.")

    # Panel de 3 configuraciones/modelos
    # Para mayor compatibilidad y evitar fallos por cuotas/permisos, usamos modelos estándar con temp distintas
    configuraciones = [
        {"model": "gpt-4o-mini", "temp": 0.0},
        {"model": "gpt-4o", "temp": 0.2},  # Intenta gpt-4o, si no, fallará al mini
        {"model": "gpt-3.5-turbo", "temp": 0.1}
    ]
    
    resultados: List[EvaluacionSeccion] = []
    
    # Ejecutar en paralelo
    with ThreadPoolExecutor(max_workers=3) as executor:
        futuros = []
        for config in configuraciones:
            # Si gpt-4o o gpt-3.5-turbo fallan, se intenta gpt-4o-mini como fallback inmediato
            futuros.append(
                executor.submit(
                    _ejecutar_un_juez,
                    config["model"],
                    config["temp"],
                    seccion_objetivo,
                    texto,
                    rubrica_content,
                    api_key
                )
            )
            
        for i, f in enumerate(futuros):
            res = f.result()
            if res:
                resultados.append(res)
            else:
                # Fallback secundario a gpt-4o-mini
                temp_fallback = configuraciones[i]["temp"] + 0.3
                fallback_res = _ejecutar_un_juez("gpt-4o-mini", temp_fallback, seccion_objetivo, texto, rubrica_content, api_key)
                if fallback_res:
                    resultados.append(fallback_res)

    if not resultados:
        # Fallback definitivo si todo falló
        res = _ejecutar_un_juez("gpt-4o-mini", 0.0, seccion_objetivo, texto, rubrica_content, api_key)
        if res:
            return res
        raise ValueError("Todos los jueces del panel y los fallbacks fallaron al evaluar el texto.")
        
    # Consolidar panel:
    # 1. Calcular el puntaje total promedio de los jueces exitosos
    total_scores = [r.puntaje_total for r in resultados]
    avg_score = sum(total_scores) / len(total_scores)
    
    # 2. Encontrar el juez con el puntaje más cercano al promedio
    mejor_juez = min(resultados, key=lambda r: abs(r.puntaje_total - avg_score))
    
    # 3. Retornar su evaluación pero con el puntaje_total promedio para reflejar el consenso del panel
    # (Clamped a 1 decimal para limpieza)
    return EvaluacionSeccion(
        secciones_seleccionadas=mejor_juez.secciones_seleccionadas,
        items=mejor_juez.items,
        puntaje_total=round(avg_score, 1),
        puntaje_maximo=mejor_juez.puntaje_maximo
    )
