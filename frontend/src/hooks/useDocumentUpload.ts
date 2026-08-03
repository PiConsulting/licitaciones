import { useMutation } from "@tanstack/react-query";

import { createAnalysis } from "../api/analyses";

export function useDocumentUpload() {
  return useMutation({
    mutationFn: createAnalysis,
  });
}
