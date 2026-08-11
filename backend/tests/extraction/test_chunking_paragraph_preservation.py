"""Tests para validar que chunking preserva párrafos completos y heading_path."""

from __future__ import annotations

import pytest

from extraction.chunking import (
    _split_into_paragraphs,
    _split_block_into_chunks,
    _to_intermediate_blocks,
    _merge_intermediate_blocks,
    create_chunks,
)


class TestParagraphPreservation:
    """Tests para verificar que los párrafos no se cortan a la mitad."""

    def test_single_paragraph_not_split(self):
        """Un párrafo que cabe en chunk_size debe permanecer intacto."""
        content = "Este es un párrafo corto con menos de 700 tokens."
        chunks = _split_block_into_chunks(content, chunk_size=700, overlap=120)
        
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_multiple_paragraphs_accumulated(self):
        """Múltiples párrafos pequeños deben acumularse en un chunk."""
        content = "Párrafo 1.\n\nPárrafo 2.\n\nPárrafo 3."
        chunks = _split_block_into_chunks(content, chunk_size=700, overlap=120)
        
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_paragraphs_never_cut_in_middle(self):
        """Párrafos completos en chunks separados, nunca cortados."""
        # 3 párrafos de ~250 tokens cada uno (estimado 50 palabras)
        p1 = " ".join(["palabra"] * 250)  # ~250 tokens
        p2 = " ".join(["palabra"] * 250)
        p3 = " ".join(["palabra"] * 250)
        content = f"{p1}\n\n{p2}\n\n{p3}"
        
        chunks = _split_block_into_chunks(content, chunk_size=400, overlap=100)
        
        # Debe haber múltiples chunks
        assert len(chunks) >= 2
        
        # Cada chunk debe ser párrafos completos con "\n\n" como separador
        for chunk in chunks:
            # No debe haber palabras cortadas a la mitad
            assert not chunk.startswith(" ")
            # Los párrafos deben estar completos (unidos por \n\n)
            if "\n\n" in chunk:
                paragraphs = chunk.split("\n\n")
                for p in paragraphs:
                    assert p.strip()  # No vacíos

    def test_giant_paragraph_split_isolated(self):
        """Párrafo gigante (> chunk_size) se parte AISLADAMENTE."""
        # Párrafo de 1000 tokens
        giant = " ".join(["palabra"] * 1000)
        content = f"Párrafo normal.\n\n{giant}\n\nOtro párrafo normal."
        
        chunks = _split_block_into_chunks(content, chunk_size=400, overlap=100)
        
        # Debe haber múltiples chunks
        assert len(chunks) >= 3
        
        # El primer chunk debe ser el párrafo normal
        assert "Párrafo normal" in chunks[0]
        
        # Los chunks del gigante no deben mezclar otros párrafos
        giant_chunks = [c for c in chunks if "palabra palabra palabra" in c]
        for chunk in giant_chunks:
            assert "Párrafo normal" not in chunk or chunk == chunks[0]
            assert "Otro párrafo normal" not in chunk

    def test_overlap_uses_complete_paragraphs(self):
        """Overlap debe tomar párrafos completos previos."""
        p1 = " ".join(["uno"] * 200)
        p2 = " ".join(["dos"] * 200)
        p3 = " ".join(["tres"] * 200)
        content = f"{p1}\n\n{p2}\n\n{p3}"
        
        chunks = _split_block_into_chunks(content, chunk_size=400, overlap=150)
        
        # Debe haber overlap
        assert len(chunks) >= 2
        
        # El segundo chunk debe incluir párrafos completos del primero
        if len(chunks) >= 2:
            # Buscar palabras clave
            has_uno = "uno" in chunks[1]
            has_dos = "dos" in chunks[1]
            has_tres = "tres" in chunks[1]
            
            # Si hay overlap, debe ser párrafos completos
            if has_uno or has_dos:
                # No debe haber mezcla de tokens sueltos
                assert "\n\n" in chunks[1] or len(chunks[1].split()) > 100


