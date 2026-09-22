"""Tests para `_filter_non_hitos` (`analysis/extraction/extractors/eventos_temporales.py`).

FIX (2026-09-21, rediseño arquitectónico -- ver memoria
`eventos-temporales-auditoria-completa-2026-09-21`): hasta acá, el juicio de
"¿esto es un hito real?" vivía en ~6 funciones de post-filtrado por regex
sobre `nombre`/`fuente_fragmento` (obligación recurrente, métrica de SLA,
garantía de equipo huérfana, etiqueta genérica, facultad discrecional) -- una
por cada síntoma textual encontrado en un pliego real, que no generalizaba a
una redacción nueva del mismo problema. Ahora el LLM declara 3 propiedades
por cada ítem en el momento de generarlo (`accion_concreta`,
`es_ocurrencia_unica`, `depende_de_decision_discrecional` -- ver
`HitoTemporalExtracted` en `schemas.py` y la regla 8 del prompt), y
`_is_irrelevant_hito` solo LEE esos 3 campos -- no vuelve a inferirlos por
texto libre. Estos tests verifican esa lectura, más los mecanismos de
integridad de datos que siguen siendo por código (disparadores colgantes,
duplicados por cita idéntica, huérfanos de `mencion_propia`).
"""
from __future__ import annotations

from analysis.extraction.extractors.eventos_temporales import (
    _consolidate_duplicate_hitos,
    _filter_non_hitos,
    _merge_enumerated_fragment_duplicates,
    _strip_dangling_disparador,
)


def _hito(nombre: str, fragmento: str, **overrides) -> dict:
    """Los 3 campos nuevos (`accion_concreta`/`es_ocurrencia_unica`/
    `depende_de_decision_discrecional`) por default describen un hito VÁLIDO
    -- los tests que quieren simular un candidato irrelevante los
    sobreescriben explícitamente, igual que como lo haría una corrida real
    donde el LLM los completa con convicción."""
    defaults = {
        "nombre": nombre,
        "fecha_explicita": None,
        "origen_fecha": "pendiente",
        "evento_disparador": None,
        "cantidad": None,
        "unidad": None,
        "tipo_dias": None,
        "direccion": None,
        "es_plazo_maximo": False,
        "mencion_propia": True,
        "accion_concreta": f"se produce la acción de {nombre}",
        "es_ocurrencia_unica": True,
        "depende_de_decision_discrecional": False,
        "fuente_documento_id": "doc-1",
        "fuente_pagina": 1,
        "fuente_fragmento": fragmento,
        "extraction_status": "success",
    }
    defaults.update(overrides)
    return defaults



class TestDanglingDisparador:
    def test_strips_evento_disparador_sin_cantidad(self):
        """Bug real (3 pliegos distintos): una secuencia narrativa sin plazo
        numérico ("X luego de Y") no debe modelarse como plazo relativo --
        `timeline/materializer.py` convertía el `cantidad: null` resultante en
        una duración de 0, mostrando un plazo "0 días" que el pliego nunca
        afirmó."""
        item = _hito(
            "Capacitación del Personal",
            "El personal será capacitado luego de la puesta en marcha del sistema.",
            evento_disparador="Puesta en Marcha del Sistema",
            cantidad=None,
            unidad=None,
        )

        stripped = _strip_dangling_disparador(item)

        assert stripped["evento_disparador"] is None
        assert stripped["unidad"] is None
        assert stripped["direccion"] is None
        assert stripped["es_plazo_maximo"] is False

    def test_no_toca_un_plazo_relativo_completo(self):
        item = _hito(
            "Firma del Contrato",
            "Dentro de los 10 días de la adjudicación.",
            evento_disparador="Adjudicación",
            cantidad=10,
            unidad="días",
            direccion="desde",
        )

        stripped = _strip_dangling_disparador(item)

        assert stripped == item

    def test_filter_non_hitos_aplica_el_strip_antes_de_evaluar_relevancia(self):
        """El strip corre primero -- pero la decisión de "es esto un hito"
        ahora depende de los 3 campos declarados, no de si tiene
        `evento_disparador`. Un ítem que el LLM marcó como recurrente
        (`es_ocurrencia_unica: False`) se elimina igual, tenga o no un
        disparador colgante."""
        item = _hito(
            "Reporte Mensual",
            "El adjudicatario deberá entregar un reporte mensual con el "
            "detalle de los casos.",
            evento_disparador="Puesta en Marcha del Sistema",
            cantidad=None,
            es_ocurrencia_unica=False,
        )

        assert _filter_non_hitos([item]) == []



