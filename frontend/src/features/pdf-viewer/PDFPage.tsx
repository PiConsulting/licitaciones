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
  page: number;
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
  /** Avisa que esta página terminó de renderizar y ya ocupa su alto real.
   *
   * FIX (2026-08-14): el posicionamiento se movió entero a `PDFViewer`. Esta
   * página no sabe -- ni puede saber -- si las páginas de ARRIBA ya terminaron
   * de cargar, y hasta que terminen su propia posición dentro del panel sigue
   * cambiando. Quien tiene esa información es el visor. */
  onRendered?: (pageNumber: number) => void;
}

export function PDFPage({
  pageNumber,
  scale,
  fitWidth,
  citationTexts,
  sources,
  onScaleResolved,
  onRendered,
}: PDFPageProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  // Escala EFECTIVA de la página renderizada respecto de su tamaño nativo en
  // puntos. FIX (auditoría 2026-08-13, hallazgos HL-01 y HL-08): no alcanza con
  // la prop `scale`, que es el zoom elegido por el usuario y queda `undefined`
  // en modo ancho-de-columna -- el modo por defecto del visor. Con `scale`
  // undefined la condición de abajo era falsa y el overlay NUNCA se dibujaba.
  const [effectiveScale, setEffectiveScale] = useState<number>(0);
  const customTextRenderer = useMemo(() => createCitationTextRenderer(citationTexts), [citationTexts]);
  const hasActiveCitation = citationTexts.length > 0;
  
  // FIX CRÍTICO: Usar coordenadas pre-computadas si están disponibles
  const highlightRegions = useMemo(
    () => (sources ? getCombinedHighlightRegions(sources, pageNumber) : []),
    [sources, pageNumber]
  );
  const useCoordinateHighlight = highlightRegions.length > 0 && effectiveScale > 0;

  const handleLoadSuccess = (page: PageLoadResult) => {
    if (!page.originalWidth) {
      return;
    }
    const resolved = page.width / page.originalWidth;
    setEffectiveScale(resolved);
    onScaleResolved?.(resolved);
    onRendered?.(pageNumber);
  };

  const handleTextLayerRendered = () => {
    onRendered?.(pageNumber);
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
      
      {/* Highlight por coordenadas pre-computadas. Ver el CONTRATO DE
          COORDENADAS en `coordinateBasedHighlight.tsx`. */}
      {useCoordinateHighlight && (
        <HighlightOverlay regions={highlightRegions} scale={effectiveScale} />
      )}
    </div>
  );
}
