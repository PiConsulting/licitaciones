import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "../../../components/ToastContainer";
import { businessStateQueryKey, useUpdateBusinessStatus } from "./useBusinessState";

interface UseBusinessDecisionActionsArgs {
  analysisId: string;
  canStartCategories: boolean;
  onApproveCategories?: () => Promise<void> | void;
  onRejectCategories?: () => Promise<void> | void;
}

/**
 * Logica de aprobar/rechazar la decision de "pendiente_decision", compartida entre
 * el panel de Preview y el de Estado (bug real 2026-09-29: cada tab tenia su propia
 * copia -- distinto texto, y una podia quedar desincronizada de la otra). Si
 * `canStartCategories` esta activo, delega en el flujo de categorias (fase 2);
 * si no, actualiza `business_status` directamente.
 */
export function useBusinessDecisionActions({
  analysisId,
  canStartCategories,
  onApproveCategories,
  onRejectCategories,
}: UseBusinessDecisionActionsArgs) {
  const { addToast } = useToast();
  const queryClient = useQueryClient();
  const updateStatus = useUpdateBusinessStatus();

  const refreshState = () => queryClient.invalidateQueries({ queryKey: businessStateQueryKey(analysisId) });

  const handleApprove = async () => {
    if (canStartCategories && onApproveCategories) {
      await onApproveCategories();
      await refreshState();
      return;
    }
    try {
      await updateStatus.mutateAsync({ analysisId, payload: { business_status: "en_revision" } });
      addToast("success", "Licitacion aprobada: paso a En revision.");
    } catch {
      addToast("error", "No se pudo aprobar la licitacion.");
    }
  };

  const handleReject = async (note: string) => {
    try {
      await updateStatus.mutateAsync({
        analysisId,
        payload: { business_status: "no_aprobada", note: note || undefined },
      });
    } catch {
      addToast("error", "No se pudo marcar la licitacion como no aprobada.");
      return;
    }
    if (canStartCategories && onRejectCategories) {
      await onRejectCategories();
      await refreshState();
      return;
    }
    addToast("success", "Licitacion marcada como No aprobada.");
  };

  return { handleApprove, handleReject, isPending: updateStatus.isPending };
}
