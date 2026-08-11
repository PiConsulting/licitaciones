import { useMemo, useRef, useState } from "react";
import { Page } from "react-pdf";

import { createCitationTextRenderer } from "../../utils/highlightText";
import { HighlightOverlay, getCombinedHighlightRegions } from "../../utils/coordinateBasedHighlight";
import type { HighlightRegion } from "../analysis-detail/types";

interface PageLoadResult {
  width: number;
  originalWidth: number;
  height: number;
}

interface SourceForHighlight {
  page_number: number;
  highlight_regions?: HighlightRegion[];
}

interface PDFPageProps {
  pageNumber: number;
  scale?: number;
  fitWidth?: number;
  citationTexts: string[];
  /** FIX CRÍTICO (2026-08): Sources con coordenadas pre-computadas para highlight */
  sources?: SourceForHighlight[];
  onScaleResolved?: (scale: number) => void;
}

export function PDFPage({ pageNumber, scale, fitWidth, citationTexts, sources, onScaleResolved }: PDFPageProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [pageHeight, setPageHeight] = useState<number>(0);
  const customTextRenderer = useMemo(() => createCitationTextRenderer(citationTexts), [citationTexts]);
  const hasActiveCitation = citationTexts.length > 0;
  
  // FIX CRÍTICO: Usar coordenadas pre-computadas si están disponibles
  const highlightRegions = useMemo(
    () => (sources ? getCombinedHighlightRegions(sources, pageNumber) : []),
    [sources, pageNumber]
  );
  const useCoordinateHighlight = highlightRegions.length > 0;

  const handleLoadSuccess = (page: PageLoadResult) => {
    if (!page.originalWidth) {
      return;
    }
    setPageHeight(page.height);
    onScaleResolved?.(page.width / page.originalWidth);
  };

  const handleTextLayerRendered = () => {
    if (!hasActiveCitation) {
      return;
    }
    const container = wrapperRef.current;
    const mark = container?.querySelector("mark");
    if (mark) {
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      container?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div id={`pdf-page-${pageNumber}`} ref={wrapperRef} className="relative mx-auto mb-4 min-w-0 max-w-full">
      <Page
        pageNumber={pageNumber}
        {...(fitWidth ? { width: fitWidth } : { scale })}
        renderTextLayer
        renderAnnotationLayer={false}
        customTextRenderer={hasActiveCitation && !useCoordinateHighlight ? customTextRenderer : undefined}
        onRenderTextLayerSuccess={handleTextLayerRendered}
        className="shadow"
        data-testid={`pdf-page-${pageNumber}`}
        onLoadSuccess={handleLoadSuccess}
      />
      
      {/* FIX CRÍTICO (2026-08): Highlight basado en coordenadas pre-computadas */}
      {useCoordinateHighlight && scale && pageHeight > 0 && (
        <HighlightOverlay
          regions={highlightRegions}
          scale={scale}
          pageHeight={pageHeight}
        />
      )}
    </div>
  );
}
