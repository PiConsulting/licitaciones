export interface UpcomingEvent {
  analysis_id: string;
  analysis_name: string | null;
  organismo: string | null;
  business_status: string | null;
  business_unit: string | null;
  event_id: string;
  event_name: string;
  event_date: string;
  days_until: number;
  additional_events: number;
}
