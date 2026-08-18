from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable
import unicodedata

import structlog
from langgraph.graph import END, StateGraph

from analysis.extraction.extractors import (
    extractor_anexos_obligatorios,
    extractor_causales,
    extractor_criterios_evaluacion,
    extractor_garantias,
    extractor_identificacion_procedimiento,
    extractor_objeto_alcance,
    extractor_plazos,
    extractor_requisitos_admisibilidad,
)
from pydantic import BaseModel, ValidationError

from analysis.extraction.extractors.base import shorten_citation_to_evidence
from analysis.extraction.schemas import (
    CITATION_MAX_CHARS,
    CITATION_MIN_CHARS,
    NOT_ANALYZED_STATUS,
    AnexoObligatorioItem,
    CausalRechazoItem,
    CriterioEvaluacionItem,
    ExtractedData,
    GarantiaItem,
    IdentificacionProcedimientoItem,
    ObjetoAlcanceItem,
    PlazoItem,
    RequisitoAdmisibilidadItem,
)
from analysis.extraction.state import GraphState
from analysis.extraction.synthesis import (
    NARRATIVE_CATEGORIES,
    enrich_narrative_with_highlights,
    run_synthesis,
)

logger = structlog.get_logger(__name__)


def _cleanup_temp_highlights(analysis_id: str) -> None:
    """Limpia archivos temporales de highlights descargados desde Azure.
    
    FIX CRÍTICO (2026-08): Los PDFs descargados desde Azure para calcular
    highlights se guardan en /tmp/highlights-{analysis_id}/. Esta función
    los elimina después de que synthesize_node complete el cálculo.
    
    FIX MEDIUM (#8): Ahora mide tamaño del directorio y loggea error prominente
    si falla, para facilitar monitoreo de /tmp y detectar problemas de cleanup.
    
    Args:
        analysis_id: ID del análisis
    """
    try:
        from pathlib import Path
        import shutil
        import tempfile
        
        temp_dir = Path(tempfile.gettempdir()) / f"highlights-{analysis_id}"
        if not temp_dir.exists():
            logger.debug(
                "temp_highlights_already_clean",
                analysis_id=analysis_id,
                temp_dir=str(temp_dir),
            )
            return
        
        # Medir tamaño del directorio antes de limpiarlo
        total_size = sum(f.stat().st_size for f in temp_dir.rglob("*") if f.is_file())
        file_count = sum(1 for _ in temp_dir.rglob("*") if _.is_file())
        
        shutil.rmtree(temp_dir)
        logger.info(
            "temp_highlights_cleaned",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            files_removed=file_count,
            bytes_freed=total_size,
        )
    except PermissionError as exc:
        # Permission errors son más probables de ser problemas del sistema
        logger.error(
            "temp_highlights_cleanup_permission_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            action_required="Check /tmp permissions and disk space",
        )
    except OSError as exc:
        # Disk full, read-only filesystem, etc.
        logger.error(
            "temp_highlights_cleanup_os_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            action_required="Check disk space and filesystem health",
        )
    except Exception as exc:
        # Otros errores inesperados
        logger.error(
            "temp_highlights_cleanup_unexpected_error",
            analysis_id=analysis_id,
            temp_dir=str(temp_dir),
            error=str(exc),
            error_type=type(exc).__name__,
            action_required="Investigate cleanup failure - /tmp may be filling up",
            exc_info=True,
        )



def _build_document_mapping(analysis_id: str, db_session: Any) -> dict[str, str]:
    """Construye mapeo document_id → ruta absoluta del PDF en blob storage.
    
    FIX CRÍTICO (2026-08): Necesario para calcular coordenadas de highlight
    con PyMuPDF en synthesize_node. Funciona tanto en local como en Azure
    (descarga PDFs temporalmente desde Azure Blob Storage).
    
    Args:
        analysis_id: ID del análisis
        db_session: Sesión de SQLAlchemy (puede ser None en cosmos_only_mode o tests)
    
    Returns:
        Diccionario document_id → ruta absoluta del PDF
        (vacío si db_session es None en development/test)
    
    Raises:
        RuntimeError: Si db_session es None en producción sin cosmos_only_mode
    
    Note:
        En Azure, descarga PDFs a /tmp/highlights-{analysis_id}/. Estos archivos
        deben limpiarse manualmente después de calcular highlights.
    """
    from shared.config import get_settings
    settings = get_settings()
    
    # Obtener documentos según el modo de persistencia
    documents = []
    
    if db_session is not None:
        # Path normal: PostgreSQL
        from documents.models import Document
        documents = (
            db_session.query(Document)
            .filter(Document.analysis_id == analysis_id, Document.deleted_at.is_(None))
            .all()
        )
        # Convertir a formato común (lista de objetos con .id y .blob_name)
        # SQLAlchemy models ya tienen estos atributos
    elif settings.is_cosmos_only_mode():
        # Path Cosmos: obtener documentos desde Cosmos DB
        try:
            from analysis.cosmos_runtime import get_cosmos_container
            
            container = get_cosmos_container()
            query = (
                "SELECT c.document_id, c.blob_name FROM c "
                "WHERE c.type = 'document' AND c.analysis_id = @analysis_id AND c.deleted = false"
            )
            items = container.query_items(
                query=query,
                parameters=[{"name": "@analysis_id", "value": analysis_id}],
                partition_key=analysis_id,
            )
            
            # Convertir a objetos simples con .id y .blob_name para compatibilidad
            class DocumentDTO:
                def __init__(self, doc_id: str, blob_name: str):
                    self.id = doc_id
                    self.blob_name = blob_name
            
            documents = [DocumentDTO(item["document_id"], item["blob_name"]) for item in items]
            
            logger.info(
                "build_document_mapping_cosmos_source",
                analysis_id=analysis_id,
                documents_found=len(documents),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "build_document_mapping_cosmos_query_failed",
                analysis_id=analysis_id,
                error=str(exc),
            )
            return {}
    elif settings.is_production:
        # Producción sin db_session ni cosmos_only_mode: error
        logger.error(
            "build_document_mapping_failed_no_session",
            analysis_id=analysis_id,
            reason="db_session is None in production context without cosmos_only_mode",
        )
        raise RuntimeError(
            f"Cannot build document mapping for analysis {analysis_id}: "
            "db_session is required in production for highlight computation"
        )
    else:
        # Development/test sin db_session: solo advertir
        logger.warning(
            "build_document_mapping_skipped",
            analysis_id=analysis_id,
            reason="db_session not available (test context)",
        )
        return {}
    
    # Construir mapeo con los documentos obtenidos (PostgreSQL o Cosmos)
    try:
        from shared.adapters.azure_blob_storage import AzureBlobStorageAdapter
        
        # Usar solo Azure Blob Storage
        blob_storage = AzureBlobStorageAdapter(
            settings.azure_blob_connection_string,
            settings.azure_blob_container_name,
        )
        
        mapping = {}
        
        # Local: acceso directo al filesystem
        if hasattr(blob_storage, "root"):
            for doc in documents:
                blob_path = blob_storage.root / doc.blob_name
                if blob_path.exists():
                    mapping[doc.id] = str(blob_path)
                else:
                    logger.warning(
                        "document_blob_not_found",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        blob_name=doc.blob_name,
                    )
        
        # Azure: descargar PDFs temporalmente
        elif hasattr(blob_storage, "download_to_temp"):
            from pathlib import Path
            import tempfile
            
            # Crear directorio temporal para este análisis
            temp_dir = Path(tempfile.gettempdir()) / f"highlights-{analysis_id}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            for doc in documents:
                temp_path = temp_dir / f"{doc.id}.pdf"
                try:
                    blob_storage.download_to_temp(doc.blob_name, str(temp_path))
                    mapping[doc.id] = str(temp_path)
                    logger.info(
                        "document_downloaded_for_highlights",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        temp_path=str(temp_path),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "document_download_failed",
                        analysis_id=analysis_id,
                        document_id=doc.id,
                        blob_name=doc.blob_name,
                        error=str(exc),
                    )
        
        else:
            logger.warning(
                "build_document_mapping_unsupported_storage",
                analysis_id=analysis_id,
                storage_type=type(blob_storage).__name__,
            )
        
        logger.info(
            "build_document_mapping_completed",
            analysis_id=analysis_id,
            documents_mapped=len(mapping),
        )
        return mapping
        
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "build_document_mapping_failed",
            analysis_id=analysis_id,
            error=str(exc),
        )
        return {}


