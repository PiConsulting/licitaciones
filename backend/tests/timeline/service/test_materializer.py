"""Tests de `timeline.materializer` -- materialización automática del
Timeline (Event/Deadline) a partir de lo que extrae el pipeline de análisis
(`eventos_temporales`/`plazos_relativos`). Ver docstring del módulo para el
contexto completo.
"""
from __future__ import annotations

from timeline import repository
from timeline.materializer import materialize_timeline_from_extraction
from timeline.models import Event

from tests.timeline.service.conftest import TEST_USER_ID


def _evento_temporal(nombre: str, **overrides) -> dict:
    defaults = {
        "nombre": nombre,
        "fecha_explicita": None,
        "origen_fecha": "pendiente",
        "fuente_documento_id": None,
        "fuente_pagina": 1,
        "fuente_fragmento": f"Fragmento de ejemplo mencionando {nombre}.",
    }
    defaults.update(overrides)
    return defaults


def _plazo_relativo(descripcion: str, evento_disparador: str, **overrides) -> dict:
    defaults = {
        "descripcion": descripcion,
        "cantidad": 15,
        "unidad": "días",
        "tipo_dias": "corridos",
        "evento_disparador": evento_disparador,
        "direccion": "desde",
        "es_plazo_maximo": True,
        "fuente_documento_id": None,
        "fuente_pagina": 3,
        "fuente_fragmento": f"Fragmento de ejemplo: {descripcion} desde {evento_disparador}.",
    }
    defaults.update(overrides)
    return defaults


