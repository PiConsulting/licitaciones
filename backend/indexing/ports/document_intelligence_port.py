from typing import Protocol


class DocumentIntelligencePort(Protocol):
    def extract_text(
        self,
        blob_url: str,
        *,
        document_id: str | None = None,
        correlation_id: str | None = None,
    ) -> list[dict]:
        """Return extracted page text from a PDF source URL.

        `document_id`/`correlation_id` son opcionales (compatibilidad hacia
        atrás) -- FIX (2026-09-14, Fase 1 de auditoría RAG, finding P2-7): sin
        ellos, los logs de telemetría internos (`table_position_fallback`,
        `table_position_mismatch`) no se podían correlacionar con ningún
        documento/análisis puntual en producción -- solo el wrapper de más
        arriba (`indexing.document_intelligence.extract_text`) los loggeaba.
        """
