import { useNavigate } from "react-router-dom";

import { AnalysisTable } from "../features/analysis/components/AnalysisTable";
import { DateRangeFilter } from "../features/analysis/components/DateRangeFilter";
import { EmptyState } from "../features/analysis/components/EmptyState";
import { SearchInput } from "../features/analysis/components/SearchInput";
import { StatusFilter } from "../features/analysis/components/StatusFilter";
import { useAnalysisFilters } from "../features/analysis/hooks/useAnalysisFilters";
import { useAnalysesQuery } from "../features/analysis/hooks/useAnalysesQuery";

export default function Dashboard() {
  const navigate = useNavigate();
  const {
    filters,
    searchInput,
    setSearchInput,
    status,
    setStatus,
    datePreset,
    setDatePreset,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    page,
    setPage,
    sortBy,
    sortOrder,
    setSort,
  } = useAnalysisFilters();
  const analysesQuery = useAnalysesQuery(filters);

  const items = analysesQuery.data?.items ?? [];
  const total = analysesQuery.data?.total ?? 0;
  const currentPage = analysesQuery.data?.page ?? page;
  const perPage = analysesQuery.data?.per_page ?? 10;
  const totalPages = analysesQuery.data?.total_pages ?? 1;
  const rangeStart = total === 0 ? 0 : (currentPage - 1) * perPage + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(currentPage * perPage, total);

  const handleRowClick = (analysisId: string) => {
    navigate(`/analysis/${analysisId}`);
  };

  const handlePrevious = () => {
    if (currentPage <= 1) {
      return;
    }
    setPage(currentPage - 1);
  };

  const handleNext = () => {
    if (currentPage >= totalPages) {
      return;
    }
    setPage(currentPage + 1);
  };

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900">Historial de análisis</h1>
        <p className="mt-1 text-sm text-gray-600">Buscá, filtrá y seguí el estado de los análisis del equipo.</p>
      </header>

      <div className="flex flex-wrap gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <SearchInput value={searchInput} onChange={setSearchInput} />
        <StatusFilter value={status} onChange={setStatus} />
        <DateRangeFilter
          preset={datePreset}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onPresetChange={setDatePreset}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
        />
      </div>

      {analysesQuery.isLoading ? <p className="text-sm text-gray-600">Cargando historial...</p> : null}
      {analysesQuery.isError ? <p className="text-sm text-error">No se pudo cargar el historial.</p> : null}

      {!analysesQuery.isLoading && !analysesQuery.isError && total === 0 ? (
        <EmptyState />
      ) : (
        <>
          <AnalysisTable items={items} sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} onRowClick={handleRowClick} />

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-sm text-gray-700">Mostrando {rangeStart}-{rangeEnd} de {total}</p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded border border-gray-200 px-3 py-2 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={handlePrevious}
                disabled={currentPage <= 1}
              >
                Anterior
              </button>
              <span className="text-sm text-gray-600">
                Página {currentPage} de {Math.max(1, totalPages)}
              </span>
              <button
                type="button"
                className="rounded border border-gray-200 px-3 py-2 text-sm text-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={handleNext}
                disabled={currentPage >= totalPages}
              >
                Siguiente
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