class TestMaterializeFromPlazosRelativos:
    def test_creates_trigger_target_and_deadline(self, db_session, analysis_id):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert "Plazo de entrega de equipamiento" in events
        assert "Fecha de adjudicación" in events
        target = events["Plazo de entrega de equipamiento"]
        trigger = events["Fecha de adjudicación"]
        assert target.date_source == "pending"
        assert trigger.date_source == "pending"

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert deadlines[0].trigger_event_id == trigger.event_id
        assert deadlines[0].target_event_id == target.event_id
        assert deadlines[0].duration == 15
        assert deadlines[0].day_type == "corridos"

    def test_trigger_created_only_to_satisfy_evento_disparador_is_marked_not_self_mentioned(
        self, db_session, analysis_id
    ):
        """El usuario pidió poder distinguir "esto está en el pliego" de
        "esto lo inferimos para completar la fecha de otro evento". Cuando
        el trigger de un plazo relativo no existe todavía como su propio
        evento (el LLM no le creó su propio ítem en eventos_temporales), el
        materializador lo crea igual -- pero honestamente no hay ninguna
        mención propia conocida, así que `source_reference.mencion_propia`
        queda en False."""
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        trigger = events["Fecha de adjudicación"]
        target = events["Plazo de entrega de equipamiento"]

        assert trigger.source_reference == {"mencion_propia": False}
        assert target.source_reference == {"mencion_propia": True}

    def test_hito_extraido_con_mencion_propia_false_se_propaga_al_event(
        self, db_session, analysis_id
    ):
        """Cuando el hito SÍ vino con su propio ítem en eventos_temporales
        pero el LLM lo marcó `mencion_propia=False` (porque solo lo agregó
        para completar un evento_disparador), el materializador respeta ese
        valor en vez de asumir True por default."""
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal("Puesta en Marcha del Sistema", mencion_propia=False),
            ],
            plazos_relativos=[],
        )

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert events["Puesta en Marcha del Sistema"].source_reference == {
            "mencion_propia": False
        }

    def test_two_deadlines_share_the_same_trigger_event(self, db_session, analysis_id):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación"),
                _plazo_relativo("Presentación para kick off", "Fecha de adjudicación", cantidad=10),
            ],
        )

        # 2 targets + 1 solo trigger compartido = 3 eventos, no 4.
        assert result.events_created == 3
        assert result.deadlines_created == 2

        events = repository.list_events(db_session, analysis_id)
        adjudicacion_events = [e for e in events if e.name == "Fecha de adjudicación"]
        assert len(adjudicacion_events) == 1

        deadlines = repository.list_deadlines(db_session, analysis_id)
        trigger_ids = {d.trigger_event_id for d in deadlines}
        assert trigger_ids == {adjudicacion_events[0].event_id}

    def test_reuses_existing_event_by_token_overlap_when_words_are_reordered(
        self, db_session, analysis_id
    ):
        """No es substring (el orden de las palabras difiere) ni casi-idéntico
        para difflib -- solo matchea por superposición de palabras clave
        (tier 3 de `_find_matching_event`)."""
        existing = repository.create_event(
            db_session,
            Event(
                partition_key=analysis_id,
                analysis_id=analysis_id,
                name="Recepción Total del Hardware",
            ),
        )

        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Hardware: recepción total adquirido", "Adjudicación")
            ],
        )

        # El target matcheó por tokens con el existente; solo se creó el trigger nuevo.
        assert result.events_created == 1
        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert "Adjudicación" in events
        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert deadlines[0].target_event_id == existing.event_id

    def test_does_not_match_unrelated_events_by_a_single_short_word(
        self, db_session, analysis_id
    ):
        """Una sola palabra corta en común ("plazo", "fecha") no alcanza --
        evita falsos positivos entre hitos que no tienen nada que ver."""
        existing = repository.create_event(
            db_session,
            Event(
                partition_key=analysis_id,
                analysis_id=analysis_id,
                name="Plazo de mantenimiento de oferta",
            ),
        )

        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[_plazo_relativo("Plazo de garantía técnica", "Recepción definitiva")],
        )

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert "Plazo de garantía técnica" in events
        assert events["Plazo de garantía técnica"].event_id != existing.event_id
        assert result.events_created == 2

    def test_reuses_existing_event_by_substring_match(self, db_session, analysis_id):
        existing = repository.create_event(
            db_session,
            Event(
                partition_key=analysis_id,
                analysis_id=analysis_id,
                name="Recepción Provisoria",
            ),
        )

        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Otorgamiento de la F.A.D.",
                    "Recepción provisoria de cada uno de los HITOS",
                )
            ],
        )

        # El trigger matcheó por substring con el existente; solo se creó el target nuevo.
        assert result.events_created == 1
        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert deadlines[0].trigger_event_id == existing.event_id

    def test_does_not_fuzzy_merge_two_different_hitos_from_the_same_extraction(
        self, db_session, analysis_id
    ):
        """Bug real (2026-09-01, pliego Banco de Córdoba): "Soporte de
        Migraciones" (un hito con su propio ítem, duración 6 meses) y
        "Inicio de la Tercera Etapa de Migraciones con Soporte" (su
        disparador, OTRO ítem de la MISMA extracción) son dos hitos
        distintos -- pero el nombre corto del primero está totalmente
        contenido, token por token, en el nombre largo del segundo. El tier
        3 de `_find_matching_event` (superposición de tokens) los
        fusionaba en un solo Event, dejando el deadline "circular" (mismo
        trigger que target, `result.skipped`) y perdiendo el plazo relativo
        entero -- justo lo que reportó el usuario al ver "Soporte de
        Migraciones" sin la fórmula de cálculo y sin que su disparador
        apareciera en "Fechas por cargar". El fix: la heurística de texto
        (substring/tokens/difflib) solo puede matchear contra eventos que
        YA EXISTÍAN antes de esta corrida, nunca entre dos ítems creados en
        la misma corrida -- ahí el LLM ya decidió que son cosas distintas
        (cada uno con su propio ítem y su propio `fuente_fragmento`)."""
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal("Soporte de Migraciones"),
                _evento_temporal("Inicio de la Tercera Etapa de Migraciones con Soporte"),
            ],
            plazos_relativos=[
                _plazo_relativo(
                    "Soporte de Migraciones",
                    "Inicio de la Tercera Etapa de Migraciones con Soporte",
                    cantidad=6,
                    unidad="meses",
                    tipo_dias="no_especificado",
                )
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1
        assert result.skipped == []

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert set(events) == {
            "Soporte de Migraciones",
            "Inicio de la Tercera Etapa de Migraciones con Soporte",
        }

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert (
            deadlines[0].trigger_event_id
            == events["Inicio de la Tercera Etapa de Migraciones con Soporte"].event_id
        )
        assert deadlines[0].target_event_id == events["Soporte de Migraciones"].event_id

    def test_direccion_antes_de_is_materialized_but_not_calculated(self, db_session, analysis_id):
        """Antes (bug real, ver test de arriba sobre 'Soporte de
        Migraciones') `direccion='antes_de'/'hasta'` hacía que el plazo
        entero se descartara en la materialización -- perdiendo la relación
        completa, incluso en casos donde el LLM solo se equivocó de
        dirección entre corridas. Ahora el Event/Deadline se crean igual
        (la relación queda visible en el Timeline); lo único que no pasa es
        que el motor de cálculo compute una fecha -- eso lo frena
        `validate_deadline_for_calculation` (`timeline/validation.py`),
        no el materializador."""
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Presentación de consultas", "Apertura de ofertas", direccion="antes_de"
                )
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1
        assert result.skipped == []

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        assert set(events) == {"Presentación de consultas", "Apertura de ofertas"}

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert deadlines[0].direccion == "antes_de"
        assert deadlines[0].calculation_status == "pending"
        assert deadlines[0].deadline_date is None

    def test_direccion_ausente_se_infiere_desde_fuente_fragmento(self, db_session, analysis_id):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Presentación de consultas",
                    "Apertura de ofertas",
                    direccion=None,
                    fuente_fragmento=(
                        "Las consultas deberán presentarse a más tardar dentro de los 5 días "
                        "hábiles contados a partir de la apertura de ofertas."
                    ),
                )
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1
        assert result.skipped == []

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert deadlines[0].direccion == "desde"

    def test_direccion_ausente_con_relacion_entre_hitos_se_infiere_como_dependencia(
        self, db_session, analysis_id
    ):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Notificación formal de adjudicación",
                    "Adjudicación",
                    cantidad=None,
                    unidad=None,
                    tipo_dias=None,
                    direccion=None,
                    fuente_fragmento=(
                        "La contratación quedará perfeccionada con la notificación formal "
                        "del acto administrativo de adjudicación."
                    ),
                )
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1
        assert result.skipped == []

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert deadlines[0].direccion == "desde"
        assert deadlines[0].duration == 0

    def test_direccion_ausente_con_una_vez_cumplida_se_infiere_como_desde(
        self, db_session, analysis_id
    ):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Emisión de la Factura",
                    "Entrega de los Bienes",
                    cantidad=None,
                    unidad=None,
                    tipo_dias=None,
                    direccion=None,
                    fuente_fragmento=(
                        "La factura deberá ser emitida una vez cumplida la entrega y obtenida "
                        "la conformidad técnica y administrativa correspondiente."
                    ),
                )
            ],
        )

        assert result.events_created == 2
        assert result.deadlines_created == 1
        assert result.skipped == []

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert len(deadlines) == 1
        assert deadlines[0].direccion == "desde"
        assert deadlines[0].duration == 0

    def test_direccion_desconocida_o_ausente_sigue_saltandose(self, db_session, analysis_id):
        """A diferencia de 'antes_de'/'hasta' (direcciones válidas que el
        motor todavía no sabe calcular), una dirección None/inválida no
        dice NADA sobre la relación temporal -- ahí sí no hay nada que
        materializar."""
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo(
                    "Presentación de consultas",
                    "Apertura de ofertas",
                    direccion=None,
                    fuente_fragmento="Recepción definitiva sujeta a validación técnica.",
                )
            ],
        )

        assert result.events_created == 0
        assert result.deadlines_created == 0
        assert len(result.skipped) == 1
        assert repository.list_events(db_session, analysis_id) == []
        assert repository.list_deadlines(db_session, analysis_id) == []

    def test_rerun_is_idempotent_and_does_not_overwrite_user_edit(self, db_session, analysis_id):
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        # El usuario carga la fecha del disparador a mano.
        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        trigger = events["Fecha de adjudicación"]
        trigger.event_date = __import__("datetime").date(2026, 9, 10)
        trigger.date_source = "user_input"
        repository.update_event(db_session, trigger)

        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        assert result.events_created == 0
        assert result.deadlines_created == 0

        refetched_trigger = repository.get_event(db_session, trigger.event_id, analysis_id)
        assert refetched_trigger.date_source == "user_input"
        assert refetched_trigger.event_date == __import__("datetime").date(2026, 9, 10)


