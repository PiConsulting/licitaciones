"""Clasificacion de chunks por categoria: heading matching, keywords del glosario y similitud semantica."""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

_KEYWORD_SCORE_SATURATION = 4
_DENSITY_SATURATION_PER_100_WORDS = 1.0
_DEFAULT_PRIMARY_THRESHOLD = 0.25
_DEFAULT_SECONDARY_THRESHOLD = 0.12
_DEFAULT_SEMANTIC_PRIMARY_THRESHOLD = 0.60
_DEFAULT_SEMANTIC_SECONDARY_THRESHOLD = 0.48
CATEGORY_HEADING_PATTERNS = {
    "objeto_alcance": [
        "objeto",
        "alcance",
        "descripcion de la contratacion",
        "alcance del servicio",
        "modalidad",
        "lugar de entrega",
    ],
    "requisitos_admisibilidad": [
        "requisito",
        "admisibilidad",
        "documentacion",
        "antecedente",
        "habilitacion",
        "condiciones de admision",
        "requisitos habilitantes",
    ],
    "garantias": [
        "garantia",
        "caucion",
        "seguro de caucion",
        "mantenimiento de oferta",
        "cumplimiento de contrato",
        "fianza",
    ],
    "plazos_clave": [
        "plazo",
        "cronograma",
        "fecha",
        "vencimiento",
        "presentacion de ofertas",
        "apertura",
    ],
    "criterios_evaluacion": [
        "evaluacion",
        "ponderacion",
        "criterio",
        "puntaje",
        "adjudicacion",
        "oferta mas conveniente",
    ],
    "causales_rechazo": [
        "rechazo",
        "descalificacion",
        "inadmisibilidad",
        "causal",
        "motivos de rechazo",
    ],
    "anexos_obligatorios": [
        "anexo",
        "formulario",
        "planilla",
        "modelo",
    ],
    "identificacion_procedimiento": [
        "carátula",
        "expediente",
        "organismo",
        "procedimiento",
        "licitacion",
    ],
    # FASE 2 (plan RAG v2, 2026-08-24): faltaba por completo -- "riesgos" es
    # una categoría de extracción real (ver analysis/extraction/prompts/
    # riesgos.txt) pero nunca podía ganar por heading match, porque no había
    # ninguna entrada acá. Un chunk bajo un encabezado literal "Riesgos" caía
    # directo a clasificación por keywords (más débil) o quedaba sin
    # categoría. Términos genéricos de encabezado, no vocabulario de un
    # pliego puntual -- mismo criterio que las demás categorías de esta
    # tabla.
    "riesgos": [
        "riesgo",
        "riesgos para el oferente",
        "consideraciones comerciales",
        "aspectos a considerar",
    ],
}


def _normalize_for_matching(text: str) -> str:
    """Normaliza texto para matching (lowercase, sin acentos, sin puntuación)"""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def _classify_single_heading(heading: str) -> str | None:
    """Clasifica UN encabezado (no una ruta) contra los patrones de categoría.

    Scoring por categoría: cantidad de patrones que matchean y, como desempate,
    cuál aparece ANTES en el título. En castellano el núcleo del sintagma va
    primero, así que "GARANTÍA DE ADJUDICACIÓN" es una garantía y no un
    criterio de adjudicación. Sin este desempate el resultado dependía del
    orden de iteración del diccionario de patrones.
    """
    normalized = _normalize_for_matching(heading.lower())
    if not normalized:
        return None

    scores: dict[str, tuple[int, int]] = {}
    for category, patterns in CATEGORY_HEADING_PATTERNS.items():
        matches = 0
        earliest = len(normalized)
        for pattern in patterns:
            position = normalized.find(_normalize_for_matching(pattern))
            if position >= 0:
                matches += 1
                earliest = min(earliest, position)
        if matches > 0:
            scores[category] = (matches, earliest)

    if not scores:
        return None
    return min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]


def _classify_by_heading(heading_path: list[str]) -> str | None:
    """Clasifica un chunk por su título de sección, de la hoja hacia la raíz."""
    if not heading_path:
        return None

    for heading in reversed(heading_path):
        category = _classify_single_heading(str(heading))
        if category is not None:
            return category

    return None


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict]:
    """Carga el glossary.json para clasificación por keywords"""
    from pathlib import Path
    import json

    # parents[2]: este módulo vive en indexing/chunking/ (un nivel más
    # profundo que el indexing/chunking.py original) -- parents[2] sigue
    # apuntando a backend/.
    glossary_path = (
        Path(__file__).resolve().parents[2] / "analysis" / "extraction" / "glossary.json"
    )
    if not glossary_path.exists():
        return {}

    with glossary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _semantic_classification_enabled() -> bool:
    """Flag de activación de la Fase 2 (plan RAG v2, 4.3). Default False --
    sin esto activado, `classify_chunk_categories` se comporta exactamente
    igual que antes de esta fase. Import perezoso para no acoplar
    `chunking.py` (hoy sin dependencias externas) a `infra.config` salvo
    cuando efectivamente hace falta consultarlo."""
    try:
        from infra.config import get_settings

        return bool(get_settings().chunking_use_semantic_classification)
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_classification_flag_unavailable", error=str(exc)[:200])
        return False


