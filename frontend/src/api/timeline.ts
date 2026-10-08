import { EventResponse, DeadlineResponse } from "../types/timeline";
import apiClient from "./client";

export async function getTimelineEvents(
  analysisId: string,
  options?: { includeHidden?: boolean }
): Promise<EventResponse[]> {
  const { data } = await apiClient.get<EventResponse[]>(`/analyses/${analysisId}/timeline/events`, {
    params: options?.includeHidden ? { include_hidden: true } : undefined,
  });
  return data;
}

export async function getTimelineDeadlines(analysisId: string): Promise<DeadlineResponse[]> {
  const { data } = await apiClient.get<DeadlineResponse[]>(`/analyses/${analysisId}/timeline/deadlines`);
  return data;
}

export async function createEvent(
  analysisId: string,
  eventData: {
    name: string;
    event_date: string | null;
    date_source: "user_input" | "pending";
    status: "confirmed";
    source_fragment?: string;
  }
): Promise<EventResponse> {
  const { data } = await apiClient.post<EventResponse>(
    `/analyses/${analysisId}/timeline/events`,
    eventData
  );
  return data;
}

export async function updateEvent(
  analysisId: string,
  eventId: string,
  updates: {
    event_date?: string | null;
    date_source?: "user_input" | "pending" | "detected" | "calculated";
    name?: string;
    status?: "pending" | "confirmed";
    source_fragment?: string;
  }
): Promise<EventResponse> {
  const { data } = await apiClient.patch<EventResponse>(
    `/analyses/${analysisId}/timeline/events/${eventId}`,
    updates
  );
  return data;
}

export async function recalculateDependentDates(
  analysisId: string,
  eventId: string
): Promise<{ events_updated: number; errors: string[] }> {
  const { data } = await apiClient.post<{ events_updated: number; errors: string[] }>(
    `/analyses/${analysisId}/timeline/events/${eventId}/recalculate`
  );
  return data;
}

export async function deleteEvent(analysisId: string, eventId: string): Promise<void> {
  await apiClient.delete(`/analyses/${analysisId}/timeline/events/${eventId}`);
}

// Oculta un evento sin borrarlo (sigue participando del cálculo de fechas, solo deja de contar en estadísticas/"fechas por cargar").
export async function setEventHidden(
  analysisId: string,
  eventId: string,
  hidden: boolean
): Promise<EventResponse> {
  const { data } = await apiClient.patch<EventResponse>(
    `/analyses/${analysisId}/timeline/events/${eventId}/hide`,
    { hidden }
  );
  return data;
}