class TestStructuralRelevance:
    """Reemplaza las 4 clases retiradas (`TestRecurringObligations`,
    `TestOrphanEquipmentWarranty`, `TestRecurringSlaTrigger`,
    `TestDiscretionaryFaculty`) -- las mismas 5 clases de error reales
    encontradas esta sesión (obligación recurrente, métrica de SLA, garantía
    de equipo huérfana, etiqueta genérica, facultad discrecional) ahora se
    verifican a través de los 3 campos estructurados, no de regexes
    dedicados por síntoma."""

    def test_filtra_obligacion_recurrente_marcada_por_el_llm(self):
        """Caso real (Bancor): "Reporte Mensual" -- antes se reconocía por
        regex de periodicidad+entregable, ahora por el campo declarado."""
        item = _hito(
            "Reporte Mensual",
            "El adjudicatario deberá entregar un reporte mensual con el "
            "detalle de los casos y las horas consumidas.",
            es_ocurrencia_unica=False,
        )

        assert _filter_non_hitos([item]) == []

    def test_filtra_metrica_de_sla_disparador_y_dependiente(self):
        """Caso real (Dell, Ce.Si.Da, Nucleoeléctrica): un tiempo de
        respuesta contado desde un llamado/reclamo repetible -- tanto el
        disparador como el dependiente deben declararse como NO ocurrencia
        única."""
        llamado = _hito(
            "Llamado Telefónico",
            "El usuario reportará la falla mediante llamado telefónico al "
            "centro de atención.",
            es_ocurrencia_unica=False,
        )
        respuesta = _hito(
            "Tiempo de Respuesta",
            "El proveedor deberá responder dentro de las 24 horas del "
            "llamado telefónico.",
            evento_disparador="Llamado Telefónico",
            cantidad=24,
            unidad="horas",
            direccion="desde",
            es_ocurrencia_unica=False,
        )

        assert _filter_non_hitos([llamado, respuesta]) == []

    def test_filtra_garantia_de_equipo_huerfana(self):
        """Caso real (Bancor): duración de garantía de un producto -- no es
        una ocurrencia puntual, es una característica continua."""
        item = _hito(
            "Garantía de Hardware",
            "Se requiere para los equipos un servicio contra todo defecto "
            "de materiales, con 3 años de garantía de reemplazo de "
            "hardware, brindado por el fabricante.",
            es_ocurrencia_unica=False,
        )

        assert _filter_non_hitos([item]) == []

    def test_conserva_garantia_tecnica_usada_como_disparador_real(self):
        """Caso real (Nucleoeléctrica): "Garantía Técnica" es, en el fondo,
        el inicio de un período (no una ocurrencia puntual en sí), pero
        cumple un rol real como disparador de "Recepción Definitiva" 36
        meses después -- la protección por `_referenced_as_trigger` sigue
        aplicando aunque `es_ocurrencia_unica` sea `False`."""
        garantia = _hito(
            "Garantía Técnica",
            "A partir de este momento comenzará el período de 36 meses de "
            "garantía técnica.",
            es_ocurrencia_unica=False,
        )
        recepcion = _hito(
            "Recepción Definitiva",
            "Se realizará dentro de los 36 meses de garantía técnica.",
            evento_disparador="Garantía Técnica",
            cantidad=36,
            unidad="meses",
            direccion="desde",
        )

        filtered = _filter_non_hitos([garantia, recepcion])

        names = {item["nombre"] for item in filtered}
        assert "Garantía Técnica" in names
        assert "Recepción Definitiva" in names

    def test_filtra_etiqueta_generica_sin_accion_concreta(self):
        """Caso real (Bancor): "Hito Intermedio del Plan de Trabajo" y
        variantes -- si no se puede escribir una acción concreta con
        convicción, el campo queda vacío o insuficiente."""
        item = _hito(
            "Hito Intermedio del Plan de Trabajo",
            "Incumplimiento de un hito intermedio del plan de trabajo "
            "(kick-off, PoC, documentación, capacitación).",
            accion_concreta="",
        )

        assert _filter_non_hitos([item]) == []

    def test_filtra_facultad_discrecional_marcada_por_el_llm(self):
        """Caso real (Bancor 9cc0a4c1): "Facultad Resolutoria Implícita",
        "Auditorías e Inspecciones", "Resolución de Conflictos"."""
        item = _hito(
            "Auditorías e Inspecciones",
            "El Banco tiene la facultad de inspeccionar los servicios en "
            "cualquier momento durante la ejecución del contrato.",
            depende_de_decision_discrecional=True,
        )

        assert _filter_non_hitos([item]) == []

    def test_no_filtra_facultad_atada_a_una_ventana_puntual(self):
        item = _hito(
            "Prórroga de la Fecha de Apertura",
            "El organismo podrá prorrogar la fecha de apertura hasta 2 "
            "días antes de la fecha original.",
            depende_de_decision_discrecional=False,
        )

        assert _filter_non_hitos([item]) == [item]

    def test_conserva_items_con_fecha_explicita_pase_lo_que_pase(self):
        """Una `fecha_explicita` propia protege el ítem sin importar cómo se
        hayan declarado los otros 3 campos -- es la señal más fuerte de que
        es un hito real."""
        item = _hito(
            "Auditoría Anual",
            "La auditoría anual se realizará el 15/03/2027.",
            fecha_explicita="2027-03-15",
            origen_fecha="detectada",
            es_ocurrencia_unica=False,
        )

        assert _filter_non_hitos([item]) == [item]

    def test_filtra_el_par_que_se_protege_mutuamente(self):
        """Caso real (Bancor c2928f68): "Acumulación de Penalidades" y
        "Regularización del Servicio" se protegían mutuamente -- el segundo
        depende del primero como `evento_disparador`, así que el primero
        parece "referenciado" y sobrevive la primera pasada. Necesita la
        segunda pasada: una vez que "Regularización del Servicio" cae por
        sus propios campos, "Acumulación de Penalidades" deja de tener quién
        lo referencie y también cae."""
        fragmento = (
            "La reincidencia en incumplimientos de nivel Crítico o Alto, o la "
            "acumulación de penalidades por dos meses consecutivos, facultará "
            "al Banco a intimar la regularización del servicio bajo "
            "apercibimiento de rescisión."
        )
        acumulacion = _hito(
            "Acumulación de Penalidades",
            fragmento,
            accion_concreta="",
        )
        regularizacion = _hito(
            "Regularización del Servicio",
            fragmento,
            evento_disparador="Acumulación de Penalidades",
            cantidad=2,
            unidad="meses",
            direccion="desde",
            depende_de_decision_discrecional=True,
        )

        assert _filter_non_hitos([acumulacion, regularizacion]) == []

    def test_conserva_hitos_genuinos_sin_tocar(self):
        """Control: una lista de hitos genuinos (con los 3 campos en sus
        valores "válidos" por default de `_hito`) no pierde nada."""
        items = [
            _hito("Apertura de Ofertas", "La apertura será el 20/09/2026.", fecha_explicita="2026-09-20"),
            _hito(
                "Firma del Contrato",
                "Dentro de los 10 días de la adjudicación, se firma el contrato.",
                evento_disparador="Adjudicación",
                cantidad=10,
                unidad="días",
                direccion="desde",
            ),
            _hito("Adjudicación", "La adjudicación se notificará a los oferentes."),
        ]

        assert _filter_non_hitos(items) == items



