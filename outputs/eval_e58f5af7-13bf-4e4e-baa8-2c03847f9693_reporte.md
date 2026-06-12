# Reporte de Calidad y Métricas Académicas — e58f5af7-13bf-4e4e-baa8-2c03847f9693

**Universidad:** upao  
**Arquitectura:** langgraph-hub-spoke  

## 📊 Métricas de Calidad Académica

| Métrica | Valor | Interpretación | Detalles |
| :--- | :--- | :--- | :--- |
| **LLM-as-Judge (G-Eval)** | **14.5/15.0** (96.7%) | Calidad Metodológica Global | Evaluado con rúbrica especializada por panel de jueces |
| **Gain Score** | **+0.8182** | Mejora Alta | Delta pre (12.25) → post (14.5) según Juez LLM |
| **Similitud Coseno (e5)** | **0.9813** | alta similitud semántica (sin desviaciones) | Guardrail semántico utilizando multilingual-e5-small |
| **Context Precision** | **0.8632** | alta relevancia RAG | 7/10 chunks de libros recuperados relevantes |

---

## 📋 Detalle de la Evaluación del Juez LLM

**Secciones de la Rúbrica Especializada Aplicadas:** 2. Descripción y delimitación del problema, 3. Formulación del problema (pregunta central)  

| Ítem ID | Criterio de la Rúbrica | Pts Asignados | Pts Máx | Justificación Académica |
| :--- | :--- | :--- | :--- | :--- |
| 2.1 | Se presenta evidencia empírica (datos estadísticos, estudios previos o reportes oficiales) que demuestra la existencia del problema. | **1.5** | 1.5 | Se menciona un estudio previo (Abdelhamid & Alotaibi, 2021) que respalda la existencia del problema de calidad metodológica en los proyectos de tesis, lo que cumple completamente con el criterio. |
| 2.2 | El problema está enmarcado desde lo global hacia lo local (contextualización multinivel: mundial → regional → local). | **0.5** | 1.0 | El texto menciona la situación a nivel local (UPAO) pero no proporciona un contexto más amplio que lo relacione con un marco global o regional, por lo que se cumple parcialmente. |
| 2.3 | Se identifica con claridad la brecha de conocimiento o la deficiencia tecnológica/metodológica que motiva el estudio. | **1.5** | 1.5 | Se identifica claramente la deficiencia en la calidad metodológica y la falta de supervisión como motivaciones del estudio, cumpliendo completamente con el criterio. |
| 2.4 | Se delimitan las variables principales del problema (qué se va a medir o comparar) de manera explícita. | **1.0** | 1.0 | Se mencionan variables como la calidad metodológica y la supervisión, lo que permite una delimitación clara de lo que se va a medir. |
| 2.5 | Se delimita el alcance temporal y espacial del estudio (periodo y lugar de ejecución). | **1.0** | 1.0 | Se especifica que el estudio se realizará en el año 2026 en la UPAO, cumpliendo con el criterio. |
| 2.6 | La descripción del problema es coherente con el tipo y diseño de investigación declarado más adelante. | **1.0** | 1.0 | La descripción del problema se alinea con el enfoque de investigación que se espera desarrollar, cumpliendo completamente con el criterio. |
| 2.7 | Se mencionan las consecuencias o impacto negativo de no resolver el problema (argumento de urgencia o relevancia). | **1.0** | 1.0 | Se argumenta que la falta de atención a este problema puede llevar a investigaciones con escaso rigor y abandono de proyectos, lo que cumple completamente con el criterio. |
| 2.8 | La redacción es clara, libre de ambigüedad y no mezcla el problema con la solución propuesta. | **1.0** | 1.0 | La redacción es clara y se enfoca en describir el problema sin mezclarlo con soluciones, cumpliendo completamente con el criterio. |
| 2.9 | El problema puede ser investigado empíricamente, es decir, sus variables son observables o medibles. | **1.0** | 1.0 | Las variables mencionadas son observables y medibles, lo que permite la investigación empírica, cumpliendo completamente con el criterio. |
| 3.1 | El problema está formulado como una pregunta clara, directa y sin ambigüedad (¿en qué medida?, ¿qué efecto?, ¿cómo se relaciona?). | **1.5** | 1.5 | La pregunta formulada es clara y directa, cumpliendo completamente con el criterio. |
| 3.2 | La pregunta involucra al menos dos variables o conceptos y su posible relación, diferencia o efecto. | **1.0** | 1.0 | La pregunta incluye las variables 'sistemas multi-agente' y 'calidad metodológica', cumpliendo con el criterio. |
| 3.3 | La pregunta es respondible mediante el diseño de investigación propuesto (no requiere datos imposibles de obtener). | **1.0** | 1.0 | La pregunta es respondible con el diseño de investigación propuesto, cumpliendo completamente con el criterio. |
| 3.4 | La pregunta no es demasiado amplia ni demasiado estrecha; delimita un problema tratable en el tiempo del estudio. | **0.75** | 0.75 | La pregunta está bien delimitada y es tratable dentro del tiempo del estudio, cumpliendo completamente con el criterio. |
| 3.5 | La pregunta es coherente con los objetivos (la respuesta a la pregunta equivale a lograr el objetivo general). | **0.75** | 0.75 | La pregunta formulada es coherente con los objetivos planteados, cumpliendo completamente con el criterio. |
