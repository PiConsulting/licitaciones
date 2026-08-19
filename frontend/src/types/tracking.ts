export type TrackingStatus = "active" | "completed";
export type TrackingCategoryStatus = "not_reviewed" | "in_review" | "closed";
export type TrackingItemStatus = "not_evaluated" | "compliant" | "non_compliant" | "not_applicable";
export type TrackingCommentScope = "category" | "checklist_item";

export interface TrackingSourceItemRef {
  version_id: string;
  field_name: string;
  document_id?: string | null;
  page?: number | null;
  citation_hash?: string | null;
}

export interface TrackingItem {
  tracking_item_id: string;
  category_key: string;
  source_item_ref: TrackingSourceItemRef;
  status: TrackingItemStatus;
  updated_by?: string | null;
  updated_at?: string | null;
  comments_count?: number;
}

export interface TrackingCategory {
  category_key: string;
  status: TrackingCategoryStatus;
  updated_by?: string | null;
  updated_at?: string | null;
  closed_by?: string | null;
  closed_at?: string | null;
  reopened_by?: string | null;
  reopened_at?: string | null;
  items: TrackingItem[];
  comments_count: number;
}

export interface TrackingSummary {
  total_categories: number;
  not_reviewed: number;
  in_review: number;
  closed: number;
  closed_percentage: number;
}

export interface AnalysisTracking {
  id: string;
  type: "tracking";
  analysis_id: string;
  version_id: string;
  status: TrackingStatus;
  started_by: string;
  started_at: string;
  completed_by?: string | null;
  completed_by_name?: string | null;
  completed_at?: string | null;
  updated_at: string;
  categories: TrackingCategory[];
  summary: TrackingSummary;
}

export interface TrackingComment {
  id: string;
  analysis_id: string;
  version_id: string;
  category_key: string;
  scope: TrackingCommentScope;
  tracking_item_id?: string | null;
  content: string;
  created_by: string;
  created_by_name?: string | null;
  created_at: string;
  edited_by?: string | null;
  edited_by_name?: string | null;
  edited_at?: string | null;
  deleted?: boolean;
  deleted_at?: string | null;
  deleted_by?: string | null;
}
