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
    # "anexo" a secas dice DÓNDE vive el párrafo, no de qué trata -- marcado
    # como patrón DÉBIL (ver `_HEADING_WEAK_PATTERNS`); el contenido real puede
    # ganarle el primary, pero se conserva como secondary.
    "anexos_obligatorios": [
        "anexo",
        "anexos obligatorios",
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
    # "riesgos" faltaba por completo (Fase 2, plan RAG v2, 2026-08-24): un
    # chunk bajo un heading literal "Riesgos" nunca ganaba por heading match.
    # FIX (Bancor): "penalidad"/"multa" tampoco estaban -- sin ellos, un heading
    # de penalidades subía hasta un ancestro que matcheaba `garantias` por
    # casualidad, repartiendo la sección entre `garantias`/`plazos_clave`.
    "riesgos": [
        "riesgo",
        "riesgos para el oferente",
        "consideraciones comerciales",
        "aspectos a considerar",
        "penalidad",
        "penalidades",
        "multa",
        "multas",
        "regimen de penalidades",
    ],
}


# Un match por SOLO uno de estos términos es señal débil (dice DÓNDE vive el
# contenido, no DE QUÉ trata): compite con la clasificación por contenido real
# en vez de ganar automáticamente (ver `classify_chunk_categories`).
_HEADING_WEAK_PATTERNS = {
    "requisitos_admisibilidad": {"requisito", "documentacion"},
    # FIX (Bancor Nube): "modelo" a secas matchea headings técnicos sin relación
    # con anexos/formularios (ej. "modelo de despliegue" de una nube privada).
    "anexos_obligatorios": {"anexo", "modelo"},
    # FIX (PLIEGO_5443-26): "licitacion" matchea el TÍTULO del documento, que DI
    # pone como ancestro de TODO heading_path -- sin esto, cualquier chunk sin
    # match propio heredaba identificacion_procedimiento por el título.
    "identificacion_procedimiento": {"licitacion"},
}
# "Requisitos técnicos/funcionales/de rendimiento" es la ficha del bien ofertado,
# no documentación habilitante del oferente. Medido: 42/42 chunks
# `requisitos_admisibilidad` por heading eran spec-sheet técnico (mono_label_audit).
_HEADING_ANTIPATTERNS = {
    "requisitos_admisibilidad": (
        "tecnic", "funcional", "rendimiento", "prestacion", "hardware",
        "software", "equipamiento", "caracteristica", "especificacion",
        "dimensionamiento", "arquitectura", "conectividad",
    ),
}


def _suppressed_by_antipattern(
    category: str, matched_patterns: set[str], normalized_heading: str
) -> bool:
    weak = _HEADING_WEAK_PATTERNS.get(category)
    anti = _HEADING_ANTIPATTERNS.get(category)
    if not weak or not anti:
        return False
    only_weak = matched_patterns <= weak
    has_anti = any(term in normalized_heading for term in anti)
    return only_weak and has_anti


def _normalize_for_matching(text: str) -> str:
    """Normaliza texto para matching (lowercase, sin acentos, sin puntuación)"""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def _classify_single_heading_detailed(heading: str) -> tuple[str | None, bool]:
    """Como `_classify_single_heading`, pero además indica si el ÚNICO motivo
    del match fue un patrón débil (`_HEADING_WEAK_PATTERNS`) -- una etiqueta
    que dice DÓNDE vive el contenido, no DE QUÉ trata. `classify_chunk_categories`
    usa esa señal para decidir si conviene dejar competir a la clasificación
    por contenido real antes de aceptar el heading como definitivo.

    Scoring por categoría: cantidad de patrones que matchean y, como desempate,
    cuál aparece ANTES en el título. En castellano el núcleo del sintagma va
    primero, así que "GARANTÍA DE ADJUDICACIÓN" es una garantía y no un
    criterio de adjudicación. Sin este desempate el resultado dependía del
    orden de iteración del diccionario de patrones.
    """
    normalized = _normalize_for_matching(heading.lower())
    if not normalized:
        return None, False

    scores: dict[str, tuple[int, int]] = {}
    matched_by_category: dict[str, set[str]] = {}
    for category, patterns in CATEGORY_HEADING_PATTERNS.items():
        matches = 0
        earliest = len(normalized)
        matched_patterns: set[str] = set()
        for pattern in patterns:
            position = normalized.find(_normalize_for_matching(pattern))
            if position >= 0:
                matches += 1
                earliest = min(earliest, position)
                matched_patterns.add(pattern)
        if matches == 0:
            continue
        if _suppressed_by_antipattern(category, matched_patterns, normalized):
            continue
        scores[category] = (matches, earliest)
        matched_by_category[category] = matched_patterns

    if not scores:
        return None, False

    winner = min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]
    weak_patterns = _HEADING_WEAK_PATTERNS.get(winner, set())
    is_weak_only = bool(matched_by_category[winner]) and matched_by_category[winner] <= weak_patterns
    return winner, is_weak_only


