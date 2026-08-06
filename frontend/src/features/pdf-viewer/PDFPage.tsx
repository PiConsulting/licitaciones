import { Page } from "react-pdf";

import { PDFHighlighter } from "./PDFHighlighter";
import type { HighlightCoordinates } from "./types";

interface PDFPageProps {
  pageNumber: number;
  zoom: number;
  highlights: HighlightCoordinates[];
}

export function PDFPage({ pageNumber, zoom, highlights }: PDFPageProps) {
  return (
    <div id={`pdf-page-${pageNumber}`} className="relative mx-auto mb-4 w-fit">
      <Page
        pageNumber={pageNumber}
        scale={zoom}
        renderTextLayer
        renderAnnotationLayer={false}
        className="shadow"
        data-testid={`pdf-page-${pageNumber}`}
      />
      <PDFHighlighter coordinates={highlights} />
    </div>
  );
}
