import { useQueryClient } from "@tanstack/react-query";

import type { EventResponse } from "../../types/timeline";

export type MarkedDates = Record<string, string[]>;

export function buildMarkedDates(
  events: EventResponse[] | undefined,
  excludeEventId?: string,
): MarkedDates {
  const marked: MarkedDates = {};
  for (const event of events ?? []) {
    if (event.deleted || event.hidden || !event.event_date) {
      continue;
    }
    if (excludeEventId && event.event_id === excludeEventId) {
      continue;
    }
    marked[event.event_date] = [...(marked[event.event_date] ?? []), event.name];
  }
  return marked;
}

export function useTimelineMarkedDates(analysisId: string, excludeEventId?: string): MarkedDates {
  const queryClient = useQueryClient();
  const events = queryClient.getQueryData<EventResponse[]>(["timeline", analysisId]);
  return buildMarkedDates(events, excludeEventId);
}