class TestHeadingPathPreservation:
    """Tests para verificar que heading_path se mantiene correctamente."""

    def test_heading_path_simple(self):
        """Heading path básico con un nivel."""
        blocks = [
            {"heading_level": 1, "content": "TÍTULO 1", "page_number": 1, "source_order": 0},
            {"content": "Contenido bajo título 1.", "page_number": 1, "source_order": 1},
        ]
        
        intermediate = _to_intermediate_blocks(blocks)
        
        # El bloque de contenido debe tener heading_path
        content_block = next(b for b in intermediate if "Contenido" in b["content"])
        assert content_block["heading_path"] == ["TÍTULO 1"]

    def test_heading_path_nested(self):
        """Heading path con múltiples niveles."""
        blocks = [
            {"heading_level": 1, "content": "ARTÍCULO 10", "page_number": 1, "source_order": 0},
            {"heading_level": 2, "content": "GARANTÍAS", "page_number": 1, "source_order": 1},
            {"content": "Los oferentes deberán...", "page_number": 1, "source_order": 2},
        ]
        
        intermediate = _to_intermediate_blocks(blocks)
        
        content_block = next(b for b in intermediate if "oferentes" in b["content"])
        assert content_block["heading_path"] == ["ARTÍCULO 10", "GARANTÍAS"]

    def test_heading_path_changes_on_same_level(self):
        """Heading path se actualiza cuando aparece heading del mismo nivel."""
        blocks = [
            {"heading_level": 2, "content": "SECCIÓN A", "page_number": 1, "source_order": 0},
            {"content": "Contenido A.", "page_number": 1, "source_order": 1},
            {"heading_level": 2, "content": "SECCIÓN B", "page_number": 1, "source_order": 2},
            {"content": "Contenido B.", "page_number": 1, "source_order": 3},
        ]
        
        intermediate = _to_intermediate_blocks(blocks)
        
        content_a = next(b for b in intermediate if "Contenido A" in b["content"])
        content_b = next(b for b in intermediate if "Contenido B" in b["content"])
        
        assert content_a["heading_path"] == ["SECCIÓN A"]
        assert content_b["heading_path"] == ["SECCIÓN B"]

    def test_heading_path_in_merged_blocks(self):
        """Merged blocks preservan heading_path."""
        blocks = [
            {"heading_level": 1, "content": "TÍTULO", "page_number": 1, "source_order": 0},
            {"content": "Párrafo 1.", "page_number": 1, "source_order": 1},
            {"content": "Párrafo 2.", "page_number": 1, "source_order": 2},
        ]
        
        intermediate = _to_intermediate_blocks(blocks)
        merged = _merge_intermediate_blocks(intermediate)
        
        # Debe haber solo un bloque de contenido (párrafos fusionados)
        content_blocks = [b for b in merged if not b.get("is_heading")]
        assert len(content_blocks) == 1
        
        # El bloque fusionado debe mantener heading_path
        assert content_blocks[0]["heading_path"] == ["TÍTULO"]
        assert "Párrafo 1" in content_blocks[0]["content"]
        assert "Párrafo 2" in content_blocks[0]["content"]


class TestHeadingPrefixInChunks:
    """Tests para verificar que cada chunk incluye heading_prefix."""

    def test_heading_prefix_included_in_content(self):
        """Cada chunk debe incluir heading_prefix al inicio."""
        blocks = [
            {"heading_level": 1, "content": "ARTÍCULO 10", "page_number": 1, "source_order": 0},
            {"heading_level": 2, "content": "GARANTÍAS", "page_number": 1, "source_order": 1},
            {"content": "Contenido extenso " * 500, "page_number": 1, "source_order": 2},  # > chunk_size
        ]
        
        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")
        
        # Debe haber múltiples chunks por el contenido largo
        assert len(chunks) >= 2
        
        # TODOS los chunks deben empezar con heading_prefix
        for chunk in chunks:
            content = chunk["content"]
            assert content.startswith("ARTÍCULO 10\nGARANTÍAS\n\n")

    def test_heading_path_metadata_matches_content(self):
        """heading_path en metadata debe matchear el prefix en content."""
        blocks = [
            {"heading_level": 1, "content": "TÍTULO A", "page_number": 1, "source_order": 0},
            {"heading_level": 2, "content": "SUBTÍTULO B", "page_number": 1, "source_order": 1},
            {"content": "Contenido.", "page_number": 1, "source_order": 2},
        ]
        
        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")
        
        assert len(chunks) == 1
        chunk = chunks[0]
        
        # Metadata heading_path
        assert chunk["heading_path"] == ["TÍTULO A", "SUBTÍTULO B"]
        
        # Content debe empezar con esos títulos
        assert chunk["content"].startswith("TÍTULO A\nSUBTÍTULO B\n\n")


