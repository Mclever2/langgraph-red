"""
ChromaDB efímero para el PDF del estudiante.

Ciclo de vida: se crea por sesión y se destruye al cerrar el navegador.
Responsabilidad única: indexar la tesis y recuperar contexto por sección.

Estrategia de chunking:
  Si el PDF tiene índice (TOC) detectado, se divide el contenido por secciones
  usando los números de página del TOC. Cada sección queda como uno o varios
  documentos con metadata {"seccion": nombre}. Esto evita que fragmentos fijos
  corten secciones a la mitad y permite recuperar la sección correcta de forma
  más precisa.

  Si no hay TOC, se aplica el splitter clásico de tamaño fijo como fallback.
"""

import logging
import re

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import SECCIONES_TESIS

logger = logging.getLogger(__name__)


# ── Helpers de jerarquía de secciones ────────────────────────────────────────

def _extraer_prefijo(nombre: str) -> str:
    """Extrae el prefijo numérico de sección: '2.1. Título' → '2.1'"""
    m = re.match(r'^(\d[\d\.]*)', nombre.strip())
    return m.group(1).rstrip('.') if m else ""


def _extraer_prefijos_rango(seccion: str) -> list[str]:
    """
    Extrae todos los prefijos de una sección con rango explícito.
    "4.1–4.3 Tipo, Método y Diseño" → ["4.1", "4.2", "4.3"]
    "3.1–3.2 Hipótesis"             → ["3.1", "3.2"]
    "1.2 Objetivos"                 → ["1.2"]
    "III. Referencias"              → []
    """
    m = re.match(r'^(\d[\d\.]*)[\s]*[–\-][\s]*(\d[\d\.]*)', seccion.strip())
    if not m:
        p = _extraer_prefijo(seccion)
        return [p] if p else []
    ini = m.group(1).rstrip('.')
    fin = m.group(2).rstrip('.')
    p_ini = [int(x) for x in ini.split('.')]
    p_fin = [int(x) for x in fin.split('.')]
    if len(p_ini) != len(p_fin) or not p_ini:
        return [ini]
    if p_ini[:-1] != p_fin[:-1]:
        return [ini]
    padre = '.'.join(str(x) for x in p_ini[:-1])
    return [
        f"{padre}.{i}" if padre else str(i)
        for i in range(p_ini[-1], p_fin[-1] + 1)
    ]


def _prefijo_ancestro_comun(prefijos: list[str]) -> str:
    """
    Halla el prefijo numérico ancestro común más largo de una lista.
    ["2.1.1", "2.1.2"] → "2.1"
    ["3.1",   "3.2"]   → "3"
    ["2",     "4"]     → ""  (capítulos distintos, no se amalgaman)
    Sube máximo 2 niveles para no sobrepasar el contexto relevante.
    """
    unicos = list({p for p in prefijos if p})
    if not unicos:
        return ""
    if len(unicos) == 1:
        return unicos[0]
    partes = [p.split('.') for p in unicos]
    prof_max = max(len(p) for p in partes)
    prof_min = min(len(p) for p in partes)
    for nivel in range(prof_min, 0, -1):
        candidatos = {'.'.join(p[:nivel]) for p in partes}
        if len(candidatos) == 1:
            if prof_max - nivel <= 2:
                return candidatos.pop()
            return ""
    return ""


def _es_subseccion(nombre: str, prefijo_padre: str) -> bool:
    """True si la sección pertenece al prefijo padre o es una subsección de él."""
    if not prefijo_padre:
        return False
    p = _extraer_prefijo(nombre)
    return p == prefijo_padre or p.startswith(prefijo_padre + ".")


CHUNK_SIZE    = 600
CHUNK_OVERLAP = 80
K_RESULTADOS  = 4        # solo para fallback sin metadata de sección
K_INICIAL     = 6        # cuántos resultados top usar para detectar la sección dominante
MAX_FRAGMENTOS_SECCION = 20  # límite de fragmentos por sección (~12 000 chars máx)

# Umbral mínimo de caracteres para considerar que un chunk tiene contenido real.
# Por debajo de este valor, el chunk es solo un encabezado/título y no aporta
# información útil — incluirlo confunde a los agentes (ven la sección pero vacía).
_MIN_CHARS_CHUNK = 80


# ── Agrupación por TOC ────────────────────────────────────────────────────────

