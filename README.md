# Sistema de Mentoría Académica UPAO — Red Multiagente

> Sistema de inteligencia artificial multiagente que evalúa y mejora proyectos de tesis de la **Universidad Privada Antenor Orrego (UPAO)**, Facultad de Ingeniería, usando la rúbrica oficial de 33 ítems.

---

## Tabla de Contenidos

- [Descripción](#descripción)
- [Arquitectura](#arquitectura)
- [Requisitos previos](#requisitos-previos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Arrancar el proyecto](#arrancar-el-proyecto)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Cómo usar el sistema](#cómo-usar-el-sistema)
- [Agentes y sus roles](#agentes-y-sus-roles)
- [Sistema RAG dual](#sistema-rag-dual)
- [Protección anti-bucle](#protección-anti-bucle)
- [Variables de entorno](#variables-de-entorno)
- [Notas de desarrollo](#notas-de-desarrollo)

---

## Descripción

El sistema recibe el PDF de un proyecto de tesis, selecciona una sección específica a evaluar y lanza una **red multiagente** que itera para mejorar el texto hasta que el mentor humano lo aprueba.

**Stack tecnológico:**

| Componente | Tecnología |
|---|---|
| Orquestación multiagente | LangGraph `StateGraph` |
| LLM | Groq `llama-3.3-70b-versatile` |
| Base de datos vectorial | ChromaDB (dual: efímera + persistente) |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` (local, CPU) |
| Interfaz | Streamlit |
| Salida estructurada | Pydantic v2 |
| Persistencia de sesión | LangGraph `MemorySaver` checkpointer |

---

## Arquitectura

### Topología: Red Multiagente con Supervisor Orquestador

El sistema implementa una **arquitectura de red pura (Supervisor Network)**. El Supervisor LLM lee el estado completo en cada turno y decide dinámicamente qué agente ejecutar. No existen edges hardcodeados entre agentes.

```
START
  │
  ▼
┌─────────────────────────────────────────┐
│         SUPERVISOR ORQUESTADOR          │  ← LLM decide el siguiente paso
│    Lee estado → elige agente → routing  │    en cada iteración de la red
└──────┬──────┬──────┬──────┬─────────────┘
       │      │      │      │   (5 edges condicionales — nunca hardcodeados)
       ▼      ▼      ▼      ▼
  REDACTOR AUDITOR METOD. DEBATE     ← cada agente devuelve resultado
       │      │      │      │          y regresa al Supervisor
       └──────┴──────┴──────┘
                  │
                  ▼  (cuando el Supervisor decide)
          ┌──────────────┐
          │  nodo_humano │  ← HITL: pausa para el mentor
          │ (HITL pause) │
          └──────────────┘
                  │
                 END
```

**Verificación técnica (0 edges hardcodeados entre agentes):**
```
nodo_supervisor  →  nodo_redactor      [CONDICIONAL]
nodo_supervisor  →  nodo_auditor       [CONDICIONAL]
nodo_supervisor  →  nodo_metodologico  [CONDICIONAL]
nodo_supervisor  →  nodo_debate        [CONDICIONAL]
nodo_supervisor  →  nodo_humano        [CONDICIONAL]
nodo_redactor    →  nodo_supervisor    [FIJO - retorno]
nodo_auditor     →  nodo_supervisor    [FIJO - retorno]
nodo_metodologico → nodo_supervisor   [FIJO - retorno]
nodo_debate      →  nodo_supervisor    [FIJO - retorno]
nodo_humano      →  END               [FIJO]
```

---

## Requisitos previos

- **Python** 3.10 o superior
- **pip** actualizado (`pip install --upgrade pip`)
- **4 claves de API de Groq** (gratuitas): [console.groq.com/keys](https://console.groq.com/keys)
- ~**500 MB** de espacio en disco (modelo de embeddings HuggingFace ~80 MB + dependencias)
- Conexión a internet para la primera descarga del modelo de embeddings

---

## Instalación

```bash
# 1. Clonar o descomprimir el proyecto
cd poc_langgraph_mentoria

# 2. Crear entorno virtual (recomendado)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

> **Nota:** La primera ejecución descarga el modelo `all-MiniLM-L6-v2` (~80 MB). Se cachea automáticamente y no se vuelve a descargar.

---

## Configuración

### 1. Crear el archivo `.env`

Copia el archivo de ejemplo y rellena tus claves:

```bash
cp .env.example .env
```

Edita `.env`:

```env
# Una clave de Groq por agente → distribuye el rate limit (6.000 TPM × 4 = 24.000 TPM efectivos)
GROQ_KEY_SUPERVISOR=gsk_...
GROQ_KEY_REDACTOR=gsk_...
GROQ_KEY_AUDITOR=gsk_...
GROQ_KEY_METODOLOGICO=gsk_...

# Fallback: si no defines claves individuales, todos los agentes usan esta
GROQ_API_KEY=gsk_...
```

> **¿Por qué 4 claves?** La API gratuita de Groq tiene un límite de 6.000 tokens por minuto por clave. Con 4 claves independientes el sistema tiene 24.000 TPM efectivos, evitando errores 429 durante el procesamiento paralelo.

### 2. (Opcional) Pre-cargar libros de metodología

Coloca PDFs de libros de metodología de investigación en la carpeta `books/`:

```
books/
  Hernandez-Metodologia-de-la-investigacion.pdf
  otro-libro.pdf
```

Se cargan automáticamente en ChromaDB persistente la primera vez que arranca el servidor.

---

## Arrancar el proyecto

```bash
# Desde la raíz del proyecto (poc_langgraph_mentoria/)
streamlit run frontend/app.py
```

El servidor arranca en `http://localhost:8501`

**Primera ejecución (puede tardar 2-3 minutos):**
- Descarga y cachea el modelo de embeddings HuggingFace
- Compila el grafo LangGraph
- Indexa los libros de la carpeta `books/` en ChromaDB persistente

**Ejecuciones siguientes:** arranque en ~5 segundos (todo cacheado con `@st.cache_resource`).

---

## Estructura del proyecto

```
poc_langgraph_mentoria/
│
├── frontend/                          # Interfaz Streamlit
│   ├── app.py                         # Punto de entrada + router de pantallas
│   ├── resources.py                   # Singletons cacheados (grafo, embeddings, biblioteca)
│   ├── session_manager.py             # Helpers de st.session_state
│   └── components/
│       ├── sidebar.py                 # Sidebar: gestión de biblioteca de libros
│       ├── pantalla_upload.py         # [1] Subida y vectorización del PDF de tesis
│       ├── pantalla_seleccion.py      # [2] Selección de sección + configuración + lanzamiento
│       ├── pantalla_revision.py       # [3] Revisión HITL del mentor (tabs: Auditor/Debate/Supervisor/RAG)
│       └── pantalla_resultado.py      # [4] Texto final aprobado + descarga
│
├── backend/
│   ├── config.py                      # Rúbrica UPAO (33 ítems), secciones, dependencias cruzadas
│   │
│   ├── graph/
│   │   ├── state.py                   # MentoriaState (TypedDict) — estado compartido de la red
│   │   ├── workflow.py                # Compilación del StateGraph — topología de red
│   │   ├── edges.py                   # routing_supervisor: lee state["siguiente_nodo"]
│   │   └── nodes/
│   │       ├── supervisor.py          # Orquestador LLM: decide el siguiente agente (DecisionSupervisor)
│   │       ├── redactor.py            # Mejora el texto académico con RAG + feedback
│   │       ├── auditor.py             # Evalúa rúbrica 33 ítems (AuditorOutput Pydantic)
│   │       ├── metodologico.py        # Rigor científico + coherencia cruzada entre secciones
│   │       ├── debate.py              # Debate argumentativo Redactor ↔ Evaluadores (Pydantic)
│   │       ├── human.py               # Nodo HITL — registra la decisión del mentor
│   │       └── _utils.py              # cargar_prompt(), invocar_con_backoff() (anti-429)
│   │
│   ├── prompts/                       # Prompts en Markdown — editables sin tocar código
│   │   ├── supervisor_red_prompt.md   # Prompt del Supervisor Orquestador (routing dinámico)
│   │   ├── redactor_prompt.md         # Prompt del Redactor (estructura UPAO + reglas de lenguaje)
│   │   ├── auditor_prompt.md          # Prompt del Auditor (rúbrica completa + instrucciones)
│   │   ├── metodologico_prompt.md     # Prompt del Metodólogo (rigor + coherencia cruzada)
│   │   ├── debate_redactor_prompt.md  # Prompt para el Redactor en ronda de debate
│   │   └── debate_evaluadores_prompt.md # Prompt para los Evaluadores en ronda de debate
│   │
│   └── rag/
│       ├── embeddings.py              # Singleton HuggingFaceEmbeddings (all-MiniLM-L6-v2)
│       ├── extractor.py               # Extracción de texto de PDFs con pdfplumber
│       ├── tesis_store.py             # ChromaDB EphemeralClient — tesis del estudiante (por sesión)
│       ├── library_store.py           # ChromaDB PersistentClient — biblioteca de libros
│       └── vector_store.py            # recuperar_contexto(), recuperar_contexto_teorico()
│
├── books/                             # PDFs de libros de metodología (pre-carga automática)
│   └── *.pdf
│
├── chroma_db/                         # ChromaDB persistente (generado automáticamente)
│   └── biblioteca/                    # Índice vectorial de los libros
│
├── .env                               # Variables de entorno (NO subir a git)
├── .env.example                       # Plantilla de variables de entorno
├── .gitignore
└── requirements.txt
```

---

## Cómo usar el sistema

### Flujo completo

```
[1] Subir PDF  →  [2] Seleccionar sección  →  [3] Red multiagente trabaja
      →  [4] Revisar y aprobar  →  [5] Descargar texto final
```

### Paso a paso

**1. Subir el PDF del estudiante**
- Arrastra o selecciona el PDF de la tesis
- El sistema extrae el texto y construye un ChromaDB efímero (en memoria)

**2. Configurar y lanzar la evaluación**
- Elige la sección a evaluar (19 secciones disponibles según estructura UPAO)
- Configura en "⚙️ Configuración avanzada":
  - **Ciclos máximos de mejora** (1–5): cuántas veces puede el Redactor reescribir el texto
  - **Rondas máximas de debate** (1–3): cuántas rondas de argumentación por ciclo
- Pulsa **Iniciar Evaluación Multiagente**

**3. La red multiagente trabaja (automático)**

El Supervisor LLM orquesta el flujo dinámicamente:

```
Supervisor → Redactor (genera versión mejorada)
Supervisor → Auditor  (evalúa rúbrica 33 ítems)
Supervisor → Metodólogo (rigor científico + coherencia)
Supervisor → Debate   (Redactor argumenta ↔ Evaluadores responden)
Supervisor → Redactor (nueva iteración si quedan errores)
     ...
Supervisor → Humano   (cuando el texto está listo o se alcanza el límite)
```

**4. Revisar y aprobar (HITL)**

El sistema pausa y muestra al mentor:
- **Tab "Informe del Auditor"**: errores por ítem, puntaje, feedback
- **Tab "Debate entre Agentes"**: historial de rondas argumentativas
- **Tab "Informe del Supervisor"**: análisis y recomendación del orquestador
- **Tab "Texto Original"**: lo que escribió el estudiante en el PDF
- **Tab "Contexto RAG"**: fragmentos recuperados por ChromaDB

El mentor puede **editar el texto** directamente en el editor antes de:
- ✅ **Aprobar**: el texto editado queda como versión final
- ❌ **Rechazar**: descarta el resultado y permite una nueva evaluación

**5. Resultado final**
- Texto aprobado con métricas (puntaje, nota vigesimal, iteraciones)
- Opción de descarga en `.txt`

---

## Agentes y sus roles

| Agente | Archivo | Modelo | Rol |
|---|---|---|---|
| **Supervisor** | `nodes/supervisor.py` | `llama-3.3-70b` temp=0.2 | Orquestador: lee estado completo y decide el siguiente agente (routing dinámico) |
| **Redactor** | `nodes/redactor.py` | `llama-3.3-70b` temp=0.4 | Mejora el texto académico usando plan del Supervisor, feedback del Auditor, observaciones del Metodólogo y contexto RAG cruzado |
| **Auditor** | `nodes/auditor.py` | `llama-3.3-70b` temp=0.1 | Evalúa el texto contra los 33 ítems de la rúbrica oficial UPAO (escala 0–3). Salida estructurada Pydantic `AuditorOutput` |
| **Metodólogo** | `nodes/metodologico.py` | `llama-3.3-70b` temp=0.2 | Evalúa el rigor científico y la coherencia entre secciones relacionadas del documento |
| **Debate** | `nodes/debate.py` | `llama-3.3-70b` temp=0.3 | Intercambio argumentativo: Redactor defiende sus decisiones, Evaluadores responden con veredicto Pydantic (`VeredictoEvaluadores`). Actualiza `errores_rubrica` aceptando o manteniendo cada ítem |

### Estado compartido (`MentoriaState`)

Todos los agentes leen y escriben en un `TypedDict` centralizado con persistencia via `MemorySaver`:

```python
MentoriaState:
  # Contexto de entrada
  seccion_objetivo, contexto_recuperado, contexto_dependencias, contexto_teorico

  # Control de ciclos
  max_iteraciones, max_rondas_debate

  # Routing de red (nuevo en v3)
  siguiente_nodo        # el Supervisor escribe aquí su decisión
  pasos_ejecutados      # contador anti-bucle
  max_pasos_red         # techo calculado automáticamente
  iter_auditada         # el Supervisor sabe si el Auditor ya corrió esta iteración
  iter_metodologica     # ídem para el Metodólogo

  # Agentes
  plan_supervisor, texto_iterado, numero_iteracion
  feedback_auditor, errores_rubrica, puntaje_estimado
  observaciones_metodologicas
  ronda_debate, historial_debate, veredicto_debate

  # HITL
  aprobacion_humana
```

---

## Sistema RAG Dual

El sistema usa **dos instancias de ChromaDB independientes**:

| Instancia | Tipo | Contenido | Ciclo de vida |
|---|---|---|---|
| **Tesis** | `EphemeralClient` (en memoria) | PDF del estudiante actual | Por sesión — se destruye al reiniciar |
| **Biblioteca** | `PersistentClient` (en disco) | PDFs de libros de metodología | Permanente — sobrevive reinicios |

### Embeddings

Modelo: `sentence-transformers/all-MiniLM-L6-v2`
- Se ejecuta **localmente en CPU** (sin costo, sin latencia de API)
- Se descarga automáticamente en la primera ejecución (~80 MB)
- Se cachea con `@st.cache_resource` — un solo modelo para toda la sesión

### RAG Cruzado entre Secciones

Antes de invocar el grafo, el sistema consulta `DEPENDENCIAS_SECCIONES` (definido en `config.py`) para recuperar contexto de secciones relacionadas. Por ejemplo, al evaluar "Título del proyecto" también recupera fragmentos de Objetivos, Variables, Hipótesis y Marco Metodológico — garantizando que el Redactor y el Auditor detecten incoherencias entre secciones.

---

## Protección Anti-Bucle

El sistema tiene **dos capas independientes** para evitar bucles infinitos:

### Capa 1 — Semántica (Supervisor)
```python
max_pasos_red = max_iteraciones × (4 + max_rondas_debate) + 3
# Ejemplo: 3 iter × (4 + 2) + 3 = 21 pasos máximos

if pasos_ejecutados >= max_pasos_red:
    # El Supervisor fuerza "humano" sin llamar al LLM
    return {"siguiente_nodo": "humano", ...}
```

### Capa 2 — Sistémica (LangGraph)
```python
RECURSION_LIMIT = 60  # en workflow.py
# LangGraph lanza GraphRecursionError si se superan 60 supersteps
```

Con configuración por defecto (3 iteraciones, 2 rondas de debate):
- Pasos máximos semánticos: **21**
- Supersteps máximos de LangGraph: **60**
- Hay ~40 supersteps de margen antes de que LangGraph corte

---

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `GROQ_KEY_SUPERVISOR` | Recomendada | Clave Groq exclusiva para el Supervisor |
| `GROQ_KEY_REDACTOR` | Recomendada | Clave Groq exclusiva para el Redactor |
| `GROQ_KEY_AUDITOR` | Recomendada | Clave Groq exclusiva para el Auditor |
| `GROQ_KEY_METODOLOGICO` | Recomendada | Clave Groq exclusiva para el Metodólogo |
| `GROQ_API_KEY` | Sí (fallback) | Si no se definen las claves individuales, todos los agentes usan esta |
| `LANGCHAIN_TRACING_V2` | Opcional | `true` para activar tracing con LangSmith |
| `LANGCHAIN_API_KEY` | Opcional | Clave de LangSmith para tracing |
| `LANGCHAIN_PROJECT` | Opcional | Nombre del proyecto en LangSmith |

---

## Notas de desarrollo

### Modificar prompts sin tocar código

Todos los prompts están en `backend/prompts/*.md` como archivos Markdown independientes. Edítalos directamente y recarga el servidor — no es necesario modificar ningún archivo `.py`.

### Añadir nuevas secciones de tesis

Edita `backend/config.py`:
1. Agrega la sección a `SECCIONES_TESIS` con su `nombre` y `query`
2. Agrega los ítems UPAO correspondientes a `SECCION_ITEMS_MAP`
3. (Opcional) Define dependencias cruzadas en `DEPENDENCIAS_SECCIONES`

### Cambiar el modelo LLM

En `backend/graph/workflow.py`, cambia el modelo en la función `_llm()`:

```python
return ChatGroq(
    api_key=api_key,
    model="llama-3.3-70b-versatile",  # ← cambia aquí
    ...
)
```

Modelos compatibles con Groq: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, entre otros.

### Tracing con LangSmith

Para trazabilidad completa de cada llamada al LLM, activa LangSmith en `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=mentoria-upao
```

### Rate limits de Groq (API gratuita)

| Límite | Por clave | Con 4 claves |
|---|---|---|
| Tokens por minuto (TPM) | 6.000 | ~24.000 |
| Tokens por día (TPD) | 500.000 | ~2.000.000 |
| Requests por minuto (RPM) | 30 | ~120 |

El sistema incluye `invocar_con_backoff()` en `nodes/_utils.py` con reintentos exponenciales (5s × 2^intento + jitter) ante errores 429.

---

## Licencia

Proyecto académico desarrollado como prueba de concepto (PoC) para la **Universidad Privada Antenor Orrego (UPAO)**, Facultad de Ingeniería. Uso educativo y de investigación.