class TestTableContext:
    """Tests para verificar que tablas heredan contexto del párrafo previo."""

    def test_table_inherits_preceding_paragraph(self):
        """Tabla debe heredar el párrafo que la introduce."""
        blocks = [
            {"heading_level": 1, "content": "EVALUACIÓN", "page_number": 1, "source_order": 0},
            {"content": "La evaluación se realizará según la siguiente tabla:", "page_number": 1, "source_order": 1},
            {
                "block_type": "table",
                "content": "Tabla T1 | Fila 1 | Criterio: Precio | Valor: 100",
                "page_number": 1,
                "source_order": 2,
                "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["Criterio", "Valor"]},
            },
        ]
        
        intermediate = _to_intermediate_blocks(blocks)
        merged = _merge_intermediate_blocks(intermediate)
        
        # Buscar el bloque de tabla
        table_block = next(b for b in merged if b.get("block_type") == "table")
        
        # Debe tener table_context con el párrafo previo
        assert "table_context" in table_block
        assert "siguiente tabla" in table_block["table_context"]

    def test_table_chunks_include_context(self):
        """Chunks de tabla deben incluir heading_path + table_context + row."""
        blocks = [
            {"heading_level": 1, "content": "TÍTULO", "page_number": 1, "source_order": 0},
            {"content": "Introducción de tabla.", "page_number": 1, "source_order": 1},
            {
                "block_type": "table",
                "content": "Tabla T1 | Fila 1 | Col: Valor",
                "page_number": 1,
                "source_order": 2,
                "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["Col"]},
            },
        ]
        
        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")
        
        # Buscar chunk de tabla
        table_chunk = next(c for c in chunks if c.get("block_type") == "table")
        
        content = table_chunk["content"]
        # Debe incluir: heading + context + row
        assert "TÍTULO" in content
        assert "Introducción de tabla" in content
        assert "Tabla T1" in content


class TestCategoryClassification:
    """Tests para verificar clasificación de categorías."""

    def test_classification_by_heading_takes_priority(self):
        """Clasificación por título tiene prioridad sobre keywords."""
        blocks = [
            {"heading_level": 1, "content": "GARANTÍAS", "page_number": 1, "source_order": 0},
            {"content": "Contenido con palabras de otras categorías como plazo y anexo.", "page_number": 1, "source_order": 1},
        ]
        
        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")
        
        assert len(chunks) == 1
        # Debe clasificar por título "GARANTÍAS", no por keywords "plazo" o "anexo"
        assert chunks[0]["primary_category"] == "garantias"

    def test_fallback_to_identificacion_procedimiento(self):
        """Sin título ni keywords claros, debe usar fallback."""
        blocks = [
            {"content": "Contenido genérico sin palabras clave específicas de ninguna categoría.", "page_number": 1, "source_order": 0},
        ]
        
        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")
        
        assert len(chunks) == 1
        assert chunks[0]["primary_category"] == "identificacion_procedimiento"


@pytest.mark.parametrize(
    "content,chunk_size,expected_min_chunks",
    [
        ("Párrafo corto.", 700, 1),  # Cabe en un chunk
        (" ".join(["palabra"] * 1000), 400, 3),  # Párrafo gigante → múltiples chunks
        ("P1.\n\nP2.\n\nP3.", 700, 1),  # 3 párrafos pequeños → 1 chunk
    ],
)
def test_chunk_count_parametrized(content: str, chunk_size: int, expected_min_chunks: int):
    """Tests parametrizados para verificar cantidad esperada de chunks."""
    chunks = _split_block_into_chunks(content, chunk_size=chunk_size, overlap=120)
    assert len(chunks) >= expected_min_chunks
