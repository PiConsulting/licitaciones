import { useQuery } from "@tanstack/react-query";

import { fetchAnalyses } from "../../../api/analyses";
import type { AnalysisListFilters, AnalysisListItem } from "../../../types/analysis";

const POLLING_INTERVAL_MS = 3000;

function hasRunningItems(items: AnalysisListItem[]): boolean {
  return items.some((item) => item.status === "queued" || item.status === "analyzing");
}

export function useAnalysesQuery(filters: AnalysisListFilters) {
  return useQuery({
    queryKey: ["analyses", filters],
    queryFn: () => fetchAnalyses(filters),
    staleTime: 30000,
    refetchInterval: (queryContext) => {
      const items = queryContext.state.data?.items ?? [];
      return hasRunningItems(items) ? POLLING_INTERVAL_MS : false;
    },
    refetchIntervalInBackground: true,
  });
}
