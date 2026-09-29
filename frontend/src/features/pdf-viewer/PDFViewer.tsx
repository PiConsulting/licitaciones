import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  focusIsStillPending,
  focusScrollTop,
  offsetWithinContainer,
  scrollContainerTo,
} from "./scrollWithinContainer";
import { AlertTriangle, Loader2, X } from "lucide-react";
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
import type { NarrativeSource } from "../analysis-detail/types";
import { normalizeText } from "../../utils/highlightText";

const PAGE_ZOOM_STEP = 0.25;
const PAGE_MIN_ZOOM = 0.5;
const PAGE_MAX_ZOOM = 2;
// Margen para que la página (más su box-shadow) no dispare un scrollbar no deseado.
const PAGE_FIT_SAFETY_MARGIN = 4;

type ZoomMode = "fit" | number;

interface PDFViewerProps {
  documentId: string;
  documentName: string;
  citations: Citation[];
  documents: ViewerDocument[];
  showDocumentSelector?: boolean;
  /** Cita puntual que el usuario clickeó (ej. una fuente específica de la
   * lista de "Fuentes verificables"), a diferencia de `citations`, que es el
   * conjunto completo por el que se puede navegar con "Cita anterior/siguiente".
   * Determina en qué cita del conjunto arranca el visor — sin esto, siempre
   * arrancaba en la primera cita de `citations`, sin importar cuál se clickeó. */
  focusCitation?: Citation | null;
  /** FIX CRÍTICO (2026-08): Sources con coordenadas pre-computadas para highlight.
   * Si está presente, PDFPage usa highlight basado en coordenadas en lugar de
   * heurísticas frágiles. */
  sources?: NarrativeSource[];
  onClose?: () => void;
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

/** Tope de páginas montadas a la vez. Un pliego típico ronda las 10-40, así que
 * en la práctica se renderiza entero; el tope existe para que un documento de
 * cientos de páginas no reviente la memoria con un canvas por página. */
const MAX_PAGES_RENDERED_AT_ONCE = 60;

export function PDFViewer({
  documentId,
  documentName,
  citations,
  documents,
  showDocumentSelector = true,
  focusCitation,
  sources,
  onClose,
}: PDFViewerProps) {
  const [activeDocumentId, setActiveDocumentId] = useState(documentId);
  const initialIndex = findFocusIndex(citations, focusCitation);
  const initialPage = citations[initialIndex]?.page ?? focusCitation?.page ?? 1;
  const [currentCitationIndex, setCurrentCitationIndex] = useState(initialIndex);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [pagePositions, setPagePositions] = useState<Record<string, number>>(() => ({ [documentId]: initialPage }));
  const [numPages, setNumPages] = useState(0);
  const [zoomMode, setZoomMode] = useState<ZoomMode>("fit");
  const [displayScale, setDisplayScale] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const { ref: measureContainerRef, width: containerWidth } = useContainerWidth<HTMLDivElement>();

  // `useContainerWidth` devuelve un callback ref, no un ref object; se compone con un ref propio para poder leer `.current` en el enfoque.
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);
  const setPdfContainer = useCallback(
    (node: HTMLDivElement | null) => {
      pdfContainerRef.current = node;
      measureContainerRef(node);
    },
    [measureContainerRef],
  );

  // Contador para que reclickear la misma cita cuente como un nuevo pedido de enfoque (la clave documento+página+texto por sí sola no cambiaba).
  const [focusRequest, setFocusRequest] = useState(0);

  useEffect(() => {
    setActiveDocumentId(documentId);
    const focusIndex = findFocusIndex(citations, focusCitation);
    const focusedCitation = citations[focusIndex] ?? focusCitation ?? null;
    const focusBelongsToTarget = focusedCitation?.document_id === documentId;
    const firstCitationInTarget = citations.find((citation) => citation.document_id === documentId);
    const focusPage = focusedCitation?.page ?? 1;
    const restoredPage = pagePositions[documentId] ?? firstCitationInTarget?.page ?? 1;
    const nextPage = focusBelongsToTarget ? focusPage : restoredPage;

    setCurrentCitationIndex(focusIndex);
    setCurrentPage(nextPage);
    setPagePositions((previous) => ({ ...previous, [documentId]: nextPage }));
    setFocusRequest((request) => request + 1);
  }, [documentId, citations, focusCitation]);

  const { data, isLoading, refetch } = useSASUrl(activeDocumentId);
  // Solo la cita enfocada por "Cita anterior/siguiente" se resalta y scrollea, para que quede claro a cuál apunta "Ver fuente".
  const activeCitation = citations[currentCitationIndex] ?? null;
  const activeCitationInDocument =
    activeCitation && activeCitation.document_id === activeDocumentId ? activeCitation : null;

