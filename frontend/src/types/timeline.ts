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
  event_date: string | null; // ISO date or null
  date_source: DateSource;
  status: EventStatus;
  source_document_id?: string;
  source_page?: number;
  source_fragment?: string;
  source_reference?: Record<string, unknown>;
  deleted: boolean;
  // Opcional (con default false a nivel backend) para no romper mocks de
  // tests existentes que construyen un EventResponse sin este campo -- ver
  // timeline/schemas.py::EventResponse.hidden (2026-09-01).
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
