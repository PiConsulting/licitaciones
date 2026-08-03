import type { DocumentSummary, DocumentWarning } from "./document";

export interface AnalysisCreateResponse {
  id: string;
  status: string;
  documents: DocumentSummary[];
  warnings: DocumentWarning[];
}
