"""
Cálculo de coordenadas de highlight en PDFs usando PyMuPDF.

Este módulo resuelve el problema crítico de highlight frágil identificado en la
auditoría RAG: en lugar de usar heurísticas de matching en el frontend, pre-
computamos las coordenadas exactas de cada citation en el PDF usando PyMuPDF
(fitz), que tiene acceso directo a la estructura interna del PDF.

El resultado son coordenadas precisas (x, y, width, height) que el frontend
puede usar para dibujar rectangles de highlight sin falsos positivos/negativos.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _normalize_for_search(text: str) -> str:
    """Normaliza texto para búsqueda tolerante a diferencias de OCR/extracción.
    
    Replica la normalización del backend (_normalize_for_grounding) y la
    extiende para tolerar diferencias comunes de OCR:
    - Elimina acentos (á → a)
    - Normaliza espacios múltiples → espacio simple
    - Lowercase
    - Normaliza guiones (– — → -)
    - Elimina puntuación de fin de oración (opcional, preserva dentro de texto)
    """
    # 1. Normalización Unicode: decompose
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    
    # 2. Eliminar marcas diacríticas (acentos)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    
    # 3. Normalizar espacios (múltiples → simple, tabs/newlines → espacio)
    normalized = " ".join(normalized.split())
    
    # 4. Lowercase
    normalized = normalized.lower()
    
    # 5. Normalizar guiones de diferentes tipos
    normalized = normalized.replace("–", "-").replace("—", "-")
    
    return normalized.strip()


# Palabras que aparecen en el encabezado de CUALQUIER artículo de un pliego:
# no distinguen una sección de otra, así que no pueden contar como coincidencia.
_HEADING_STOPWORDS = {"articulo", "art", "capitulo", "seccion", "anexo", "clausula", "punto", "inciso"}


def _heading_tokens(text: str) -> set[str]:
    """Palabras significativas de un encabezado, sin puntuación ni genéricos."""
    normalized = _normalize_for_search(text)
    tokens = {token.strip(".,;:()[]>-") for token in normalized.split()}
    return {token for token in tokens if len(token) >= 2 and token not in _HEADING_STOPWORDS}


def _select_best_instance(
    page: Any,  # fitz.Page
    instances: list[Any],  # list[fitz.Rect]
    section_hint: str,
    correlation_id: str,
) -> list[Any]:
    """Selecciona la instancia más relevante cuando hay múltiples matches.
    
    FIX DEFINITIVO (2026-08): Resuelve el problema de highlighting cruzado
    entre secciones. Cuando el mismo texto aparece en múltiples lugares de
    la página (ej: "adquisición de insumos" en "Objeto" y en "Requisitos"),
    selecciona la instancia más cercana al título de la sección esperada.
    
    Args:
        page: Página de PyMuPDF
        instances: Lista de rectángulos donde se encontró el texto
        section_hint: Hint de sección (ej: "Objeto y Alcance", "Requisitos")
        correlation_id: ID para logging
    
    Returns:
        Lista con la mejor instancia (o todas si no se puede decidir)
    
    Algoritmo:
        1. Extraer todos los textos en tamaño grande (probables títulos)
        2. Buscar títulos que matcheen con section_hint
        3. Para cada instancia, calcular distancia al título más cercano
        4. Retornar la instancia más cercana a un título relevante
    """
    try:
        import fitz
        
        # Extraer todos los bloques de texto de la página con su posición
        blocks = page.get_text("dict")["blocks"]
        
        # Buscar títulos/headings grandes que contengan palabras del section_hint
        #
        # FIX (2026-08-14): esto comparaba palabras SIN sacar la puntuación, y
        # los títulos de un pliego son "Artículo 10. Garantías." -- con punto
        # pegado. Así, "garantias." nunca igualaba a "garantias" y la única
        # palabra que llegaba a coincidir era "articulo", que está en TODOS los
        # títulos. El bonus por palabras en común quedaba inerte y la elección
        # degeneraba en "el encabezado más cercano", que ante dos apariciones
        # equidistantes de su propio título devuelve siempre la primera.
        section_words = _heading_tokens(section_hint)
        relevant_headings = []
        
        for block in blocks:
            if block.get("type") != 0:  # Solo bloques de texto
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    size = float(span.get("size", 0))
                    bbox = span.get("bbox", None)
                    
                    # Considerar como heading si es texto grande (> 11pt típicamente)
                    if size < 11 or not bbox:
                        continue
                    
                    # Verificar si contiene palabras del section_hint
                    text_words = _heading_tokens(text)

                    # Match si comparte al menos 1 palabra significativa
                    common_words = section_words & text_words
                    if common_words:
                        relevant_headings.append({
                            "text": text,
                            "y": bbox[1],  # top y coordinate
                            "x": bbox[0],  # left x coordinate
                            "common_words": len(common_words),
                        })
        
        if not relevant_headings:
            logger.info(
                "highlight_no_relevant_headings_found",
                correlation_id=correlation_id,
                section_hint=section_hint,
                returning_first_instance=True,
            )
            # Sin headings relevantes, retornar primera instancia (más arriba)
            return [min(instances, key=lambda r: r.y0)]
        
        # Calcular distancia de cada instancia al heading más cercano
        instance_scores = []
        for instance in instances:
            # Calcular distancia Manhattan al heading más cercano y relevante
            min_distance = float('inf')
            best_heading = None
            
            for heading in relevant_headings:
                # Distancia vertical (más importante) + distancia horizontal
                v_dist = abs(instance.y0 - heading["y"])
                h_dist = abs(instance.x0 - heading["x"])
                
                # Peso mayor a distancia vertical (secciones están una sobre otra)
                # Bonus por cada palabra común con el section_hint
                distance = (v_dist * 2 + h_dist * 0.5) / (1 + heading["common_words"])
                
                if distance < min_distance:
                    min_distance = distance
                    best_heading = heading
            
            instance_scores.append({
                "instance": instance,
                "distance": min_distance,
                "heading": best_heading["text"] if best_heading else None,
            })
        
        # Seleccionar la instancia con menor distancia
        best = min(instance_scores, key=lambda s: s["distance"])
        
        logger.info(
            "highlight_instance_selected",
            correlation_id=correlation_id,
            section_hint=section_hint,
            selected_near_heading=best["heading"],
            distance=round(best["distance"], 2),
            total_instances=len(instances),
        )
        
        return [best["instance"]]
        
    except Exception as exc:
        logger.warning(
            "highlight_instance_selection_failed",
            correlation_id=correlation_id,
            error=str(exc),
            fallback="returning first instance",
        )
        # Fallback: retornar primera instancia
        return [instances[0]] if instances else []


def _normalize_for_search(text: str) -> str:
    """Normaliza texto para búsqueda tolerante a diferencias de OCR/extracción.
    
    Replica la normalización del backend (_normalize_for_grounding) y la
    extiende para tolerar diferencias comunes de OCR:
    - Elimina acentos (á → a)
    - Normaliza espacios múltiples → espacio simple
    - Lowercase
    - Normaliza guiones (– — → -)
    - Elimina puntuación de fin de oración (opcional, preserva dentro de texto)
    """
    # 1. Normalización Unicode: decompose
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    
    # 2. Eliminar marcas diacríticas (acentos)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    
    # 3. Normalizar espacios (múltiples → simple, tabs/newlines → espacio)
    normalized = " ".join(normalized.split())
    
    # 4. Lowercase
    normalized = normalized.lower()
    
    # 5. Normalizar guiones de diferentes tipos
    normalized = normalized.replace("–", "-").replace("—", "-")
    
    return normalized.strip()


def _group_rects_by_occurrence(instances: list[Any]) -> list[list[Any]]:
    """Agrupa los rectángulos de `page.search_for()` por APARICIÓN.

    FIX (auditoría 2026-08-13): PyMuPDF devuelve UN RECTÁNGULO POR RENGLÓN
    cuando el texto buscado ocupa varias líneas. Una cita de 3 renglones
    devuelve 3 rects de una sola aparición:

        x0=60.0 y0=88.2  ancho=318.5
        x0=60.0 y0=100.2 ancho=314.2
        x0=60.0 y0=112.2 ancho=120.5   <- el sobrante del último renglón

    El código anterior interpretaba `len(text_instances) > 1` como "el texto
    aparece en varios lugares de la página" y llamaba a `_select_best_instance`,
    que se queda con UNO. Para una cita multilínea -- o sea, casi todas las de
    un pliego -- eso tiraba 2 de cada 3 fragmentos y a veces conservaba el más
    chico. Se vio en producción: una cita de 154 caracteres resaltada con un
    recuadro de `width: 8.93` px.

    Una misma aparición también se parte DENTRO de un renglón cuando el texto
    cambia de span. Medido sobre el pliego auditado, la cita
    "c) Propuesta Técnica debidamente firmada: ..." devuelve:

        x0= 56.8 x1= 65.7 y0=448.5 ancho=  8.9   <- "c)"
        x0= 68.8 x1=538.2 y0=448.5 ancho=469.4   <- resto del primer renglón
        x0= 56.8 x1=299.1 y0=460.0 ancho=242.3   <- segundo renglón

    `_select_best_instance` se quedaba con el primero: los 8.9 px que se vieron
    en producción.

    Criterio de agrupación -- dos rectángulos consecutivos son la misma
    aparición si:
      - están en el mismo renglón y separados por un hueco chico (continuación
        del match tras un cambio de span), o
      - el segundo empieza un renglón más abajo.

    Dos rects a la misma altura pero MUY separados horizontalmente son
    apariciones distintas (caso real: "GARANT" aparece dos veces en la línea
    y=548.7, en x=129 y x=482).
    """
    if not instances:
        return []

    def _right_edge(rect: Any) -> float:
        x1 = getattr(rect, "x1", None)
        if x1 is not None:
            return float(x1)
        return float(rect.x0) + float(rect.width)

    groups: list[list[Any]] = [[instances[0]]]
    for rect in instances[1:]:
        previous = groups[-1][-1]
        line_height = max(float(previous.height), 1.0)
        line_advance = float(rect.y0) - float(previous.y0)

        same_line = abs(line_advance) <= line_height * 0.3
        if same_line:
            # Continuación en el mismo renglón: el hueco tiene que ser del
            # orden de un espacio, no de media página.
            horizontal_gap = float(rect.x0) - _right_edge(previous)
            belongs = 0 <= horizontal_gap <= line_height * 1.5
        else:
            # Renglón siguiente, con tolerancia para interlineado holgado.
            belongs = 0 < line_advance <= line_height * 1.8

        if belongs:
            groups[-1].append(rect)
        else:
            groups.append([rect])
    return groups


def _select_occurrence_rects(
    page: Any,
    instances: list[Any],
    section_hint: str | None,
    correlation_id: str,
) -> list[Any]:
    """Elige QUÉ aparición resaltar y devuelve TODOS sus renglones.

    Política única para los dos caminos de `compute_highlight_regions` (búsqueda
    exacta y búsqueda por ancla). Antes el camino por ancla no desambiguaba
    nada y devolvía todos los rectángulos de todas las apariciones -- pintaba
    varios párrafos a la vez, uno solo correcto (hallazgo HL-04). Pintar de más
    es peor que no pintar: parece que el sistema está seguro.
    """
    return _select_from_occurrences(
        page, _group_rects_by_occurrence(instances), section_hint, correlation_id
    )


def _select_from_occurrences(
    page: Any,
    occurrences: list[list[Any]],
    section_hint: str | None,
    correlation_id: str,
) -> list[Any]:
    """Misma política de selección, sobre apariciones YA agrupadas.

    La búsqueda por palabras (`_search_citation_by_words`) conoce los límites de
    cada aparición mientras matchea, así que no necesita reagruparlas por
    geometría -- pero sí necesita la misma política para elegir entre varias.
    """
    if not occurrences:
        return []

    if len(occurrences) == 1:
        return occurrences[0]

    if section_hint:
        # Se desambigua entre apariciones usando su primer renglón, y después
        # se devuelve la aparición ENTERA.
        first_rects = [occurrence[0] for occurrence in occurrences]
        chosen = _select_best_instance(
            page=page,
            instances=first_rects,
            section_hint=section_hint,
            correlation_id=correlation_id,
        )
        if chosen:
            for occurrence in occurrences:
                if occurrence[0] is chosen[0]:
                    logger.info(
                        "highlight_occurrence_selected",
                        correlation_id=correlation_id,
                        total_occurrences=len(occurrences),
                        selected_lines=len(occurrence),
                        section_hint=section_hint,
                    )
                    return occurrence

    # Sin hint para desambiguar: la primera aparición en orden de lectura.
    logger.info(
        "highlight_multiple_occurrences_first_kept",
        correlation_id=correlation_id,
        total_occurrences=len(occurrences),
        selected_lines=len(occurrences[0]),
        reason="sin section_hint para desambiguar; resaltar todas confundiría más",
    )
    return occurrences[0]


# Caracteres que se conservan al comparar la cita contra el texto del PDF.
# Todo lo demás -- espacios, saltos de renglón, guiones de corte, comillas
# tipográficas, puntuación -- se descarta, porque es exactamente donde el texto
# del PDF y el de la cita difieren.
_ALNUM_RE = re.compile(r"[^a-z0-9]")


def _fold(text: str) -> str:
    """Colapsa un texto a sólo letras y dígitos, sin acentos ni mayúsculas."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _ALNUM_RE.sub("", stripped.lower())