class TestMaterializeCascade:
    def test_explicit_date_on_trigger_cascades_immediately(self, db_session, analysis_id):
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal(
                    "Fecha de adjudicación",
                    fecha_explicita="2026-09-10",
                    origen_fecha="detectada",
                    fuente_documento_id="00000000-0000-0000-0000-000000000000",
                )
            ],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        assert result.deadlines_created == 1

        deadlines = repository.list_deadlines(db_session, analysis_id)
        assert deadlines[0].calculation_status == "calculated"
        assert deadlines[0].deadline_date.isoformat() == "2026-09-25"

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        target = events["Plazo de entrega de equipamiento"]
        assert target.date_source == "calculated"
        assert target.event_date.isoformat() == "2026-09-25"

    def test_cascade_does_not_overwrite_a_target_the_user_fixed_by_hand(
        self, db_session, analysis_id
    ):
        """Si el usuario corrigió a mano la fecha calculada de un evento
        (date_source='user_input', vía EditDateModal en el frontend), una
        corrida posterior de la cascada -- disparada acá porque el trigger
        cambia de fecha -- NO debe pisarla. Reproduce el bug real: antes de
        este fix, `recalculate_dependent_dates` siempre sobreescribía el
        evento target con la fecha recalculada, sin importar su
        date_source."""
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal(
                    "Fecha de adjudicación",
                    fecha_explicita="2026-09-10",
                    fuente_documento_id="00000000-0000-0000-0000-000000000000",
                )
            ],
            plazos_relativos=[
                _plazo_relativo("Plazo de entrega de equipamiento", "Fecha de adjudicación")
            ],
        )

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}
        target = events["Plazo de entrega de equipamiento"]
        assert target.event_date.isoformat() == "2026-09-25"  # 2026-09-10 + 15 corridos

        target.event_date = __import__("datetime").date(2026, 10, 1)
        target.date_source = "user_input"
        repository.update_event(db_session, target)

        trigger = events["Fecha de adjudicación"]
        trigger.event_date = __import__("datetime").date(2026, 9, 15)
        trigger.date_source = "user_input"
        repository.update_event(db_session, trigger)

        from timeline.calculation_engine import recalculate_dependent_dates
        from timeline.service import TimelineService

        service = TimelineService(db_session)
        recalculate_dependent_dates(service, analysis_id, trigger.event_id, TEST_USER_ID)

        refetched_target = repository.get_event(db_session, target.event_id, analysis_id)
        # Sigue en la fecha cargada a mano, NO en 2026-09-15+15=2026-09-30 (lo que daría la cascada).
        assert refetched_target.date_source == "user_input"
        assert refetched_target.event_date.isoformat() == "2026-10-01"

        deadlines = repository.list_deadlines(db_session, analysis_id)
        # "calculated" pero reflejando la fecha real del evento (la del usuario), no la fórmula.
        assert deadlines[0].calculation_status == "calculated"
        assert deadlines[0].deadline_date.isoformat() == "2026-10-01"


