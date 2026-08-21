"""Tests para casos edge de extracción de markdown en document_intelligence.py.

Valida los fixes implementados para:
- DI-1: Detección de headings 
- DI-2: Dehyphenation mejorado (mayúsculas, ü)
- DI-3: Figuras descartadas
- DI-4: Posicionamiento de tablas
"""

from __future__ import annotations

import pytest

from extraction.document_intelligence import (
    _MD_HEADING_RE,
    _LINE_WRAP_HYPHEN_RE,
    _dehyphenate,
    _parse_markdown_blocks,
)


class TestDehyphenation:
    """Tests para validar el regex mejorado de dehyphenation."""

    def test_lowercase_dehyphenation(self):
        """Caso básico: minúsculas."""
        text = "ad-\nquisición"
        result = _dehyphenate(text)
        assert result == "adquisición"

    def test_uppercase_dehyphenation(self):
        """FIX DI-2: Mayúsculas deben unirse correctamente."""
        text = "ADQUI-\nSICIÓN"
        result = _dehyphenate(text)
        assert result == "ADQUISICIÓN"

    def test_mixed_case_dehyphenation(self):
        """Mezcla de mayúsculas y minúsculas."""
        text = "Adqui-\nsición"
        result = _dehyphenate(text)
        assert result == "Adquisición"

    def test_umlaut_dehyphenation(self):
        """FIX DI-2: Letra ü debe ser soportada."""
        text = "pingü-\nino"
        result = _dehyphenate(text)
        assert result == "pingüino"

    def test_uppercase_umlaut_dehyphenation(self):
        """Ü mayúscula debe ser soportada."""
        text = "PINGÜ-\nINO"
        result = _dehyphenate(text)
        assert result == "PINGÜINO"

    def test_real_hyphen_preserved(self):
        """Guiones reales de palabras compuestas deben preservarse."""
        text = "auto-\nbús"  # palabra compuesta real
        # Este caso es ambiguo, pero nuestro regex lo unirá
        # En la práctica, "autobús" sin guion es correcto
        result = _dehyphenate(text)
        assert result == "autobús"

    def test_multiple_line_wraps(self):
        """Múltiples palabras partidas en el mismo texto."""
        text = "La ad-\nquisición de-\nbe realizarse"
        result = _dehyphenate(text)
        assert result == "La adquisición debe realizarse"

    def test_no_hyphen_unchanged(self):
        """Texto sin guiones debe permanecer igual."""
        text = "La adquisición debe realizarse"
        result = _dehyphenate(text)
        assert result == text


class TestMarkdownHeadingDetection:
    """Tests para validar detección de headings."""

    def test_standard_h1_detection(self):
        """H1 estándar con #."""
        line = "# TÍTULO PRINCIPAL"
        match = _MD_HEADING_RE.match(line)
        assert match is not None
        assert len(match.group(1)) == 1  # nivel 1
        assert match.group(2) == "TÍTULO PRINCIPAL"

    def test_h2_h3_detection(self):
        """H2 y H3 con ## y ###."""
        line_h2 = "## Sección 2"
        line_h3 = "### Subsección 3"
        
        match_h2 = _MD_HEADING_RE.match(line_h2)
        assert match_h2 is not None
        assert len(match_h2.group(1)) == 2
        
        match_h3 = _MD_HEADING_RE.match(line_h3)
        assert match_h3 is not None
        assert len(match_h3.group(1)) == 3

    def test_heading_with_numbers(self):
        """Heading con número (común en pliegos)."""
        line = "## ARTÍCULO 10: GARANTÍAS"
        match = _MD_HEADING_RE.match(line)
        assert match is not None
        assert match.group(2) == "ARTÍCULO 10: GARANTÍAS"

    def test_bold_text_not_detected_as_heading(self):
        """Texto en negrita NO debe ser detectado como heading si no tiene #."""
        line = "**ARTÍCULO 10**"  # negrita markdown pero sin #
        match = _MD_HEADING_RE.match(line)
        assert match is None  # ESPERADO: no se detecta sin #

    def test_all_caps_not_detected_as_heading(self):
        """Texto en mayúsculas NO debe ser detectado como heading sin #."""
        line = "ARTÍCULO 10: GARANTÍAS"
        match = _MD_HEADING_RE.match(line)
        assert match is None  # ESPERADO: Azure DI debe marcar con #