class TestOrphanNonSelfMentioned:
    def test_filtra_referencia_a_documento_externo_sin_uso(self):
        """Regresión real (Dell): "Cronograma del Proceso" salió con
        `mencion_propia: false` (el LLM mismo reconoce que el pliego no lo
        menciona por sí solo) pero nada lo usa como `evento_disparador` --
        no cumplió el propósito de ese campo (regla 2) ni es un hito real
        (es una referencia a un documento externo: "las consultas se harán
        según el cronograma previsto para el proceso")."""
        item = _hito(
            "Cronograma del Proceso",
            "Las consultas se realizarán a partir y hasta la fecha y hora "
            "establecidas en el cronograma previsto para el presente proceso.",
            mencion_propia=False,
        )

        assert _filter_non_hitos([item]) == []

    def test_conserva_el_disparador_que_si_cumple_su_proposito(self):
        disparador = _hito(
            "Recepción de la Orden de Compra",
            "El plazo para el inicio de la prestación es de 30 días desde "
            "la notificación de la orden de compra.",
            mencion_propia=False,
        )
        dependiente = _hito(
            "Inicio de la Prestación",
            "El plazo para el inicio de la prestación es de 30 días desde "
            "la notificación de la orden de compra.",
            evento_disparador="Recepción de la Orden de Compra",
            cantidad=30,
            unidad="días",
            direccion="desde",
        )

        filtered = _filter_non_hitos([disparador, dependiente])

        names = {item["nombre"] for item in filtered}
        assert "Recepción de la Orden de Compra" in names
        assert "Inicio de la Prestación" in names