def _search_citation_by_words(page: Any, citation: str) -> list[list[Any]]:
    """Ubica la cita en la página comparando PALABRAS, no la cadena entera.

    FIX (2026-08-14): `page.search_for()` busca la cadena literal en el texto
    del PDF y falla cuando la cita cruza cualquier costura del maquetado.
    Medido contra el pliego real del usuario, 3 de 6 citas devolvían CERO
    rectángulos:

      - "...la oferta econó|mica."  -> el PDF corta la palabra en dos renglones;
      - "...de cinco |(5) días hábiles" -> salto de renglón en el medio;
      - 'llama a Licitación P|RIVADA para la "Adquisición...' -> el título está
        maquetado con espaciado entre letras, así que "PRIVADA" son dos spans
        distintos, y además las comillas del PDF son tipográficas (“ ”) mientras
        que las de la cita son rectas (").

    Ninguna de esas diferencias existe para el LLM: la cita salió del texto que
    devuelve Azure Document Intelligence, que ya viene reflowed y limpio. Es un
    desajuste entre el texto con el que se GENERA la cita y el texto con el que
    se la BUSCA.

    Esta función compara sobre `_fold()` -- sólo letras y dígitos -- así que los
    saltos de renglón, los guiones de corte, la puntuación y las comillas dejan
    de importar. Devuelve una lista de apariciones; cada aparición es la lista
    de rectángulos de las palabras que la componen, en orden de lectura.
    """
    import fitz  # PyMuPDF

    words = page.get_text("words")
    if not words:
        return []

    target = _fold(citation)
    if not target:
        return []

    # Texto plegado de la página + mapa carácter -> índice de palabra.
    pieces: list[str] = []
    owner: list[int] = []
    for index, word in enumerate(words):
        folded = _fold(word[4])
        if not folded:
            continue
        pieces.append(folded)
        owner.extend([index] * len(folded))
    haystack = "".join(pieces)
    if not haystack:
        return []

    occurrences: list[list[Any]] = []
    start = haystack.find(target)
    while start >= 0:
        first_word = owner[start]
        last_word = owner[start + len(target) - 1]
        occurrences.append([fitz.Rect(words[i][:4]) for i in range(first_word, last_word + 1)])
        start = haystack.find(target, start + 1)

    return occurrences


