import { Event, Deadline } from "../types/timeline";
import apiClient from "./client";

export async function getTimelineEvents(analysisId: string): Promise<Event[]> {
  const { data } = await apiClient.get<Event[]>(`/analyses/${analysisId}/timeline/events`);
  return data;
}

export async function getTimelineDeadlines(analysisId: string): Promise<Deadline[]> {
  const { data } = await apiClient.get<Deadline[]>(`/analyses/${analysisId}/timeline/deadlines`);
  return data;
}
