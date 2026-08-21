import { useMutation } from "@tanstack/react-query";

import { deleteAnalysis } from "../api/analyses";

export function useDeleteAnalysis() {
  return useMutation<void, Error, string>({
    mutationFn: async (analysisId) => deleteAnalysis(analysisId),
  });
}