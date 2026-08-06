import { useMemo } from "react";

import { findTextCoordinates } from "../../../utils/highlightText";
import type { Citation, HighlightCoordinates } from "../types";

export function usePDFHighlight(citations: Citation[]): Map<number, HighlightCoordinates[]> {
  return useMemo(() => {
    const grouped = new Map<number, HighlightCoordinates[]>();

    citations.forEach((citation) => {
      const current = grouped.get(citation.page) ?? [];
      const computed = findTextCoordinates(citation.text, citation.text);
      grouped.set(citation.page, [...current, ...computed]);
    });

    return grouped;
  }, [citations]);
}
