import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Document } from "react-pdf";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "../../utils/pdfWorker";
import { DocumentSelector } from "./DocumentSelector";
import { PDFCitationNav } from "./PDFCitationNav";
import { PDFControls } from "./PDFControls";
import { PDFPage } from "./PDFPage";
import { usePDFHighlight } from "./hooks/usePDFHighlight";
import { useSASUrl } from "./hooks/useSASUrl";
import type { Citation, ViewerDocument } from "./types";

interface PDFViewerProps {
  documentId: string;
  documentName: string;
  citations: Citation[];
  documents: ViewerDocument[];
}

function isForbiddenError(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  const message = "message" in error ? String(error.message) : "";
  return message.toLowerCase().includes("forbidden") || message.toLowerCase().includes("403");
}

export function PDFViewer({ documentId, documentName, citations, documents }: PDFViewerProps) {
  const [activeDocumentId, setActiveDocumentId] = useState(documentId);
  const [currentCitationIndex, setCurrentCitationIndex] = useState(0);
  const [currentPage, setCurrentPage] = useState(citations[0]?.page ?? 1);
  const [numPages, setNumPages] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setActiveDocumentId(documentId);
    setCurrentCitationIndex(0);
    setCurrentPage(citations[0]?.page ?? 1);
  }, [documentId, citations]);

  const { data, isLoading, refetch } = useSASUrl(activeDocumentId);
  const highlightsByPage = usePDFHighlight(citations);

  const pagesToRender = useMemo(() => {
    const buffer = 2;
    const start = Math.max(1, currentPage - buffer);
    const end = Math.min(numPages || currentPage, currentPage + buffer);
    const pages: number[] = [];
    for (let page = start; page <= end; page += 1) {
      pages.push(page);
    }
    return pages;
  }, [currentPage, numPages]);

  useEffect(() => {
    const pageElement = document.getElementById(`pdf-page-${currentPage}`);
    if (pageElement) {
      pageElement.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [currentPage]);

  const activeDocumentName = documents.find((doc) => doc.id === activeDocumentId)?.filename ?? documentName;

  const onCitationChange = (nextIndex: number) => {
    const target = citations[nextIndex];
    if (!target) {
      return;
    }
    setCurrentCitationIndex(nextIndex);
    setCurrentPage(target.page);
    if (target.document_id !== activeDocumentId) {
      setActiveDocumentId(target.document_id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <span>Cargando documento...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-gray-50 p-4 text-center">
        <div>
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-error" />
          <p className="text-sm text-error">{error}</p>
          <button
            type="button"
            className="mt-3 rounded bg-primary px-3 py-2 text-xs font-semibold text-white"
            onClick={() => {
              setError(null);
              void refetch();
            }}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (!data?.url) {
    return <p className="p-4 text-sm text-gray-600">No se pudo cargar el documento. Intente nuevamente o contacte soporte.</p>;
  }

  return (
    <div className="flex h-full flex-col" data-testid="pdf-viewer">
      <div className="flex items-center gap-2 border-b border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700">
        <span className="truncate">{activeDocumentName}</span>
        <DocumentSelector
          documents={documents}
          value={activeDocumentId}
          onChange={(nextDocumentId) => {
            setActiveDocumentId(nextDocumentId);
            setCurrentCitationIndex(0);
            const firstCitationInDocument = citations.find((citation) => citation.document_id === nextDocumentId);
            setCurrentPage(firstCitationInDocument?.page ?? 1);
          }}
        />
      </div>

      <PDFControls
        currentPage={currentPage}
        totalPages={numPages}
        zoom={zoom}
        onPageChange={(page) => setCurrentPage(page)}
        onZoomIn={() => setZoom((previous) => Math.min(previous + 0.25, 2))}
        onZoomOut={() => setZoom((previous) => Math.max(previous - 0.25, 0.5))}
      />

      <PDFCitationNav
        currentIndex={currentCitationIndex}
        total={citations.length}
        onPrev={() => onCitationChange(Math.max(currentCitationIndex - 1, 0))}
        onNext={() => onCitationChange(Math.min(currentCitationIndex + 1, citations.length - 1))}
      />

      <div className="flex-1 overflow-auto bg-gray-100 p-3" data-testid="pdf-container">
        <Document
          file={data.url}
          onLoadSuccess={({ numPages: pages }) => {
            setNumPages(pages);
            setError(null);
          }}
          onLoadError={(loadError) => {
            if (isForbiddenError(loadError)) {
              void refetch();
              return;
            }
            setError("No se pudo cargar el documento. Intente nuevamente o contacte soporte.");
          }}
          loading={<Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />}
          data-testid="pdf-document"
        >
          {pagesToRender.map((page) => (
            <PDFPage key={page} pageNumber={page} zoom={zoom} highlights={highlightsByPage.get(page) ?? []} />
          ))}
        </Document>
      </div>
    </div>
  );
}
