import type { DocumentResponse, DocumentWarning } from "./document";

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

export interface AnalysisCreateResponse {
  id: string;
  status: string;
  documents: DocumentResponse[];
  warnings: DocumentWarning[];
  requires_resolution: boolean;
  duplicates: DuplicateWarning[];
}

export interface StartAnalysisRequest {
  decisions: DuplicateDecision[];
  analysis_name?: string;
}

export interface AnalysisStartResponse {
  id: string;
  status: string;
  message: string;
  requires_resolution: boolean;
  duplicates: DuplicateWarning[];
  redirect_analysis_id: string | null;
}

export type CategoriesDecision = "approved" | "rejected";

export interface CategoriesDecisionResponse {
  id: string;
  status: string;
  message: string;
  decision: CategoriesDecision;
  decision_by_name: string | null;
  decision_at: string | null;
}

export interface AnalysisStatusResponse {
  id: string;
  status: "draft" | "queued" | "processing" | "en_revision" | "analyzed" | "error" | "cancelled";
  current_stage: "queued" | "extracting_text" | "indexing" | "analyzing" | "consolidating" | "completed";
  stage_progress?: string | null;
  progress_percentage: number;
  started_at?: string | null;
  timeout_at?: string | null;
  timeout_warning_at?: string | null;
  error_message?: string | null;
  extracted_data?: Record<string, unknown> | null;
  conflicts?: Array<Record<string, unknown>> | null;
  reanalysis_type?: "all" | "phase1" | "phase2" | "categories" | null;
  reanalysis_categories?: string[];
  reanalysis_started_at?: string | null;
}

export type ReanalyzeType = "all" | "phase1" | "phase2" | "categories";

export interface ReanalyzeRequest {
  reanalysis_type: ReanalyzeType;
  categories?: string[];
}

export interface ReanalyzeResponse {
  id: string;
  status: string;
  message: string;
  reanalysis_type: ReanalyzeType;
  categories: string[];
  source_version_id: string | null;
  target_version_id: string | null;
  target_version_number: number | null;
}

export interface PatchAnalysisRequest {
  monto_estimado: number;
  moneda: string;
}

export interface PatchAnalysisResponse {
  id: string;
  monto_estimado: number;
  moneda: string;
  monto_estimado_source: "manual";
  message: string;
}

export type AnalysisListSortBy = "created_at" | "status" | "current_stage";
export type AnalysisListSortOrder = "asc" | "desc";

export interface AnalysisListFilters {
  search?: string;
  status?: string;
  business_unit?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  per_page?: number;
  sort_by?: AnalysisListSortBy;
  sort_order?: AnalysisListSortOrder;
}

export interface AnalysisListItem {
  id: string;
  analysis_name?: string | null;
  business_unit?: string | null;
  business_status?: string | null;
  monto_estimado?: number | null;
  moneda?: string | null;
  opening_date?: string | null;
  closing_date?: string | null;
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

export interface AnalysisBusinessUnitItem {
  business_unit: string;
  count: number;
}
