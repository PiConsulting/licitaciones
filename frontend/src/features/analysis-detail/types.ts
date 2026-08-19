import type { AnalysisTracking } from "../../types/tracking";

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

/** Campos crudos de un plazo (PlazoItem del backend), preservados sin aplanar
 * para que la timeline de Plazos Clave pueda ubicar fechas literales en un eje
 * sin inventar ninguna a partir de una expresión relativa. */
export interface PlazoRawFields {
  fecha: string | null;
  hora: string | null;
  expresion_relativa: string | null;
  texto_original: string | null;
  lugar: string | null;
}

export interface FieldItem {
  field_name: string;
  field_value: string | null;
  field_state: FieldState;
  confidence: number;
  citations: Citation[];
  modified_by?: string;
  modified_at?: string;
  /** Solo presente en items de plazos_clave. */
  raw?: PlazoRawFields;
}

/** Región de highlight pre-computada por el backend usando PyMuPDF.
 * FIX CRÍTICO (2026-08): Reemplaza heurísticas frágiles con coordenadas exactas. */
export interface HighlightRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Fuente deduplicada de una CategoryNarrative, referenciada por índice desde
 * los bloques (`source_ids`). Distinta de `Citation`/`SourceReference`, que
 * siguen existiendo para el flujo legado por-campo. */
export interface NarrativeSource {
  id: number;
  document_id: string;
  document_name: string;
  page: number;
  text: string;
  /** El backend marca como no verificada una cita que no pudo respaldar
   * contra los chunks recuperados. Estas fuentes no deben mostrarse. */
  unverified?: boolean;
  /** Coordenadas exactas de highlight calculadas con PyMuPDF en el backend.
   * Si está vacío, PyMuPDF no disponible o texto no encontrado (mostrar página
   * sin highlight). FIX CRÍTICO (2026-08). */
  highlight_regions?: HighlightRegion[];
}

export interface NarrativeParagraphBlock {
  type: "paragraph";
  text: string;
  confidence_level: ConfidenceLevel;
  source_ids: number[];
}

export interface NarrativeBulletItem {
  text: string;
  confidence_level: ConfidenceLevel;
  source_ids: number[];
}

export interface NarrativeBulletListBlock {
  type: "bullet_list";
  items: NarrativeBulletItem[];
}

export interface NarrativeTableRow {
  cells: string[];
  confidence_level: ConfidenceLevel;
  source_ids: number[];
}

export interface NarrativeTableBlock {
  type: "table";
  headers: string[];
  rows: NarrativeTableRow[];
}

export type NarrativeBlockData = NarrativeParagraphBlock | NarrativeBulletListBlock | NarrativeTableBlock;

/**
 * Respuesta de experto para una categoría: nunca metadata cruda, siempre
 * bloques en lenguaje natural (párrafo/lista/tabla) con confianza y fuentes
 * deduplicadas. La arma el LLM en el backend (`<categoria>_narrative`); si no
 * está disponible, el frontend arma la misma forma con `buildNarrativeBlocks`
 * en `utils/narrativeSynthesis.ts`.
 */
export interface CategoryNarrative {
  blocks: NarrativeBlockData[];
  sources: NarrativeSource[];
}

export interface CategoryData {
  items: FieldItem[];
  confidence: number;
  source_references: SourceReference[];
  /** `not_analyzed` (CTX-03) es distinto de `not_found`: significa que el
   * pipeline no cubre esa categoría, no que el pliego calle sobre ella. */
  extraction_status:
    | "success"
    | "partial"
    | "failed"
    | "not_found"
    | "not_applicable"
    | "not_analyzed";
  summary: string;
  is_reviewed: boolean;
  /** Narrativa generada por el LLM de síntesis en el backend. Ausente cuando
   * la síntesis falló o todavía no corrió para este análisis. */
  narrative?: CategoryNarrative;
  /** Cuántos hallazgos se descartaron en esta categoría y por qué (ATR-03).
   * Sin esto, una categoría "parcial" no se distingue de una categoría en la
   * que el modelo produjo hallazgos que no se pudieron respaldar. */
  quality?: CategoryQuality;
}

export interface CategoryQuality {
  /** Items descartados por no tener ninguna cita verificable contra los chunks. */
  descartados_sin_evidencia?: number;
  /** Items descartados por no cumplir su schema. */
  descartados_por_formato?: number;
  /** Items conservados cuya cita declarada no verificaba y hubo que reemplazar. */
  con_evidencia_rescatada?: number;
  /** Items que llegaron al usuario. */
  conservados?: number;
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
  analysis_name?: string | null;
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
  tracking?: AnalysisTracking | null;
}
