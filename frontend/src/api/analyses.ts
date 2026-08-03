import apiClient from "./client";
import type { AnalysisCreateResponse } from "../types/analysis";

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