def _merge_category_status(*statuses: str) -> str:
    pool = {str(status or "").strip() for status in statuses}
    if "success" in pool:
        return "success"
    if "partial" in pool:
        return "partial"
    if "not_applicable" in pool:
        return "not_applicable"
    if "not_found" in pool:
        return "not_found"
    if "failed" in pool:
        return "failed"
    return "unknown"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().strip().split())


def _canonical_plazo_tipo(value: str, *, item: dict | None = None) -> str:
    """Canonicaliza el tipo de plazo. Si el tipo original es ambiguo ('otro'),
    intenta rescatar el tipo correcto buscando keywords en texto_original."""
    text = _normalize_text(value)
    if not text:
        return "otro"

    # Intentar rescate por texto_original si tipo es "otro"
    if text == "otro" and item:
        # Buscar en texto_original y expresion_relativa
        texto_completo = " ".join([
            str(item.get("texto_original") or ""),
            str(item.get("expresion_relativa") or ""),
        ])
        rescue_text = _normalize_text(texto_completo)
        
        # Aplicar misma lógica de reconocimiento pero sobre el texto completo
        if "respuesta" in rescue_text and "consulta" in rescue_text:
            return "respuesta_consultas"
        if "consulta" in rescue_text:
            return "consultas"
        if "impugn" in rescue_text or "recurs" in rescue_text:
            return "impugnacion"
        if "visita" in rescue_text:
            return "visita_lugar"
        if "apertura" in rescue_text:
            return "apertura_ofertas"
        if "mantenimiento" in rescue_text and "oferta" in rescue_text:
            return "mantenimiento_oferta"
        if "adjudic" in rescue_text:
            return "adjudicacion"
        if "firma" in rescue_text and "contrato" in rescue_text:
            return "firma_contrato"
        if any(term in rescue_text for term in ["ejecucion", "entrega", "provision", "suministro"]):
            return "plazo_ejecucion"
        if any(term in rescue_text for term in ["presentacion", "recepcion"]):
            return "presentacion_ofertas"
        # Si no rescatamos nada, mantener "otro"
        return "otro"

    # Reconocimiento estándar por tipo
    if "respuesta" in text and "consulta" in text:
        return "respuesta_consultas"
    if "consulta" in text:
        return "consultas"
    if "visita" in text and "obra" in text:
        return "visita_lugar"
    if "apertura" in text:
        return "apertura_ofertas"
    if "mantenimiento" in text and "oferta" in text:
        return "mantenimiento_oferta"
    if "adjudic" in text:
        return "adjudicacion"
    if "firma" in text and "contrato" in text:
        return "firma_contrato"
    if "impugn" in text:
        return "impugnacion"
    # Plazo de ejecución/entrega (del contrato, no del procedimiento)
    if any(term in text for term in ["ejecucion", "entrega", "provision", "suministro"]):
        return "plazo_ejecucion"
    if (
        "presentacion de ofertas" in text
        or "cierre de recepcion de ofertas" in text
        or "fecha limite de presentacion" in text
        or ("presentacion" in text and "oferta" in text)
        or ("recepcion" in text and "oferta" in text)
    ):
        return "presentacion_ofertas"
    return "otro"


def _canonical_garantia_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otra"

    if "cumplimiento" in text and "contrato" in text:
        return "cumplimiento_contrato"
    if "anticipo" in text:
        return "anticipo"
    if (
        "mantenimiento" in text
        or "seriedad" in text
        or ("garantia" in text and "oferta" in text)
        or ("caucion" in text and "oferta" in text)
        or ("fianza" in text and "oferta" in text)
    ):
        return "mantenimiento_oferta"
    return "otra"


_TIPOS_IDENTIFICACION_VALIDOS = {
    "organismo_convocante",
    "expediente",
    "numero_procedimiento",
    "tipo_procedimiento",
    "presupuesto_oficial",
    "jurisdiccion",
    "denominacion",
}


