import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";

import { cancelAnalysis } from "../../api/analyses";

interface CancelButtonProps {
  analysisId: string;
  disabled?: boolean;
}

export function CancelButton({ analysisId, disabled = false }: CancelButtonProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => cancelAnalysis(analysisId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "status"] });
    },
  });

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={disabled || mutation.isPending}
      className="inline-flex items-center gap-2 rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <X className="h-4 w-4" />
      {mutation.isPending ? "Cancelando..." : "Cancelar analisis"}
    </button>
  );
}
