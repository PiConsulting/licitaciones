import { useEffect, useMemo, useState } from "react";

import type { AnalysisListFilters, AnalysisListSortBy, AnalysisListSortOrder } from "../../../types/analysis";

export type DatePreset = "all" | "last_week" | "custom";

const SEARCH_DEBOUNCE_MS = 300;

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function useAnalysisFilters() {
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [status, setStatus] = useState("");
  const [datePreset, setDatePreset] = useState<DatePreset>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<AnalysisListSortBy>("created_at");
  const [sortOrder, setSortOrder] = useState<AnalysisListSortOrder>("desc");

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    if (datePreset === "all") {
      setDateFrom("");
      setDateTo("");
      setPage(1);
      return;
    }

    if (datePreset === "last_week") {
      const now = new Date();
      const sevenDaysAgo = new Date(now);
      sevenDaysAgo.setDate(now.getDate() - 7);
      setDateFrom(toIsoDate(sevenDaysAgo));
      setDateTo(toIsoDate(now));
      setPage(1);
    }
  }, [datePreset]);

  const filters: AnalysisListFilters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: status || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page,
      per_page: 20,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [dateFrom, dateTo, debouncedSearch, page, sortBy, sortOrder, status],
  );

  const setSort = (column: AnalysisListSortBy) => {
    setPage(1);
    if (column === sortBy) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }

    setSortBy(column);
    setSortOrder("asc");
  };

  return {
    filters,
    searchInput,
    setSearchInput,
    status,
    setStatus: (nextStatus: string) => {
      setStatus(nextStatus);
      setPage(1);
    },
    datePreset,
    setDatePreset,
    dateFrom,
    setDateFrom: (next: string) => {
      setDatePreset("custom");
      setDateFrom(next);
      setPage(1);
    },
    dateTo,
    setDateTo: (next: string) => {
      setDatePreset("custom");
      setDateTo(next);
      setPage(1);
    },
    page,
    setPage,
    sortBy,
    sortOrder,
    setSort,
  };
}
