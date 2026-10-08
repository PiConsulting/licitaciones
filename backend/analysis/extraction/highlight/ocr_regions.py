"""Camino de highlight para PDFs escaneados: geometría por renglón de Document Intelligence."""
from __future__ import annotations

import json
import re
from typing import Any


_CITATION_GAP_MARKER_RE = re.compile(r"\s*(?:\[\.\.\.\]|\u2026)\s*")


def pagina_sin_capa_de_texto(pdf_path: str, page_number: int) -> bool:
    """¿La página no tiene texto embebido? (HL-09)

    Es la compuerta de todo el camino OCR, y está escrita para ser CONSERVADORA:
    ante cualquier duda --no se pudo abrir el PDF, la página no existe, PyMuPDF
    tiró una excepción-- devuelve `False`, o sea "tiene texto", que es el camino
    de siempre. Un falso positivo acá activaría el camino nuevo en un documento
    que ya andaba bien, y eso es exactamente lo que no puede pasar.
    """
    if not pdf_path:
        return False
    try:
        import fitz  # PyMuPDF; se importa acá como en el resto del módulo

        with fitz.open(pdf_path) as documento:
            indice = int(page_number) - 1
            if indice < 0 or indice >= len(documento):
                return False
            return not documento[indice].get_text().strip()
    except Exception:  # noqa: BLE001
        return False


def _safe_int_page(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _renglones_del_chunk(chunk: dict[str, Any] | None, page_number: int) -> list[dict[str, Any]]:
    """La geometría por renglón que dejó la indexación, para esta página."""
    if not chunk:
        return []
    origen = chunk.get("source")
    if isinstance(origen, str):
        try:
            origen = json.loads(origen)
        except (ValueError, TypeError):
            return []
    if not isinstance(origen, dict):
        return []

    renglones: list[dict[str, Any]] = []
    for bloque in origen.get("blocks") or []:
        if not isinstance(bloque, dict):
            continue
        paginas = {
            _safe_int_page(caja.get("page"))
            for caja in (bloque.get("bbox") or [])
            if isinstance(caja, dict)
        }
        if paginas and page_number not in paginas:
            continue
        for renglon in bloque.get("lines") or []:
            if isinstance(renglon, dict) and renglon.get("t"):
                renglones.append(renglon)
    return renglones


def regiones_desde_renglones_ocr(
    renglones: list[dict[str, Any]], citation: str
) -> list[dict[str, float]]:
    """Ubica la cita entre los renglones que leyó Azure DI (HL-09)."""
    if not renglones or not citation:
        return []

    from analysis.extraction.highlight.search_matching import _fold

    raw_citation = (citation or "").strip()
    candidates = [raw_citation]
    if _CITATION_GAP_MARKER_RE.search(raw_citation):
        parts = [part.strip(" .;,:\n\t") for part in _CITATION_GAP_MARKER_RE.split(raw_citation)]
        parts = [part for part in parts if part]
        parts.sort(key=len, reverse=True)
        for part in parts:
            if part not in candidates:
                candidates.append(part)

    concatenado: list[str] = []
    procedencia: list[tuple[int, int, int]] = []  # (índice de renglón, offset, largo del renglón)
    for indice, renglon in enumerate(renglones):
        plegado = _fold(str(renglon.get("t") or ""))
        for offset, caracter in enumerate(plegado):
            concatenado.append(caracter)
            procedencia.append((indice, offset, len(plegado)))
    texto = "".join(concatenado)
    if not texto:
        return []

    por_renglon: dict[int, tuple[int, int, int]] = {}
    for candidate in candidates:
        buscada = _fold(candidate)
        if not buscada:
            continue

        comienzo = texto.find(buscada)
        if comienzo < 0:
            continue

        final = comienzo + len(buscada) - 1
        for posicion in range(comienzo, final + 1):
            indice, offset, largo = procedencia[posicion]
            if indice in por_renglon:
                desde, hasta_existente, _l = por_renglon[indice]
                por_renglon[indice] = (min(desde, offset), max(hasta_existente, offset), largo)
            else:
                por_renglon[indice] = (offset, offset, largo)

        if por_renglon:
            break

    if not por_renglon:
        return []

    regiones: list[dict[str, float]] = []
    for indice in sorted(por_renglon):
        desde, hasta, largo = por_renglon[indice]
        renglon = renglones[indice]
        try:
            x = float(renglon["x"])
            y = float(renglon["y"])
            ancho = float(renglon["width"])
            alto = float(renglon["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if largo <= 0 or ancho <= 0:
            continue
        inicio_rel = desde / largo
        fin_rel = (hasta + 1) / largo
        regiones.append(
            {
                "x": round(x + ancho * inicio_rel, 2),
                "y": round(y, 2),
                "width": round(ancho * (fin_rel - inicio_rel), 2),
                "height": round(alto, 2),
            }
        )
    return regiones