class TestConsolidateDuplicateHitosNoConectada:
    """`_consolidate_duplicate_hitos` NO está conectada a `_filter_non_hitos`
    (ver nota grande en esa función) -- validada contra los 10 pliegos reales
    disponibles, fusionaba pares genuinamente distintos que solo comparten
    vocabulario común de licitaciones (ej. "Adjudicación" es substring literal
    de "Preadjudicación" por el prefijo "pre-"; "Cumplimiento del Contrato"
    vs "Vencimiento del Contrato" da 0.86 de similitud de texto pese a ser
    conceptos opuestos). Estos tests llaman a la función DIRECTAMENTE (no vía
    `_filter_non_hitos`) para documentar qué SÍ resuelve bien mientras se
    diseña un reemplazo más seguro en otra sesión."""

    def test_fusiona_variantes_de_puesta_en_marcha(self):
        """Caso real (Nucleoeléctrica) que si funciona bien: "Puesta en
        Marcha del Sistema" (pág. 17) y "Puesta en Marcha" (pág. 31)."""
        a = _hito(
            "Puesta en Marcha del Sistema",
            "El oferente deberá contemplar en su propuesta el suministro, "
            "instalación y puesta en marcha del firewall de aplicación web.",
        )
        b = _hito(
            "Puesta en Marcha",
            "Se realizará luego de haberse ejecutado la instalación "
            "completa, en un todo de acuerdo con el presente pliego.",
            fecha_explicita="2026-11-01",
            origen_fecha="detectada",
        )

        merged = _consolidate_duplicate_hitos([a, b])

        assert len(merged) == 1
        assert merged[0]["fecha_explicita"] == "2026-11-01"

    def test_no_fusiona_un_disparador_con_su_propio_dependiente(self):
        """Guardia de seguridad que sí funciona -- bug real ya documentado en
        `timeline/materializer.py` (pliego Banco de Córdoba): un nombre
        corto totalmente contenido en el nombre largo de su propio
        disparador/dependiente NO debe fusionarse, aunque los tiers de
        similitud lo sugieran, porque son dos hitos distintos por diseño."""
        trigger = _hito(
            "Migraciones",
            "Se iniciará la tercera etapa de migraciones con soporte una "
            "vez completadas las anteriores.",
        )
        dependent = _hito(
            "Inicio de la Tercera Etapa de Migraciones con Soporte",
            "Dentro de los 10 días de finalizadas las migraciones, se dará "
            "inicio a la tercera etapa.",
            evento_disparador="Migraciones",
            cantidad=10,
            unidad="días",
            direccion="desde",
        )

        merged = _consolidate_duplicate_hitos([trigger, dependent])

        names = {item["nombre"] for item in merged}
        assert "Migraciones" in names
        assert "Inicio de la Tercera Etapa de Migraciones con Soporte" in names

    def test_falso_positivo_conocido_prefijo_pre(self):
        """Documenta el bug real encontrado (2026-09-21): "Adjudicación" es
        substring literal de "Preadjudicación" por el prefijo "pre-", no
        porque sean el mismo hito -- esta función los fusiona hoy por error.
        Este test PASA con el bug presente (`len(merged) == 1`) a propósito:
        documenta el estado real de la función para no reintroducir la
        confusión de "ya está arreglado" en otra sesión."""
        a = _hito("Adjudicación", "La adjudicación se resolverá por acto fundado.")
        b = _hito(
            "Impugnaciones a la Preadjudicación o Preselección",
            "Los oferentes podrán impugnar el informe de preadjudicación "
            "dentro de los 3 días de notificado.",
        )

        merged = _consolidate_duplicate_hitos([a, b])

        assert len(merged) == 1  # bug conocido, no el comportamiento deseado

    def test_falso_positivo_conocido_vocabulario_compartido(self):
        """Documenta el segundo bug real encontrado (2026-09-21):
        "Cumplimiento del Contrato" y "Vencimiento del Contrato" (conceptos
        opuestos) dan 0.86 de similitud de texto -- por encima del umbral --
        solo por compartir la terminación "-imiento del Contrato"."""
        a = _hito("Cumplimiento del Contrato", "El contrato se dará por cumplido tras la recepción final.")
        b = _hito("Vencimiento del Contrato", "El contrato vencerá a los 12 meses de su firma.")

        merged = _consolidate_duplicate_hitos([a, b])

        assert len(merged) == 1  # bug conocido, no el comportamiento deseado