def _rects_to_regions(rects: list[Any]) -> list[dict[str, float]]:
    """Convierte rectángulos de PyMuPDF al contrato de coordenadas del módulo,
    uniendo en uno solo los fragmentos que caen en el mismo renglón.

    PyMuPDF parte el match por span, así que una cita de 198 caracteres puede
    volver en 24 rectangulitos contiguos. Son correctos, pero el visor tendría
    que dibujar 24 recuadros pegados para representar 3 renglones. Unirlos por
    renglón da la misma superficie con la estructura que el usuario ve.
    """
    if not rects:
        return []

    def _right_edge(rect: Any) -> float:
        x1 = getattr(rect, "x1", None)
        return float(x1) if x1 is not None else float(rect.x0) + float(rect.width)

    lines: list[dict[str, float]] = []
    for rect in rects:
        height = float(rect.height)
        top = float(rect.y0)
        left = float(rect.x0)
        right = _right_edge(rect)

        if lines and abs(top - lines[-1]["y"]) <= max(lines[-1]["height"], 1.0) * 0.3:
            line = lines[-1]
            line["x"] = min(line["x"], left)
            line["_right"] = max(line["_right"], right)
            line["y"] = min(line["y"], top)
            line["height"] = max(line["height"], height)
        else:
            lines.append({"x": left, "y": top, "height": height, "_right": right})

    return [
        {
            "x": line["x"],
            "y": line["y"],
            "width": line["_right"] - line["x"],
            "height": line["height"],
        }
        for line in lines
    ]


