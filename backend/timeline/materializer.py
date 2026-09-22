"""
Materialización automática del Timeline a partir de la extracción.

Convierte lo que el LLM extrae en las ramas `eventos_temporales` y
`plazos_relativos` (ver `analysis/extraction/extractors/eventos_temporales.py`,
`analysis/extraction/extractors/plazos_relativos.py` y los schemas
`EventoTemporalExtracted`/`PlazoRelativoExtracted` en
`analysis/extraction/schemas.py`) en `Event`/`Deadline` reales del módulo
`timeline`, para que el motor de cálculo determinístico
(`timeline/calculation_engine.py`) tenga algo para propagar.

Se llama una vez por corrida de extracción, desde
`analysis/extraction/runner.py::extract_categories` y desde cada reanálisis
de una sola categoría (`analysis/service/lifecycle.py`), después de que el
grafo termina. NO usa LLM para resolver a qué evento se refiere cada
`evento_disparador` -- usa normalización de texto + heurísticas simples
(ver `_find_matching_event`). Es intencionalmente conservador: nunca pisa un
evento existente (para no perder una fecha ya cargada por el usuario), y es
idempotente si se vuelve a llamar con la misma extracción.

BUG real (encontrado 2026-09-18): esa idempotencia solo cubre el caso "misma
extracción, corrida de nuevo" -- si una corrida posterior extrae hitos DISTINTOS
(porque se ajustó el prompt, o el LLM no es determinístico), los `Event`/
`Deadline` de la corrida anterior NUNCA se limpiaban, porque esta función solo
sabía agregar. Con reanálisis repetidos (algo que pasa en producción, no solo
en testing) los pliegos golden de este repo acumularon entre 12 y 30 filas
"fantasma" por pliego, con `created_at` esparcidos en corridas de casi dos
semanas -- exactamente el síntoma reportado por la usuaria como "se están
mezclando con versiones anteriores". El bloque de reconciliación al final de
`materialize_timeline_from_extraction` (`touched_event_ids`) resuelve esto:
después de procesar la extracción actual, cualquier `Event`/`Deadline`
preexistente que NO fue tocado por ningún ítem de esta corrida se soft-elimina
(`deleted=True`), salvo que el usuario ya lo haya confirmado o cargado a mano
(`status="confirmed"` o `date_source="user_input"`) -- eso sigue siendo
intocable, igual que antes.

IMPORTANTE: al igual que `timeline/calculation_engine.py`, este módulo NO usa
LLM ni inventa fechas -- solo texto determinístico y llamadas a
`timeline.repository`.
"""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from timeline import repository
from timeline.calculation_engine import recalculate_dependent_dates
from timeline.models import Deadline, Event
from timeline.service import TimelineService

logger = logging.getLogger(__name__)

# Deliberadamente alto: solo variantes de redacción cercanas (ej. "12 meses" vs "doce meses"), no sinónimos/abreviaturas.
_FUZZY_MATCH_THRESHOLD = 0.82

# No es una lista exhaustiva de stopwords del español, solo las suficientes para el tier 3 de _find_matching_event.
_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "en", "y", "o", "u", "a", "al",
    "un", "una", "unos", "unas", "para", "por", "con", "su", "sus", "que",
    "cada", "se", "es", "the", "of",
}

# Descarta ruido corto como "n"/"nº" del matching por tokens (tier 3).
_MIN_TOKEN_LEN = 3

# Fracción del conjunto de tokens más chico que debe estar en el más grande para considerarlo el mismo hito.
_TOKEN_OVERLAP_THRESHOLD = 0.75

# Las 4 direcciones se materializan aunque el motor solo calcule hacia adelante -- descartar el Deadline en vez de dejarlo pendiente perdía el plazo cuando el LLM etiquetaba mal la dirección entre corridas (bug real, Banco de Córdoba).
_VALID_DIRECTIONS = {"desde", "después_de", "hasta", "antes_de"}

