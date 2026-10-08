"""Conversion de bounding boxes de Azure Document Intelligence a puntos PDF (top-left origin), y geometria de renglon."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_POINTS_PER_INCH = 72.0
_TOLERANCIA_DE_CONTENCION_PT = 2.0


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _first_page_number(item: object) -> int:
    regions = getattr(item, "bounding_regions", None) or []
    for region in regions:
        page_number = getattr(region, "page_number", None)
        if page_number is not None:
            return _safe_int(page_number, default=1)
    return 1


def _normalized_length_unit(unit: object) -> str:
    """El nombre de la unidad de `DocumentPage.unit`, venga como enum o como str."""
    if unit is None:
        return ""
    raw = getattr(unit, "value", unit)
    text = str(raw).strip().lower()
    return text.rsplit(".", 1)[-1] if "." in text else text


def _page_unit_scales(result: object) -> dict[int, float]:
    """Factor de conversión a PUNTOS para cada página del documento."""
    scales: dict[int, float] = {}
    unsupported: dict[int, str] = {}

    for page in list(getattr(result, "pages", None) or []):
        page_number = _safe_int(getattr(page, "page_number", None), default=0)
        if page_number <= 0:
            continue
        unit = _normalized_length_unit(getattr(page, "unit", None))

        if unit == "inch":
            scales[page_number] = _POINTS_PER_INCH
        elif unit in {"point", "pt"}:
            scales[page_number] = 1.0
        else:
            unsupported[page_number] = unit or "(sin unidad)"

    if unsupported:
        logger.error(
            "document_intelligence_unsupported_bbox_unit",
            pages=sorted(unsupported),
            units=sorted(set(unsupported.values())),
            impact="esas páginas quedan sin bbox; el highlighting cae al camino de PyMuPDF",
        )

    return scales


def _extract_bounding_boxes(
    item: object, unit_scales: dict[int, float] | None = None
) -> list[dict[str, float]]:
    """Extrae bounding boxes de un item de Azure Document Intelligence.

    Convierte las bounding_regions a coordenadas top-left origin (estándar web)
    y a PUNTOS de PDF, que es la unidad del contrato de `highlight_regions`
    (ver `analysis/extraction/highlight/highlight.py::compute_highlight_regions`).

    Args:
        item: entidad de Azure DI con `bounding_regions`.
        unit_scales: {page_number: factor a puntos}, de `_page_unit_scales`.
            Si es None no se convierte nada -- sólo para llamadores de test que
            ya trabajan en puntos.

    Returns:
        Lista de bbox: [{"page": int, "x": float, "y": float, "width": float, "height": float}]
    """
    regions = getattr(item, "bounding_regions", None) or []
    bboxes = []

    if not regions:
        has_attr = hasattr(item, "bounding_regions")
        logger.debug(
            "no_bounding_regions",
            has_attr=has_attr,
            attr_value=getattr(item, "bounding_regions", "NOT_SET"),
        )
        return bboxes

    for region in regions:
        page_number = getattr(region, "page_number", None)
        polygon = getattr(region, "polygon", None)

        if page_number is None or not polygon or len(polygon) < 4:
            continue
        x_coords = [polygon[i] for i in range(0, len(polygon), 2)]
        y_coords = [polygon[i] for i in range(1, len(polygon), 2)]

        x = min(x_coords)
        y = min(y_coords)
        width = max(x_coords) - x
        height = max(y_coords) - y

        page = _safe_int(page_number, default=1)
        if unit_scales is None:
            scale = 1.0
        elif page in unit_scales:
            scale = unit_scales[page]
        else:
            continue

        bboxes.append(
            {
                "page": page,
                "x": float(x) * scale,
                "y": float(y) * scale,
                "width": float(width) * scale,
                "height": float(height) * scale,
            }
        )

    return bboxes


def _page_sizes_in_points(
    result: object, unit_scales: dict[int, float]
) -> dict[int, tuple[float, float]]:
    """Dimensiones (ancho, alto) de cada página, en PUNTOS.

    Reemplaza los límites hardcodeados `x <= 1200 / y <= 1600` que usaba
    `_enrich_blocks_with_para_id` para validar coordenadas (ING-03). Esos dos
    números no correspondían a ninguna unidad concreta: para un PDF en pulgadas
    (valores 0-11) nunca disparaban, y para cualquier documento en píxeles
    descartaban el 100% de los bbox. Validar contra el tamaño REAL de la página
    es correcto en cualquier unidad y detecta el caso que importa: un bbox que
    cae fuera de la hoja.
    """
    sizes: dict[int, tuple[float, float]] = {}
    for page in list(getattr(result, "pages", None) or []):
        page_number = _safe_int(getattr(page, "page_number", None), default=0)
        scale = unit_scales.get(page_number)
        if page_number <= 0 or scale is None:
            continue
        width = getattr(page, "width", None)
        height = getattr(page, "height", None)
        if width is None or height is None:
            continue
        try:
            sizes[page_number] = (float(width) * scale, float(height) * scale)
        except (TypeError, ValueError):
            continue
    return sizes


def _renglon_dentro_de(renglon: dict[str, Any], caja: dict[str, Any]) -> bool:
    """El centro del renglón cae dentro de la caja, con tolerancia.

    Por el centro y no por las cuatro esquinas: un renglón que sobresale un
    punto por el borde derecho sigue siendo del párrafo, y descartarlo dejaría
    justo el renglón más largo --el que más probablemente contiene la cita--
    afuera.
    """
    try:
        centro_x = float(renglon["x"]) + float(renglon["width"]) / 2
        centro_y = float(renglon["y"]) + float(renglon["height"]) / 2
        x = float(caja.get("x", 0.0))
        y = float(caja.get("y", 0.0))
        ancho = float(caja.get("width", 0.0))
        alto = float(caja.get("height", 0.0))
    except (TypeError, ValueError, KeyError):
        return False
    margen = _TOLERANCIA_DE_CONTENCION_PT
    return (
        x - margen <= centro_x <= x + ancho + margen and y - margen <= centro_y <= y + alto + margen
    )


class _RegionDeRenglon:
    """Adaptador mínimo: le da a un `line` de DI la forma que espera
    `_extract_bounding_boxes` (un item con `bounding_regions`)."""

    def __init__(self, page_number: int, polygon: object) -> None:
        self.bounding_regions = [_PoligonoDeRenglon(page_number, polygon)]


class _PoligonoDeRenglon:
    def __init__(self, page_number: int, polygon: object) -> None:
        self.page_number = page_number
        self.polygon = polygon
