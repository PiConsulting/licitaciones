import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";

import { cancelAnalysis } from "../../api/analyses";

interface CancelButtonProps {
  analysisId: string;
  disabled?: boolean;
  label?: string;
}

export function CancelButton({ analysisId, disabled = false, label = "Cancelar análisis" }: CancelButtonProps) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => cancelAnalysis(analysisId),
    onSuccess: (response) => {
      // Escribe la respuesta directo: invalidar dispararía un refetch que puede pisarse con el polling en curso.
      queryClient.setQueryData(["analysis", analysisId, "status"], response);
    },
  });

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={disabled || mutation.isPending}
      className="inline-flex h-9 flex-shrink-0 items-center gap-2 whitespace-nowrap rounded-full border-[1.5px] border-[rgba(220,38,38,.4)] bg-white px-4 text-[13px] font-semibold text-[#DC2626] hover:bg-[#FEE2E2] disabled:cursor-not-allowed disabled:opacity-50"
    >
      <X className="h-3.5 w-3.5" strokeWidth={2.5} />
      {mutation.isPending ? "Cancelando..." : label}
    </button>
  );
}
