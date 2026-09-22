"""Tests para validar que chunking preserva párrafos completos y heading_path."""

from __future__ import annotations

import pytest

from indexing.chunking import create_chunks
from indexing.chunking.block_merging import _merge_intermediate_blocks, _to_intermediate_blocks
from indexing.chunking.text_splitting import _split_block_into_chunks, _split_into_paragraphs


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
        p1 = " ".join(["palabra"] * 250)
        p2 = " ".join(["palabra"] * 250)
        p3 = " ".join(["palabra"] * 250)
        content = f"{p1}\n\n{p2}\n\n{p3}"

        chunks = _split_block_into_chunks(content, chunk_size=400, overlap=100)

        assert len(chunks) >= 2

        for chunk in chunks:
            # No debe haber palabras cortadas a la mitad
            assert not chunk.startswith(" ")
            if "\n\n" in chunk:
                paragraphs = chunk.split("\n\n")
                for p in paragraphs:
                    assert p.strip()

    def test_giant_paragraph_split_isolated(self):
        """Párrafo gigante (> chunk_size) se parte AISLADAMENTE."""
        giant = " ".join(["palabra"] * 1000)
        content = f"Párrafo normal.\n\n{giant}\n\nOtro párrafo normal."

        chunks = _split_block_into_chunks(content, chunk_size=400, overlap=100)

        assert len(chunks) >= 3

        assert "Párrafo normal" in chunks[0]

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

        assert len(chunks) >= 2

        if len(chunks) >= 2:
            has_uno = "uno" in chunks[1]
            has_dos = "dos" in chunks[1]
            has_tres = "tres" in chunks[1]

            if has_uno or has_dos:
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

        content_blocks = [b for b in merged if not b.get("is_heading")]
        assert len(content_blocks) == 1

        assert content_blocks[0]["heading_path"] == ["TÍTULO"]
        assert "Párrafo 1" in content_blocks[0]["content"]
        assert "Párrafo 2" in content_blocks[0]["content"]


class TestHeadingPrefixInChunks:
    """Tests para verificar que cada chunk incluye heading_prefix."""

    def test_heading_prefix_included_in_content(self):
        """RAG ARCHITECTURE: content puro (sin títulos), title en metadata."""
        blocks = [
            {"heading_level": 1, "content": "ARTÍCULO 10", "page_number": 1, "source_order": 0},
            {"heading_level": 2, "content": "GARANTÍAS", "page_number": 1, "source_order": 1},
            {
                "content": "Contenido extenso " * 500,
                "page_number": 1,
                "source_order": 2,
            },  # > chunk_size
        ]

        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")

        assert len(chunks) >= 2

        for chunk in chunks:
            content = chunk["content"]
            assert content.startswith("Contenido extenso")
            assert "ARTÍCULO 10" not in content
            assert "GARANTÍAS" not in content
            assert chunk["heading_path"] == ["ARTÍCULO 10", "GARANTÍAS"]
            assert chunk["title"] == "GARANTÍAS"

    def test_heading_path_metadata_matches_content(self):
        """RAG: heading_path completo en metadata, content puro."""
        blocks = [
            {"heading_level": 1, "content": "TÍTULO A", "page_number": 1, "source_order": 0},
            {"heading_level": 2, "content": "SUBTÍTULO B", "page_number": 1, "source_order": 1},
            {"content": "Contenido.", "page_number": 1, "source_order": 2},
        ]

        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")

        assert len(chunks) == 1
        chunk = chunks[0]

        assert chunk["heading_path"] == ["TÍTULO A", "SUBTÍTULO B"]

        assert chunk["title"] == "SUBTÍTULO B"

        assert chunk["content"] == "Contenido."
        assert "TÍTULO A" not in chunk["content"]
        assert "SUBTÍTULO B" not in chunk["content"]