def _classify_single_heading(heading: str) -> str | None:
    """Clasifica UN encabezado (no una ruta) contra los patrones de categoría."""
    category, _is_weak = _classify_single_heading_detailed(heading)
    return category


def _classify_by_heading_detailed(heading_path: list[str]) -> tuple[str | None, bool]:
    """Como `_classify_by_heading`, pero además indica si el match viene
    ÚNICAMENTE de un patrón débil -- ver `_classify_single_heading_detailed`."""
    if not heading_path:
        return None, False

    for heading in reversed(heading_path):
        category, is_weak = _classify_single_heading_detailed(str(heading))
        if category is not None:
            return category, is_weak

    return None, False


def _classify_by_heading(heading_path: list[str]) -> str | None:
    """Clasifica un chunk por su título de sección, de la hoja hacia la raíz."""
    category, _is_weak = _classify_by_heading_detailed(heading_path)
    return category


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, dict]:
    """Carga el glossary.json para clasificación por keywords"""
    from pathlib import Path
    import json

    # parents[2]: este módulo está un nivel más profundo que el indexing/chunking.py
    # original, pero parents[2] sigue apuntando a backend/.
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


# Clasificación multi-label (reindex C): category_scores = max sin veto de heading/keyword/semántico; primary = argmax sobre `_MULTILABEL_PRIMARY_FLOOR`.
_MULTILABEL_PRIMARY_FLOOR = 0.30
_MULTILABEL_SECONDARY_FLOOR = 0.40
_MULTILABEL_MAX_SECONDARY = 3
# Señal de apoyo: solo importa cuando heading y keyword están calladas.
_SEMANTIC_WEIGHT = 0.75
# Piso ABSOLUTO de coseno crudo: el reescalado relativo infla a 1.0 el argmax de chunks técnicos sin categoría real (bancor_nube); por debajo, sin señal semántica.
_SEMANTIC_COS_FLOOR = 0.44
# Un span FIJO reduce ese inflado pero rompe el gold de nucleoelectrica_requisitos; un gate de margen mejora garantias pero empeora requisitos_admisibilidad -- fix per-categoría pendiente, se queda solo el piso absoluto.


_PSEUDO_HEADING_ARTICULO_RE = re.compile(
    r"^\s*art[íi]culo\s+\d+\s*[°º]?\s*[:.\-–]?\s*(.{2,70})", re.IGNORECASE
)
_PSEUDO_HEADING_NUM_RE = re.compile(
    r"^\s*\d+\s*[°º]?\s*[.)\-–]+\s*(.{2,70})", re.IGNORECASE
)
_PSEUDO_HEADING_ANEXO_RE = re.compile(
    r"^\s*(anexo\s+[ivxlcdm0-9]+\b.{0,60})", re.IGNORECASE
)