def _encontrar_encabezado_en_texto(texto: str, nombre_seccion: str) -> int:
    """
    Localiza el encabezado de una sección en el texto de contenido de una página.

    Returns posición de inicio (0-indexed), o -1 si no se encuentra.
    Estrategia en cascada: búsqueda exacta → normalización de espacios → prefijo numérico al inicio de línea.
    """
    # 1. Búsqueda exacta
    idx = texto.find(nombre_seccion)
    if idx >= 0:
        return idx

    # 2. Normalizar espacios y buscar de nuevo
    nombre_norm = re.sub(r'\s+', ' ', nombre_seccion).strip()
    idx = texto.find(nombre_norm)
    if idx >= 0:
        return idx

    # 3. Buscar por prefijo numérico al inicio de una línea (ej. "1.4.2")
    m_pref = re.match(r'^(\d[\d\.]*)', nombre_norm)
    if m_pref:
        prefix = m_pref.group(1).rstrip('.')
        # El prefijo debe aparecer al inicio del texto o después de un salto de línea
        pattern = r'(?:(?<=\n)|^)' + re.escape(prefix) + r'[.\s]'
        m = re.search(pattern, texto)
        if m:
            pos = m.start()
            return pos + (1 if pos < len(texto) and texto[pos] == '\n' else 0)

    return -1


def _agrupar_por_toc(
    paginas: list[tuple[int, str]],
    estructura_toc: dict[str, int],
) -> list[tuple[str, str, int]]:
    """
    Agrupa las páginas de contenido en secciones según el TOC.

    Algoritmo mejorado:
      - Páginas de continuación (ninguna sección empieza en ellas): texto completo
        a la sección que estaba en curso.
      - Páginas donde empieza una o más secciones nuevas: se detectan las posiciones
        de cada encabezado en el texto con _encontrar_encabezado_en_texto, se ordena
        por posición y se reparte el texto en segmentos. El texto anterior al primer
        encabezado va a la sección anterior. Si no se detecta ningún encabezado,
        todo el texto va a la última sección que empieza en esa página (fallback).

    Returns:
        Lista de (nombre_seccion, texto_seccion, pagina_inicio), solo secciones
        con contenido no vacío. Si no hay TOC o no hay coincidencias, retorna
        un único grupo con todo el texto.
    """
    if not estructura_toc or not paginas:
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    secciones_ord = sorted(estructura_toc.items(), key=lambda x: x[1])
    acumulado: dict[str, list[str]] = {nombre: [] for nombre, _ in secciones_ord}
    paginas_asignadas = 0

    for pag, texto_pag in sorted(paginas):
        # Secciones que empiezan exactamente en esta página
        secciones_en_pag = [n for n, p in secciones_ord if p == pag]

        if not secciones_en_pag:
            # Página de continuación: asignar a la sección en curso (última con inicio ≤ pag)
            running: str | None = None
            for nombre, pag_inicio in reversed(secciones_ord):
                if pag_inicio <= pag:
                    running = nombre
                    break
            if running is not None:
                acumulado[running].append(texto_pag)
                paginas_asignadas += 1
        else:
            # Una o más secciones nuevas empiezan aquí.
            # La sección anterior a esta página recibe el texto previo al primer encabezado.
            prev: str | None = None
            for nombre, pag_inicio in reversed(secciones_ord):
                if pag_inicio < pag:
                    prev = nombre
                    break

            # Detectar posición de cada encabezado en el texto de la página
            posiciones: dict[str, int] = {}
            for nombre in secciones_en_pag:
                pos = _encontrar_encabezado_en_texto(texto_pag, nombre)
                if pos >= 0:
                    posiciones[nombre] = pos

            if posiciones:
                secciones_pos = sorted(posiciones.items(), key=lambda x: x[1])
                # Texto antes del primer encabezado → sección anterior
                primera_pos = secciones_pos[0][1]
                if primera_pos > 0 and prev is not None:
                    previo = texto_pag[:primera_pos].strip()
                    if previo:
                        acumulado[prev].append(previo)
                # Repartir segmentos entre las secciones encontradas
                for i, (nombre, pos) in enumerate(secciones_pos):
                    sig = secciones_pos[i + 1][1] if i + 1 < len(secciones_pos) else len(texto_pag)
                    frag = texto_pag[pos:sig].strip()
                    if frag:
                        acumulado[nombre].append(frag)
            else:
                # Fallback: no se encontraron encabezados → última sección en la página
                acumulado[secciones_en_pag[-1]].append(texto_pag)

            paginas_asignadas += 1

    if paginas_asignadas == 0:
        logger.warning(
            "TOC detectado pero ninguna página coincide con sus números de página. "
            "Fallback a chunking por tamaño fijo."
        )
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        return [("Documento completo", texto_total, 1)]

    grupos: list[tuple[str, str, int]] = []
    for nombre, pag_inicio in secciones_ord:
        texto_sec = "\n\n".join(acumulado[nombre])
        if texto_sec.strip():
            grupos.append((nombre, texto_sec.strip(), pag_inicio))

    logger.info(
        f"TOC: {len(grupos)} secciones con contenido "
        f"({paginas_asignadas}/{len(paginas)} páginas asignadas)"
    )
    return grupos