@lru_cache(maxsize=1)
def _load_category_definitions() -> dict[str, dict]:
    """Carga category_definitions.json para clasificación semántica (Fase 2,
    4.3). Config versionada, no en código -- ver el archivo para el
    razonamiento completo."""
    from pathlib import Path
    import json

    # parents[2]: ver nota de _load_glossary sobre la profundidad de este módulo.
    definitions_path = (
        Path(__file__).resolve().parents[2]
        / "analysis"
        / "extraction"
        / "category_definitions.json"
    )
    if not definitions_path.exists():
        return {}

    with definitions_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _category_definition_embeddings() -> dict[str, tuple[float, ...]]:
    """Embeddings de la definición semántica de cada categoría, cacheados una
    sola vez por proceso -- son ~9 textos cortos que no cambian salvo que se
    edite `category_definitions.json` (y el proceso se reinicia si eso pasa,
    como con cualquier `lru_cache` a nivel módulo).

    Si el servicio de embeddings no está disponible (sin credenciales, red
    caída, etc.) se degrada a `{}` en vez de propagar la excepción -- la
    clasificación semántica es un fallback opcional sobre heading+keywords,
    nunca debe tumbar el chunking completo de un análisis.
    """
    definitions = _load_category_definitions()
    if not definitions:
        return {}
    try:
        from indexing.embeddings import embed_query
    except Exception as exc:  # noqa: BLE001
        logger.warning("category_definitions_embedding_unavailable", error=str(exc)[:200])
        return {}

    embeddings: dict[str, tuple[float, ...]] = {}
    for category, entry in definitions.items():
        if not isinstance(entry, dict):
            continue
        definition_text = entry.get("definition")
        if not definition_text:
            continue
        try:
            embeddings[category] = tuple(embed_query(definition_text))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "category_definition_embedding_failed",
                category=category,
                error=str(exc)[:200],
            )
    return embeddings


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _classify_by_semantic_similarity(content: str) -> dict[str, float]:
    """Fase 2 (plan RAG v2, 4.3): similitud coseno entre un embedding del
    contenido del chunk y el embedding de la definición semántica de cada
    categoría.

    Se usa SOLO como fallback -- ver el llamador en `classify_chunk_
    categories` -- cuando ni el heading ni las keywords del glosario
    encontraron una categoría primaria con confianza suficiente. Es la señal
    más cara de las tres (una llamada real a Azure OpenAI Embeddings, aunque
    cacheada por texto normalizado vía `embed_query`), así que se reserva
    para el caso que realmente la necesita: contenido con vocabulario que el
    glosario no contempla, que es exactamente el problema que esta fase
    ataca (ver plan, sección 4.3).
    """
    category_embeddings = _category_definition_embeddings()
    if not category_embeddings or not content.strip():
        return {}

    try:
        from indexing.embeddings import embed_query

        content_embedding = embed_query(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chunk_semantic_classification_failed", error=str(exc)[:200])
        return {}

    return {
        category: _cosine_similarity(content_embedding, list(definition_embedding))
        for category, definition_embedding in category_embeddings.items()
    }


def _term_appears_in(normalized_term: str, content_tokens: set[str], padded_content: str) -> bool:
    """¿El término del glosario aparece en el chunk?"""
    if not normalized_term:
        return False
    tokens = normalized_term.split()
    if len(tokens) == 1:
        return tokens[0] in content_tokens
    return f" {normalized_term} " in padded_content


def _count_keyword_matches(content: str, glossary: dict) -> dict[str, int]:
    """Cuenta, por categoría, cuántos términos distintos del glossary aparecen
    en el contenido del chunk."""
    normalized_content = _normalize_for_matching(content)
    content_tokens = set(normalized_content.split())
    padded_content = f" {normalized_content} "

    match_counts: dict[str, int] = {}

    for category, entry in glossary.items():
        if not isinstance(entry, dict):
            continue

        query_terms = entry.get("query_terms", [])
        aliases = entry.get("aliases", [])
        all_terms = [*query_terms, *aliases]

        matches = 0
        for term in all_terms:
            if _term_appears_in(_normalize_for_matching(str(term)), content_tokens, padded_content):
                matches += 1

        if matches > 0:
            match_counts[category] = matches

    return match_counts


def _compute_density_score(
    match_count: int, content_length: int, category_weight: float = 1.0
) -> float:
    """Calcula score normalizado por densidad de keywords en el contenido."""
    if match_count == 0 or content_length == 0:
        return 0.0
    term_coverage = min(match_count / _KEYWORD_SCORE_SATURATION, 1.0)
    words_per_100 = max(content_length / 100.0, 1.0)
    matches_per_100_words = match_count / words_per_100
    keyword_density = min(matches_per_100_words / _DENSITY_SATURATION_PER_100_WORDS, 1.0)
    score = term_coverage * keyword_density * category_weight

    return min(score, 1.0)  # Cap at 1.0


def _classify_by_keywords(content: str, glossary: dict) -> dict[str, float]:
    """Score relativo de cada categoría por matching de términos clave.

    CAMBIO v2 (2026-08-12): Score basado en DENSIDAD adaptativa en vez de
    conteo simple. Usa thresholds configurables por categoría.

    Fórmula: density_score = term_coverage * keyword_density * category_weight

    Ver _compute_density_score() para detalles."""
    match_counts = _count_keyword_matches(content, glossary)
    content_length = len(content.split())

    scores = {}
    for category, match_count in match_counts.items():
        entry = glossary.get(category, {})
        category_weight = entry.get("weight", 1.0) if isinstance(entry, dict) else 1.0

        score = _compute_density_score(match_count, content_length, category_weight)
        scores[category] = score

    return scores


def classify_chunk_categories(chunk: dict) -> dict:
    """Clasifica un chunk en categorías usando scoring adaptativo por densidad."""
    glossary = _load_glossary()
    heading_path = chunk.get("heading_path", [])
    content = chunk.get("content", "")
    chunk_id = chunk.get("chunk_id", "unknown")

    heading_category = _classify_by_heading(heading_path)

    keyword_scores = _classify_by_keywords(content, glossary)

    primary_category = heading_category  # El título tiene prioridad

    if not primary_category and keyword_scores:
        candidates = []
        for cat, score in keyword_scores.items():
            entry = glossary.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            primary_threshold = thresholds.get("primary", _DEFAULT_PRIMARY_THRESHOLD)

            if score >= primary_threshold:
                candidates.append((cat, score))

        if candidates:
            primary_category = max(candidates, key=lambda x: x[1])[0]

            if len(candidates) > 1:
                sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
                top_score = sorted_candidates[0][1]
                close_competitors = [c for c in sorted_candidates[1:] if c[1] >= top_score * 0.85]

                if close_competitors:
                    logger.info(
                        "chunk_classification_ambiguous",
                        chunk_id=chunk_id,
                        primary_chosen=primary_category,
                        primary_score=round(top_score, 3),
                        close_competitors={c[0]: round(c[1], 3) for c in close_competitors},
                        heading_path=" > ".join(heading_path) if heading_path else None,
                    )

    # FASE 2 (plan RAG v2, 2026-08-24, sección 4.3): si ni el heading ni las
    # keywords del glosario encontraron una categoría primaria, el chunk
    # probablemente usa vocabulario que el glosario no contempla -- que es
    # justo la debilidad que motivó esta fase. Se intenta un fallback
    # semántico (similitud coseno contra la definición de cada categoría)
    # ANTES de resolver secondary_categories, para que el resultado semántico
    # también pueda participar como primary. Detrás de un flag (default
    # False): sin activarlo, este bloque nunca corre y el comportamiento es
    # idéntico al de antes de esta fase.
    semantic_scores: dict[str, float] = {}
    if not primary_category and _semantic_classification_enabled():
        semantic_scores = _classify_by_semantic_similarity(content)
        if semantic_scores:
            definitions = _load_category_definitions()
            semantic_candidates = []
            for cat, score in semantic_scores.items():
                entry = definitions.get(cat, {})
                thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
                primary_threshold = thresholds.get(
                    "primary", _DEFAULT_SEMANTIC_PRIMARY_THRESHOLD
                )
                if score >= primary_threshold:
                    semantic_candidates.append((cat, score))

            if semantic_candidates:
                primary_category = max(semantic_candidates, key=lambda x: x[1])[0]
                logger.info(
                    "chunk_classification_semantic_fallback_used",
                    chunk_id=chunk_id,
                    primary_chosen=primary_category,
                    score=round(max(score for _cat, score in semantic_candidates), 3),
                    heading_path=" > ".join(heading_path) if heading_path else None,
                    reason="sin match de heading ni de keywords del glosario",
                )

    secondary_categories = []
    for cat, score in keyword_scores.items():
        if cat == primary_category:
            continue  # No incluir la primary en secondary

        entry = glossary.get(cat, {})
        thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
        secondary_threshold = thresholds.get("secondary", _DEFAULT_SECONDARY_THRESHOLD)

        if score >= secondary_threshold:
            secondary_categories.append(cat)

    if semantic_scores:
        definitions = _load_category_definitions()
        for cat, score in semantic_scores.items():
            if cat == primary_category or cat in secondary_categories:
                continue  # No duplicar la primary ni lo que keywords ya agregó

            entry = definitions.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            secondary_threshold = thresholds.get(
                "secondary", _DEFAULT_SEMANTIC_SECONDARY_THRESHOLD
            )
            if score >= secondary_threshold:
                secondary_categories.append(cat)

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": keyword_scores,
        "semantic_scores": semantic_scores or None,
    }