def _pseudo_heading_from_content(content: str) -> str | None:
    """Muchos pliegos (PDF sin estructura de secciones) traen el título de la
    cláusula DENTRO del contenido: "Artículo 16. GARANTÍAS", "6º .- MONEDA DE
    COTIZACIÓN", "ANEXO II - FORMULARIO DE OFERTA", o una línea íntegra en
    MAYÚSCULAS. Se extrae de la primera línea y se usa como nivel de heading
    extra SOLO para la clasificación (no se persiste en `heading_path`).
    """
    if not content:
        return None
    first_line = content.strip().splitlines()[0].strip()
    if not first_line or len(first_line) > 90 or first_line.lower().startswith("col_"):
        return None
    for rx in (_PSEUDO_HEADING_ARTICULO_RE, _PSEUDO_HEADING_NUM_RE, _PSEUDO_HEADING_ANEXO_RE):
        m = rx.match(first_line)
        if m:
            return m.group(1).strip() or None
    letters = [c for c in first_line if c.isalpha()]
    if len(letters) >= 6 and all(c.isupper() for c in letters) and len(first_line.split()) >= 2:
        return first_line
    return None


def _heading_score_by_category(
    heading_path: list[str], pseudo_heading: str | None = None
) -> dict[str, float]:
    scores: dict[str, float] = {}
    levels = [str(h) for h in (heading_path or [])]
    if pseudo_heading:
        # Actúa como hoja: la señal más específica cuando el PDF no tiene estructura de secciones.
        levels = [*levels, pseudo_heading]
    if not levels:
        return scores
    for depth, heading in enumerate(reversed(levels)):
        cat = _classify_single_heading(heading)
        if cat:
            value = 1.0 if depth == 0 else 0.55
            scores[cat] = max(scores.get(cat, 0.0), value)
    return scores


def _softened_keyword_score(match_count: int, content_length: int, weight: float) -> float:
    """Como `_compute_density_score` pero blend en vez de producto: un chunk
    con varios términos discriminantes puntúa aunque el párrafo sea largo."""
    if match_count == 0 or content_length == 0:
        return 0.0
    term_coverage = min(match_count / _KEYWORD_SCORE_SATURATION, 1.0)
    words_per_100 = max(content_length / 100.0, 1.0)
    keyword_density = min(
        (match_count / words_per_100) / _DENSITY_SATURATION_PER_100_WORDS, 1.0
    )
    blended = 0.7 * term_coverage + 0.3 * keyword_density
    return min(blended * weight, 1.0)


def _semantic_score_by_category(chunk_embedding: list[float] | None) -> dict[str, float]:
    """Señal semántica RELATIVA: cuánto más matchea el chunk cada categoría
    que el promedio de sus propias categorías. El coseno crudo contra las
    definiciones no discrimina (todas viven en el mismo vecindario "pliego de
    licitación"); lo que importa es la distancia de cada categoría al coseno
    medio del propio chunk. La mejor categoría de un chunk queda ~1.0, la
    media 0, las de abajo 0.
    """
    if not chunk_embedding:
        return {}
    category_embeddings = _category_definition_embeddings()
    if not category_embeddings:
        return {}
    cosines = {
        category: _cosine_similarity(chunk_embedding, list(def_embedding))
        for category, def_embedding in category_embeddings.items()
    }
    if not cosines:
        return {}
    mean_cos = sum(cosines.values()) / len(cosines)
    max_cos = max(cosines.values())
    span = max_cos - mean_cos
    if span <= 1e-6:
        return {}
    # Piso absoluto: si ni la mejor categoría llega, sin señal semántica.
    if max_cos < _SEMANTIC_COS_FLOOR:
        return {}
    return {
        category: max(0.0, min((cos - mean_cos) / span, 1.0))
        for category, cos in cosines.items()
    }


