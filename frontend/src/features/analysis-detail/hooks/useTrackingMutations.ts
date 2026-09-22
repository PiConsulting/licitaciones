import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  completeTracking,
  createTrackingComment,
  deleteTrackingComment,
  startTracking,
  updateTrackingComment,
  updateTrackingCategoryStatus,
  updateTrackingItemStatus,
} from "../../../api/tracking";
import type {
  AnalysisTracking,
  TrackingCategoryStatus,
  TrackingComment,
  TrackingItemStatus,
} from "../../../types/tracking";
import type { AnalysisDetail } from "../types";

function updateAnalysisTrackingCache(
  queryClient: ReturnType<typeof useQueryClient>,
  analysisId: string,
  tracking: AnalysisTracking,
) {
  queryClient.setQueryData<AnalysisDetail | undefined>(["analysis", analysisId, "detail"], (current) => {
    if (!current) {
      return current;
    }
    return {
      ...current,
      tracking,
    };
  });
}

export function trackingCommentsQueryKey(analysisId: string, categoryKey: string) {
  return ["tracking-comments", analysisId, categoryKey] as const;
}

export function useStartTracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId }: { analysisId: string }) => startTracking(analysisId),
    onSuccess: (tracking, variables) => {
      updateAnalysisTrackingCache(queryClient, variables.analysisId, tracking);
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}

export function useCompleteTracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId }: { analysisId: string }) => completeTracking(analysisId),
    onSuccess: (tracking, variables) => {
      updateAnalysisTrackingCache(queryClient, variables.analysisId, tracking);
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}

export function useUpdateTrackingCategoryStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId, categoryKey, status }: { analysisId: string; categoryKey: string; status: TrackingCategoryStatus }) =>
      updateTrackingCategoryStatus(analysisId, categoryKey, status),
    onSuccess: (tracking, variables) => {
      updateAnalysisTrackingCache(queryClient, variables.analysisId, tracking);
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}

export function useUpdateTrackingItemStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysisId,
      categoryKey,
      trackingItemId,
      status,
    }: {
      analysisId: string;
      categoryKey: string;
      trackingItemId: string;
      status: TrackingItemStatus;
    }) => updateTrackingItemStatus(analysisId, categoryKey, trackingItemId, status),

    onMutate: async (variables) => {
      // Cancelar queries en vuelo para evitar race conditions
      await queryClient.cancelQueries({ 
        queryKey: ["analysis", variables.analysisId, "detail"] 
      });

      // Guardar snapshot del estado anterior para rollback
      const previousData = queryClient.getQueryData<AnalysisDetail>([
        "analysis",
        variables.analysisId,
        "detail",
      ]);

      queryClient.setQueryData<AnalysisDetail>(
        ["analysis", variables.analysisId, "detail"],
        (current) => {
          if (!current?.tracking) return current;

          return {
            ...current,
            tracking: {
              ...current.tracking,
              categories: current.tracking.categories.map((cat) => {
                if (cat.category_key !== variables.categoryKey) return cat;

                return {
                  ...cat,
                  items: cat.items.map((item) => {
                    if (item.tracking_item_id !== variables.trackingItemId) return item;

                    return {
                      ...item,
                      status: variables.status,
                      updated_at: new Date().toISOString(),
                    };
                  }),
                };
              }),
            },
          };
        },
      );

      return { previousData };
    },

    onError: (error, variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(
          ["analysis", variables.analysisId, "detail"],
          context.previousData,
        );
      }
    },

    // Delay antes de invalidar para permitir que múltiples mutations completen sin pisarse (React Query las agrupa en batch).
    onSuccess: (tracking, variables) => {
      setTimeout(() => {
        void queryClient.invalidateQueries({ 
          queryKey: ["analysis", variables.analysisId, "detail"] 
        });
      }, 100);
    },
  });
}

export function useCreateTrackingComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysisId,
      categoryKey,
      content,
    }: {
      analysisId: string;
      categoryKey: string;
      content: string;
    }) =>
      createTrackingComment(analysisId, categoryKey, {
        content,
      }),
    onSuccess: (comment, variables) => {
      queryClient.setQueryData<TrackingComment[]>(
        trackingCommentsQueryKey(variables.analysisId, variables.categoryKey),
        (current = []) => [...current, comment],
      );
      void queryClient.invalidateQueries({ queryKey: trackingCommentsQueryKey(variables.analysisId, variables.categoryKey) });
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}

export function useUpdateTrackingComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysisId,
      categoryKey,
      commentId,
      content,
    }: {
      analysisId: string;
      categoryKey: string;
      commentId: string;
      content: string;
    }) => updateTrackingComment(analysisId, categoryKey, commentId, content),
    onSuccess: (comment, variables) => {
      queryClient.setQueryData<TrackingComment[]>(
        trackingCommentsQueryKey(variables.analysisId, variables.categoryKey),
        (current = []) => current.map((item) => (item.id === comment.id ? comment : item)),
      );
      void queryClient.invalidateQueries({ queryKey: trackingCommentsQueryKey(variables.analysisId, variables.categoryKey) });
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}

export function useDeleteTrackingComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysisId,
      categoryKey,
      commentId,
    }: {
      analysisId: string;
      categoryKey: string;
      commentId: string;
    }) => deleteTrackingComment(analysisId, categoryKey, commentId),
    onSuccess: (_data, variables) => {
      queryClient.setQueryData<TrackingComment[]>(
        trackingCommentsQueryKey(variables.analysisId, variables.categoryKey),
        (current = []) => current.filter((item) => item.id !== variables.commentId),
      );
      void queryClient.invalidateQueries({ queryKey: trackingCommentsQueryKey(variables.analysisId, variables.categoryKey) });
      void queryClient.invalidateQueries({ queryKey: ["analysis", variables.analysisId, "detail"] });
    },
  });
}
