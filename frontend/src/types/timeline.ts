// Coordenadas pre-computadas por el backend (PyMuPDF + fallback OCR, ver
// `analysis/extraction/highlight/highlight.py`) para dibujar el highlight
// exacto sobre el PDF -- mismo contrato que `HighlightRegion` en
// `features/analysis-detail/types.ts`, copiado acá para no acoplar este
// módulo top-level a esa feature.
export interface HighlightRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type DateSource = "detected" | "user_input" | "calculated" | "pending";
export type EventStatus = "pending" | "confirmed";
export type DurationUnit = "días" | "meses" | "años" | "horas";
export type DayType = "corridos" | "hábiles" | "no_especificado";
export type DireccionTemporal = "desde" | "hasta" | "antes_de" | "después_de";
export type CalculationStatus = "pending" | "calculated" | "error";

export interface EventResponse {
  id: string;
  event_id: string;
  analysis_id: string;
  name: string;
  event_date: string | null;
  date_source: DateSource;
  status: EventStatus;
  source_document_id?: string;
  source_page?: number;
  source_fragment?: string;
  // Descripción breve sintetizada (ej. "El oferente presenta la oferta"), no la cita literal del pliego -- ver EventResponse.detalle (backend). Ausente en eventos de análisis previos al 2026-09-28, sin reanalizar: la UI cae a source_fragment.
  detalle?: string;
  source_reference?: Record<string, unknown>;
  deleted: boolean;
  // Opcional (default false en backend) para no romper mocks de tests viejos sin este campo -- ver EventResponse.hidden.
  hidden?: boolean;
  // Ausente en eventos materializados antes de esta columna (2026-10-01) -- "ver fuente" cae a página sin resaltar.
  highlight_regions?: HighlightRegion[];
  created_at: string;
  updated_at: string;
}

// Alias pre-existentes que varios componentes de timeline ya importaban (`Event`/`Deadline`)
// sin que este módulo los exportara -- `tsc --noEmit` ya los marcaba como error antes de este
// cambio; se agregan acá en vez de tocar cada import, misma forma que EventResponse/DeadlineResponse.
export type Event = EventResponse;

export interface DeadlineResponse {
  id: string;
  deadline_id: string;
  analysis_id: string;
  name: string;
  trigger_event_id?: string | null;
  target_event_id?: string | null;
  duration: number;
  unit: DurationUnit;
  day_type: DayType;
  direccion?: DireccionTemporal | null;
  es_plazo_maximo: boolean;
  deadline_date: string | null;
  calculation_status: CalculationStatus;
  calculation_error?: string;
  source_document_id?: string;
  source_page?: number;
  source_fragment?: string;
  source_reference?: Record<string, unknown>;
  deleted: boolean;
  highlight_regions?: HighlightRegion[];
  created_at: string;
  updated_at: string;
}

export type Deadline = DeadlineResponse;
