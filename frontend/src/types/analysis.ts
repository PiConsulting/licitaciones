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
  status: "draft" | "queued" | "processing" | "analyzed" | "error" | "cancelled";
  current_stage: "queued" | "extracting_text" | "indexing" | "analyzing" | "consolidating" | "completed";
  stage_progress?: string | null;
  progress_percentage: number;
  started_at?: string | null;
  timeout_at?: string | null;
  timeout_warning_at?: string | null;
  error_message?: string | null;
  extracted_data?: Record<string, unknown> | null;
  conflicts?: Array<Record<string, unknown>> | null;
}

export type AnalysisListSortBy = "created_at" | "status" | "current_stage";
export type AnalysisListSortOrder = "asc" | "desc";

export interface AnalysisListFilters {
  search?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  per_page?: number;
  sort_by?: AnalysisListSortBy;
  sort_order?: AnalysisListSortOrder;
}

export interface AnalysisListItem {
  id: string;
  status: string;
  current_stage: string;
  stage_progress?: string | null;
  progress_percentage: number;
  created_at: string;
  primary_document_name?: string | null;
  organismo?: string | null;
  created_by_name?: string | null;
}

export interface AnalysisListResponse {
  items: AnalysisListItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}
