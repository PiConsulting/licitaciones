import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deletePresentationReceipt,
  getBusinessState,
  saveResult,
  savePresentation,
  updateBusinessStatus,
  uploadPresentationReceipt,
} from "../../../api/businessStatus";
import type {
  BusinessState,
  BusinessStatus,
  BusinessStatusUpdatePayload,
  PresentationPayload,
  ResultPayload,
} from "../../../types/businessStatus";
import type { AnalysisDetail } from "../types";

type QueryClientInstance = ReturnType<typeof useQueryClient>;

export function businessStateQueryKey(analysisId: string) {
  return ["analysis", analysisId, "business-state"] as const;
}

export function syncDetailBusinessStatus(
  queryClient: QueryClientInstance,
  analysisId: string,
  businessStatus: BusinessStatus,
) {
  queryClient.setQueryData<AnalysisDetail | undefined>(["analysis", analysisId, "detail"], (current) => {
    if (!current) {
      return current;
    }
    return { ...current, business_status: businessStatus };
  });
}

function refreshAnalysisLists(queryClient: QueryClientInstance) {
  void queryClient.invalidateQueries({ queryKey: ["analyses"] });
}

export function useBusinessState(analysisId: string) {
  return useQuery({
    queryKey: businessStateQueryKey(analysisId),
    queryFn: () => getBusinessState(analysisId),
    enabled: analysisId.length > 0,
    staleTime: 1000 * 30,
  });
}

export function useUpdateBusinessStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId, payload }: { analysisId: string; payload: BusinessStatusUpdatePayload }) =>
      updateBusinessStatus(analysisId, payload),
    onSuccess: (response, variables) => {
      syncDetailBusinessStatus(queryClient, variables.analysisId, response.business_status);
      void queryClient.invalidateQueries({ queryKey: businessStateQueryKey(variables.analysisId) });
      refreshAnalysisLists(queryClient);
    },
  });
}

export interface ReceiptChange {
  file: File | null;
  remove: boolean;
}

export function useSavePresentation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      analysisId,
      payload,
      receipt,
    }: {
      analysisId: string;
      payload: PresentationPayload;
      receipt?: ReceiptChange;
    }) => {
      let state = await savePresentation(analysisId, payload);
      if (receipt?.file) {
        state = await uploadPresentationReceipt(analysisId, receipt.file);
      } else if (receipt?.remove) {
        state = await deletePresentationReceipt(analysisId);
      }
      return state;
    },
    onSuccess: (state: BusinessState, variables) => {
      queryClient.setQueryData(businessStateQueryKey(variables.analysisId), state);
      syncDetailBusinessStatus(queryClient, variables.analysisId, state.business_status);
      refreshAnalysisLists(queryClient);
    },
    onError: (_error, variables) => {
      void queryClient.invalidateQueries({ queryKey: businessStateQueryKey(variables.analysisId) });
      refreshAnalysisLists(queryClient);
    },
  });
}

export function useSaveResult() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId, payload }: { analysisId: string; payload: ResultPayload }) =>
      saveResult(analysisId, payload),
    onSuccess: (state: BusinessState, variables) => {
      queryClient.setQueryData(businessStateQueryKey(variables.analysisId), state);
      syncDetailBusinessStatus(queryClient, variables.analysisId, state.business_status);
      refreshAnalysisLists(queryClient);
    },
  });
}
