export type DateSource = "detected" | "user_input" | "calculated" | "pending";
export type EventStatus = "pending" | "confirmed";
export type DayType = "corridos" | "hábiles" | "no_especificado";
export type CalculationStatus = "pending" | "calculated" | "error";

export interface Event {
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
  created_at: string;
  updated_at: string;
}

export interface Deadline {
  id: string;
  deadline_id: string;
  analysis_id: string;
  target_event_id: string;
  trigger_event_id: string;
  duration: number;
  unit: string;
  day_type: DayType;
  calculated_date: string | null;
  calculation_status: CalculationStatus;
  calculation_error?: string;
  source_document_id?: string;
  source_page?: number;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}