class TestMergeEnumeratedFragmentDuplicates:
    def test_fusiona_enumeracion_con_citas_identicas(self):
        """Regresión real (Bancor): "Pruebas de Concepto", "Visitas" y
        "Verificaciones" salieron como 3 ítems con el `fuente_fragmento`
        IDÉNTICO carácter por carácter -- el prompt ya tiene una regla (con
        un ejemplo casi textual de este caso) para no fragmentar una
        enumeración de sinónimos, pero el LLM la fragmentó igual."""
        fragmento = (
            "El Banco se reserva el derecho de realizar pruebas de "
            "concepto, visitas o verificaciones para validar el "
            "cumplimiento declarado antes de la adjudicación."
        )
        items = [
            _hito("Pruebas de Concepto", fragmento),
            _hito("Visitas", fragmento),
            _hito("Verificaciones", fragmento),
        ]

        filtered = _merge_enumerated_fragment_duplicates(items)

        assert len(filtered) == 1
        assert filtered[0]["nombre"] == "Pruebas de Concepto / Visitas / Verificaciones"

    def test_no_fusiona_hechos_distintos_que_comparten_cita(self):
        """Regresión evitada: "Firma del Acta de Recepción" y "Garantía de
        Hardware" comparten una cita porque el pliego redacta ambos hechos
        en la misma oración, pero son hitos genuinamente distintos -- el
        nombre completo de la garantía NO aparece literal en el fragmento
        compartido (está separado por "bajo régimen NBD de reemplazo de"),
        así que no debe fusionarse con la firma."""
        fragmento = (
            "Se requiere para los equipos un servicio contra todo defecto "
            "de materiales, con 3 años de garantía bajo régimen NBD de "
            "reemplazo de hardware, con vigencia a partir de la firma del "
            "acta de recepción."
        )
        items = [
            _hito("Garantía de Hardware", fragmento),
            _hito("Firma del Acta de Recepción", fragmento),
        ]

        filtered = _merge_enumerated_fragment_duplicates(items)

        assert len(filtered) == 2

    def test_no_fusiona_nombres_muy_cortos_por_coincidencia(self):
        fragmento = "El pago se realizará contra la presentación de la factura conformada."
        items = [
            _hito("Pago", fragmento),
            _hito("Factura", fragmento),
        ]

        filtered = _merge_enumerated_fragment_duplicates(items)

        assert len(filtered) == 2
