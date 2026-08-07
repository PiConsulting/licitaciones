import { useMemo, useState } from "react";

import { AnalysisDetailHeader } from "./AnalysisDetailHeader";
import { AnalysisSummaryStrip } from "./AnalysisSummaryStrip";
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

  const primaryDocument = query.data.documents.find((document) => document.is_primary) ?? query.data.documents[0];
  const activeDocumentId = selectedCitation?.document_id ?? primaryDocument?.id;
  const activeDocumentName = selectedCitation
    ? (documentsById.get(selectedCitation.document_id)?.filename ?? selectedCitation.document_name)
    : primaryDocument?.filename;
  const activeCitations = selectedCitations.length > 0 ? selectedCitations : selectedCitation ? [selectedCitation] : [];

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div data-testid="detail-summary-panel" className="-mx-6 -mt-6 border-b border-gray-200 bg-surface px-6 pt-6 pb-4">
        <AnalysisDetailHeader analysis={query.data} />
      </div>

      <div className="flex min-w-0 flex-col gap-6 xl:flex-row">
        <div data-testid="categories-panel" className="min-w-0 w-full rounded-md border border-gray-200 bg-white p-5 xl:w-[60%] 2xl:w-[55%]">
          <AnalysisSummaryStrip analysis={query.data} />
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
          className="min-w-0 w-full rounded-md border border-gray-200 bg-white p-2 text-sm text-gray-600 xl:sticky xl:top-4 xl:h-[calc(100vh-6rem)] xl:w-[40%] 2xl:w-[45%]"
        >
          {activeDocumentId ? (
            <PDFViewer
              key={activeDocumentId}
              documentId={activeDocumentId}
              documentName={activeDocumentName ?? "Documento"}
              citations={activeCitations}
              documents={query.data.documents}
              focusCitation={selectedCitation}
            />
          ) : (
            <p className="p-4">No hay documentos disponibles para este análisis.</p>
          )}
        </aside>
      </div>
    </section>
  );
}