class TestTableContext:
    """Tests para verificar que tablas heredan contexto del párrafo previo."""

    def test_table_inherits_preceding_paragraph(self):
        """Tabla debe heredar el párrafo que la introduce."""
        blocks = [
            {"heading_level": 1, "content": "EVALUACIÓN", "page_number": 1, "source_order": 0},
            {
                "content": "La evaluación se realizará según la siguiente tabla:",
                "page_number": 1,
                "source_order": 1,
            },
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

        table_block = next(b for b in merged if b.get("block_type") == "table")

        assert "table_context" in table_block
        assert "siguiente tabla" in table_block["table_context"]

    def test_table_chunks_include_context(self):
        """RAG: Tabla con table_context + row (sin heading)."""
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

        table_chunk = next(c for c in chunks if c.get("block_type") == "table")

        content = table_chunk["content"]
        assert "TÍTULO" not in content
        assert table_chunk["heading_path"] == ["TÍTULO"]
        assert table_chunk["title"] == "TÍTULO"
        assert "Introducción de tabla" in content
        assert "Tabla T1" in content

    def test_table_rows_consolidated(self):
        """RAG PHASE 3: Filas consecutivas de misma tabla se consolidan en un chunk."""
        blocks = [
            {"heading_level": 1, "content": "DATOS", "page_number": 1, "source_order": 0},
            {"content": "Información de la contratación:", "page_number": 1, "source_order": 1},
            {
                "block_type": "table",
                "content": "Tabla T1 | Fila 1 | Organismo: Municipalidad",
                "page_number": 1,
                "source_order": 2,
                "table_ref": {"table_id": "T1", "row_index": 1, "headers": ["Campo", "Valor"]},
                "para_id": "para_1",
                "bbox": [[0, 0, 100, 20]],
            },
            {
                "block_type": "table",
                "content": "Tabla T1 | Fila 2 | Procedimiento: CD 014/2026",
                "page_number": 1,
                "source_order": 3,
                "table_ref": {"table_id": "T1", "row_index": 2, "headers": ["Campo", "Valor"]},
                "para_id": "para_2",
                "bbox": [[0, 20, 100, 40]],
            },
            {
                "block_type": "table",
                "content": "Tabla T1 | Fila 3 | Presupuesto: $3.850.000",
                "page_number": 1,
                "source_order": 4,
                "table_ref": {"table_id": "T1", "row_index": 3, "headers": ["Campo", "Valor"]},
                "para_id": "para_3",
                "bbox": [[0, 40, 100, 60]],
            },
        ]

        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")

        table_chunks = [c for c in chunks if c.get("block_type") == "table"]

        assert len(table_chunks) == 1, f"Expected 1 table chunk, got {len(table_chunks)}"

        table_chunk = table_chunks[0]
        content = table_chunk["content"]

        assert "Organismo: Municipalidad" in content
        assert "Procedimiento: CD 014/2026" in content
        assert "Presupuesto: $3.850.000" in content

        source = table_chunk.get("source", {})
        blocks_in_source = source.get("blocks", [])
        assert len(blocks_in_source) == 3, (
            f"Expected 3 blocks in source, got {len(blocks_in_source)}"
        )

        assert blocks_in_source[0]["para_id"] == "para_1"
        assert blocks_in_source[1]["para_id"] == "para_2"
        assert blocks_in_source[2]["para_id"] == "para_3"

    def test_large_table_split_by_size_limit(self):
        """RAG PHASE 3 V2: Tablas grandes se dividen en múltiples chunks según límite de tamaño."""
        # 10 filas x ~200 chars (~50 tokens) para exceder el límite default de 500 tokens
        blocks = [
            {
                "heading_level": 1,
                "content": "ANEXO I - PLANILLA",
                "page_number": 1,
                "source_order": 0,
            },
        ]

        for i in range(1, 11):
            row_content = f"Renglón {i}: " + " ".join(["descripción detallada"] * 12)
            blocks.append(
                {
                    "block_type": "table",
                    "content": row_content,
                    "page_number": 1,
                    "source_order": i,
                    "table_ref": {
                        "table_id": "T1",
                        "row_index": i,
                        "headers": ["Renglón", "Descripción"],
                    },
                    "para_id": f"para_{i}",
                    "bbox": [[0, i * 20, 100, (i + 1) * 20]],
                }
            )

        # Usar chunk_size grande para no interferir con el límite de tabla
        chunks = create_chunks(
            blocks, document_id="test-doc", correlation_id="test-corr", chunk_size=2000
        )

        table_chunks = [c for c in chunks if c.get("block_type") == "table"]

        assert len(table_chunks) > 1, (
            f"Expected multiple table chunks due to size limit, got {len(table_chunks)}"
        )

        for chunk in table_chunks:
            assert "ANEXO I - PLANILLA" in chunk.get("heading_path", [])
            source = chunk.get("source", {})
            assert source.get("blocks"), "Each table chunk should have source.blocks"

        all_para_ids = set()
        for chunk in table_chunks:
            source = chunk.get("source", {})
            for block in source.get("blocks", []):
                if block.get("para_id"):
                    all_para_ids.add(block["para_id"])

        expected_para_ids = {f"para_{i}" for i in range(1, 11)}
        assert all_para_ids == expected_para_ids, "All table rows should be present across chunks"


class TestCategoryClassification:
    """Tests para verificar clasificación de categorías."""

    def test_classification_by_heading_takes_priority(self):
        """Clasificación por título tiene prioridad sobre keywords."""
        blocks = [
            {"heading_level": 1, "content": "GARANTÍAS", "page_number": 1, "source_order": 0},
            {
                "content": "Contenido con palabras de otras categorías como plazo y anexo.",
                "page_number": 1,
                "source_order": 1,
            },
        ]

        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")

        assert len(chunks) == 1
        # Debe clasificar por título "GARANTÍAS", no por keywords "plazo" o "anexo"
        assert chunks[0]["primary_category"] == "garantias"

    def test_sin_titulo_ni_keywords_el_chunk_queda_sin_categoria(self):
        """FIX (auditoría 2026-08-13, hallazgo CHK-05): este test fijaba el
        fallback a `identificacion_procedimiento`, que era justamente el bug --
        convertía a esa categoría en el tacho de basura de la clasificación y
        hacía que todo el relleno del pliego cobrara el boost de retrieval de
        la carátula. Ver `tests/test_classification_sin_categoria.py`."""
        blocks = [
            {
                "content": "Contenido genérico sin palabras clave específicas de ninguna categoría.",
                "page_number": 1,
                "source_order": 0,
            },
        ]

        chunks = create_chunks(blocks, document_id="test-doc", correlation_id="test-corr")

        assert len(chunks) == 1
        assert chunks[0]["primary_category"] is None


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
