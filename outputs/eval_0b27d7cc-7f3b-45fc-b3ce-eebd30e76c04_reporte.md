# Reporte de Calidad y Métricas Académicas — 0b27d7cc-7f3b-45fc-b3ce-eebd30e76c04

**Universidad:** upao  
**Arquitectura:** langgraph-hub-spoke  

## 📊 Métricas de Calidad Académica

| Métrica | Valor | Interpretación | Detalles |
| :--- | :--- | :--- | :--- |
| **LLM-as-Judge (G-Eval)** | **12.25/15.0** (81.7%) | Calidad Metodológica Global | Evaluado con rúbrica especializada por panel de jueces |
| **Gain Score** | **+0.2143** | Mejora Baja | Delta pre (11.5) → post (12.25) según Juez LLM |
| **Similitud Coseno (e5)** | **0.9883** | alta similitud semántica (sin desviaciones) | Guardrail semántico utilizando multilingual-e5-small |
| **Context Precision** | **0.9068** | alta relevancia RAG | 8/10 chunks de libros recuperados relevantes |

---

## 📋 Detalle de la Evaluación del Juez LLM

**Secciones de la Rúbrica Especializada Aplicadas:** 2. Descripción y delimitación del problema, 3. Formulación del problema (pregunta central)  

| Ítem ID | Criterio de la Rúbrica | Pts Asignados | Pts Máx | Justificación Académica |
| :--- | :--- | :--- | :--- | :--- |
| 2.1 | Se presenta evidencia empírica (datos estadísticos, estudios previos o reportes oficiales) que demuestra la existencia del problema. | **0.75** | 1.5 | Se menciona que investigaciones previas evidencian la baja calidad metodológica, pero no se proporciona una referencia específica ni datos concretos que respalden esta afirmación, lo que limita la evidencia empírica presentada. |
| 2.2 | El problema está enmarcado desde lo global hacia lo local (contextualización multinivel: mundial → regional → local). | **0.0** | 1.0 | No se presenta un marco contextual que abarque desde lo global hasta lo local. La descripción se centra en la situación específica de los estudiantes de Ingeniería de la UPAO sin un contexto más amplio. |
| 2.3 | Se identifica con claridad la brecha de conocimiento o la deficiencia tecnológica/metodológica que motiva el estudio. | **1.5** | 1.5 | Se identifica claramente la brecha en la calidad metodológica y las competencias de los estudiantes, así como la insuficiencia en la supervisión, lo que motiva el estudio. |
| 2.4 | Se delimitan las variables principales del problema (qué se va a medir o comparar) de manera explícita. | **1.0** | 1.0 | Se mencionan variables como la calidad metodológica y la supervisión, así como las competencias de los estudiantes, lo que permite una delimitación clara de lo que se va a medir. |
| 2.5 | Se delimita el alcance temporal y espacial del estudio (periodo y lugar de ejecución). | **0.0** | 1.0 | No se especifica claramente el alcance temporal y espacial del estudio, lo que limita la comprensión del contexto en el que se desarrollará la investigación. |
| 2.6 | La descripción del problema es coherente con el tipo y diseño de investigación declarado más adelante. | **1.0** | 1.0 | La descripción del problema es coherente con el enfoque de investigación que se espera aplicar, ya que se relaciona con la calidad metodológica de los proyectos de tesis. |
| 2.7 | Se mencionan las consecuencias o impacto negativo de no resolver el problema (argumento de urgencia o relevancia). | **1.0** | 1.0 | Se argumenta que la falta de atención a la calidad metodológica puede llevar a investigaciones con poco rigor y al abandono de proyectos, lo que resalta la urgencia de abordar el problema. |
| 2.8 | La redacción es clara, libre de ambigüedad y no mezcla el problema con la solución propuesta. | **1.0** | 1.0 | La redacción es clara y se enfoca en describir el problema sin mezclarlo con posibles soluciones, lo que facilita la comprensión. |
| 2.9 | El problema puede ser investigado empíricamente, es decir, sus variables son observables o medibles. | **1.0** | 1.0 | Las variables mencionadas son observables y medibles, lo que permite que el problema sea investigado empíricamente. |
| 3.1 | El problema está formulado como una pregunta clara, directa y sin ambigüedad (¿en qué medida?, ¿qué efecto?, ¿cómo se relaciona?). | **1.5** | 1.5 | La pregunta central está formulada de manera clara y directa, lo que permite entender el enfoque de la investigación. |
| 3.2 | La pregunta involucra al menos dos variables o conceptos y su posible relación, diferencia o efecto. | **1.0** | 1.0 | La pregunta central involucra la implementación de sistemas multi-agente y la calidad metodológica, cumpliendo con el criterio de incluir al menos dos variables. |
| 3.3 | La pregunta es respondible mediante el diseño de investigación propuesto (no requiere datos imposibles de obtener). | **1.0** | 1.0 | La pregunta es respondible con el diseño de investigación propuesto, ya que se pueden obtener los datos necesarios para responderla. |
| 3.4 | La pregunta no es demasiado amplia ni demasiado estrecha; delimita un problema tratable en el tiempo del estudio. | **0.75** | 0.75 | La pregunta está bien delimitada y se enfoca en un aspecto específico de la calidad metodológica, lo que la hace tratable dentro del tiempo del estudio. |
| 3.5 | La pregunta es coherente con los objetivos (la respuesta a la pregunta equivale a lograr el objetivo general). | **0.75** | 0.75 | La pregunta es coherente con los objetivos planteados, ya que la respuesta contribuirá a alcanzar el objetivo general de la investigación. |
