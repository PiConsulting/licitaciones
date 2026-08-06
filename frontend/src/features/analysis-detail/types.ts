export type CategoryId =
  | "objeto_alcance"
  | "requisitos_admisibilidad"
  | "garantias"
  | "plazos_clave"
  | "criterios_evaluacion"
  | "causales_rechazo"
  | "anexos_obligatorios"
  | "datos_procedimiento";

export type FieldState = "extraido" | "no_encontrado" | "no_aplica" | "en_conflicto";
export type ConfidenceLevel = "high" | "medium" | "low";

export interface Citation {
  text: string;
  page: number;
  document_id: string;
  document_name: string;
  value?: string;
}

export interface SourceReference {
  page: number;
  document_id: string;
  text_snippet: string;
}

export interface FieldItem {
  field_name: string;
  field_value: string | null;
  field_state: FieldState;
  confidence: number;
  citations: Citation[];
  modified_by?: string;
  modified_at?: string;
}

export interface CategoryData {
  items: FieldItem[];
  confidence: number;
  source_references: SourceReference[];
  extraction_status: "success" | "partial" | "failed" | "not_found" | "not_applicable";
  summary: string;
  is_reviewed: boolean;
  /** Párrafo en lenguaje natural generado por LLM a partir de la metadata extraída.
   * Todavía no lo emite el backend; hasta entonces se arma en frontend, ver
   * `buildCategoryNarrative` en `utils/categoryNarrative.ts`. */
  narrative?: string;
}

export interface ConflictData {
  field_path: string;
  values: Array<{
    value: string;
    document_id: string;
    citation: Citation;
  }>;
}

export interface AnalysisVersion {
  id: string;
  version_number: number;
  extracted_data: Record<CategoryId, CategoryData>;
  conflicts: Record<string, ConflictData>;
  created_at: string;
  created_by?: string;
}

export interface AnalysisDetail {
  id: string;
  created_at: string;
  status: "queued" | "processing" | "analyzed" | "validated" | "error" | "cancelled";
  current_stage: string;
  current_version: AnalysisVersion;
  documents: Array<{
    id: string;
    filename: string;
    is_primary: boolean;
    page_count?: number;
  }>;
  created_by?: string;
}