_DIRECTION_CUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "desde",
        re.compile(r"\b(contad[oa]s?\s+desde|contad[oa]s?\s+a\s+partir\s+de|a\s+partir\s+de)\b"),
    ),
    ("antes_de", re.compile(r"\b(antes\s+de|previo\s+a|anteriores?\s+a)\b")),
    ("hasta", re.compile(r"\b(hasta|no\s+mas\s+alla\s+de|a\s+mas\s+tardar)\b")),
    (
        "desde",
        re.compile(r"\b(desde)\b"),
    ),
    ("después_de", re.compile(r"\b(despues\s+de|luego\s+de|posterior(?:es)?\s+a)\b")),
]

_SEQUENCE_RELATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern)
    for pattern in (
        r"\b(quedara\s+perfeccionad[oa]\s+con|se\s+formaliza\s+con|se\s+perfecciona\s+con)\b",
        r"\b(con\s+la\s+notificacion|con\s+la\s+recepcion|mediante\s+la\s+notificacion)\b",
        r"\b(una\s+vez|cumplid[oa]\s+la|obtenid[oa]\s+la)\b",
        r"\b(tras\s+la|tras\s+el|al\s+recibir)\b",
    )
]


def _normalize_direction(value: Any) -> str | None:
    """Normaliza direcciones equivalentes a las 4 canónicas del schema."""
    if value is None:
        return None
    raw = _normalize(str(value))
    if not raw:
        return None
    aliases = {
        "despues de": "después_de",
        "despues_de": "después_de",
        "después de": "después_de",
        "desde": "desde",
        "hasta": "hasta",
        "antes de": "antes_de",
        "antes_de": "antes_de",
    }
    normalized = aliases.get(raw, raw.replace(" ", "_"))
    return normalized if normalized in _VALID_DIRECTIONS else None


def _infer_direction_from_text(*texts: str | None) -> str | None:
    """Infiere dirección temporal por pistas léxicas cuando el extractor la omite."""
    combined = " ".join(_normalize(t or "") for t in texts if t)
    if not combined:
        return None

    for direction, pattern in _DIRECTION_CUE_PATTERNS:
        if pattern.search(combined):
            return direction

    return None


def _is_missing_duration(item: dict[str, Any]) -> bool:
    raw = item.get("cantidad")
    if raw is None:
        return True
    if isinstance(raw, str) and not raw.strip():
        return True
    return False


def _event_is_mentioned_in_fragment(event_name: str, normalized_fragment: str) -> bool:
    normalized_event = _normalize(event_name)
    if not normalized_event:
        return False
    if normalized_event in normalized_fragment:
        return True
    fragment_tokens = _significant_tokens(normalized_fragment)
    event_tokens = _significant_tokens(normalized_event)
    return bool(fragment_tokens & event_tokens)


def _infer_structural_dependency_direction(
    *,
    descripcion: str,
    evento_disparador: str,
    source_fragment: str | None,
    item: dict[str, Any],
) -> str | None:
    """Fallback conservador para relaciones entre hitos sin duración.

    Si falta dirección y cantidad, modela dependencia instantánea (`desde`,
    duración 0) SOLO cuando el fragmento menciona ambos hitos y trae una
    pista secuencial explícita.
    """
    if not _is_missing_duration(item):
        return None
    if not source_fragment:
        return None

    normalized_fragment = _normalize(source_fragment)
    if not normalized_fragment:
        return None

    mentions_target = _event_is_mentioned_in_fragment(descripcion, normalized_fragment)
    mentions_trigger = _event_is_mentioned_in_fragment(evento_disparador, normalized_fragment)
    if not (mentions_target and mentions_trigger):
        return None

    if any(pattern.search(normalized_fragment) for pattern in _SEQUENCE_RELATION_PATTERNS):
        return "desde"

    # Fallback final: relación ya afirmada sin dirección/duración se persiste como "desde" duración 0.
    return "desde"