def compute_highlight_regions(
    pdf_path: str,
    page_number: int,
    citation: str,
    *,
    correlation_id: str,
    section_hint: str | None = None,
) -> list[dict[str, float]]:
    """Calcula las coordenadas exactas donde aparece una citation en el PDF.
    
    FIX DEFINITIVO (2026-08): Cuando hay múltiples instancias del mismo texto,
    usa section_hint para seleccionar la instancia correcta basándose en
    proximidad a headings/títulos de la sección.
    
    Args:
        pdf_path: Ruta absoluta al PDF
        page_number: Número de página (1-indexed)
        citation: Texto a buscar (puede venir del chunk original)
        correlation_id: ID para logging
        section_hint: Hint de sección (ej: "Objeto y Alcance") para disambiguación
    
    Returns:
        Lista de rectángulos con coordenadas top-left origin (estándar web):
        [{"x": float, "y": float, "width": float, "height": float}]
        Lista vacía si no se encuentra el texto.

    Note:
        CONTRATO DE COORDENADAS (fijado en la auditoría 2026-08-13, hallazgo
        HL-01) -- toda función de este módulo que devuelva `highlight_regions`
        debe respetarlo:

          - origen TOP-LEFT: (0, 0) es la esquina superior izquierda de la
            página y `y` crece hacia abajo;
          - `y` es la distancia desde el borde SUPERIOR de la página hasta el
            borde SUPERIOR del rectángulo;
          - unidad: PUNTOS de PDF, en el sistema de la página SIN escalar
            (el consumidor multiplica por su propio factor de zoom).

        MuPDF ya normaliza el PDF a origen top-left: `page.rect` es
        (0, 0, width, height) con `y` creciendo hacia abajo, y `search_for()`
        devuelve `Rect` en ese mismo sistema. Por eso `rect.y0` se devuelve
        tal cual: NO hay ninguna conversión que hacer. La versión anterior
        aplicaba `page_height - rect.y1` bajo la premisa (falsa) de que
        PyMuPDF usa bottom-left, lo que espejaba verticalmente cada región.
        El visor compensaba con una segunda inversión, así que el resultado
        solo era correcto en zoom exactamente 1.0 y para este camino; el
        camino de bbox almacenado (que ya emitía top-left) salía espejado.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "highlight_pymupdf_not_installed",
            correlation_id=correlation_id,
            message="PyMuPDF (fitz) no está instalado. Instalar con: pip install PyMuPDF",
        )
        return []
    
    # Threshold configurable para longitud mínima de citation
    from shared.config import get_settings
    settings = get_settings()
    min_length = getattr(settings, "highlight_citation_min_length", 3)
    
    if not citation or len(citation.strip()) < min_length:
        logger.warning(
            "highlight_citation_too_short",
            correlation_id=correlation_id,
            citation_length=len(citation.strip()),
            min_length_required=min_length,
        )
        return []
    
    try:
        doc = fitz.open(pdf_path)
        
        if page_number < 1 or page_number > len(doc):
            logger.warning(
                "highlight_invalid_page_number",
                correlation_id=correlation_id,
                page_number=page_number,
                total_pages=len(doc),
            )
            return []
        
        page = doc[page_number - 1]  # PyMuPDF usa 0-indexed

        # Estrategia 1: Búsqueda exacta (case-insensitive por defecto en PyMuPDF)
        text_instances = page.search_for(citation)
        
        if text_instances:
            # Los rects ya vienen en el contrato de coordenadas del módulo
            # (top-left, puntos, página sin escalar) -- ver docstring.
            selected = _select_occurrence_rects(
                page, text_instances, section_hint, correlation_id
            )
            regions = _rects_to_regions(selected)
            logger.info(
                "highlight_found_exact",
                correlation_id=correlation_id,
                page_number=page_number,
                rects_returned_by_search=len(text_instances),
                regions_count=len(regions),
            )
            return regions
        
        # Estrategia 2: búsqueda por palabras, tolerante a las costuras del
        # maquetado del PDF (saltos de renglón dentro de una palabra, espaciado
        # entre letras, comillas tipográficas, guiones de corte). Reemplaza al
        # viejo camino "por ancla", que buscaba las primeras 10 palabras con
        # `search_for` -- o sea, la misma búsqueda literal que ya había fallado,
        # sólo que sobre menos texto y por lo tanto MÁS ambigua. Ver
        # `_search_citation_by_words` para el detalle de qué falla y por qué.
        occurrences = _search_citation_by_words(page, citation)
        if occurrences:
            selected = _select_from_occurrences(
                page, occurrences, section_hint, correlation_id
            )
            regions = _rects_to_regions(selected)
            logger.info(
                "highlight_found_by_words",
                correlation_id=correlation_id,
                page_number=page_number,
                occurrences=len(occurrences),
                regions_count=len(regions),
                reason="search_for no matcheó: la cita cruza una costura del maquetado",
            )
            return regions

        logger.warning(
            "highlight_not_found_in_page",
            correlation_id=correlation_id,
            page_number=page_number,
            citation_preview=citation[:50],
        )
        return []
        
    except Exception as exc:
        logger.error(
            "highlight_computation_failed",
            correlation_id=correlation_id,
            page_number=page_number,
            error=str(exc),
        )
        return []
    finally:
        if "doc" in locals():
            doc.close()


def _resolve_source_chunk(
    source: dict,
    chunks_by_doc_page: dict | None,
    correlation_id: str,
) -> dict | None:
    """El chunk del que salió esta cita, si se lo puede identificar.

    Prioridad al `chunk_id` que anotó `_verify_citation_grounding` (ATR-01):
    adivinar por texto es ambiguo justo donde más duele -- una frase como
    "conforme lo establecido en el presente pliego" aparece en varios chunks de
    la misma página, y el primero que matcheara ganaba.
    """
    if not chunks_by_doc_page:
        return None

    candidates = chunks_by_doc_page.get((source.get("document_id"), source.get("page_number")), [])
    if not candidates:
        return None

    chunk_id = source.get("chunk_id")
    if chunk_id:
        for chunk in candidates:
            if str(chunk.get("id") or chunk.get("chunk_id") or "") == str(chunk_id):
                return chunk
        logger.debug(
            "highlight_chunk_id_not_in_index",
            correlation_id=correlation_id,
            chunk_id=chunk_id,
            fallback="búsqueda por texto entre los chunks de la página",
        )

    citation_normalized = _normalize_for_search(str(source.get("citation", "")))
    if not citation_normalized:
        return None
    for chunk in candidates:
        if citation_normalized in _normalize_for_search(str(chunk.get("content", ""))):
            return chunk
    return None


def compute_highlights_for_sources(
    sources: list[dict[str, Any]],
    document_id_to_blob_path: dict[str, str],
    correlation_id: str,
    *,
    category_key: str | None = None,
    chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Enriquece una lista de sources con highlight_regions pre-computadas.
    
    SOLUCIÓN DEFINITIVA V4 (2026-08): Usa campo 'source' estructurado.
    - Migrado de campo legacy 'blocks' a nuevo campo 'source.blocks'
    - Estructura: source.blocks = [{block_id, bbox, text}]
    - Filtra qué block específico contiene la citation
    - Solo agrega bbox del block que matchea (no todos los blocks del chunk)
    - Si no hay source o no matchea, deja highlight_regions vacío
    
    Args:
        sources: Lista de sources (output de synthesis)
        document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF (NO usado)
        correlation_id: ID para logging
        category_key: Clave de categoría (ej: "objeto_alcance") para logs
        chunks_by_doc_page: Índice de chunks por (document_id, page_number) para lookup de source
    
    Returns:
        Lista de sources enriquecidas con campo "highlight_regions"
    """
    enriched_sources = []
    stats = {"total": 0, "with_bbox": 0, "no_bbox": 0, "multiple_blocks": 0}
    
    for source in sources:
        stats["total"] += 1
        source_copy = dict(source)
        document_id = source.get("document_id")
        page_number = source.get("page_number")
        citation = source.get("citation", "")
        
        if not document_id or not page_number or not citation:
            # Source incompleta, conservar sin highlight
            source_copy["highlight_regions"] = []
            stats["no_bbox"] += 1
            enriched_sources.append(source_copy)
            continue
        
        # Buscar chunk que contenga esta citation
        regions = []

        # FIX CRÍTICO (auditoría 2026-08-12, hallazgo C-2): intentar primero
        # búsqueda viva con PyMuPDF sobre el PDF real (compute_highlight_regions),
        # que ubica la citation directamente en el documento en vez de confiar en
        # el bbox pre-computado en ingestion (el cual podía quedar desalineado
        # por el bug posicional de _parse_markdown_blocks corregido en esta misma
        # auditoría). Solo se intenta cuando tenemos una ruta real de PDF; si no
        # hay PDF disponible o la búsqueda viva no encuentra nada, se cae al
        # matching por bbox almacenado de más abajo (retrocompatible: todos los
        # tests existentes pasan document_id_to_blob_path={}, por lo que este
        # bloque nunca se activa para ellos).
        # ATR-01 (auditoría 2026-08-13): el chunk que verificó la cita en
        # `_verify_citation_grounding` viaja en la source como `chunk_id`. Su
        # `section_path` es un hint MUCHO mejor que el nombre de la categoría
        # para desambiguar entre varias apariciones de la misma frase en la
        # página: dice en qué artículo del pliego estaba la evidencia, no a qué
        # categoría pertenece el dato.
        source_chunk = _resolve_source_chunk(source, chunks_by_doc_page, correlation_id)
        section_hint = None
        if source_chunk:
            section_hint = str(source_chunk.get("section_path") or "") or None
            if not section_hint:
                heading_path = source_chunk.get("heading_path") or []
                if isinstance(heading_path, list) and heading_path:
                    section_hint = " ".join(str(part) for part in heading_path)
        if not section_hint and category_key:
            section_hint = category_key.replace("_", " ")

        pdf_path = (document_id_to_blob_path or {}).get(document_id)
        if pdf_path:
            live_regions = compute_highlight_regions(
                pdf_path,
                page_number,
                citation,
                correlation_id=correlation_id,
                section_hint=section_hint,
            )
            if live_regions:
                source_copy["highlight_regions"] = live_regions
                stats["with_bbox"] += 1
                stats["from_live_search"] = stats.get("from_live_search", 0) + 1
                logger.debug(
                    "highlight_from_live_pymupdf_search",
                    correlation_id=correlation_id,
                    document_id=document_id,
                    page_number=page_number,
                    category_key=category_key,
                    regions_count=len(live_regions),
                )
                enriched_sources.append(source_copy)
                continue

        # FIX (2026-08-14): acá vivía el "camino de bbox almacenado". Cuando la
        # búsqueda viva no encontraba la cita, se emitía el bbox del BLOQUE de
        # Azure Document Intelligence que la contenía -- y ese bbox es el del
        # PÁRRAFO completo (`min/max` sobre el polígono del párrafo, ver
        # `extraction/document_intelligence.py::_extract_bounding_boxes`). Una
        # cita de 100 caracteres dentro de un párrafo de 600 producía un
        # rectángulo del párrafo entero: ESE era el "resaltado por párrafo".
        #
        # Pintar un párrafo entero es peor que no pintar nada. Le dice a la
        # persona "la evidencia es todo esto", que no es cierto, y no deja
        # ninguna señal de que el sistema no supo ubicar la cita. Sin regiones,
        # el visor marca sobre la capa de texto de react-pdf -- degradado, pero
        # acotado al texto de la cita y siempre bien posicionado.
        #
        # El chunk NO se dejó de usar: pasó a alimentar el `section_hint` de la
        # búsqueda viva (ver más arriba), que es donde su identidad realmente
        # sirve: elegir CUÁL de las apariciones de la cita en la página es la
        # correcta.
        if regions:
            stats["with_bbox"] += 1
            logger.debug(
                "highlight_from_azure_di_blocks",
                correlation_id=correlation_id,
                document_id=document_id,
                page_number=page_number,
                category_key=category_key,
                regions_count=len(regions),
            )
        else:
            stats["no_bbox"] += 1
            logger.warning(
                "highlight_no_blocks_available",
                correlation_id=correlation_id,
                document_id=document_id,
                page_number=page_number,
                category_key=category_key,
                citation_preview=citation[:100],
                message="No blocks found for source - highlighting disabled for precision",
            )
        
        source_copy["highlight_regions"] = regions
        enriched_sources.append(source_copy)
    
    # Log stats finales
    bbox_rate = (stats["with_bbox"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(
        "highlight_enrichment_complete",
        correlation_id=correlation_id,
        category_key=category_key,
        total_sources=stats["total"],
        with_bbox=stats["with_bbox"],
        no_bbox=stats["no_bbox"],
        multiple_blocks_filtered=stats["multiple_blocks"],
        from_live_search=stats.get("from_live_search", 0),
        bbox_rate_pct=round(bbox_rate, 1),
    )
    
    return enriched_sources