class TestMaterializeReconciliation:
    """Reproduce el bug real reportado por la usuaria: reanálisis sucesivos
    del pliego (prompt distinto, o simplemente no-determinismo del LLM) iban
    ACUMULANDO `Event`/`Deadline` de corridas anteriores sin límite, porque
    `materialize_timeline_from_extraction` solo sabía agregar -- nunca
    reconciliar contra lo que la corrida actual ya no menciona. Confirmado
    contra la base real: los 8 pliegos golden de este repo tenían entre 12 y
    30 filas "fantasma" por pliego, con `created_at` de corridas de casi dos
    semanas de reanálisis manuales durante esta sesión."""

    def test_second_run_with_unrelated_items_prunes_stale_events_and_deadlines(
        self, db_session, analysis_id
    ):
        first = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[_evento_temporal("Hito viejo del prompt anterior")],
            plazos_relativos=[
                _plazo_relativo("Plazo viejo de entrega", "Fecha de adjudicación vieja")
            ],
        )
        assert first.events_created == 3
        assert first.deadlines_created == 1

        second = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[_evento_temporal("Hito nuevo del prompt corregido")],
            plazos_relativos=[],
        )

        assert second.events_created == 1
        # Los 3 eventos de la corrida anterior (ninguno confirmado ni a mano) y su deadline se podan.
        assert second.events_pruned == 3
        assert second.deadlines_pruned == 1

        remaining = {e.name for e in repository.list_events(db_session, analysis_id)}
        assert remaining == {"Hito nuevo del prompt corregido"}
        assert repository.list_deadlines(db_session, analysis_id) == []

        # Nada desapareció de verdad -- sigue en la base como soft-delete.
        all_events = repository.list_events(db_session, analysis_id, include_deleted=True)
        assert len(all_events) == 4

    def test_reconciliation_never_prunes_confirmed_or_user_input_events(
        self, db_session, analysis_id
    ):
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal("Hito confirmado a mano"),
                _evento_temporal("Hito con fecha cargada por el usuario"),
                _evento_temporal("Hito que sí debería podarse"),
            ],
            plazos_relativos=[],
        )

        events = {e.name: e for e in repository.list_events(db_session, analysis_id)}

        confirmed = events["Hito confirmado a mano"]
        confirmed.status = "confirmed"
        repository.update_event(db_session, confirmed)

        user_loaded = events["Hito con fecha cargada por el usuario"]
        user_loaded.event_date = __import__("datetime").date(2026, 11, 1)
        user_loaded.date_source = "user_input"
        repository.update_event(db_session, user_loaded)

        # La corrida siguiente (prompt nuevo) ya no menciona ninguno de los tres hitos anteriores.
        result = materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[_evento_temporal("Hito totalmente distinto")],
            plazos_relativos=[],
        )

        # Solo se podó el que ni estaba confirmado ni tenía fecha de usuario.
        assert result.events_pruned == 1

        remaining = {e.name for e in repository.list_events(db_session, analysis_id)}
        assert remaining == {
            "Hito confirmado a mano",
            "Hito con fecha cargada por el usuario",
            "Hito totalmente distinto",
        }

    def test_rerun_with_identical_items_prunes_nothing(self, db_session, analysis_id):
        """La idempotencia documentada en el módulo sigue valiendo: correr
        la MISMA extracción dos veces no debe podar nada, porque cada ítem
        de la segunda corrida matchea (tier 1, nombre exacto) contra el
        evento que ya existía."""
        items = [_evento_temporal("Hito estable")]
        materialize_timeline_from_extraction(
            db_session, analysis_id, TEST_USER_ID, eventos_temporales=items, plazos_relativos=[]
        )
        result = materialize_timeline_from_extraction(
            db_session, analysis_id, TEST_USER_ID, eventos_temporales=items, plazos_relativos=[]
        )

        assert result.events_created == 0
        assert result.events_pruned == 0
        assert len(repository.list_events(db_session, analysis_id)) == 1


