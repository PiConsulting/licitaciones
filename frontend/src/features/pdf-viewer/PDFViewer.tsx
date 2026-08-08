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
import { useContainerWidth } from "./hooks/useContainerWidth";
import { useSASUrl } from "./hooks/useSASUrl";
import type { Citation, ViewerDocument } from "./types";
import { normalizeText } from "../../utils/highlightText";

const PAGE_ZOOM_STEP = 0.25;
const PAGE_MIN_ZOOM = 0.5;
const PAGE_MAX_ZOOM = 2;
// Small safety margin so the rendered page (plus its box-shadow) never bleeds
// past the container by a pixel or two and triggers an unwanted scrollbar.
const PAGE_FIT_SAFETY_MARGIN = 4;

type ZoomMode = "fit" | number;

interface PDFViewerProps {
  documentId: string;
  documentName: string;
  citations: Citation[];
  documents: ViewerDocument[];
  /** Cita puntual que el usuario clickeó (ej. una fuente específica de la
   * lista de "Fuentes verificables"), a diferencia de `citations`, que es el
   * conjunto completo por el que se puede navegar con "Cita anterior/siguiente".
   * Determina en qué cita del conjunto arranca el visor — sin esto, siempre
   * arrancaba en la primera cita de `citations`, sin importar cuál se clickeó. */
  focusCitation?: Citation | null;
}

/** Misma cita: mismo documento, página, y texto igual o uno subcadena del
 * otro — igual criterio que `dedupeCitations` usa para "misma fuente". */
function isSameCitation(a: Citation, b: Citation): boolean {
  if (a.document_id !== b.document_id || a.page !== b.page) {
    return false;
  }
  const normalizedA = normalizeText(a.text);
  const normalizedB = normalizeText(b.text);
  if (normalizedA === "" || normalizedB === "") {
    return normalizedA === normalizedB;
  }
  return normalizedA.includes(normalizedB) || normalizedB.includes(normalizedA);
}

/** Índice en `citations` que corresponde a `focusCitation`, o 0 si no hay
 * coincidencia (o no se especificó ninguna cita puntual a enfocar). */
function findFocusIndex(citations: Citation[], focusCitation: Citation | null | undefined): number {
  if (!focusCitation) {
    return 0;
  }
  const index = citations.findIndex((citation) => isSameCitation(citation, focusCitation));
  return index === -1 ? 0 : index;
}

function isForbiddenError(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  const message = "message" in error ? String(error.message) : "";
  return message.toLowerCase().includes("forbidden") || message.toLowerCase().includes("403");
}

export function PDFViewer({ documentId, documentName, citations, documents, focusCitation }: PDFViewerProps) {
  const [activeDocumentId, setActiveDocumentId] = useState(documentId);
  const initialIndex = findFocusIndex(citations, focusCitation);
  const [currentCitationIndex, setCurrentCitationIndex] = useState(initialIndex);
  const [currentPage, setCurrentPage] = useState(citations[initialIndex]?.page ?? focusCitation?.page ?? 1);
  const [numPages, setNumPages] = useState(0);
  const [zoomMode, setZoomMode] = useState<ZoomMode>("fit");
  const [displayScale, setDisplayScale] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const { ref: pdfContainerRef, width: containerWidth } = useContainerWidth<HTMLDivElement>();

  useEffect(() => {
    setActiveDocumentId(documentId);
    const focusIndex = findFocusIndex(citations, focusCitation);
    setCurrentCitationIndex(focusIndex);
    setCurrentPage(citations[focusIndex]?.page ?? focusCitation?.page ?? 1);
  }, [documentId, citations, focusCitation]);

  const { data, isLoading, refetch } = useSASUrl(activeDocumentId);
  // Only the citation currently focused via "Cita anterior/siguiente" gets highlighted
  // and scrolled to — highlighting every citation on a page at once made it unclear
  // which one "Ver fuente" was actually pointing at.
  const activeCitation = citations[currentCitationIndex] ?? null;

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
    <div className="flex h-full min-w-0 flex-col" data-testid="pdf-viewer">
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
        zoom={displayScale}
        isFitMode={zoomMode === "fit"}
        onPageChange={(page) => setCurrentPage(page)}
        onZoomIn={() =>
          setZoomMode((previous) =>
            Math.min((typeof previous === "number" ? previous : displayScale) + PAGE_ZOOM_STEP, PAGE_MAX_ZOOM),
          )
        }
        onZoomOut={() =>
          setZoomMode((previous) =>
            Math.max((typeof previous === "number" ? previous : displayScale) - PAGE_ZOOM_STEP, PAGE_MIN_ZOOM),
          )
        }
        onFitToWidth={() => setZoomMode("fit")}
      />

      <PDFCitationNav
        currentIndex={currentCitationIndex}
        total={citations.length}
        onPrev={() => onCitationChange(Math.max(currentCitationIndex - 1, 0))}
        onNext={() => onCitationChange(Math.min(currentCitationIndex + 1, citations.length - 1))}
      />

      <div
        ref={pdfContainerRef}
        className={`min-w-0 flex-1 overflow-y-auto bg-gray-100 p-3 ${zoomMode === "fit" ? "overflow-x-hidden" : "overflow-x-auto"}`}
        data-testid="pdf-container"
      >
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
            <PDFPage
              key={page}
              pageNumber={page}
              scale={typeof zoomMode === "number" ? zoomMode : undefined}
              fitWidth={
                zoomMode === "fit" && containerWidth > 0
                  ? Math.floor(Math.max(containerWidth - PAGE_FIT_SAFETY_MARGIN, 0))
                  : undefined
              }
              citationTexts={activeCitation && activeCitation.page === page ? [activeCitation.text] : []}
              onScaleResolved={setDisplayScale}
            />
          ))}
        </Document>
      </div>
    </div>
  );
}