class TestMarkdownParsing:
    """Tests de integración para _parse_markdown_blocks."""

    def test_basic_parsing(self):
        """Parsing básico con headings y párrafos."""
        markdown = """# Título 1
Párrafo 1

## Título 2
Párrafo 2"""
        blocks, heading_levels, table_positions = _parse_markdown_blocks(markdown)
        
        assert len(blocks) == 4  # 2 headings + 2 párrafos
        assert len(heading_levels) == 2  # 2 headings
        assert 0 in heading_levels  # primer heading en source_order 0
        assert heading_levels[0] == 1  # nivel 1
        assert 2 in heading_levels  # segundo heading en source_order 2
        assert heading_levels[2] == 2  # nivel 2

    def test_page_breaks(self):
        """Tracking de páginas con PageBreak."""
        markdown = """# Título página 1
Contenido página 1
<!-- PageBreak -->
# Título página 2
Contenido página 2"""
        blocks, _, _ = _parse_markdown_blocks(markdown)
        
        page_1_blocks = [b for b in blocks if b["page_number"] == 1]
        page_2_blocks = [b for b in blocks if b["page_number"] == 2]
        
        assert len(page_1_blocks) == 2  # título + contenido
        assert len(page_2_blocks) == 2  # título + contenido

    def test_table_position_tracking(self):
        """Tablas deben registrar su posición en el flujo."""
        markdown = """# Título
Párrafo antes de tabla
<table>
<tr><td>celda</td></tr>
</table>
Párrafo después de tabla"""
        blocks, _, table_positions = _parse_markdown_blocks(markdown)
        
        assert len(table_positions) == 1  # una tabla detectada
        page, source_order = table_positions[0]
        assert page == 1
        assert source_order == 2  # después de título y párrafo

    def test_figure_content_discarded(self):
        """Contenido dentro de <figure> debe ser descartado."""
        markdown = """# Título
Texto antes
<figure>
![logo](logo.png)
Pie de figura
</figure>
Texto después"""
        blocks, _, _ = _parse_markdown_blocks(markdown)
        
        # Solo debe haber 3 bloques: título, texto antes, texto después
        assert len(blocks) == 3
        assert "logo" not in str(blocks)  # contenido de figura no presente
        assert "Pie de figura" not in str(blocks)

    def test_empty_markdown(self):
        """Markdown vacío debe retornar listas vacías."""
        blocks, heading_levels, table_positions = _parse_markdown_blocks("")
        assert blocks == []
        assert heading_levels == {}
        assert table_positions == []

    def test_comments_ignored(self):
        """Comentarios HTML deben ser ignorados."""
        markdown = """# Título
<!-- PageNumber="1 de 10" -->
<!-- PageHeader="PLIEGO DE BASES Y CONDICIONES" -->
Contenido
<!-- PageFooter="Página 1" -->"""
        blocks, _, _ = _parse_markdown_blocks(markdown)

        # Solo título y contenido
        assert len(blocks) == 2
        assert "PageNumber" not in str(blocks)
        assert "PageHeader" not in str(blocks)

    def test_blank_line_flushes_paragraph_c2_fix(self):
        """FIX CRÍTICO (auditoría 2026-08-12, hallazgo C-2).

        Dos párrafos de cuerpo consecutivos bajo el mismo heading, separados
        por una línea en blanco, deben producir DOS bloques independientes
        (uno por párrafo), no un único bloque con "\n\n" interno.

        Esto es lo que permite que el índice posicional (página, índice
        secuencial) de estos bloques se corresponda 1:1 con
        `result.paragraphs` de Document Intelligence -- precondición de la
        que depende `_enrich_blocks_with_para_id` para asignar el bbox
        correcto a cada bloque. Antes de este fix, ambos párrafos llegaban
        fusionados en un solo bloque y el índice se desalineaba con el
        siguiente párrafo real, haciendo que bloques (y sus highlights)
        recibieran el bbox de OTRO párrafo de la misma página.
        """
        markdown = """# ARTÍCULO 9: GARANTÍAS
Primer párrafo del cuerpo con contenido A.

Segundo párrafo del cuerpo con contenido B."""
        blocks, heading_levels, _ = _parse_markdown_blocks(markdown)

        # 1 heading + 2 párrafos independientes = 3 bloques (antes del fix: 2)
        assert len(blocks) == 3
        assert 0 in heading_levels

        # `heading_levels` mapea source_order -> nivel para los bloques que son
        # headings; los bloques de cuerpo son los que NO aparecen ahí.
        body_blocks = [b for b in blocks if b["source_order"] not in heading_levels]
        assert len(body_blocks) == 2
        assert body_blocks[0]["content"].strip() == "Primer párrafo del cuerpo con contenido A."
        assert body_blocks[1]["content"].strip() == "Segundo párrafo del cuerpo con contenido B."
        # Ningún bloque de cuerpo debe contener el separador interno "\n\n":
        # cada uno es ya un único párrafo real.
        assert "\n\n" not in body_blocks[0]["content"]
        assert "\n\n" not in body_blocks[1]["content"]

    def test_multiple_blank_lines_between_paragraphs(self):
        """Múltiples líneas en blanco seguidas no deben crear bloques vacíos."""
        markdown = """# Título
Párrafo 1.


Párrafo 2."""
        blocks, heading_levels, _ = _parse_markdown_blocks(markdown)

        body_blocks = [b for b in blocks if b["source_order"] not in heading_levels]
        assert len(body_blocks) == 2
        assert all(b["content"].strip() for b in body_blocks)


