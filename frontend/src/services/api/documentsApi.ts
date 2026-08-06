import apiClient from "../../api/client";

export interface DocumentSASUrlResponse {
  url: string;
  expires_at: string;
  document_id: string;
  filename: string;
}

export const documentsApi = {
  async getSASUrl(documentId: string): Promise<DocumentSASUrlResponse> {
    const response = await apiClient.get<DocumentSASUrlResponse>(`/documents/${documentId}/url`);
    return response.data;
  },
};
