import apiClient from "./client";
import type {
  BusinessState,
  BusinessStatusUpdatePayload,
  BusinessStatusUpdateResponse,
  PresentationPayload,
  ReceiptLink,
  ResultPayload,
} from "../types/businessStatus";

export async function getBusinessState(analysisId: string): Promise<BusinessState> {
  const response = await apiClient.get<BusinessState>(`/analyses/${analysisId}/business-status`);
  return response.data;
}

export async function updateBusinessStatus(
  analysisId: string,
  payload: BusinessStatusUpdatePayload,
): Promise<BusinessStatusUpdateResponse> {
  const response = await apiClient.patch<BusinessStatusUpdateResponse>(
    `/analyses/${analysisId}/business-status`,
    payload,
  );
  return response.data;
}

export async function savePresentation(
  analysisId: string,
  payload: PresentationPayload,
): Promise<BusinessState> {
  const response = await apiClient.put<BusinessState>(`/analyses/${analysisId}/presentation`, payload);
  return response.data;
}

export async function saveResult(analysisId: string, payload: ResultPayload): Promise<BusinessState> {
  const response = await apiClient.put<BusinessState>(`/analyses/${analysisId}/result`, payload);
  return response.data;
}

export async function uploadPresentationReceipt(analysisId: string, file: File): Promise<BusinessState> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<BusinessState>(
    `/analyses/${analysisId}/presentation/receipt`,
    formData,
  );
  return response.data;
}

export async function deletePresentationReceipt(analysisId: string): Promise<BusinessState> {
  const response = await apiClient.delete<BusinessState>(`/analyses/${analysisId}/presentation/receipt`);
  return response.data;
}

export async function getPresentationReceiptLink(analysisId: string): Promise<ReceiptLink> {
  const response = await apiClient.get<ReceiptLink>(`/analyses/${analysisId}/presentation/receipt`);
  return response.data;
}