def _secciones_a_documentos(
    grupos: list[tuple[str, str, int]],
    collection_name: str,
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """
    Convierte grupos de sección en documentos para ChromaDB.

    Secciones cortas → un documento.
    Secciones largas → múltiples chunks preservando el nombre de sección en metadata.
    """
    docs: list[Document] = []
    for nombre, texto, pag_inicio in grupos:
        texto_limpio = texto.strip()
        if len(texto_limpio) < _MIN_CHARS_CHUNK:
            # Solo contiene el encabezado de sección sin cuerpo — no aporta a RAG
            logger.debug(
                f"Sección '{nombre}' descartada del índice ({len(texto_limpio)} chars — solo título)"
            )
            continue

        metadata = {
            "source":        collection_name,
            "tipo":          "proyecto_tesis",
            "seccion":       nombre,
            "pagina_inicio": pag_inicio,
        }

        if len(texto_limpio) <= CHUNK_SIZE:
            docs.append(Document(page_content=texto_limpio, metadata=metadata))
        else:
            chunks = splitter.create_documents([texto_limpio], metadatas=[metadata])
            docs.extend(chunks)

    return docs


# Palabras vacías del español que no aportan al matching de secciones
_STOP_WORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "o", "u",
    "con", "en", "al", "para", "por", "que", "se", "su", "sus", "es", "son",
    "a", "ante", "bajo", "desde", "sin", "sobre", "tras", "como",
}


def _palabras_clave(texto: str) -> set[str]:
    """Extrae palabras significativas (sin números, puntuación ni stop words)."""
    tokens = re.sub(r'[\d\.\,\-–\(\)\[\]/]', ' ', texto.lower()).split()
    return {t for t in tokens if len(t) > 2 and t not in _STOP_WORDS}


def _buscar_query_semantica(seccion: str) -> str:
    """
    Elige la query de SECCIONES_TESIS más adecuada para una sección del TOC del PDF.

    Estrategia en tres pasos:
      1. Nombre exacto (más fiable).
      2. Overlap de palabras clave (robusto a formatos Proyecto vs Informe de Tesis).
      3. Prefijo numérico (último recurso; puede ser ambiguo entre formatos).

    El matching por palabras clave evita confundir, p.ej.,
    "2.2. Objetivos de la investigación" (Informe) con
    "2.2 Investigaciones antecedentes" (Proyecto) aunque compartan el prefijo 2.2.
    """
    # 1. Coincidencia exacta
    for sec in SECCIONES_TESIS:
        if sec["nombre"] == seccion:
            return sec["query"]

    # 2. Mayor overlap de palabras clave (ignora números y stop words)
    kw_seccion = _palabras_clave(seccion)
    if kw_seccion:
        mejor_score = 0
        mejor_query: str | None = None
        for sec in SECCIONES_TESIS:
            score = len(kw_seccion & _palabras_clave(sec["nombre"]))
            if score > mejor_score:
                mejor_score = score
                mejor_query = sec["query"]
        if mejor_score >= 1 and mejor_query:
            return mejor_query

    # 3. Prefijo numérico (fallback)
    prefijo = _extraer_prefijo(seccion)
    if prefijo:
        for sec in SECCIONES_TESIS:
            p = _extraer_prefijo(sec["nombre"])
            if p and p == prefijo:
                return sec["query"]

    return seccion  # último recurso: usar el nombre literal