  // Amplía a todas las citas de `citations` (ya acotado por el llamador a este click) que caigan en la misma página que la enfocada, no solo la que matchea exacto -- así un ítem con varias citas propias (ej. plazo + lugar de entrega) se resalta completo en vez de solo la primera.
  const activeSources = useMemo(() => {
    if (!activeCitationInDocument) {
      return [];
    }
    const citationsOnSamePage = citations.filter(
      (citation) =>
        citation.document_id === activeCitationInDocument.document_id &&
        citation.page === activeCitationInDocument.page,
    );
    const textMatched = (sources ?? []).filter((source) =>
      citationsOnSamePage.some((citation) =>
        isSameCitation(
          {
            document_id: source.document_id,
            page: source.page,
            text: source.text,
            document_name: source.document_name,
          },
          citation,
        ),
      ),
    );
    if (textMatched.length > 0) {
      return textMatched;
    }

    // Fallback: si la cita textual no matchea exacto (ej. source concatenada o recortada distinto), doc+página evita perder el highlight.
    return (sources ?? []).filter(
      (source) =>
        source.document_id === activeCitationInDocument.document_id &&
        source.page === activeCitationInDocument.page,
    );
  }, [sources, citations, activeCitationInDocument]);

  const pagesToRender = useMemo(() => {
    // Se renderizan todas las páginas cuando el documento entra cómodo: una ventana de ±2 deja el alto inestable (páginas de arriba creciendo) y rompe el scroll manual. Por encima del tope se vuelve a la ventana por memoria.
    const total = numPages || currentPage;
    if (total <= MAX_PAGES_RENDERED_AT_ONCE) {
      return Array.from({ length: total }, (_unused, index) => index + 1);
    }

    const buffer = 2;
    const start = Math.max(1, currentPage - buffer);
    const end = Math.min(total, currentPage + buffer);
    const pages: number[] = [];
    for (let page = start; page <= end; page += 1) {
      pages.push(page);
    }
    return pages;
  }, [currentPage, numPages]);

  // Enfoque de la cita: un solo efecto que reintenta en cada página renderizada, porque las páginas de arriba siguen creciendo y desplazan la posición objetivo.
  const renderedPagesRef = useRef<Set<number>>(new Set());
  const [renderTick, setRenderTick] = useState(0);
  const focusDoneRef = useRef<string | null>(null);

  const handlePageRendered = useCallback((pageNumber: number) => {
    if (renderedPagesRef.current.has(pageNumber)) {
      return;
    }
    renderedPagesRef.current.add(pageNumber);
    setRenderTick((tick) => tick + 1);
  }, []);

  // Cambiar de documento o de zoom invalida todos los altos ya medidos.
  useEffect(() => {
    renderedPagesRef.current = new Set();
    focusDoneRef.current = null;
  }, [activeDocumentId, zoomMode, containerWidth]);

  /** Y de la primera línea del resaltado, en puntos de la página sin escalar.
   *
   * FIX (2026-09-17): `activeSources` incluye TODAS las citas del ítem que
   * caen en la misma página (ver FIX 2026-09-03 arriba) para poder pintarlas
   * juntas -- correcto para el resaltado, pero acá se usaba ese mismo
   * conjunto ampliado para elegir a QUÉ Y hacer scroll, con `Math.min` sobre
   * todas. Un ítem de "Plazos Clave" con dos citas en la misma página (ej. el
   * plazo en sí + el lugar de entrega) donde la cita clickeada es la de MÁS
   * ABAJO terminaba haciendo scroll a la de arriba -- se pintaba el
   * resaltado correcto, pero quedaba fuera de la vista, y visualmente parecía
   * que no había fuente. Ahora se prioriza el/los renglón(es) de la cita
   * puntual que el usuario enfocó (`activeCitationInDocument`); solo si esa
   * cita puntual no matchea ningún source (fallback de robustez ya existente
   * en `activeSources`) se vuelve al mínimo sobre el conjunto ampliado. */
  const activeRegionTop = useMemo(() => {
    if (!activeCitationInDocument || activeCitationInDocument.page !== currentPage) {
      return null;
    }
    const ownSources = activeSources.filter((source) =>
      isSameCitation(
        {
          document_id: source.document_id,
          page: source.page,
          text: source.text,
          document_name: source.document_name,
        },
        activeCitationInDocument,
      ),
    );
    const sourcesForTop = ownSources.length > 0 ? ownSources : activeSources;
    const tops = sourcesForTop.flatMap((source) =>
      (source.highlight_regions ?? []).map((region) => region.y),
    );
    return tops.length > 0 ? Math.min(...tops) : null;
  }, [activeSources, activeCitationInDocument, currentPage]);

  const focusKey = `${focusRequest}|${activeDocumentId}|${currentPage}|${activeCitationInDocument?.text ?? ""}`;

  useEffect(() => {
    focusDoneRef.current = null;
  }, [focusKey]);

