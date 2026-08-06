import apiClient from "./client";
import type {
  AnalysisCreateResponse,
  AnalysisListFilters,
  AnalysisListResponse,
  AnalysisStartPayload,
  AnalysisStartResponse,
  AnalysisStatusResponse,
} from "../types/analysis";

interface CreateAnalysisPayload {
  files: File[];
  primaryFileIndex: number;
}

export async function createAnalysis(payload: CreateAnalysisPayload): Promise<AnalysisCreateResponse> {
  const formData = new FormData();
  formData.append("primary_file_index", String(payload.primaryFileIndex));
  payload.files.forEach((file) => {
    formData.append("files", file, file.name);
  });

  const response = await apiClient.post<AnalysisCreateResponse>("/analyses", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
}

export async function startAnalysis(
  analysisId: string,
  payload: AnalysisStartPayload = { decisions: [] },
): Promise<AnalysisStartResponse> {
  const response = await apiClient.post<AnalysisStartResponse>(`/analyses/${analysisId}/start`, payload);
  return response.data;
}

export async function getAnalysisStatus(analysisId: string): Promise<AnalysisStatusResponse> {
  const response = await apiClient.get<AnalysisStatusResponse>(`/analyses/${analysisId}/status`);
  return response.data;
}

export async function cancelAnalysis(analysisId: string): Promise<AnalysisStatusResponse> {
  const response = await apiClient.post<AnalysisStatusResponse>(`/analyses/${analysisId}/cancel`);
  return response.data;
}

export async function fetchAnalyses(filters: AnalysisListFilters = {}): Promise<AnalysisListResponse> {
  const response = await apiClient.get<AnalysisListResponse>("/analyses", {
    params: {
      search: filters.search,
      status: filters.status,
      date_from: filters.date_from,
      date_to: filters.date_to,
      page: filters.page ?? 1,
      per_page: filters.per_page ?? 10,
      sort_by: filters.sort_by ?? "created_at",
      sort_order: filters.sort_order ?? "desc",
    },
  });
  return response.data;
}
