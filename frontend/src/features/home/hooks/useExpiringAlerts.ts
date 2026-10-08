import { useQuery } from "@tanstack/react-query";

import { getUpcomingEvents } from "../../../api/upcomingEvents";

export interface ExpiringAlertItem {
  id: string;
  analysisId: string;
  analysisName: string;
  organismo: string | null;
  businessStatus: string | null;
  businessUnit: string | null;
  eventName: string;
  daysUntil: number;
  dateLabel: string;
  additionalEvents: number;
}

function formatDateLabel(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

export function useExpiringAlerts(): ExpiringAlertItem[] {
  const query = useQuery({
    queryKey: ["home", "upcoming-events"],
    queryFn: getUpcomingEvents,
    staleTime: 1000 * 60,
  });

  return (query.data ?? []).map((item) => ({
    id: `${item.analysis_id}-${item.event_id}`,
    analysisId: item.analysis_id,
    analysisName: item.analysis_name ?? "Licitación sin nombre",
    organismo: item.organismo,
    businessStatus: item.business_status,
    businessUnit: item.business_unit,
    eventName: item.event_name,
    daysUntil: item.days_until,
    dateLabel: formatDateLabel(item.event_date),
    additionalEvents: item.additional_events,
  }));
}
