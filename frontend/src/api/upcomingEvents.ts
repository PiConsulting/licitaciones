import apiClient from "./client";
import type { UpcomingEvent } from "../types/upcomingEvents";

export async function getUpcomingEvents(): Promise<UpcomingEvent[]> {
  const response = await apiClient.get<UpcomingEvent[]>("/analyses/upcoming-events");
  return response.data;
}
