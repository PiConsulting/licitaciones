export interface ApiErrorPayload {
  code?: string;
  message?: string;
}

export function extractApiError(caught: unknown): ApiErrorPayload {
  const data = (caught as { response?: { data?: { error?: ApiErrorPayload } } })?.response?.data;
  return data?.error ?? {};
}
