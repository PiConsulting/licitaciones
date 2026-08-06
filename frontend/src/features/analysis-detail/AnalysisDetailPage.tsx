import { useMemo, useState } from "react";

import { AnalysisHeader } from "./AnalysisHeader";
import { CategoryList } from "./CategoryList";
import { PDFViewer } from "../pdf-viewer/PDFViewer";
import { useAnalysisDetail } from "./hooks/useAnalysisDetail";
import type { Citation } from "./types";

interface AnalysisDetailPageProps {
  analysisId: string;
}

export function AnalysisDetailPage({ analysisId }: AnalysisDetailPageProps) {
  const query = useAnalysisDetail(analysisId);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedCitations, setSelectedCitations] = useState<Citation[]>([]);
  const documentsById = useMemo(() => {
    return new Map((query.data?.documents ?? []).map((document) => [document.id, document]));
  }, [query.data?.documents]);

  if (query.isLoading) {
    return <p className="text-sm text-gray-600">Cargando detalle del análisis...</p>;
  }

  if (query.isError) {
    return <p className="text-sm text-error">No se pudo cargar el detalle del análisis.</p>;
  }

  if (!query.data) {
    return <p className="text-sm text-gray-600">No hay datos de análisis disponibles.</p>;
  }

  const selectedDocument = selectedCitation ? documentsById.get(selectedCitation.document_id) : null;

  return (
    <section>
      <AnalysisHeader analysis={query.data} />

      <div className="flex flex-col gap-4 lg:flex-row">
        <div data-testid="categories-panel" className="w-full lg:w-[60%]">
          <CategoryList
            analysis={query.data}
            onViewSource={({ citation, citations }) => {
              setSelectedCitation(citation);
              setSelectedCitations(citations);
            }}
          />
        </div>

        <aside
          data-testid="pdf-viewer-panel"
          className="w-full rounded-md border border-gray-200 bg-white p-2 text-sm text-gray-600 lg:sticky lg:top-4 lg:h-[calc(100vh-6rem)] lg:w-[40%]"
        >
          {selectedCitation ? (
            <PDFViewer
              key={selectedCitation.document_id}
              documentId={selectedCitation.document_id}
              documentName={selectedDocument?.filename ?? selectedCitation.document_name}
              citations={selectedCitations.length > 0 ? selectedCitations : [selectedCitation]}
              documents={query.data.documents}
            />
          ) : (
            <p className="p-4">Selecciona Ver fuente en cualquier campo para abrir el visor PDF.</p>
          )}
        </aside>
      </div>
    </section>
  );
}
