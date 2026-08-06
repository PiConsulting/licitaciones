import { useMemo, useRef } from "react";
import { Page } from "react-pdf";

import { createCitationTextRenderer } from "../../utils/highlightText";

interface PageLoadResult {
  width: number;
  originalWidth: number;
}

interface PDFPageProps {
  pageNumber: number;
  scale?: number;
  fitWidth?: number;
  citationTexts: string[];
  onScaleResolved?: (scale: number) => void;
}

export function PDFPage({ pageNumber, scale, fitWidth, citationTexts, onScaleResolved }: PDFPageProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const customTextRenderer = useMemo(() => createCitationTextRenderer(citationTexts), [citationTexts]);
  const hasActiveCitation = citationTexts.length > 0;

  const handleLoadSuccess = (page: PageLoadResult) => {
    if (!page.originalWidth) {
      return;
    }
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
        customTextRenderer={hasActiveCitation ? customTextRenderer : undefined}
        onRenderTextLayerSuccess={handleTextLayerRendered}
        className="shadow"
        data-testid={`pdf-page-${pageNumber}`}
        onLoadSuccess={handleLoadSuccess}
      />
    </div>
  );
}
