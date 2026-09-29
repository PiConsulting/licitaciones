import apiClient from "./client";
import type {
  AnalysisBusinessUnitItem,
  AnalysisCreateResponse,
  AnalysisListFilters,
  AnalysisListResponse,
  PatchAnalysisRequest,
  PatchAnalysisResponse,
  StartAnalysisRequest,
  AnalysisStartResponse,
  AnalysisStatusResponse,
  CategoriesDecision,
  CategoriesDecisionResponse,
  ReanalyzeRequest,
  ReanalyzeResponse,
} from "../types/analysis";

interface CreateAnalysisPayload {
  files: File[];
  primaryFileIndex: number;
  analysisName?: string;
  businessUnit?: string;
}

export async function createAnalysis(payload: CreateAnalysisPayload): Promise<AnalysisCreateResponse> {
  const formData = new FormData();
  formData.append("primary_file_index", String(payload.primaryFileIndex));
  if (payload.analysisName?.trim()) {
    formData.append("analysis_name", payload.analysisName.trim());
  }
  if (payload.businessUnit?.trim()) {
    formData.append("business_unit", payload.businessUnit.trim());
  }
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
  payload: StartAnalysisRequest = { decisions: [] },
): Promise<AnalysisStartResponse> {
  const response = await apiClient.post<AnalysisStartResponse>(`/analyses/${analysisId}/start`, payload);
  return response.data;
}

export async function decideAnalysisCategories(
  analysisId: string,
  decision: CategoriesDecision,
): Promise<CategoriesDecisionResponse> {
  const response = await apiClient.post<CategoriesDecisionResponse>(
    `/analyses/${analysisId}/categories-decision`,
    { decision },
  );
  return response.data;
}

export async function reanalyzeAnalysis(
  analysisId: string,
  payload: ReanalyzeRequest,
): Promise<ReanalyzeResponse> {
  const response = await apiClient.post<ReanalyzeResponse>(`/analyses/${analysisId}/reanalyze`, payload);
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

export async function deleteAnalysis(analysisId: string): Promise<void> {
  await apiClient.delete(`/analyses/${analysisId}`);
}

export async function fetchAnalyses(filters: AnalysisListFilters = {}): Promise<AnalysisListResponse> {
  const response = await apiClient.get<AnalysisListResponse>("/analyses", {
    params: {
      search: filters.search,
      status: filters.status,
      business_unit: filters.business_unit,
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

export async function fetchAnalysisBusinessUnits(
  filters: Pick<AnalysisListFilters, "search" | "status" | "date_from" | "date_to"> = {},
): Promise<AnalysisBusinessUnitItem[]> {
  const response = await apiClient.get<AnalysisBusinessUnitItem[]>("/analyses/units", {
    params: {
      search: filters.search,
      status: filters.status,
      date_from: filters.date_from,
      date_to: filters.date_to,
    },
  });
  return response.data;
}

export async function patchAnalysis(
  analysisId: string,
  payload: PatchAnalysisRequest,
): Promise<PatchAnalysisResponse> {
  const response = await apiClient.patch<PatchAnalysisResponse>(`/analyses/${analysisId}`, payload);
  return response.data;
}