class MaterializeResult(BaseModel):
    """Resultado de una corrida de materialización."""

    events_created: int = 0
    deadlines_created: int = 0
    events_pruned: int = 0
    deadlines_pruned: int = 0
    skipped: list[str] = []


def _normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin puntuación, espacios colapsados."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_accents.lower()
    only_word_chars = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", only_word_chars).strip()


def _significant_tokens(normalized: str) -> set[str]:
    """Palabras "de contenido" de un nombre ya normalizado (sin stopwords ni
    tokens demasiado cortos), para el tier 3 de `_find_matching_event`."""
    return {
        token
        for token in normalized.split(" ")
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


def _token_overlap_ratio(a_tokens: set[str], b_tokens: set[str]) -> float:
    """Fracción del conjunto de tokens más chico que aparece en el más
    grande. Con un solo token significativo de cada lado, solo cuenta si es
    una palabra "fuerte" (>=6 caracteres, ej. "adjudicacion") -- evita que
    una sola palabra corta y genérica dispare un match."""
    if not a_tokens or not b_tokens:
        return 0.0
    smaller, larger = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    overlap = smaller & larger
    if not overlap:
        return 0.0
    if len(smaller) == 1:
        token = next(iter(smaller))
        return 1.0 if len(token) >= 6 else 0.0
    return len(overlap) / len(smaller)


def _find_matching_event(
    name: str,
    existing_events: list[Event],
    *,
    fuzzy_candidates: list[Event] | None = None,
) -> Event | None:
    """
    Busca en `existing_events` un evento que represente el mismo hito que
    `name`, en orden de confianza decreciente:

    1. Igualdad exacta tras normalizar. Se busca en TODO `existing_events`
       -- incluye eventos ya creados más temprano en esta misma corrida.
       Es el mecanismo intencional para que dos ítems de la MISMA
       extracción se refieran al mismo hito: la regla 2 del prompt le pide
       al LLM copiar el `nombre` tal cual cuando dos ítems son el mismo
       hito, así que dos ítems distintos con nombres distintos ya fueron
       juzgados "cosas diferentes" por el LLM -- no hay que volver a
       adivinar eso con texto.
    2. Contención de substring tras normalizar (en cualquier dirección) --
       cubre el caso real "Recepción Provisoria" (nombre corto de un
       eventos_temporales) vs "Recepción provisoria de cada uno de los
       HITOS" (evento_disparador de un plazo_relativo, más largo pero con
       el nombre corto como prefijo).
    3. Superposición de palabras clave (`_token_overlap_ratio`) por encima
       de `_TOKEN_OVERLAP_THRESHOLD` -- cubre menciones más libres del mismo
       hito que no son ni substring ni casi-idénticas, ej. "Kick-Off Del
       Proyecto" vs "Presentación del equipo técnico ... para el kick-off",
       mientras compartan casi todas las palabras clave del nombre más
       corto.
    4. Similaridad de texto (difflib) por encima de `_FUZZY_MATCH_THRESHOLD`,
       para variantes de redacción cercanas (ej. "12 meses" vs "doce meses").

    Los tiers 2-4 SOLO se prueban contra `fuzzy_candidates` (por default,
    los mismos `existing_events` si no se pasa nada) -- NUNCA contra un
    evento recién creado más temprano en esta misma corrida. Bug real
    (2026-09-01, pliego Banco de Córdoba): "Soporte de Migraciones" (un
    hito con su propio ítem) y "Inicio de la Tercera Etapa de Migraciones
    con Soporte" (su disparador, otro ítem de la MISMA extracción) son dos
    hitos distintos, pero el nombre corto del primero está totalmente
    contenido, token por token, en el nombre largo del segundo -- el tier 3
    los fusionaba en un solo Event, dejando el deadline "circular" (mismo
    trigger que target) y perdiendo el plazo relativo entero. Restringir
    los tiers 2-4 a eventos que YA EXISTÍAN antes de que arrancara esta
    corrida (`materialize_timeline_from_extraction` pasa `pre_existing`, la
    foto de la base ANTES de procesar la extracción nueva) preserva la
    reconciliación entre corridas (por qué existen estos tiers, ver
    docstring del módulo) sin que la heurística reinvente lo que el LLM ya
    decidió dentro de una misma extracción.

    No usa LLM: es una heurística de texto, así que dos menciones del mismo
    hito con redacciones MUY distintas (sinónimos, abreviaturas sin palabras
    en común) pueden no matchear -- ver docstring del módulo.
    """
    target = _normalize(name)
    if not target:
        return None

    for event in existing_events:
        if _normalize(event.name) == target:
            return event

    candidates = existing_events if fuzzy_candidates is None else fuzzy_candidates

    for event in candidates:
        candidate = _normalize(event.name)
        if not candidate:
            continue
        if target in candidate or candidate in target:
            return event

    target_tokens = _significant_tokens(target)
    best_token_match: Event | None = None
    best_token_ratio = _TOKEN_OVERLAP_THRESHOLD
    for event in candidates:
        candidate = _normalize(event.name)
        if not candidate:
            continue
        ratio = _token_overlap_ratio(target_tokens, _significant_tokens(candidate))
        if ratio >= best_token_ratio:
            best_token_ratio = ratio
            best_token_match = event
    if best_token_match is not None:
        return best_token_match

    best_match: Event | None = None
    best_ratio = _FUZZY_MATCH_THRESHOLD
    for event in candidates:
        candidate = _normalize(event.name)
        if not candidate:
            continue
        ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
        if ratio >= best_ratio:
            best_ratio = ratio
            best_match = event

    return best_match


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning("materializer_invalid_iso_date", extra={"value": value})
        return None


def _refresh_stale_source(
    db: Session,
    event: Event,
    *,
    source_document_id: str | None,
    source_page: int | None,
    source_fragment: str | None,
) -> None:
    """
    BUG real (Santa Fe, encontrado 2026-09-21): un evento que ya existe
    (match por nombre) puede venir de una extracción vieja cuya
    `fuente_pagina`/`fuente_fragmento` ya no corresponde a la extracción
    actual -- el map-reduce de `eventos_temporales` no es determinístico
    entre corridas, y el mismo hito puede terminar citando otro chunk/página
    la próxima vez. Como `_find_or_create_event` nunca creaba un evento
    nuevo para un nombre que ya existía, la cita quedaba CONGELADA en la
    primera corrida para siempre: el evento "Retiro de las Muestras de
    Ofertas No Adjudicadas" tenía `source_page=12` desde 2026-09-14 pese a
    13 reanálisis posteriores, cuando la cita real siempre estuvo en la
    página 11 -- el botón "ver fuente" del Timeline navegaba a la página
    equivocada y el highlight nunca encontraba el texto ahí.

    Se refresca siempre que el evento no esté protegido -- misma protección
    que la reconciliación de soft-delete de este módulo (`status="confirmed"`
    o `date_source="user_input"` quedan intocables, porque ahí ya hay una
    decisión humana de por medio). El resto de los campos (`event_date`,
    `date_source`, `name`) sigue sin tocarse acá, a propósito.
    """
    if event.status == "confirmed" or event.date_source == "user_input":
        return

    trimmed_fragment = source_fragment[:500] if source_fragment else None
    changed = (
        bool(source_document_id) and event.source_document_id != source_document_id
    ) or (
        source_page is not None and event.source_page != source_page
    ) or (
        bool(trimmed_fragment) and event.source_fragment != trimmed_fragment
    )
    if not changed:
        return

    if source_document_id:
        event.source_document_id = source_document_id
    if source_page is not None:
        event.source_page = source_page
    if trimmed_fragment:
        event.source_fragment = trimmed_fragment
    event.updated_at = datetime.now(UTC)
    repository.update_event(db, event)


def _find_or_create_event(
    db: Session,
    analysis_id: str,
    name: str,
    *,
    index: list[Event],
    fuzzy_candidates: list[Event] | None = None,
    fecha_explicita: str | None = None,
    source_document_id: str | None = None,
    source_page: int | None = None,
    source_fragment: str | None = None,
    result: MaterializeResult,
    mencion_propia: bool = True,
) -> Event:
    """
    Busca `name` en `index` (eventos ya existentes + creados en esta
    corrida). Si hay match, nunca pisa `event_date`/`date_source` de un
    evento existente, para no perder una fecha ya cargada por el usuario --
    pero SÍ refresca `source_document_id`/`source_page`/`source_fragment` si
    la extracción actual trae una cita distinta (ver `_refresh_stale_source`)
    salvo que el evento ya esté confirmado o con fecha manual. La función
    sigue siendo idempotente si se vuelve a llamar con la misma extracción
    (no hay cambio real, `_refresh_stale_source` no escribe nada).

    `fuzzy_candidates` (default: `index`) es el subconjunto contra el que
    se permite matchear por substring/tokens/difflib (tiers 2-4 de
    `_find_matching_event`) -- `materialize_timeline_from_extraction` pasa
    acá SOLO los eventos que ya existían antes de esta corrida, para que la
    heurística de texto nunca fusione dos ítems distintos de la MISMA
    extracción (ver docstring de `_find_matching_event`). El match exacto
    (tier 1) sigue probándose contra `index` completo.

    Si no hay match, crea un `Event` nuevo: con fecha y `date_source`
    "detected" si `fecha_explicita` es una fecha ISO válida, si no
    `date_source="pending"` (aparece en "Eventos Pendientes" del Timeline).

    `mencion_propia` (default True) queda grabado en `source_reference` --
    False marca un evento que el pliego nunca declara por sí mismo, creado
    solo porque hacía falta como `evento_disparador` de otro hito (ver
    `mencion_propia` en `HitoTemporalExtracted`). El frontend lo usa para
    distinguir "esto está en el pliego" de "esto lo inferimos para poder
    calcular otra fecha" -- ver AC del pedido del usuario sobre no poder
    diferenciar ambos casos.
    """
    match = _find_matching_event(name, index, fuzzy_candidates=fuzzy_candidates)
    if match is not None:
        _refresh_stale_source(
            db,
            match,
            source_document_id=source_document_id,
            source_page=source_page,
            source_fragment=source_fragment,
        )
        return match

    parsed_date = _parse_iso_date(fecha_explicita)
    event = Event(
        partition_key=analysis_id,
        analysis_id=analysis_id,
        name=name[:120],
        event_date=parsed_date,
        date_source="detected" if parsed_date else "pending",
        status="pending",
        source_document_id=source_document_id,
        source_page=source_page,
        source_fragment=source_fragment[:500] if source_fragment else None,
        source_reference={"mencion_propia": mencion_propia},
    )
    created = repository.create_event(db, event)
    index.append(created)
    result.events_created += 1
    return created


def _deadline_already_exists(
    existing_deadlines: list[Deadline],
    *,
    trigger_event_id: str,
    target_event_id: str,
    duration: int,
    unit: str,
    day_type: str,
) -> bool:
    return any(
        d.trigger_event_id == trigger_event_id
        and d.target_event_id == target_event_id
        and d.duration == duration
        and d.unit == unit
        and d.day_type == day_type
        for d in existing_deadlines
    )


def materialize_timeline_from_extraction(
    db: Session,
    analysis_id: str,
    created_by: str | None,
    eventos_temporales: list[dict[str, Any]],
    plazos_relativos: list[dict[str, Any]],
) -> MaterializeResult:
    """
    Puebla el Timeline (`Event`/`Deadline`) de `analysis_id` a partir de lo
    que la extracción encontró en `eventos_temporales` y `plazos_relativos`.

    Idempotente: correrla dos veces con la misma extracción no duplica
    eventos ni deadlines, y nunca modifica un evento que ya exista (para no
    pisar una fecha que el usuario ya haya cargado a mano).

    No lanza excepciones de negocio -- los casos no materializables
    (dirección "antes_de"/"hasta", auto-referencias) se registran en
    `result.skipped` y se saltean. Errores de datos inesperados sí se
    propagan; el caller (`extract_categories`) los atrapa para que un fallo
    acá nunca bloquee que el análisis se marque como analizado.
    """
    result = MaterializeResult()

    # Foto de la base antes de tocar nada: los tiers 2-4 de matching solo reconcilian contra corridas anteriores, nunca contra un evento creado en este mismo `for`.
    pre_existing: list[Event] = list(repository.list_events(db, analysis_id))
    index: list[Event] = list(pre_existing)
    existing_deadlines: list[Deadline] = list(repository.list_deadlines(db, analysis_id))
    pre_existing_deadlines: list[Deadline] = list(existing_deadlines)

    # Eventos que esta corrida usó (creados o reconciliados); consumido por la reconciliación al final.
    touched_event_ids: set[str] = set()

    logger.info(
        "timeline_materialization_started",
        extra={
            "analysis_id": analysis_id,
            "created_by": created_by,
            "eventos_temporales_count": len(eventos_temporales),
            "plazos_relativos_count": len(plazos_relativos),
            "existing_events": len(index),
        },
    )

    # 1. Hitos con nombre propio (algunos ya con fecha explícita del pliego).
    for item in eventos_temporales:
        nombre = str(item.get("nombre") or "").strip()
        if not nombre:
            continue
        event = _find_or_create_event(
            db,
            analysis_id,
            nombre,
            index=index,
            fuzzy_candidates=pre_existing,
            fecha_explicita=item.get("fecha_explicita"),
            source_document_id=item.get("fuente_documento_id") or item.get("_source_document_id"),
            source_page=item.get("fuente_pagina"),
            source_fragment=item.get("fuente_fragmento"),
            result=result,
            mencion_propia=bool(item.get("mencion_propia", True)),
        )
        touched_event_ids.add(event.event_id)

    # 2. Plazos relativos: target + trigger + el Deadline que los conecta.
    triggers_with_date: set[str] = set()

    for item in plazos_relativos:
        descripcion = str(item.get("descripcion") or "").strip()
        evento_disparador = str(item.get("evento_disparador") or "").strip()
        if not descripcion or not evento_disparador:
            result.skipped.append(
                f"Plazo relativo sin descripcion/evento_disparador válidos: {item!r}"
            )
            continue

        direccion = _normalize_direction(item.get("direccion"))
        if direccion is None:
            direccion = _infer_direction_from_text(
                item.get("fuente_fragmento"),
                descripcion,
                evento_disparador,
            )
        if direccion is None:
            direccion = _infer_structural_dependency_direction(
                descripcion=descripcion,
                evento_disparador=evento_disparador,
                source_fragment=item.get("fuente_fragmento"),
                item=item,
            )
        if direccion not in _VALID_DIRECTIONS:
            # Se descarta solo porque la dirección es desconocida, no porque el motor no la calcule (ver _VALID_DIRECTIONS).
            result.skipped.append(
                f"'{descripcion}': dirección '{direccion}' desconocida o ausente -- "
                "no se puede crear el plazo sin saber la relación temporal con el "
                "disparador."
            )
            continue

        source_document_id = item.get("fuente_documento_id") or item.get("_source_document_id")
        source_page = item.get("fuente_pagina")
        source_fragment = item.get("fuente_fragmento")

        target = _find_or_create_event(
            db,
            analysis_id,
            descripcion,
            index=index,
            fuzzy_candidates=pre_existing,
            source_document_id=source_document_id,
            source_page=source_page,
            source_fragment=source_fragment,
            result=result,
        )
        trigger = _find_or_create_event(
            db,
            analysis_id,
            evento_disparador,
            index=index,
            fuzzy_candidates=pre_existing,
            source_document_id=source_document_id,
            source_page=source_page,
            source_fragment=source_fragment,
            result=result,
            # Sin match acá: el LLM no le dio su propio ítem en eventos_temporales; se crea igual sin mención propia conocida.
            mencion_propia=False,
        )
        touched_event_ids.add(target.event_id)
        touched_event_ids.add(trigger.event_id)

        if trigger.event_id == target.event_id:
            result.skipped.append(
                f"'{descripcion}': el disparador y el resultado resolvieron al "
                "mismo evento -- no tiene sentido crear un deadline circular."
            )
            continue

        if trigger.event_date is not None:
            triggers_with_date.add(trigger.event_id)

        duration = int(item.get("cantidad") or 0)
        unit = str(item.get("unidad") or "días")
        day_type = str(item.get("tipo_dias") or "no_especificado")

        if _deadline_already_exists(
            existing_deadlines,
            trigger_event_id=trigger.event_id,
            target_event_id=target.event_id,
            duration=duration,
            unit=unit,
            day_type=day_type,
        ):
            continue

        deadline = Deadline(
            partition_key=analysis_id,
            analysis_id=analysis_id,
            name=descripcion[:120],
            trigger_event_id=trigger.event_id,
            target_event_id=target.event_id,
            duration=duration,
            unit=unit,
            day_type=day_type,
            direccion=direccion,
            es_plazo_maximo=bool(item.get("es_plazo_maximo", False)),
            source_document_id=source_document_id,
            source_page=source_page,
            source_fragment=source_fragment[:500] if source_fragment else None,
        )
        created_deadline = repository.create_deadline(db, deadline)
        existing_deadlines.append(created_deadline)
        result.deadlines_created += 1

    # 3. Reconciliación: lo no vuelto a mencionar se soft-elimina (salvo confirmado/user_input) para que el reanálisis no solo acumule filas (bug real, ver docstring del módulo).
    stale_event_ids: set[str] = set()
    for event in pre_existing:
        if event.event_id in touched_event_ids:
            continue
        if event.status == "confirmed" or event.date_source == "user_input":
            continue
        pruned_event = event.model_copy(
            update={"deleted": True, "updated_at": datetime.now(UTC)}
        )
        repository.update_event(db, pruned_event)
        stale_event_ids.add(event.event_id)
        result.events_pruned += 1

    if stale_event_ids:
        for deadline in pre_existing_deadlines:
            if (
                deadline.trigger_event_id in stale_event_ids
                or deadline.target_event_id in stale_event_ids
            ):
                pruned_deadline = deadline.model_copy(
                    update={"deleted": True, "updated_at": datetime.now(UTC)}
                )
                repository.update_deadline(db, pruned_deadline)
                result.deadlines_pruned += 1

    # 4. Corre la cascada ahora para triggers con fecha, en vez de esperar una acción del usuario.
    if triggers_with_date:
        service = TimelineService(db)
        for trigger_event_id in triggers_with_date:
            cascade = recalculate_dependent_dates(
                service, analysis_id, trigger_event_id, user_id=created_by
            )
            if cascade.errors:
                result.skipped.extend(cascade.errors)

    logger.info(
        "timeline_materialization_completed",
        extra={
            "analysis_id": analysis_id,
            "events_created": result.events_created,
            "deadlines_created": result.deadlines_created,
            "events_pruned": result.events_pruned,
            "deadlines_pruned": result.deadlines_pruned,
            "skipped_count": len(result.skipped),
        },
    )

    return result