def classify_chunk_multilabel(
    chunk: dict, chunk_embedding: list[float] | None = None
) -> dict:
    """Vector de score multi-label. Ver bloque de comentario arriba."""
    glossary = _load_glossary()
    content = chunk.get("content", "") or ""
    heading_path = chunk.get("heading_path", []) or []

    heading_scores = _heading_score_by_category(
        heading_path, _pseudo_heading_from_content(content)
    )

    match_counts = _count_keyword_matches(content, glossary)
    content_length = len(content.split())
    keyword_scores: dict[str, float] = {}
    for category, match_count in match_counts.items():
        entry = glossary.get(category, {})
        weight = entry.get("weight", 1.0) if isinstance(entry, dict) else 1.0
        keyword_scores[category] = _softened_keyword_score(match_count, content_length, weight)

    semantic_scores = _semantic_score_by_category(chunk_embedding)

    all_categories = set(heading_scores) | set(keyword_scores) | set(semantic_scores)
    category_scores: dict[str, float] = {}
    for category in all_categories:
        merged = max(
            heading_scores.get(category, 0.0),
            keyword_scores.get(category, 0.0),
            _SEMANTIC_WEIGHT * semantic_scores.get(category, 0.0),
        )
        if merged >= 0.05:
            category_scores[category] = round(merged, 4)

    primary_category = None
    if category_scores:
        top_cat, top_score = max(category_scores.items(), key=lambda kv: kv[1])
        if top_score >= _MULTILABEL_PRIMARY_FLOOR:
            primary_category = top_cat

    secondary_categories = [
        cat
        for cat, _score in sorted(
            (
                (c, s)
                for c, s in category_scores.items()
                if c != primary_category and s >= _MULTILABEL_SECONDARY_FLOOR
            ),
            key=lambda kv: kv[1],
            reverse=True,
        )[:_MULTILABEL_MAX_SECONDARY]
    ]

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": category_scores,
    }


def classify_chunk_categories(chunk: dict) -> dict:
    """Clasifica un chunk en categorías usando scoring adaptativo por densidad."""
    glossary = _load_glossary()
    heading_path = chunk.get("heading_path", [])
    content = chunk.get("content", "")
    chunk_id = chunk.get("chunk_id", "unknown")

    heading_category, heading_is_weak = _classify_by_heading_detailed(heading_path)

    # Una fila de tabla no tiene heading_path propio, pero su table_context
    # (el párrafo que la introduce) suele nombrar la categoría igual de claro.
    if not heading_category and chunk.get("table_context"):
        heading_category, heading_is_weak = _classify_single_heading_detailed(
            str(chunk["table_context"])
        )

    keyword_scores = _classify_by_keywords(content, glossary)

    # Un heading que matcheó SOLO por un patrón débil no gana automáticamente:
    # compite con la clasificación por contenido real (abajo).
    primary_category = heading_category if not heading_is_weak else None

    if not primary_category and keyword_scores:
        # Umbral más bajo (secondary) cuando el contenido solo tiene que superar
        # a un heading ya sabido DÉBIL, en vez de no tener heading en absoluto.
        threshold_key = "secondary" if heading_category else "primary"
        default_threshold = _DEFAULT_SECONDARY_THRESHOLD if heading_category else _DEFAULT_PRIMARY_THRESHOLD

        candidates = []
        for cat, score in keyword_scores.items():
            entry = glossary.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            required = thresholds.get(threshold_key, default_threshold)

            if score >= required:
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

    # Si el contenido tampoco aportó nada, el heading débil es mejor que nada.
    if not primary_category and heading_category:
        primary_category = heading_category

    # Fase 2: fallback semántico cuando ni heading ni keywords dieron primary; detrás de un flag default False.
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
            continue

        entry = glossary.get(cat, {})
        thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
        secondary_threshold = thresholds.get("secondary", _DEFAULT_SECONDARY_THRESHOLD)

        if score >= secondary_threshold:
            secondary_categories.append(cat)

    if semantic_scores:
        definitions = _load_category_definitions()
        for cat, score in semantic_scores.items():
            if cat == primary_category or cat in secondary_categories:
                continue

            entry = definitions.get(cat, {})
            thresholds = entry.get("thresholds", {}) if isinstance(entry, dict) else {}
            secondary_threshold = thresholds.get(
                "secondary", _DEFAULT_SEMANTIC_SECONDARY_THRESHOLD
            )
            if score >= secondary_threshold:
                secondary_categories.append(cat)

    # El heading débil desplazado de primary sigue siendo información real: se conserva como secondary.
    if (
        heading_category
        and heading_category != primary_category
        and heading_category not in secondary_categories
    ):
        secondary_categories.append(heading_category)

    return {
        "primary_category": primary_category,
        "secondary_categories": secondary_categories,
        "category_scores": keyword_scores,
        "semantic_scores": semantic_scores or None,
    }
