"""Tests unitarios para clasificación de categorías en chunks"""

import pytest

from extraction.chunking import (
    CATEGORY_HEADING_PATTERNS,
    _classify_by_heading,
    _classify_by_keywords,
    _normalize_for_matching,
    classify_chunk_categories,
)


class TestNormalizeForMatching:
    def test_removes_accents(self):
        assert _normalize_for_matching("Garantías Técnicas") == "garantias tecnicas"

    def test_lowercase(self):
        assert _normalize_for_matching("REQUISITOS") == "requisitos"

    def test_removes_punctuation(self):
        assert _normalize_for_matching("Anexo I - Formulario") == "anexo i formulario"

    def test_normalizes_whitespace(self):
        assert _normalize_for_matching("  múltiples   espacios  ") == "multiples espacios"


class TestClassifyByHeading:
    def test_detects_requisitos_admisibilidad(self):
        result = _classify_by_heading(["Requisitos de Admisibilidad"])
        assert result == "requisitos_admisibilidad"

    def test_detects_garantias(self):
        result = _classify_by_heading(["Garantías y Cauciones"])
        assert result == "garantias"

    def test_detects_plazos(self):
        result = _classify_by_heading(["Cronograma y Plazos"])
        assert result == "plazos_clave"

    def test_returns_none_for_unmatched(self):
        result = _classify_by_heading(["Otras Consideraciones"])
        assert result is None

    def test_nested_heading_path(self):
        result = _classify_by_heading(["Capítulo 3", "Documentación", "Habilitación"])
        assert result == "requisitos_admisibilidad"

    def test_empty_heading_path(self):
        result = _classify_by_heading([])
        assert result is None


class TestClassifyByKeywords:
    @pytest.fixture
    def sample_glossary(self):
        return {
            "garantias": {
                "query_terms": ["garantia", "caucion", "fianza"],
                "aliases": ["poliza", "seguro de caucion"],
            },
            "requisitos_admisibilidad": {
                "query_terms": ["requisitos", "habilitacion", "documentacion"],
                "aliases": ["debe presentar", "certificado"],
            },
        }

    def test_matches_guarantee_content(self, sample_glossary):
        content = "El oferente deberá constituir garantía de mantenimiento de oferta"
        scores = _classify_by_keywords(content, sample_glossary)

        assert "garantias" in scores
        assert scores["garantias"] > 0

    def test_matches_requisitos_content(self, sample_glossary):
        content = "Presentar certificado de habilitación y documentación obligatoria"
        scores = _classify_by_keywords(content, sample_glossary)

        assert "requisitos_admisibilidad" in scores
        assert scores["requisitos_admisibilidad"] > 0

    def test_no_match_returns_empty(self, sample_glossary):
        content = "Objeto de la contratación: provisión de insumos"
        scores = _classify_by_keywords(content, sample_glossary)

        assert len(scores) == 0 or all(score == 0 for score in scores.values())

    def test_normalizes_accents_in_matching(self, sample_glossary):
        content = "Garantía de caución"  # Con acentos
        scores = _classify_by_keywords(content, sample_glossary)

        assert "garantias" in scores


class TestClassifyChunkCategories:
    def test_heading_takes_priority_over_keywords(self):
        # Chunk con título de garantías pero menciona requisitos
        chunk = {
            "heading_path": ["Garantías"],
            "content": "Presentar certificado de inscripción",
        }

        result = classify_chunk_categories(chunk)

        assert result["primary_category"] == "garantias"
        # Puede tener requisitos como secundaria si supera threshold
        assert isinstance(result["secondary_categories"], list)

    def test_uses_keywords_when_no_heading(self):
        chunk = {
            "heading_path": [],
            "content": "El oferente deberá constituir garantía de mantenimiento de oferta del 1%",
        }

        result = classify_chunk_categories(chunk)

        assert result["primary_category"] is not None
        assert "category_scores" in result

    def test_secondary_categories_threshold(self):
        # Chunk que menciona múltiples categorías
        chunk = {
            "heading_path": ["Requisitos"],
            "content": """
                Presentar certificado de habilitación y antecedentes.
                Constituir garantía de mantenimiento de oferta.
                Completar Anexo I.
            """,
        }

        result = classify_chunk_categories(chunk)

        assert result["primary_category"] == "requisitos_admisibilidad"
        # Debería detectar al menos una categoría secundaria
        assert len(result["secondary_categories"]) > 0

    def test_handles_empty_content(self):
        chunk = {
            "heading_path": [],
            "content": "",
        }

        result = classify_chunk_categories(chunk)

        # No debe crashear, puede retornar None
        assert "primary_category" in result
        assert "secondary_categories" in result


