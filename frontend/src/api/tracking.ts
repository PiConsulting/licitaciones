import apiClient from "./client";
import type {
  AnalysisTracking,
  TrackingCategoryStatus,
  TrackingComment,
  TrackingCommentScope,
  TrackingItemStatus,
} from "../types/tracking";

interface StartTrackingResponse {
  tracking: AnalysisTracking;
}

export async function startTracking(analysisId: string): Promise<AnalysisTracking> {
  const response = await apiClient.post<StartTrackingResponse>(`/analyses/${analysisId}/tracking/start`);
  return response.data.tracking;
}

export async function getTracking(analysisId: string): Promise<AnalysisTracking | null> {
  const response = await apiClient.get<AnalysisTracking | null>(`/analyses/${analysisId}/tracking`);
  return response.data;
}

export async function completeTracking(analysisId: string): Promise<AnalysisTracking> {
  const response = await apiClient.post<AnalysisTracking>(`/analyses/${analysisId}/tracking/complete`);
  return response.data;
}

export async function updateTrackingCategoryStatus(
  analysisId: string,
  categoryKey: string,
  status: TrackingCategoryStatus,
): Promise<AnalysisTracking> {
  const response = await apiClient.patch<AnalysisTracking>(
    `/analyses/${analysisId}/tracking/categories/${categoryKey}/status`,
    { status },
  );
  return response.data;
}

export async function updateTrackingItemStatus(
  analysisId: string,
  categoryKey: string,
  trackingItemId: string,
  status: TrackingItemStatus,
): Promise<AnalysisTracking> {
  const response = await apiClient.patch<AnalysisTracking>(
    `/analyses/${analysisId}/tracking/categories/${categoryKey}/items/${trackingItemId}`,
    { status },
  );
  return response.data;
}

export async function listTrackingComments(
  analysisId: string,
  categoryKey: string,
  options: { scope?: TrackingCommentScope; trackingItemId?: string } = {},
): Promise<TrackingComment[]> {
  const params: Record<string, string> = {};
  if (options.scope) {
    params.scope = options.scope;
  }
  if (options.trackingItemId) {
    params.tracking_item_id = options.trackingItemId;
  }
  const response = await apiClient.get<TrackingComment[]>(
    `/analyses/${analysisId}/tracking/categories/${categoryKey}/comments`,
    { params },
  );
  return response.data;
}

export async function createTrackingComment(
  analysisId: string,
  categoryKey: string,
  payload: { content: string },
): Promise<TrackingComment> {
  const response = await apiClient.post<TrackingComment>(
    `/analyses/${analysisId}/tracking/categories/${categoryKey}/comments`,
    {
      scope: "category",
      content: payload.content,
    },
  );
  return response.data;
}

export async function updateTrackingComment(
  analysisId: string,
  categoryKey: string,
  commentId: string,
  content: string,
): Promise<TrackingComment> {
  const response = await apiClient.patch<TrackingComment>(
    `/analyses/${analysisId}/tracking/categories/${categoryKey}/comments/${commentId}`,
    { content },
  );
  return response.data;
}

export async function deleteTrackingComment(
  analysisId: string,
  categoryKey: string,
  commentId: string,
): Promise<void> {
  await apiClient.delete(`/analyses/${analysisId}/tracking/categories/${categoryKey}/comments/${commentId}`);
}
