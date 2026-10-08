import { useQuery } from "@tanstack/react-query";

import { fetchAnalysisBusinessUnits } from "../../../api/analyses";
import type { AnalysisListFilters } from "../../../types/analysis";

export function useAnalysisBusinessUnitsQuery(
  filters: Pick<AnalysisListFilters, "search" | "status" | "date_from" | "date_to">,
) {
  return useQuery({
    queryKey: ["analysis-business-units", filters],
    queryFn: () => fetchAnalysisBusinessUnits(filters),
    staleTime: 30000,
  });
}