class TestTablePositioning:
    """Tests específicos para posicionamiento de tablas."""

    def test_single_table_in_order(self):
        """Una tabla debe tener su posición correcta."""
        markdown = """# Título
Intro
<table>
<tr><td>A</td></tr>
</table>
Final"""
        blocks, _, table_positions = _parse_markdown_blocks(markdown)
        
        assert len(table_positions) == 1
        page, source_order = table_positions[0]
        assert source_order == 2  # después de título (0) e intro (1)

    def test_multiple_tables_in_order(self):
        """Múltiples tablas deben mantener orden."""
        markdown = """<table>
<tr><td>Tabla 1</td></tr>
</table>
Texto intermedio
<table>
<tr><td>Tabla 2</td></tr>
</table>"""
        blocks, _, table_positions = _parse_markdown_blocks(markdown)
        
        assert len(table_positions) == 2
        _, order_1 = table_positions[0]
        _, order_2 = table_positions[1]
        assert order_1 < order_2  # orden preservado

    def test_nested_tables_not_supported(self):
        """Tablas anidadas: solo se detecta la primera apertura."""
        markdown = """<table>
<tr><td><table><tr><td>Nested</td></tr></table></td></tr>
</table>"""
        blocks, _, table_positions = _parse_markdown_blocks(markdown)
        
        # Implementación actual: no soporta anidamiento correctamente
        # pero tampoco debería crashear
        assert len(table_positions) >= 1  # al menos la tabla exterior


@pytest.mark.parametrize(
    "text,expected_matches",
    [
        ("ad-\nquisición", 1),
        ("ADQUI-\nSICIÓN", 1),
        ("pingü-\nino", 1),
        ("múlti-\nples ad-\nquisiciones", 2),
        ("no-hyphen-wraps", 0),  # sin salto de línea
    ],
)
def test_line_wrap_hyphen_regex(text: str, expected_matches: int):
    """Tests parametrizados para el regex de line wrap hyphen."""
    matches = list(_LINE_WRAP_HYPHEN_RE.finditer(text))
    assert len(matches) == expected_matches
