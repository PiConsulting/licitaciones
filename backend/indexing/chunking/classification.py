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


# Un match por uno de estos términos, SOLO, es señal débil: se puede anular si
# el título trae además un calificador de los de abajo.
_HEADING_WEAK_PATTERNS = {
    "requisitos_admisibilidad": {"requisito", "documentacion"},
}
# "Requisitos técnicos / funcionales / de rendimiento" es la ficha del bien
# ofertado (objeto/alcance), no la documentación habilitante del oferente.
# Medido (mono_label_audit): 42/42 chunks etiquetados `requisitos_admisibilidad`
# por heading eran spec-sheet técnico, ~10% en gold. Si la categoría matcheó
# SOLO por un término débil y el título trae uno de estos, se descarta el match.
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


# ----------------------------------------------------------------------------
# Clasificación MULTI-LABEL con vector de score (plan rag-plan-latencia-2026-09-09,
# reindex C). Devuelve `{primary_category, category_scores}` donde
# category_scores es {categoria: score 0-1} = max de tres señales sin veto:
#   - heading: 1.0 si la hoja del heading_path matchea la categoría, 0.55 si
#     lo hace un ancestro.
#   - keyword density SUAVIZADA: blend de cobertura de términos y densidad, en
#     vez del producto (que castiga fuerte a la prosa larga). Absorbe el
#     "test 3" del plan.
#   - similitud semántica: coseno(embedding del chunk, embedding de la
#     definición de la categoría), reescalado de [MIN,MAX] observados a [0,1].
# `primary = argmax` si supera `_MULTILABEL_PRIMARY_FLOOR`, si no None.
# ----------------------------------------------------------------------------
_MULTILABEL_PRIMARY_FLOOR = 0.30
_MULTILABEL_SECONDARY_FLOOR = 0.40
_MULTILABEL_MAX_SECONDARY = 3
# El semántico es señal de apoyo: no puede dominar por sí solo un heading o
# keyword claro. Se pondera por debajo de 1 y solo importa cuando esas dos
# están calladas.
_SEMANTIC_WEIGHT = 0.75
# Piso ABSOLUTO de coseno crudo (2026-09-09, revisión manual de bancor_nube):
# el reescalado relativo `(cos-mean)/span` fuerza el argmax de CADA chunk a
# 1.0 -> con `_SEMANTIC_WEIGHT` daba `X: 0.75` para categorías al azar en
# cientos de chunks técnicos que no son de ninguna (Kubernetes, cifrado, HA
# → `garantias: 0.75`). Si el mejor coseno crudo no llega a este piso, el
# chunk NO es semánticamente de ninguna categoría en particular -> sin señal
# semántica. Medido: los 19/19 gold de `requisitos_admisibilidad` tienen
# cos >= 0.45 (pasan); los 13 chunks de ruido de bancor_nube 3.1.8 tienen
# cos 0.28-0.41 (caen). Es un piso ABSOLUTO, sin chequeo de margen top1-top2
# (ese chequeo mató gold de requisitos en un intento anterior).
_SEMANTIC_COS_FLOOR = 0.44
# NOTA: probado además reemplazar el reescalado relativo `(cos-media)/span`
# (que fuerza el argmax de cada chunk a 1.0) por un span FIJO. Reduce el
# `X: 0.75` inflado en chunks con cos 0.44-0.50, pero DESTRUYE el gold de
# `nucleoelectrica_requisitos` (1.0 -> 0.0): su gold real es procedural
# genérico con separación de coseno chica. Es el 4º intento de endurecer el
# semántico que rompe esa categoría -> el fix completo necesita ser
# per-categoría. Se queda solo el piso absoluto 0.44 (limpia la sección
# técnica, deja intactos garantias/requisitos).
# HALLAZGO 2026-09-09 (pliego bancor_seguridad, sin estructura de headings):
# el reescalado relativo `(cos - media) / (max - media)` AMPLIFICA el ruido
# cuando los cosenos crudos están apiñados. Una cláusula procedural genérica
# ("La sola presentación de la Oferta importa la aceptación de la
# jurisdicción") tiene coseno ~igual contra TODAS las definiciones (banda de
# 0.02-0.04) y el reescalado la lleva a s=1.0 para su argmax → cs=0.75 para
# 3 categorías → falsos positivos al top de garantias/requisitos/anexos.
# Un gate de margen (probado: `margin>=0.03` + `cos>=0.42`) mata esos falsos
# positivos y sube `garantias` +0.024, PERO baja `requisitos_admisibilidad`
# -0.042 porque parte de su gold real ES procedural genérico (documentación
# a presentar) con cosenos igualmente planos. Necesidades opuestas → el fix
# tiene que ser per-categoría (mismo patrón que query_expansion/graded),
# no global. Pendiente de tanda propia.


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
    # Línea íntegramente en MAYÚSCULAS con >=2 palabras (título de sección).
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
        # El pseudo-heading (título de cláusula dentro del content) actúa como
        # hoja: es lo más específico que tenemos cuando el PDF no dejó
        # estructura de secciones.
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
    # Piso absoluto: si ni la mejor categoría llega, el chunk no es
    # semánticamente de ninguna en particular -> sin señal semántica.
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