def _canonical_identificacion_tipo(value: str) -> str | None:
    """Mapea el `tipo` que devuelve el LLM al enum `TipoIdentificacion`.
    Devuelve None si no corresponde a ninguno: esos ítems no pueden ir al campo
    canónico (pydantic los rechazaría y tumbaría merge_node entero), pero sí
    sobreviven en el campo legacy `datos_procedimiento`, que acepta tipo libre."""
    text = _normalize_text(value)
    if not text:
        return None
    if text in _TIPOS_IDENTIFICACION_VALIDOS:
        return text
    if "organismo" in text or "convocante" in text:
        return "organismo_convocante"
    if "expediente" in text:
        return "expediente"
    if "presupuesto" in text:
        return "presupuesto_oficial"
    if "jurisdicc" in text:
        return "jurisdiccion"
    # Antes del catch-all de "proced": una variante como "denominacion del
    # procedimiento" contiene ambas palabras, y sin este check quedaría mal
    # clasificada como numero_procedimiento.
    if "denomina" in text or "nombre del llamado" in text or "nombre_del_llamado" in text:
        return "denominacion"
    if "proced" in text:
        if "tipo" in text:
            return "tipo_procedimiento"
        return "numero_procedimiento"
    return None


def _canonical_causal_tipo(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "otra"

    if any(term in text for term in ["formal", "document", "garantia", "presentacion", "termino"]):
        return "formal"
    if any(term in text for term in ["tecnic", "especificacion", "muestra"]):
        return "tecnica"
    if any(term in text for term in ["econom", "precio", "cotizacion"]):
        return "economica"
    if any(term in text for term in ["legal", "inhabilit", "registro", "juridic"]):
        return "legal"
    if any(term in text for term in ["etica", "conflicto", "corrup", "integridad"]):
        return "etica"
    return "otra"


def _plazo_dedup_value(item: dict) -> str:
    """Huella del "valor" de un plazo, para no fusionar dos plazos del mismo
    tipo que en realidad dicen cosas distintas (eso es un conflicto, no un
    duplicado). Normaliza el texto para que variaciones menores se reconozcan
    como duplicados (ej: '12 meses' vs '12 (doce) meses')."""
    raw_value = str(item.get("fecha") or item.get("expresion_relativa") or item.get("texto_original") or "")
    # Normalizar para que "12 meses desde..." y "12 (doce) meses contados desde..."
    # se reconozcan como el mismo plazo
    normalized = _normalize_text(raw_value)
    # Eliminar paréntesis explicativos comunes: "12 (doce)" → "12"
    normalized = re.sub(r'\(\w+\)', '', normalized).strip()
    # Colapsar múltiples espacios
    normalized = " ".join(normalized.split())
    return normalized


def _garantia_dedup_value(item: dict) -> str:
    return f"{item.get('monto_porcentaje')}|{item.get('monto_valor')}"


def _dedupe_source_references(refs: list[dict]) -> list[dict]:
    seen: set[tuple[str, int, str]] = set()
    result: list[dict] = []
    for ref in refs:
        key = (
            str(ref.get("document_id", "")),
            int(ref.get("page_number", 0) or 0),
            _normalize_text(str(ref.get("citation", ""))),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _merge_typed_item_group(items: list[dict]) -> dict:
    """Fusiona ítems que citan el mismo hecho (mismo tipo canónico y mismo
    valor identificador) en uno solo, combinando sus citas. Sin esto, un mismo
    plazo o garantía citado desde más de un fragmento/documento queda duplicado
    en la lista final (ej. dos ítems de "mantenimiento de oferta") en vez de
    aparecer una sola vez con todas sus fuentes."""
    primary = max(
        items,
        key=lambda item: (
            1 if item.get("extraction_status") == "success" else 0,
            float(item.get("confidence", 0.0) or 0.0),
        ),
    )
    merged = dict(primary)

    all_refs: list[dict] = []
    for item in items:
        all_refs.extend(item.get("source_references", []))
    merged["source_references"] = _dedupe_source_references(all_refs)

    # Completa campos que el primario dejó vacíos con lo que traigan los demás
    # ítems del grupo, sin pisar ningún valor que el primario sí tenga.
    for item in items:
        for key, value in item.items():
            if key in {"source_references", "confidence", "extraction_status"}:
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value

    return merged


def _merge_duplicate_items_by_key(items: list[dict], key_fn: Callable[[dict], tuple]) -> list[dict]:
    """Version generalizada de _merge_duplicate_typed_items: agrupa por una
    clave arbitraria (no necesariamente tipo + un valor) y fusiona cada grupo
    con _merge_typed_item_group."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    order: list[tuple] = []
    for item in items:
        key = key_fn(item)
        if key not in grouped:
            order.append(key)
        grouped[key].append(item)

    merged: list[dict] = []
    for key in order:
        group = grouped[key]
        merged.append(group[0] if len(group) == 1 else _merge_typed_item_group(group))
    return merged


def _merge_duplicate_typed_items(items: list[dict], dedup_value: Callable[[dict], str]) -> list[dict]:
    return _merge_duplicate_items_by_key(items, lambda item: (str(item.get("tipo", "")), dedup_value(item)))


def _normalized_valor_key(item: dict) -> str:
    """Huella de texto para detectar el mismo hecho extraido dos veces con
    redaccion casi identica (tipico cuando el mismo parrafo cae en dos chunks
    solapados). Solo normaliza espacios/mayusculas -- deliberadamente NO hace
    matching difuso (por substring o similitud) para no fusionar por error dos
    hechos distintos que comparten palabras."""
    return " ".join(str(item.get("valor", "")).split()).strip().lower()


def calculate_confidence(source_references: list[dict], extraction_status: str) -> float:
    if extraction_status in {"failed", "not_found"}:
        return 0.0

    if extraction_status == "not_applicable":
        return 0.7 if source_references else 0.0

    if not source_references:
        return 0.3

    confidence = 0.5
    if len(source_references) > 1:
        confidence += 0.3
    elif len(source_references) == 1:
        confidence += 0.2

    # FIX (auditoría 2026-08-13, hallazgo SYN-05): acá había un ajuste por LARGO
    # de la cita: +0.2 por encima de 100 caracteres, -0.2 por debajo de 25.
    #
    # El largo de la cita no mide la calidad de la evidencia: mide una decisión
    # del propio pipeline. `_expand_short_paragraph_citation`,
    # `_widen_citation_with_chunk_context` y `_rescue_paragraph_citation`
    # ensanchan la cita hasta llegar a `CITATION_PREFERRED_MIN_CHARS`. O sea que
    # el sistema alargaba la cita y después se premiaba a sí mismo por tenerla
    # larga.
    #
    # Y desde que `CITATION_MAX_CHARS` bajó a 120 (las citas ahora son cortas a
    # propósito, ver el hallazgo de legibilidad), el bonus de +0.2 pasó a ser
    # casi inalcanzable: habría bajado la confianza de todas las categorías sin
    # que cambiara nada de la evidencia.
    #
    # Lo que sí mide calidad de evidencia -- cuántas fuentes independientes
    # respaldan el dato, y si la extracción fue completa o parcial -- ya está
    # contemplado arriba y abajo.

    if extraction_status == "partial":
        confidence -= 0.2

    return max(0.0, min(confidence, 1.0))


def get_confidence_level(confidence: float) -> str:
    if confidence >= 0.8:
        return "alta"
    if confidence >= 0.6:
        return "media"
    return "baja"


def _normalize_confidence(item: dict) -> dict:
    """La confianza que ve el usuario se CALCULA; no se le pregunta al modelo.

    FIX (auditoría 2026-08-13, hallazgo SYN-05): antes, si el item traía
    `confidence` -- y el prompt se lo pide explícitamente al LLM, así que casi
    siempre lo trae -- se respetaba ese número y `calculate_confidence` no corría
    nunca. Lo que el usuario leía como "confianza alta" era la autoevaluación del
    mismo modelo que produjo el dato.

    No es una opinión de más entre varias: `get_confidence_level` marca "alta" a
    partir de 0.8, y el prompt define ese rango como "usable sin abrir el PDF".
    Un modelo que se equivoca al extraer se equivoca también al puntuarse.

    Ahora la confianza sale siempre de `calculate_confidence`, que es
    determinista y auditable: cuántas fuentes verificadas respaldan el dato y si
    la extracción quedó completa o parcial. La autoevaluación del modelo se
    conserva en `confidence_llm` -- sirve para telemetría (¿el modelo sabe
    cuándo se está equivocando?), no para decidir qué se le muestra a la
    persona.
    """
    status = str(item.get("extraction_status", "success"))
    refs = list(item.get("source_references", []))

    if "confidence" in item:
        try:
            item["confidence_llm"] = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            item["confidence_llm"] = None

    item["confidence"] = calculate_confidence(refs, status)
    item["confidence_level"] = get_confidence_level(float(item.get("confidence", 0.0) or 0.0))
    return item


def _penalize_unverifiable(item: dict) -> dict:
    """Marca como partial los items sin citas utilizables. El piso es el mismo
    `CITATION_MIN_CHARS` que usan el verificador de grounding, el schema y el
    prompt: cuando cada capa tenia su propio umbral, una cita literal y
    verificable sobrevivia al grounding y despues era degradada -- o rechazada
    por pydantic -- solo por su largo, que depende de como redacta cada pliego."""
    refs = list(item.get("source_references", []))
    status = str(item.get("extraction_status", ""))
    if status in {"success", "partial"}:
        usable = [ref for ref in refs if len(str(ref.get("citation", "")).strip()) >= CITATION_MIN_CHARS]
        if not usable:
            item["extraction_status"] = "partial"
            item["_warning"] = "cita_insuficiente"
    return item


def _category_confidence(items: list[dict]) -> float:
    """Calcula un score de confianza agregado para toda la categoría."""
    with_confidence = [
        float(item.get("confidence", 0.0) or 0.0)
        for item in items
        if float(item.get("confidence", 0.0) or 0.0) > 0.0
    ]
    if not with_confidence:
        return 0.0
    return round(sum(with_confidence) / len(with_confidence), 2)


def _enforce_citation_contract(items: list[dict]) -> list[dict]:
    """Normaliza las citas al contrato de `SourceReference` ANTES de que pydantic
    lo valide: recorta las que exceden el máximo y descarta las que no llegan al
    mínimo.

    Sin esto, una sola cita fuera de rango hacía que `ExtractedData(**...)`
    lanzara ValidationError dentro de merge_node y se perdiera el análisis
    ENTERO -- las ocho categorías, no solo la del ítem defectuoso. Y como el
    largo de una cita depende de cómo redacta cada pliego, el mismo sistema
    fallaba o no según el documento. El contrato se hace cumplir degradando el
    dato afectado, nunca tirando abajo el resto."""
    normalized_items: list[dict] = []
    for item in items:
        refs: list[dict] = []
        for ref in item.get("source_references", []):
            citation = str(ref.get("citation", "") or "").strip()
            if len(citation) < CITATION_MIN_CHARS:
                continue
            if len(citation) > CITATION_MAX_CHARS:
                # Se recorta a la ventana que contiene el dato del item, no al
                # prefijo: la carátula de un pliego respalda varios items y el
                # dato de cada uno cae en un lugar distinto del mismo texto.
                citation = shorten_citation_to_evidence(citation, item)
            normalized_ref = dict(ref)
            normalized_ref["citation"] = citation
            refs.append(normalized_ref)

        normalized_item = dict(item)
        normalized_item["source_references"] = refs
        normalized_items.append(normalized_item)

    return normalized_items


def _keep_schema_valid_items(
    items: list[dict],
    model: type[BaseModel],
    status: str,
    *,
    category: str,
    correlation_id: str,
    quality: dict[str, dict[str, int]] | None = None,
) -> tuple[list[dict], str]:
    """Descarta los items que no cumplen su schema, en vez de dejar que uno solo
    haga fallar la validacion de `ExtractedData` entera.

    `merge_node` construye `ExtractedData(**extracted_data)` con las OCHO
    categorias juntas: si un unico item trae un `tipo` fuera de su enum (caso
    real: `tipo="técnico"` en criterios_evaluacion, donde el enum admite
    "metodo"/"criterio"), pydantic levanta ValidationError y se pierde el
    analisis completo, no solo esa categoria. Y que el LLM emita o no un tipo
    fuera del enum depende de como esta redactado cada pliego -- otra fuente de
    resultados distintos entre documentos equivalentes.

    Validar item por item acota el dano al item defectuoso. Es una red de
    seguridad generica: cubre cualquier violacion de schema (enum, tipo de dato,
    campo faltante), no solo las que anticipamos con los `_canonical_*_tipo`."""
    valid: list[dict] = []
    invalid: list[str] = []

    for item in items:
        try:
            model(**item)
        except ValidationError as exc:
            invalid.append(f"{item.get('tipo')!r}: {exc.errors()[0].get('msg', '')}"[:200])
            continue
        valid.append(item)

    normalized_status = str(status or "unknown")
    if invalid:
        logger.warning(
            "items_descartados_por_schema",
            correlation_id=correlation_id,
            category=category,
            dropped=len(invalid),
            kept=len(valid),
            reasons=invalid[:5],
        )
        if normalized_status in {"success", "unknown"}:
            normalized_status = "partial"

        if quality is not None:
            registro = quality.setdefault(category, {})
            registro["descartados_por_formato"] = registro.get("descartados_por_formato", 0) + len(invalid)
            registro["conservados"] = len(valid)

    return valid, normalized_status


def _source_order_key(item: dict) -> tuple[int, str, int, str]:
    refs = item.get("source_references") or []
    if not isinstance(refs, list) or not refs:
        return (1, "", 0, "")

    first_ref = refs[0] if isinstance(refs[0], dict) else {}
    is_primary = bool(first_ref.get("is_primary"))
    filename = str(first_ref.get("filename") or "").lower()
    page_number = int(first_ref.get("page_number") or 0)
    document_id = str(first_ref.get("document_id") or "")
    return (0 if is_primary else 1, filename, page_number, document_id)


def _drop_items_without_sources(
    items: list[dict],
    status: str,
    *,
    category: str = "",
    quality: dict[str, dict[str, int]] | None = None,
) -> tuple[list[dict], str]:
    """El contrato final exige al menos una fuente por item persistido.
    Si el grounding dejó items sin citas verificables, se descartan y la
    categoría baja a partial cuando antes figuraba como success.

    ATR-03 (auditoría 2026-08-13): además se ANOTA cuántos se descartaron. El
    descarte estaba bien hecho, pero era invisible: la categoría llegaba al
    usuario como `partial` sin ninguna forma de distinguir "el pliego dice poco"
    de "el modelo produjo hallazgos que no pudimos respaldar".
    """
    items = _enforce_citation_contract(items)
    filtered = [item for item in items if list(item.get("source_references", []))]
    dropped = len(items) - len(filtered)
    normalized_status = str(status or "unknown")

    if dropped and normalized_status in {"success", "unknown"}:
        normalized_status = "partial"

    if quality is not None and category:
        registro = quality.setdefault(category, {})
        if dropped:
            registro["descartados_sin_evidencia"] = registro.get("descartados_sin_evidencia", 0) + dropped
        # Items que sobrevivieron pero cuya cita tuvo que rescatarse: su
        # evidencia declarada no verificaba (ver ATR-02).
        rescatados = sum(
            1 for item in filtered if str(item.get("_warning", "")) == "cita_reemplazada_por_rescate"
        )
        if rescatados:
            registro["con_evidencia_rescatada"] = registro.get("con_evidencia_rescatada", 0) + rescatados
        registro["conservados"] = len(filtered)

    return filtered, normalized_status


def setup_node(state: GraphState) -> GraphState:
    logger.info("setup_node_started", correlation_id=state["correlation_id"], analysis_id=state["analysis_id"])
    
    # Construir mapeo document_id → blob_path para highlight pre-computado
    document_mapping = _build_document_mapping(state["analysis_id"], state.get("db_session"))
    
    state.update(
        {
            "objeto_alcance": [],
            "objeto_alcance_status": "pending",
            "requisitos_admisibilidad": [],
            "requisitos_admisibilidad_status": "pending",
            "plazos": [],
            "plazos_status": "pending",
            "garantias": [],
            "garantias_status": "pending",
            "causales": [],
            "causales_status": "pending",
            "anexos": [],
            "anexos_status": "pending",
            "criterios": [],
            "criterios_status": "pending",
            "identificacion": [],
            "identificacion_status": "pending",
            "conflicts": [],
            "document_id_to_blob_path": document_mapping,
        }
    )
    logger.info("setup_node_completed", correlation_id=state["correlation_id"])
    return state


def merge_node(state: GraphState) -> GraphState:
    correlation_id = state["correlation_id"]
    logger.info("merge_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    plazos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("plazos", [])]
    objeto_alcance = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("objeto_alcance", [])]
    requisitos_admisibilidad = [
        _normalize_confidence(_penalize_unverifiable(item)) for item in state.get("requisitos_admisibilidad", [])
    ]
    garantias = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("garantias", [])]
    causales = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("causales", [])]
    anexos = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("anexos", [])]
    criterios = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("criterios", [])]
    identificacion = [_normalize_confidence(_penalize_unverifiable(item)) for item in state.get("identificacion", [])]

    # Canonicalizar el tipo ANTES de deduplicar: dos ítems que citan el mismo
    # hecho (ej. "mantenimiento de oferta" extraído de dos fragmentos/documentos
    # distintos) suelen llegar con una redacción de `tipo` levemente distinta, y
    # solo se reconocen como el mismo hecho después de canonicalizar.
    for plazo in plazos:
        plazo["tipo"] = _canonical_plazo_tipo(str(plazo.get("tipo", "")), item=plazo)
    plazos = _merge_duplicate_typed_items(plazos, _plazo_dedup_value)

    for garantia in garantias:
        garantia["tipo"] = _canonical_garantia_tipo(str(garantia.get("tipo", "")))
    garantias = _merge_duplicate_typed_items(garantias, _garantia_dedup_value)

    # Las otras 6 categorías no tienen un `tipo` canonicalizado especial: se
    # deduplican por (tipo tal cual, huella normalizada del valor). El chunker
    # solapa 120 tokens a propósito, así que es común que el mismo hecho quede
    # citado en dos fragmentos distintos que el extractor recupera ambos.
    objeto_alcance = _merge_duplicate_items_by_key(
        objeto_alcance, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    requisitos_admisibilidad = _merge_duplicate_items_by_key(
        requisitos_admisibilidad, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    # causales_rechazo: el único `tipo` posible es "causal_rechazo", así que
    # agrupar con ese campo no distingue nada — se deduplica solo por valor.
    for causal in causales:
        causal["tipo"] = _canonical_causal_tipo(str(causal.get("tipo", "")))
    causales = _merge_duplicate_items_by_key(causales, lambda item: (_normalized_valor_key(item),))
    anexos = _merge_duplicate_items_by_key(
        anexos, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    criterios = _merge_duplicate_items_by_key(
        criterios, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )
    identificacion = _merge_duplicate_items_by_key(
        identificacion, lambda item: (str(item.get("tipo", "")), _normalized_valor_key(item))
    )

    # ATR-03: contadores de calidad por categoría, para que el usuario pueda
    # distinguir "el pliego dice poco" de "tuvimos que descartar hallazgos".
    calidad: dict[str, dict[str, int]] = {}

    objeto_alcance, objeto_alcance_status = _drop_items_without_sources(
        objeto_alcance,
        str(state.get("objeto_alcance_status", "unknown")),
        category="objeto_alcance",
        quality=calidad,
    )
    requisitos_admisibilidad, requisitos_admisibilidad_status = _drop_items_without_sources(
        requisitos_admisibilidad,
        str(state.get("requisitos_admisibilidad_status", "unknown")),
        category="requisitos_admisibilidad",
        quality=calidad,
    )
    plazos, plazos_status = _drop_items_without_sources(plazos, str(state.get("plazos_status", "unknown")), category="plazos_clave", quality=calidad)
    garantias, garantias_status = _drop_items_without_sources(garantias, str(state.get("garantias_status", "unknown")), category="garantias", quality=calidad)
    causales, causales_status = _drop_items_without_sources(causales, str(state.get("causales_status", "unknown")), category="causales_rechazo", quality=calidad)
    anexos, anexos_status = _drop_items_without_sources(anexos, str(state.get("anexos_status", "unknown")), category="anexos_obligatorios", quality=calidad)
    criterios, criterios_status = _drop_items_without_sources(criterios, str(state.get("criterios_status", "unknown")), category="criterios_evaluacion", quality=calidad)
    identificacion, identificacion_status = _drop_items_without_sources(
        identificacion,
        str(state.get("identificacion_status", "unknown")),
        category="identificacion_procedimiento",
        quality=calidad,
    )

    # Campo canónico: solo los ítems cuyo `tipo` cae en el enum
    # `TipoIdentificacion`. El resto sigue disponible en `datos_procedimiento`.
    identificacion_canonica: list[dict] = []
    for item in identificacion:
        canonical_tipo = _canonical_identificacion_tipo(str(item.get("tipo", "")))
        if canonical_tipo is None:
            continue
        canonical_item = dict(item)
        canonical_item["tipo"] = canonical_tipo
        identificacion_canonica.append(canonical_item)

    # Red de seguridad final: ningun item que viole su schema puede llegar a
    # `ExtractedData(**...)`, porque ahi un solo item invalido tumba las ocho
    # categorias de una.
    objeto_alcance, objeto_alcance_status = _keep_schema_valid_items(
        objeto_alcance, ObjetoAlcanceItem, objeto_alcance_status,
        category="objeto_alcance", correlation_id=correlation_id, quality=calidad,
    )
    requisitos_admisibilidad, requisitos_admisibilidad_status = _keep_schema_valid_items(
        requisitos_admisibilidad, RequisitoAdmisibilidadItem, requisitos_admisibilidad_status,
        category="requisitos_admisibilidad", correlation_id=correlation_id, quality=calidad,
    )
    plazos, plazos_status = _keep_schema_valid_items(
        plazos, PlazoItem, plazos_status, category="plazos_clave", correlation_id=correlation_id, quality=calidad,
    )
    garantias, garantias_status = _keep_schema_valid_items(
        garantias, GarantiaItem, garantias_status,
        category="garantias", correlation_id=correlation_id, quality=calidad,
    )
    causales, causales_status = _keep_schema_valid_items(
        causales, CausalRechazoItem, causales_status,
        category="causales_rechazo", correlation_id=correlation_id, quality=calidad,
    )
    anexos, anexos_status = _keep_schema_valid_items(
        anexos, AnexoObligatorioItem, anexos_status,
        category="anexos_obligatorios", correlation_id=correlation_id, quality=calidad,
    )
    criterios, criterios_status = _keep_schema_valid_items(
        criterios, CriterioEvaluacionItem, criterios_status,
        category="criterios_evaluacion", correlation_id=correlation_id, quality=calidad,
    )
    identificacion_canonica, identificacion_status = _keep_schema_valid_items(
        identificacion_canonica, IdentificacionProcedimientoItem, identificacion_status,
        category="identificacion_procedimiento", correlation_id=correlation_id, quality=calidad,
    )

    objeto_alcance.sort(key=_source_order_key)
    requisitos_admisibilidad.sort(key=_source_order_key)
    plazos.sort(key=_source_order_key)
    garantias.sort(key=_source_order_key)
    causales.sort(key=_source_order_key)
    anexos.sort(key=_source_order_key)
    criterios.sort(key=_source_order_key)
    identificacion.sort(key=_source_order_key)
    identificacion_canonica.sort(key=_source_order_key)

    extracted_data = {
        # ATR-03: viaja dentro de `extracted_data` porque es lo único que llega
        # al frontend sin cambiar el contrato de la API.
        "calidad_por_categoria": calidad,
        "objeto_alcance": objeto_alcance,
        "objeto_alcance_extraction_status": objeto_alcance_status,
        "objeto_alcance_confidence": _category_confidence(objeto_alcance),
        "requisitos_admisibilidad": requisitos_admisibilidad,
        "requisitos_admisibilidad_extraction_status": requisitos_admisibilidad_status,
        "requisitos_admisibilidad_confidence": _category_confidence(requisitos_admisibilidad),
        "plazos_clave": plazos,
        "plazos_clave_extraction_status": plazos_status,
        "plazos_clave_confidence": _category_confidence(plazos),
        "plazos": plazos,
        "plazos_extraction_status": plazos_status,
        "garantias": garantias,
        "garantias_extraction_status": garantias_status,
        "garantias_confidence": _category_confidence(garantias),
        "causales_rechazo": causales,
        "causales_extraction_status": causales_status,
        "causales_rechazo_confidence": _category_confidence(causales),
        "anexos_obligatorios": anexos,
        # `ExtractedData` declara `anexos_obligatorios_extraction_status` /
        # `criterios_evaluacion_extraction_status` /
        # `identificacion_procedimiento`. Antes merge_node escribia solo los
        # nombres legacy (`anexos_extraction_status`, `criterios_...`,
        # `datos_procedimiento`), que pydantic descartaba: las categorias
        # quedaban en su default ("unknown" / lista vacia) SIEMPRE, sin importar
        # que el extractor hubiera funcionado. Se escriben ambos nombres: el
        # canonico que consume el frontend y el legacy por compatibilidad.
        "anexos_obligatorios_extraction_status": anexos_status,
        "anexos_extraction_status": anexos_status,
        "anexos_obligatorios_confidence": _category_confidence(anexos),
        "identificacion_procedimiento": identificacion_canonica,
        "identificacion_procedimiento_extraction_status": identificacion_status,
        "datos_procedimiento": identificacion,
        "datos_procedimiento_extraction_status": identificacion_status,
        "datos_procedimiento_confidence": _category_confidence(identificacion),
        # FIX (auditoría 2026-08-13, hallazgo CTX-03): estos cuatro campos
        # estaban en `not_found`, que en toda la UI significa "el pliego no lo
        # dice". Pero ningún nodo del grafo los completa: los ocho extractores
        # están listados en `_EXTRACTOR_NODES` y ninguno mapea acá. La verdad no
        # es "no encontrado" sino "no analizado".
        #
        # La diferencia importa: para `estimacion_presupuesto`, un oferente que
        # lee "no encontrado" puede concluir que el pliego no publica
        # presupuesto oficial, cuando el sistema nunca lo buscó por esa vía.
        "documentos_requeridos": [],
        "documentos_extraction_status": NOT_ANALYZED_STATUS,
        "criterios_evaluacion": criterios,
        "criterios_evaluacion_extraction_status": criterios_status,
        "criterios_extraction_status": criterios_status,
        "criterios_evaluacion_confidence": _category_confidence(criterios),
        "restricciones_participacion": [],
        "restricciones_extraction_status": NOT_ANALYZED_STATUS,
        "cronograma_proceso": [],
        "cronograma_extraction_status": NOT_ANALYZED_STATUS,
        "estimacion_presupuesto": None,
        "presupuesto_extraction_status": NOT_ANALYZED_STATUS,
    }

    token_usage = {
        "objeto_alcance": state.get("objeto_alcance_token_usage", {}),
        "requisitos_admisibilidad": state.get("requisitos_admisibilidad_token_usage", {}),
        "plazos_clave": state.get("plazos_token_usage", {}),
        "garantias": state.get("garantias_token_usage", {}),
        "causales_rechazo": state.get("causales_token_usage", {}),
        "anexos_obligatorios": state.get("anexos_token_usage", {}),
        "criterios_evaluacion": state.get("criterios_token_usage", {}),
        "identificacion_procedimiento": state.get("identificacion_token_usage", {}),
    }

    conflicts: list[dict] = []

    plazos_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for plazo in plazos:
        plazos_by_tipo[str(plazo.get("tipo", ""))].append(plazo)

    for tipo, items in plazos_by_tipo.items():
        if tipo and len(items) > 1:
            fechas = {item.get("fecha") for item in items}
            if len(fechas) > 1:
                conflicts.append(
                    {
                        "category": "plazos",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Fechas diferentes en distintos documentos",
                    }
                )

    garantias_by_tipo: dict[str, list[dict]] = defaultdict(list)
    for garantia in garantias:
        garantias_by_tipo[str(garantia.get("tipo", ""))].append(garantia)

    for tipo, items in garantias_by_tipo.items():
        if tipo and len(items) > 1:
            montos = {(item.get("monto_porcentaje"), item.get("monto_valor")) for item in items}
            if len(montos) > 1:
                conflicts.append(
                    {
                        "category": "garantias",
                        "tipo": tipo,
                        "values": items,
                        "reason": "Montos diferentes en distintos documentos",
                    }
                )

    validated = ExtractedData(**extracted_data)
    state["extracted_data"] = validated.model_dump()
    state["conflicts"] = conflicts
    state["extraction_metadata"] = {"token_usage": token_usage, "calidad_por_categoria": calidad}

    logger.info(
        "merge_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        conflicts_count=len(conflicts),
    )
    return state


def _build_chunk_indexes(
    analysis_id: str, correlation_id: str
) -> tuple[dict[str, dict], dict[tuple[str, int], list[dict]]]:
    """Enumera los chunks del análisis UNA vez y deriva los dos índices que
    necesita la síntesis.

    FIX (auditoría 2026-08-13, hallazgo SYN-03): antes había dos funciones
    equivalentes (`_build_chunks_by_id_index` acá y
    `synthesis._build_chunks_index_from_search`) que hacían la misma consulta
    por separado, y la segunda se llamaba DENTRO del loop de categorías, sin
    caché. Total: 8 enumeraciones del índice por análisis, cada una con su
    propia llamada de embedding, su búsqueda con `top=3000` y sus cientos de
    `get_document()` de la expansión children->parent. Ahora se enumera una
    sola vez y los dos índices se derivan del mismo resultado.

    Returns:
        (chunks_by_id, chunks_by_doc_page)
          - chunks_by_id: {chunk_id: chunk} -- para resolver evidencias.
          - chunks_by_doc_page: {(document_id, page_number): [chunks]} -- para
            el fallback de highlighting por bbox almacenado.
    """
    try:
        from shared.ports.azure_search import fetch_all_analysis_chunks

        all_chunks, truncated = fetch_all_analysis_chunks(analysis_id)

        chunks_by_id: dict[str, dict] = {}
        chunks_by_doc_page: dict[tuple[str, int], list[dict]] = {}

        for chunk in all_chunks:
            # El id compuesto ya viene del índice; se reconstruye sólo si
            # faltara (documentos viejos indexados antes de que `id` se
            # seleccionara).
            chunk_id = chunk.get("id")
            if not chunk_id:
                analysis_id_field = chunk.get("analysis_id")
                document_id = chunk.get("document_id")
                chunk_index = chunk.get("chunk_index")
                if analysis_id_field and document_id is not None and chunk_index is not None:
                    chunk_id = f"{analysis_id_field}--{document_id}--{chunk_index}"

            if chunk_id:
                chunk["chunk_id"] = chunk_id
                chunks_by_id[chunk_id] = chunk

            doc_id = chunk.get("document_id")
            page = chunk.get("page_number")
            if doc_id and page:
                chunks_by_doc_page.setdefault((str(doc_id), int(page)), []).append(chunk)

        logger.info(
            "chunk_indexes_built",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            total_chunks=len(all_chunks),
            indexed_by_id=len(chunks_by_id),
            unique_doc_pages=len(chunks_by_doc_page),
            truncated=truncated,
        )

        return chunks_by_id, chunks_by_doc_page

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "chunk_indexes_build_failed",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            error=str(exc),
            message="Evidence-based highlighting no disponible",
        )
        return {}, {}


def synthesize_node(state: GraphState) -> GraphState:
    """Convierte cada categoria ya mergeada en una respuesta de experto (bloques
    en lenguaje natural), una llamada LLM liviana por categoria (no vuelve a
    buscar chunks). Si una categoria falla la sintesis, simplemente no lleva
    `_narrative` en `extracted_data` — el frontend cae a su propio fallback, asi
    que un fallo aca nunca deja una categoria sin respuesta ni tumba el resto.
    
    FIX CRÍTICO (2026-08): Ahora enriquece cada narrative con coordenadas de
    highlight pre-computadas usando PyMuPDF, resolviendo el problema de highlight
    frágil identificado en la auditoría RAG.
    """
    correlation_id = state["correlation_id"]
    logger.info("synthesize_node_started", correlation_id=correlation_id, analysis_id=state["analysis_id"])

    extracted_data = state.get("extracted_data", {})
    metadata = state.get("extraction_metadata", {})
    token_usage_by_category = dict(metadata.get("token_usage", {}))
    document_mapping = state.get("document_id_to_blob_path", {})
    
    # FIX HIGH (#6): Validar que document_mapping no esté vacío en producción
    if not document_mapping:
        from shared.config import get_settings
        settings = get_settings()
        if settings.is_production:
            logger.warning(
                "highlight_unavailable_no_document_mapping",
                correlation_id=correlation_id,
                analysis_id=state["analysis_id"],
                reason="document_mapping is empty - highlights will not be computed",
            )

    # SYN-03: una sola enumeración del índice por análisis. Los dos índices
    # que necesita la síntesis se derivan del mismo resultado y se pasan a
    # `enrich_narrative_with_highlights`, que antes reconstruía el suyo desde
    # cero en CADA categoría.
    chunks_by_id, chunks_by_doc_page = _build_chunk_indexes(state["analysis_id"], correlation_id)

    synthesized = 0
    for category_key in NARRATIVE_CATEGORIES:
        items = extracted_data.get(category_key, [])
        if not isinstance(items, list):
            continue
        result = run_synthesis(
            category_key=category_key,
            items=items,
            correlation_id=correlation_id,
            chunks_by_id=chunks_by_id,
            # CTX-04: los conflictos que detectó `merge_node` tienen que llegar
            # a quien redacta la respuesta. Antes se quedaban en el estado.
            conflicts=state.get("conflicts") or [],
        )
        if result is None:
            continue
        narrative, token_usage = result

        # FIX CRÍTICO: Enriquecer con highlights pre-computados
        if document_mapping:
            narrative = enrich_narrative_with_highlights(
                narrative=narrative,
                document_id_to_blob_path=document_mapping,
                correlation_id=correlation_id,
                category_key=category_key,
                analysis_id=state["analysis_id"],
                chunks_by_doc_page=chunks_by_doc_page,
            )
        
        extracted_data[f"{category_key}_narrative"] = narrative.model_dump()
        token_usage_by_category[f"{category_key}_synthesis"] = token_usage
        synthesized += 1

    metadata["token_usage"] = token_usage_by_category
    state["extracted_data"] = extracted_data
    state["extraction_metadata"] = metadata

    logger.info(
        "synthesize_node_completed",
        correlation_id=correlation_id,
        analysis_id=state["analysis_id"],
        categories_synthesized=synthesized,
    )
    
    # FIX CRÍTICO (2026-08): Limpiar PDFs temporales descargados desde Azure
    _cleanup_temp_highlights(state["analysis_id"])
    
    return state


builder = StateGraph(GraphState)

builder.add_node("setup", setup_node)
builder.add_node("extract_objeto_alcance", extractor_objeto_alcance)
builder.add_node("extract_plazos", extractor_plazos)
builder.add_node("extract_garantias", extractor_garantias)
builder.add_node("extract_causales", extractor_causales)
builder.add_node("extract_anexos", extractor_anexos_obligatorios)
builder.add_node("extract_requisitos", extractor_requisitos_admisibilidad)
builder.add_node("extract_criterios", extractor_criterios_evaluacion)
builder.add_node("extract_identificacion", extractor_identificacion_procedimiento)
builder.add_node("merge", merge_node)
builder.add_node("synthesize", synthesize_node)

builder.set_entry_point("setup")

extractor_nodes = [
    "extract_objeto_alcance",
    "extract_plazos",
    "extract_garantias",
    "extract_causales",
    "extract_anexos",
    "extract_requisitos",
    "extract_criterios",
    "extract_identificacion",
]

for node in extractor_nodes:
    builder.add_edge("setup", node)

for node in extractor_nodes:
    builder.add_edge(node, "merge")

builder.add_edge("merge", "synthesize")
builder.add_edge("synthesize", END)

graph = builder.compile()
