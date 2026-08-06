import { useQuery } from "@tanstack/react-query";

import { documentsApi } from "../../../services/api/documentsApi";

export function useSASUrl(documentId: string) {
  return useQuery({
    queryKey: ["sas-url", documentId],
    queryFn: () => documentsApi.getSASUrl(documentId),
    enabled: documentId.length > 0,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: 2,
  });
}
