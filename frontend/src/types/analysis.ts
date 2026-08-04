import type { DocumentSummary, DocumentWarning } from "./document";

export interface AnalysisCreateResponse {
  id: string;
  status: string;
  documents: DocumentSummary[];
  warnings: DocumentWarning[];
}

export type DuplicateAction = "view_existing" | "analyze_again" | "cancel";

export interface DuplicateWarning {
  document_id: string;
  filename: string;
  existing_analysis_id: string;
  created_at: string;
  created_by: string;
  status: string;
}

export interface DuplicateDecision {
  document_id: string;
  action: DuplicateAction;
}

export interface AnalysisStartPayload {
  decisions: DuplicateDecision[];
}

export interface AnalysisStartResponse {
  id: string;
  status: string;
  message: string;
  requires_resolution: boolean;
  duplicates: DuplicateWarning[];
  redirect_analysis_id: string | null;
}

export interface AnalysisStatusResponse {
  id: string;
  status:
    | "draft"
    | "queued"
    | "extracting_text"
    | "indexing"
    | "analyzing"
    | "analyzed"
    | "completed"
    | "error";
  current_stage: string | null;
  extracted_data?: Record<string, unknown> | null;
  conflicts?: Array<Record<string, unknown>> | null;
}
