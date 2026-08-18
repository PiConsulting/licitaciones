import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  focusIsStillPending,
  focusScrollTop,
  offsetWithinContainer,
  scrollContainerTo,
} from "./scrollWithinContainer";
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
import type { NarrativeSource } from "../analysis-detail/types";
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
  /** FIX CRÍTICO (2026-08): Sources con coordenadas pre-computadas para highlight.
   * Si está presente, PDFPage usa highlight basado en coordenadas en lugar de
   * heurísticas frágiles. */
  sources?: NarrativeSource[];
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

export function PDFViewer({ documentId, documentName, citations, documents, focusCitation, sources }: PDFViewerProps) {
  const [activeDocumentId, setActiveDocumentId] = useState(documentId);
  const initialIndex = findFocusIndex(citations, focusCitation);
  const [currentCitationIndex, setCurrentCitationIndex] = useState(initialIndex);
  const [currentPage, setCurrentPage] = useState(citations[initialIndex]?.page ?? focusCitation?.page ?? 1);
  const [numPages, setNumPages] = useState(0);
  const [zoomMode, setZoomMode] = useState<ZoomMode>("fit");
  const [displayScale, setDisplayScale] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const { ref: measureContainerRef, width: containerWidth } = useContainerWidth<HTMLDivElement>();

  // `useContainerWidth` devuelve un CALLBACK ref (una función), no un objeto
  // ref: mide el ancho cuando el nodo se monta.
  //
  // FIX (2026-08-14): el código de enfoque hacía `pdfContainerRef.current` sobre
  // esa función. En una función eso es `undefined`, así que el contenedor
  // siempre resultaba nulo, la rutina de enfoque salía por el `return` temprano
  // y el visor NUNCA scrolleaba. De ahí "no enfoca las fuentes cuando se hace
  // click": el panel se quedaba donde estaba, y lo que se veía era la posición
  // anterior. TypeScript no lo detectó porque `ref` es genérico.
  //
  // Acá se compone: se guarda el nodo en un ref propio Y se le pasa al medidor.
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);
  const setPdfContainer = useCallback(
    (node: HTMLDivElement | null) => {
      pdfContainerRef.current = node;
      measureContainerRef(node);
    },
    [measureContainerRef],
  );

  // Cada click en un ojito es un PEDIDO de enfoque, aunque sea sobre la misma
  // cita que ya estaba abierta.
  //
  // FIX (2026-08-14): el enfoque se consideraba "ya hecho" comparando una clave
  // armada con documento + página + texto de la cita. Volver a clickear la misma
  // fuente daba la misma clave, así que el visor no hacía nada -- si mientras
  // tanto habías scrolleado el PDF a mano, el botón parecía roto. Este contador
  // distingue dos pedidos idénticos.
  const [focusRequest, setFocusRequest] = useState(0);

  useEffect(() => {
    setActiveDocumentId(documentId);
    const focusIndex = findFocusIndex(citations, focusCitation);
    setCurrentCitationIndex(focusIndex);
    setCurrentPage(citations[focusIndex]?.page ?? focusCitation?.page ?? 1);
    setFocusRequest((request) => request + 1);
  }, [documentId, citations, focusCitation]);

  const { data, isLoading, refetch } = useSASUrl(activeDocumentId);
  // Only the citation currently focused via "Cita anterior/siguiente" gets highlighted
  // and scrolled to — highlighting every citation on a page at once made it unclear
  // which one "Ver fuente" was actually pointing at.
  const activeCitation = citations[currentCitationIndex] ?? null;

  // FIX (2026-08-14): se pasaban TODAS las sources a cada página, y
  // `getCombinedHighlightRegions` acumula las regiones de toda source cuya
  // `page` coincida -- sin mirar siquiera el `document_id`. Resultado: al
  // navegar entre citas se resaltaban a la vez todas las citas de esa página,
  // no la que se está mirando. `citationTexts` sí estaba acotado a la cita
  // activa; el overlay de coordenadas no.
  const activeSources = useMemo(
    () =>
      activeCitation
        ? (sources ?? []).filter((source) =>
            isSameCitation(
              {
                document_id: source.document_id,
                page: source.page,
                text: source.text,
                document_name: source.document_name,
              },
              activeCitation,
            ),
          )
        : [],
    [sources, activeCitation],
  );

  const pagesToRender = useMemo(() => {
    // Renderizar TODAS las páginas cuando el documento entra cómodo.
    //
    // La ventana de ±2 páginas es la fuente de casi todos los problemas de
    // posicionamiento: las páginas de arriba de la objetivo arrancan sin alto y
    // lo van ganando, así que la posición calculada se mueve bajo los pies. Y
    // además rompe el scroll manual (más allá de dos páginas no hay nada) y
    // hace que la barra de scroll mienta sobre el largo del documento.
    //
    // Con todas las páginas montadas, el alto total es estable desde que
    // react-pdf resuelve cada página, el scroll manual funciona y la barra dice
    // la verdad. El costo es memoria: cada página es un canvas, así que hay un
    // tope -- por encima de él se vuelve a la ventana, que para documentos así
    // de grandes es el mal menor.
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

  // ENFOQUE DE LA CITA
  // ------------------
  // FIX (2026-08-14, segunda pasada): esto se hacía en dos lugares -- un
  // `scrollIntoView` acá y otro en `PDFPage` -- y los dos disparaban UNA vez,
  // apenas cambiaba la página.
  //
  // El visor renderiza una ventana de páginas alrededor de la actual, y las que
  // están ARRIBA de la página objetivo arrancan casi sin alto y crecen cuando
  // react-pdf termina de dibujarlas. Cada una que termina empuja la página
  // objetivo hacia abajo. Enfocar una sola vez deja el visor en una posición
  // que deja de ser la correcta medio segundo después: de ahí "no enfoca" y
  // "enfoca mal en cualquier página".
  //
  // Ahora hay un solo lugar que enfoca, y vuelve a hacerlo cada vez que una
  // página termina de renderizar, hasta que no quede ninguna anterior pendiente.
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

  /** Y de la primera línea del resaltado, en puntos de la página sin escalar. */
  const activeRegionTop = useMemo(() => {
    if (!activeCitation || activeCitation.page !== currentPage) {
      return null;
    }
    const tops = activeSources.flatMap((source) =>
      (source.highlight_regions ?? []).map((region) => region.y),
    );
    return tops.length > 0 ? Math.min(...tops) : null;
  }, [activeSources, activeCitation, currentPage]);

  const focusKey = `${focusRequest}|${activeDocumentId}|${currentPage}|${activeCitation?.text ?? ""}`;

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
      // Mientras las páginas de arriba siguen creciendo, cada reintento es una
      // corrección de rumbo: instantánea, para no encadenar animaciones que se
      // pisan. La última, cuando ya nada se mueve, sí es suave.
      { behavior: pending ? "auto" : "smooth" },
    );

    if (!pending) {
      focusDoneRef.current = focusKey;
    }
  }, [focusKey, renderTick, currentPage, pagesToRender, activeRegionTop, displayScale]);

  const activeDocumentName = documents.find((doc) => doc.id === activeDocumentId)?.filename ?? documentName;

  const onCitationChange = (nextIndex: number) => {
    const target = citations[nextIndex];
    if (!target) {
      return;
    }
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
            className="mt-3 rounded bg-primary px-3 py-2 text-xs font-semibold text-primary-fg"
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
        ref={setPdfContainer}
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