# ── API pública ───────────────────────────────────────────────────────────────

def construir_vector_store(
    paginas: list[tuple[int, str]],
    estructura_toc: dict[str, int],
    embeddings: HuggingFaceEmbeddings,
    collection_name: str = "tesis_upao",
) -> Chroma:
    """
    Divide el contenido de la tesis en fragmentos y los indexa en ChromaDB en memoria.

    Estrategia:
      - Con TOC: agrupa páginas por sección → cada sección es uno o varios documentos.
      - Sin TOC: splitter clásico de tamaño fijo sobre el texto completo.

    Args:
        paginas:         Lista de (numero_pagina_1indexed, texto_pagina).
        estructura_toc:  Dict {nombre_seccion: pagina_inicio} del índice del PDF.
        embeddings:      Modelo de embeddings ya cargado.
        collection_name: Nombre único de la colección (evita colisiones entre PDFs).

    Returns:
        Chroma vector store listo para búsqueda de similitud.
    """
    if not paginas:
        raise ValueError("El texto extraído del PDF está vacío.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "   ", " ", ""],
    )

    if estructura_toc:
        grupos = _agrupar_por_toc(paginas, estructura_toc)
        documentos = _secciones_a_documentos(grupos, collection_name, splitter)
        n_secciones = len(grupos)
        logger.info(
            f"Chunking por TOC: {n_secciones} secciones → {len(documentos)} fragmentos"
        )
    else:
        # Fallback: texto plano + splitter fijo
        texto_total = "\n\n".join(t for _, t in sorted(paginas))
        documentos = splitter.create_documents(
            [texto_total],
            metadatas=[{"source": collection_name, "tipo": "proyecto_tesis"}],
        )
        logger.info(f"Chunking fijo (sin TOC): {len(documentos)} fragmentos")

    logger.info(f"Tesis dividida en {len(documentos)} fragmentos")

    cliente = chromadb.EphemeralClient()
    store = Chroma(
        client=cliente,
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    store.add_documents(documentos)

    n = store._collection.count()
    logger.info(f"ChromaDB tesis listo: {n} fragmentos en '{collection_name}'")
    return store


def recuperar_contexto(
    vector_store: Chroma,
    seccion: str,
    k: int = K_RESULTADOS,
) -> str:
    """
    Recupera el contexto del PDF del estudiante para la sección indicada.

    Estrategia:
      1. Ranking semántico de todos los fragmentos del store.
      2. Determina los prefijos de sección que corresponden a la query:
         a. Extrae prefijos del nombre de config (maneja rangos "4.1–4.3").
         b. Valida que esos prefijos coincidan semánticamente con el top-K.
            Si coinciden → usa los prefijos del config (numeración igual en PDF y config).
            Si no coinciden → el PDF usa otra numeración; busca el ancestro común
            de las secciones del top-K para recuperar el árbol correcto.
      3. Devuelve hasta MAX_FRAGMENTOS_SECCION fragmentos del árbol detectado,
         ordenados por similitud semántica.
    """
    from collections import Counter

    query = _buscar_query_semantica(seccion)
    logger.info(f"RAG tesis → '{seccion}' | query: '{query[:55]}…'")

    try:
        n_total = vector_store._collection.count()
        todos_docs = vector_store.similarity_search(query, k=n_total)
    except Exception as exc:
        logger.error(f"Error en similarity_search tesis: {exc}")
        return f"[Error en búsqueda RAG: {exc}]"

    if not todos_docs:
        return (
            f"No se encontró contenido relevante en el PDF para '{seccion}'.\n"
            "El estudiante puede no haber redactado aún esta sección."
        )

    top_meta = [d.metadata.get("seccion") for d in todos_docs[:K_INICIAL]
                if d.metadata.get("seccion")]

    if not top_meta:
        docs = todos_docs[:k]
        logger.info(f"RAG tesis: {len(docs)} fragmentos (sin metadata de sección)")
    else:
        # Prefijos del config (maneja rangos como "4.1–4.3" → ["4.1","4.2","4.3"])
        config_prefijos = _extraer_prefijos_rango(seccion)
        top_prefijos    = [_extraer_prefijo(s) for s in top_meta if _extraer_prefijo(s)]

        # Verificar que los prefijos del config correspondan al top semántico
        config_relevante = bool(config_prefijos) and any(
            any(pt == cp or pt.startswith(cp + ".") or cp.startswith(pt + ".")
                for pt in top_prefijos)
            for cp in config_prefijos
        )

        if config_relevante:
            # Numeración del PDF coincide con el config: usar árbol directo
            docs = [d for d in todos_docs
                    if any(_es_subseccion(d.metadata.get("seccion", ""), cp)
                           for cp in config_prefijos)]
            docs = docs[:MAX_FRAGMENTOS_SECCION]
            logger.info(
                f"RAG tesis: prefijos config {config_prefijos} → "
                f"{len(docs)} fragmentos (sección + subsecciones)"
            )
        else:
            # Numeración diferente entre config y PDF: usar ancestro semántico del top-K
            ancestor = _prefijo_ancestro_comun(top_prefijos)
            if ancestor:
                docs = [d for d in todos_docs
                        if _es_subseccion(d.metadata.get("seccion", ""), ancestor)]
                docs = docs[:MAX_FRAGMENTOS_SECCION]
                logger.info(
                    f"RAG tesis: ancestro semántico '{ancestor}' "
                    f"(top prefijos: {sorted(set(top_prefijos))[:6]}) → "
                    f"{len(docs)} fragmentos"
                )
            else:
                # Sin ancestro común (secciones de capítulos distintos): usar dominante
                seccion_dominante = Counter(top_meta).most_common(1)[0][0]
                prefijo_dom = _extraer_prefijo(seccion_dominante)
                if prefijo_dom:
                    docs = [d for d in todos_docs
                            if _es_subseccion(d.metadata.get("seccion", ""), prefijo_dom)]
                else:
                    docs = [d for d in todos_docs
                            if d.metadata.get("seccion") == seccion_dominante]
                docs = docs[:MAX_FRAGMENTOS_SECCION]
                logger.info(
                    f"RAG tesis: dominante '{seccion_dominante}' → "
                    f"{len(docs)} fragmentos"
                )

    fragmentos = [f"[Fragmento {i + 1}]\n{d.page_content}" for i, d in enumerate(docs)]
    resultado = "\n\n" + "\n\n---\n\n".join(fragmentos) + "\n"
    logger.info(f"RAG tesis: {len(resultado)} chars totales recuperados")
    return resultado


# Consultas semánticas estructurales para contexto cruzado inteligente.
# Cubren las posiciones clave de cualquier proyecto de tesis universitaria,
# independientemente de la numeración que use cada documento.
_CONSULTAS_CRUZADAS: dict[str, str] = {
    "Título y delimitación":  "título investigación variables independiente dependiente espacio tiempo",
    "Problema central":       "problema central formulación pregunta investigación planteamiento realidad",
    "Objetivos":              "objetivo general específicos investigación derivan problema",
    "Hipótesis":              "hipótesis relación variables supuesto básico específicas",
    "Operacionalización":     "operacionalización variables dimensiones indicadores escala medición",
    "Marco metodológico":     "tipo método diseño investigación cuantitativo cualitativo",
    "Antecedentes / Marco teórico": "antecedentes investigaciones previas base teórica conceptos",
}

# Chars máximos por fragmento y total para no sobrecargar el contexto de los agentes
_MAX_CHARS_POR_FRAGMENTO = 500
_MAX_CHARS_CRUZADO       = 6_000


def recuperar_contexto_cruzado(
    vector_store: Chroma,
    seccion_principal: str,
) -> str:
    """
    Recupera contexto cruzado inteligente desde el vector store usando
    consultas semánticas estructurales — sin depender de un mapa hardcodeado.

    Objetivo: dar a los agentes fragmentos representativos de las secciones
    del proyecto que son estructuralmente relevantes para cualquier evaluación
    (problema, objetivos, hipótesis, variables, metodología…), excluyendo
    la sección que ya se está evaluando en el contexto principal.

    Los agentes reciben este contexto y deciden qué partes usar con criterio
    propio para verificar coherencia cruzada.
    """
    prefijo_principal = _extraer_prefijo(seccion_principal)
    partes: list[str] = []
    prefijos_visitados: set[str] = set()
    chars_acumulados = 0

    for nombre_consulta, query in _CONSULTAS_CRUZADAS.items():
        if chars_acumulados >= _MAX_CHARS_CRUZADO:
            break
        try:
            docs = vector_store.similarity_search(query, k=6)
            for doc in docs:
                seccion_doc = doc.metadata.get("seccion", "")
                prefijo_doc = _extraer_prefijo(seccion_doc)

                # Excluir la sección principal y sus subsecciones
                if prefijo_principal and prefijo_doc and _es_subseccion(seccion_doc, prefijo_principal):
                    continue
                # Deduplicar: solo un fragmento por prefijo de sección
                if prefijo_doc in prefijos_visitados:
                    continue
                # Descartar chunks que son solo encabezados sin contenido sustantivo
                if len(doc.page_content.strip()) < _MIN_CHARS_CHUNK:
                    logger.debug(
                        f"[Cross-context] '{seccion_doc}' omitida en recuperación "
                        f"({len(doc.page_content.strip())} chars — solo título)"
                    )
                    continue

                fragmento = doc.page_content[:_MAX_CHARS_POR_FRAGMENTO]
                partes.append(f"**{seccion_doc}**\n{fragmento}")
                prefijos_visitados.add(prefijo_doc)
                chars_acumulados += len(fragmento)
                break  # un fragmento representativo por consulta
        except Exception as exc:
            logger.warning(f"[Cross-context] Error en query '{nombre_consulta}': {exc}")

    if not partes:
        return ""

    resultado = "\n\n---\n\n".join(partes)
    logger.info(
        f"[Cross-context] {len(partes)} secciones cruzadas recuperadas "
        f"({chars_acumulados} chars) | excluido prefijo '{prefijo_principal}'"
    )
    return resultado


def recuperar_vista_general(vector_store: Chroma) -> str:
    """
    Recupera un fragmento representativo de cada capítulo principal del documento.

    Útil para la opción 'Vista general del proyecto': ofrece una panorámica
    del documento completo sin entrar al detalle de ninguna sección específica.
    Se toma el chunk más largo (más informativo) de cada capítulo (prefijo 1, 2, 3…).
    """
    try:
        result = vector_store._collection.get(include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []

        # Agrupar chunks por capítulo (primer dígito del prefijo)
        por_capitulo: dict[str, list[tuple[str, str]]] = {}
        for meta, doc in zip(metadatas, documents):
            seccion = meta.get("seccion", "")
            m = re.match(r'^(\d)', seccion.strip())
            capitulo = m.group(1) if m else "?"
            por_capitulo.setdefault(capitulo, []).append((seccion, doc))

        partes: list[str] = []
        for cap in sorted(por_capitulo.keys()):
            secciones_cap = por_capitulo[cap]
            # El chunk más largo = el más representativo del capítulo
            mejor_seccion, mejor_doc = max(secciones_cap, key=lambda x: len(x[1]))
            extracto = mejor_doc[:600]
            partes.append(f"**{mejor_seccion}**\n{extracto}")

        if not partes:
            return ""

        resultado = "\n\n---\n\n".join(partes)
        logger.info(f"[Vista general] {len(partes)} capítulos representados ({len(resultado)} chars)")
        return resultado

    except Exception as exc:
        logger.error(f"Error en recuperar_vista_general: {exc}")
        return ""


def obtener_stats_secciones(vector_store: Chroma) -> list[dict]:
    """
    Devuelve estadísticas por sección del vector store:
      [{"seccion": str, "pagina_inicio": int, "chars": int, "n_fragmentos": int}]

    Ordenado por página de inicio. Útil para mostrar al usuario cómo quedó
    la división del PDF (número de caracteres por sección).
    """
    try:
        result = vector_store._collection.get(include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []

        stats: dict[str, dict] = {}
        for meta, doc in zip(metadatas, documents):
            seccion = meta.get("seccion", "Sin sección")
            pag     = meta.get("pagina_inicio", 0)
            chars   = len(doc)
            if seccion not in stats:
                stats[seccion] = {
                    "seccion":       seccion,
                    "pagina_inicio": pag,
                    "chars":         0,
                    "n_fragmentos":  0,
                }
            stats[seccion]["chars"]        += chars
            stats[seccion]["n_fragmentos"] += 1

        return sorted(stats.values(), key=lambda x: x["pagina_inicio"])
    except Exception as exc:
        logger.error(f"Error obteniendo stats de secciones: {exc}")
        return []