  useEffect(() => {
    if (focusDoneRef.current === focusKey) {
      return;
    }

    const container = pdfContainerRef.current;
    const pageElement = document.getElementById(`pdf-page-${currentPage}`);
    if (!container || !pageElement) {
      return;
    }

    const pending = focusIsStillPending(pagesToRender, currentPage, renderedPagesRef.current);

    scrollContainerTo(
      container,
      focusScrollTop({
        pageOffset: offsetWithinContainer(container, pageElement),
        regionTop: activeRegionTop,
        scale: displayScale,
        viewportHeight: container.clientHeight,
      }),
      // Reintentos mientras el alto es inestable van instantáneos (no encadenar animaciones); el final, suave.
      { behavior: pending ? "auto" : "smooth" },
    );

    if (!pending) {
      focusDoneRef.current = focusKey;
    }
  }, [focusKey, renderTick, currentPage, pagesToRender, activeRegionTop, displayScale]);

  const activeDocumentName = documents.find((doc) => doc.id === activeDocumentId)?.filename ?? documentName;
  const hasMultipleDocuments = documents.length > 1;

  const onCitationChange = (nextIndex: number) => {
    const target = citations[nextIndex];
    if (!target) {
      return;
    }

    setPagePositions((previous) => ({
      ...previous,
      [activeDocumentId]: currentPage,
      [target.document_id]: target.page,
    }));

    setCurrentCitationIndex(nextIndex);
    setCurrentPage(target.page);
    setFocusRequest((request) => request + 1);
    if (target.document_id !== activeDocumentId) {
      setActiveDocumentId(target.document_id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-2">
        <Loader2 className="h-5 w-5 animate-spin text-[#0099DB]" />
        <span className="text-sm text-[rgba(0,60,107,.68)]">Cargando documento...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-[#F4F9FC] p-4 text-center">
        <div>
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-[#DC2626]" />
          <p className="text-sm text-[#B91C1C]">{error}</p>
          <button
            type="button"
            className="mt-3 rounded-full bg-[#0099DB] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#003C6B]"
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
    return (
      <p className="p-4 text-sm text-[rgba(0,60,107,.68)]">
        No se pudo cargar el documento. Intente nuevamente o contacte soporte.
      </p>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden" data-testid="pdf-viewer">
      <div className="flex items-center justify-between gap-2 border-b border-[rgba(0,60,107,.12)] px-4 py-2.5">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {showDocumentSelector && hasMultipleDocuments ? (
            <DocumentSelector
              documents={documents}
              value={activeDocumentId}
              onChange={(nextDocumentId) => {
                setCurrentCitationIndex(0);
                setPagePositions((previous) => ({ ...previous, [activeDocumentId]: currentPage }));
                const firstCitationInDocument = citations.find((citation) => citation.document_id === nextDocumentId);
                const nextPage = pagePositions[nextDocumentId] ?? firstCitationInDocument?.page ?? 1;
                setActiveDocumentId(nextDocumentId);
                setCurrentPage(nextPage);
                setPagePositions((previous) => ({ ...previous, [nextDocumentId]: nextPage }));
              }}
            />
          ) : (
            <span className="block min-w-0 truncate font-display text-xs font-semibold text-[#003C6B]">
              {activeDocumentName}
            </span>
          )}
        </div>
        {onClose ? (
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[rgba(0,60,107,.55)] transition-colors hover:bg-[#F4F9FC] hover:text-[#003C6B] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0099DB]"
            onClick={onClose}
            aria-label="Ocultar visor PDF"
            title="Ocultar visor PDF"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <PDFControls
        currentPage={currentPage}
        totalPages={numPages}
        zoom={displayScale}
        isFitMode={zoomMode === "fit"}
        onPageChange={(page) => {
          setCurrentPage(page);
          setPagePositions((previous) => ({ ...previous, [activeDocumentId]: page }));
        }}
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
        citationSlot={
          <PDFCitationNav
            currentIndex={currentCitationIndex}
            total={citations.length}
            onPrev={() => onCitationChange(Math.max(currentCitationIndex - 1, 0))}
            onNext={() => onCitationChange(Math.min(currentCitationIndex + 1, citations.length - 1))}
          />
        }
      />

      <div
        ref={setPdfContainer}
        className={`min-w-0 flex-1 overflow-y-auto bg-[rgba(0,60,107,.06)] p-4 ${zoomMode === "fit" ? "overflow-x-hidden" : "overflow-x-auto"}`}
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
          loading={<Loader2 className="mx-auto h-6 w-6 animate-spin text-[#0099DB]" />}
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
              citationTexts={
                activeCitationInDocument && activeCitationInDocument.page === page
                  ? [activeCitationInDocument.text]
                  : []
              }
              sources={activeSources}
              onScaleResolved={setDisplayScale}
              onRendered={handlePageRendered}
            />
          ))}
        </Document>
      </div>
    </div>
  );
}
