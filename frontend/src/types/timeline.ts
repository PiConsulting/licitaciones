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
  created_at: string;
  updated_at: string;
}

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
  created_at: string;
  updated_at: string;
}
