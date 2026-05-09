"""Extracción de texto desde archivos PDF usando pdfplumber."""

import io
import logging
import warnings

import pdfplumber

logger = logging.getLogger(__name__)

# pdfplumber emite warnings de bajo nivel por PDFs con espacios de color
# no estándar (ej. 2 componentes). Son inofensivos: el texto se extrae igual.
_PDFPLUMBER_WARNINGS = [
    "Cannot set non-stroke color",
    "Cannot set stroke color",
]


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrae el texto completo de un PDF dado como bytes.

    Args:
        pdf_bytes: Contenido del archivo PDF como bytes.

    Returns:
        Texto limpio, una página por párrafo, con páginas vacías omitidas.

    Raises:
        Exception: Si pdfplumber no puede abrir el archivo.
    """
    paginas = []
    try:
        # Suprimir warnings de espacios de color no estándar en el PDF
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Cannot set.*color")
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for i, pagina in enumerate(pdf.pages):
                    texto = pagina.extract_text()
                    if texto and texto.strip():
                        paginas.append(texto.strip())
                        logger.debug(f"  Pág. {i + 1}: {len(texto)} chars")
    except Exception as exc:
        logger.error(f"Error extrayendo texto del PDF: {exc}")
        raise

    resultado = "\n\n".join(paginas)
    logger.info(
        f"PDF extraído: {len(paginas)} páginas con texto, "
        f"{len(resultado):,} caracteres totales"
    )
    return resultado