class TestMaterializeSourceRefresh:
    """Reproduce el bug real reportado por la usuaria en Santa Fe: el evento
    "Retiro de las Muestras de Ofertas No Adjudicadas" tenía `source_page=12`
    grabado desde la primera extracción (2026-09-14), pese a 13 reanálisis
    posteriores en los que la extracción ya traía `fuente_pagina=11` (la
    página correcta, confirmada contra los chunks reales del pliego) --
    `_find_or_create_event` devolvía el evento existente TAL CUAL en un match
    por nombre, sin refrescar su cita. El botón "ver fuente" del Timeline
    navegaba a la página equivocada y el highlight nunca encontraba el texto
    ahí. Ver `_refresh_stale_source` en `timeline/materializer.py`."""

    def test_second_run_with_different_citation_refreshes_source(
        self, db_session, analysis_id
    ):
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal(
                    "Retiro de las Muestras de Ofertas No Adjudicadas",
                    fuente_documento_id="doc-1",
                    fuente_pagina=12,
                    fuente_fragmento="cita vieja, página equivocada",
                )
            ],
            plazos_relativos=[],
        )

        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal(
                    "Retiro de las Muestras de Ofertas No Adjudicadas",
                    fuente_documento_id="doc-1",
                    fuente_pagina=11,
                    fuente_fragmento="Las muestras de ofertas no adjudicadas... dentro de los treinta (30) días.",
                )
            ],
            plazos_relativos=[],
        )

        [event] = repository.list_events(db_session, analysis_id)
        assert event.source_page == 11
        assert "no adjudicadas" in event.source_fragment

    def test_refresh_never_touches_confirmed_event(self, db_session, analysis_id):
        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal("Hito confirmado", fuente_pagina=12)
            ],
            plazos_relativos=[],
        )

        [event] = repository.list_events(db_session, analysis_id)
        event.status = "confirmed"
        repository.update_event(db_session, event)

        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[
                _evento_temporal("Hito confirmado", fuente_pagina=99)
            ],
            plazos_relativos=[],
        )

        [event] = repository.list_events(db_session, analysis_id)
        assert event.source_page == 12

    def test_refresh_never_touches_event_with_user_input_date(
        self, db_session, analysis_id
    ):
        import datetime as _dt

        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[_evento_temporal("Hito con fecha manual", fuente_pagina=12)],
            plazos_relativos=[],
        )

        [event] = repository.list_events(db_session, analysis_id)
        event.event_date = _dt.date(2026, 11, 1)
        event.date_source = "user_input"
        repository.update_event(db_session, event)

        materialize_timeline_from_extraction(
            db_session,
            analysis_id,
            TEST_USER_ID,
            eventos_temporales=[_evento_temporal("Hito con fecha manual", fuente_pagina=99)],
            plazos_relativos=[],
        )

        [event] = repository.list_events(db_session, analysis_id)
        assert event.source_page == 12

    def test_rerun_with_same_citation_does_not_bump_updated_at(
        self, db_session, analysis_id
    ):
        """No refrescar cuando no hay nada distinto -- evita escrituras
        (y bumps de `updated_at`) innecesarias en el caso común (misma
        extracción, corrida de nuevo)."""
        items = [_evento_temporal("Hito estable", fuente_pagina=5)]
        materialize_timeline_from_extraction(
            db_session, analysis_id, TEST_USER_ID, eventos_temporales=items, plazos_relativos=[]
        )
        [before] = repository.list_events(db_session, analysis_id)

        materialize_timeline_from_extraction(
            db_session, analysis_id, TEST_USER_ID, eventos_temporales=items, plazos_relativos=[]
        )
        [after] = repository.list_events(db_session, analysis_id)

        assert after.updated_at == before.updated_at
        assert after.source_page == 5
