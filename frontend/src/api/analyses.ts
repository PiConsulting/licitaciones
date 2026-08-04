import apiClient from "./client";
import type {
  AnalysisCreateResponse,
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