class TestCategoryHeadingPatterns:
    """Verifica que los patrones de títulos estén bien definidos"""

    def test_all_categories_have_patterns(self):
        expected_categories = [
            "objeto_alcance",
            "requisitos_admisibilidad",
            "garantias",
            "plazos_clave",
            "criterios_evaluacion",
            "causales_rechazo",
            "anexos_obligatorios",
            "identificacion_procedimiento",
        ]

        for category in expected_categories:
            assert category in CATEGORY_HEADING_PATTERNS
            assert len(CATEGORY_HEADING_PATTERNS[category]) > 0

    def test_no_duplicate_patterns_across_categories(self):
        all_patterns = []
        for patterns in CATEGORY_HEADING_PATTERNS.values():
            all_patterns.extend([_normalize_for_matching(p) for p in patterns])

        # Verificar que no haya duplicados exactos
        # (puede haber overlap semántico pero no términos idénticos)
        assert len(all_patterns) == len(set(all_patterns))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# REGRESIÓN CHK-06 (auditoría 2026-08-13): el ancestro le ganaba a la sección.
#
# `_classify_by_heading` concatenaba TODO el heading_path en un solo string y
# desempataba por la posición más temprana del patrón. Como los ancestros van
# primero en esa concatenación, el desempate favorecía estructuralmente al
# ancestro por sobre la sección real -- y el título tiene prioridad absoluta
# sobre las keywords del contenido, así que nada aguas abajo podía corregirlo.
# ---------------------------------------------------------------------------


class TestClasificacionHojaSobreAncestro:
    def test_la_seccion_le_gana_al_nombre_del_llamado(self) -> None:
        """El caso del hallazgo: el ancestro matchea "licitacion" en posición 0
        y la hoja matchea "garantia" más adelante; empatan en cantidad."""
        assert (
            _classify_by_heading(["LICITACIÓN PÚBLICA Nº 5/2026", "GARANTÍAS"]) == "garantias"
        )

    def test_la_seccion_le_gana_a_un_ancestro_de_pliego(self) -> None:
        assert (
            _classify_by_heading(
                ["PLIEGO DE CONDICIONES PARTICULARES PARA LA LICITACIÓN", "5. PLAZOS CLAVE"]
            )
            == "plazos_clave"
        )

    def test_la_hoja_decide_aunque_el_ancestro_tenga_mas_matches(self) -> None:
        """Un ancestro con dos patrones no debe tapar una hoja inequívoca."""
        assert (
            _classify_by_heading(["ANEXO I - FORMULARIO DE PRESENTACIÓN", "GARANTÍA DE OFERTA"])
            == "garantias"
        )

    def test_se_cae_al_ancestro_cuando_la_hoja_no_matchea_nada(self) -> None:
        assert _classify_by_heading(["GARANTÍAS", "5.2 Constitución"]) == "garantias"

    def test_recorre_hacia_la_raiz_hasta_encontrar_una_categoria(self) -> None:
        assert (
            _classify_by_heading(["CRITERIOS DE EVALUACIÓN", "Generalidades", "5.2.1"])
            == "criterios_evaluacion"
        )

    def test_el_desempate_por_posicion_sigue_operando_dentro_del_titulo(self) -> None:
        """La razón por la que existe el desempate: en castellano el núcleo del
        sintagma va primero, así que esto es una garantía y no un criterio."""
        assert _classify_by_heading(["GARANTÍA DE ADJUDICACIÓN"]) == "garantias"

    def test_sin_ninguna_coincidencia_devuelve_none(self) -> None:
        assert _classify_by_heading(["PLIEGO", "Generalidades", "Otros"]) is None
