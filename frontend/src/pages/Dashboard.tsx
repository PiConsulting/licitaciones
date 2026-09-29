import { isAxiosError } from "axios";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { AnalysisDeleteConfirmModal } from "../components/analysis/AnalysisDeleteConfirmModal";
import { DuplicateWarningModal } from "../components/analysis/DuplicateWarningModal";
import { useToast } from "../components/ToastContainer";
import { AnalysisTable } from "../features/analysis/components/AnalysisTable";
import { DateRangeFilter } from "../features/analysis/components/DateRangeFilter";
import { EmptyState } from "../features/analysis/components/EmptyState";
import { SearchInput } from "../features/analysis/components/SearchInput";
import { useAnalysisBusinessUnitsQuery } from "../features/analysis/hooks/useAnalysisBusinessUnitsQuery";
import { useAnalysisFilters } from "../features/analysis/hooks/useAnalysisFilters";
import { useAnalysesQuery } from "../features/analysis/hooks/useAnalysesQuery";
import { ExpiringAlertsSection } from "../features/home/components/ExpiringAlertsSection";
import { KpiCard } from "../features/home/components/KpiCard";
import { useExpiringAlerts } from "../features/home/hooks/useExpiringAlerts";
import { useBusinessStatusCounts } from "../features/home/hooks/useBusinessStatusCounts";
import { useDeleteAnalysis } from "../hooks/useDeleteAnalysis";
import { useStartAnalysis } from "../hooks/useStartAnalysis";
import type {
  AnalysisListItem,
  AnalysisListResponse,
  AnalysisStatusResponse,
  DuplicateDecision,
  DuplicateWarning,
} from "../types/analysis";

interface DeleteModalState {
  id: string;
  label: string;
  isErrorAnalysis: boolean;
}

interface DuplicateModalState {
  analysisId: string;
  mode: "start" | "retry";
  duplicates: DuplicateWarning[];
}

type BusinessStatusKey = "no_aprobada" | "en_revision" | "presentada" | "ganada" | "perdida";

const BUSINESS_STATUS_MAP: Record<string, BusinessStatusKey> = {
  no_aprobada: "no_aprobada",
  "no aprobada": "no_aprobada",
  no_aprobadas: "no_aprobada",
  en_revision: "en_revision",
  "en revision": "en_revision",
  presentada: "presentada",
  presentadas: "presentada",
  ganada: "ganada",
  ganadas: "ganada",
  perdida: "perdida",
  perdidas: "perdida",
};

const UNIT_DOT_COLORS: Record<string, string> = {
  CEDI: "bg-[#0099DB]",
  PI: "bg-[#003C6B]",
  Wemox: "bg-[#2F4EF8]",
  Vulps: "bg-[#A966FF]",
  Korex: "bg-[#7FF3DE]",
};

function getUnitDotClass(unitName: string): string {
  return UNIT_DOT_COLORS[unitName] ?? "bg-cedi-celeste";
}

function normalizeBusinessStatus(value?: string | null): BusinessStatusKey | null {
  if (!value) {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  return BUSINESS_STATUS_MAP[normalized] ?? null;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const startMutation = useStartAnalysis();
  const deleteMutation = useDeleteAnalysis();
  const businessStatusCounts = useBusinessStatusCounts();
  const expiringAlerts = useExpiringAlerts();
  const [activeBusinessStatus, setActiveBusinessStatus] = useState<BusinessStatusKey | null>(null);
  const [retryingAnalysisId, setRetryingAnalysisId] = useState<string | null>(null);
  const [deleteModalState, setDeleteModalState] = useState<DeleteModalState | null>(null);
  const [duplicateModalState, setDuplicateModalState] = useState<DuplicateModalState | null>(null);
  const {
    filters,
    searchInput,
    setSearchInput,
    status,
    datePreset,
    setDatePreset,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    businessUnit,
    setBusinessUnit,
    clearFilters,
    page,
    setPage,
    sortBy,
    sortOrder,
    setSort,
  } = useAnalysisFilters();
  const analysesQuery = useAnalysesQuery(filters);
  const businessUnitsQuery = useAnalysisBusinessUnitsQuery({
    search: filters.search,
    status,
    date_from: filters.date_from,
    date_to: filters.date_to,
  });

  const items = analysesQuery.data?.items ?? [];
  const total = analysesQuery.data?.total ?? 0;
  const derivedCounts = items.reduce(
    (acc, item) => {
      const normalized = normalizeBusinessStatus(item.business_status);
      if (!normalized) {
        return acc;
      }
      acc[normalized] += 1;
      return acc;
    },
    {
      no_aprobada: 0,
      en_revision: 0,
      presentada: 0,
      ganada: 0,
      perdida: 0,
    } as Record<BusinessStatusKey, number>,
  );

  const hookCountsTotal =
    businessStatusCounts.noAprobadas +
    businessStatusCounts.enRevision +
    businessStatusCounts.presentadas +
    businessStatusCounts.ganadas +
    businessStatusCounts.perdidas;

  const effectiveCounts = hookCountsTotal > 0
    ? {
        no_aprobada: businessStatusCounts.noAprobadas,
        en_revision: businessStatusCounts.enRevision,
        presentada: businessStatusCounts.presentadas,
        ganada: businessStatusCounts.ganadas,
        perdida: businessStatusCounts.perdidas,
      }
    : derivedCounts;

  const tableItems = activeBusinessStatus
    ? items.filter((item) => normalizeBusinessStatus(item.business_status) === activeBusinessStatus)
    : items;

  const tableTotal = tableItems.length;
  const currentPage = analysesQuery.data?.page ?? page;
  const totalPages = analysesQuery.data?.total_pages ?? 1;
  const rangeStart = tableTotal === 0 ? 0 : 1;
  const rangeEnd = tableTotal;
  const businessUnits = businessUnitsQuery.data ?? [];
  const hasFiltersApplied =
    Boolean(filters.search) ||
    Boolean(filters.status) ||
    Boolean(filters.business_unit) ||
    Boolean(filters.date_from) ||
    Boolean(filters.date_to) ||
    Boolean(activeBusinessStatus);

  const kpis = [
    {
      label: "TOTAL",
      value: total,
      dotClass: activeBusinessStatus ? "bg-cedi-navy" : "bg-cedi-mint",
      testId: "kpi-total",
      active: activeBusinessStatus === null,
      onClick: () => {
        setActiveBusinessStatus(null);
        setPage(1);
      },
    },
    {
      key: "no_aprobada",
      label: "NO APROBADAS",
      value: effectiveCounts.no_aprobada,
      dotClass: "bg-cedi-navy-30",
      testId: "kpi-no-aprobadas",
      active: activeBusinessStatus === "no_aprobada",
    },
    {
      key: "en_revision",
      label: "EN REVISION",
      value: effectiveCounts.en_revision,
      dotClass: "bg-cedi-violet",
      testId: "kpi-en-revision",
      active: activeBusinessStatus === "en_revision",
    },
    {
      key: "presentada",
      label: "PRESENTADAS",
      value: effectiveCounts.presentada,
      dotClass: "bg-cedi-electric",
      testId: "kpi-presentadas",
      active: activeBusinessStatus === "presentada",
    },
    {
      key: "ganada",
      label: "GANADAS",
      value: effectiveCounts.ganada,
      dotClass: "bg-cedi-mint",
      testId: "kpi-ganadas",
      active: activeBusinessStatus === "ganada",
    },
    {
      key: "perdida",
      label: "PERDIDAS",
      value: effectiveCounts.perdida,
      dotClass: "bg-cedi-navy-30",
      testId: "kpi-perdidas",
      active: activeBusinessStatus === "perdida",
    },
  ];

  const progressPercent = (value: number): number => {
    if (total <= 0) {
      return 0;
    }
    return Math.round((value / total) * 100);
  };

  const handleRowClick = (analysisId: string) => {
    navigate(`/analysis/${analysisId}`);
  };

  const handleStartOrRetryAnalysis = async (
    analysisId: string,
    mode: "start" | "retry",
    decisions: DuplicateDecision[] = [],
  ) => {
    setRetryingAnalysisId(analysisId);
    try {
      const response = await startMutation.mutateAsync({
        analysisId,
        payload: { decisions },
      });

      if (response.requires_resolution) {
        setDuplicateModalState({ analysisId, mode, duplicates: response.duplicates });
        return;
      }

      setDuplicateModalState(null);

      const queuedStatus: AnalysisStatusResponse = {
        id: analysisId,
        status: "queued",
        current_stage: "queued",
        progress_percentage: 0,
        stage_progress: "En cola",
      };
      queryClient.setQueryData(["analysis", analysisId, "status"], queuedStatus);
      queryClient.setQueriesData<AnalysisListResponse>({ queryKey: ["analyses"] }, (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          items: current.items.map((item) =>
            item.id === analysisId
              ? {
                  ...item,
                  status: "queued",
                  current_stage: "queued",
                  progress_percentage: 0,
                  stage_progress: "En cola",
                }
              : item,
          ),
        };
      });

      if (response.redirect_analysis_id) {
        addToast("success", "Redirigiendo al análisis existente");
        navigate(`/analysis/${response.redirect_analysis_id}`);
      } else {
        addToast(
          "success",
          mode === "start"
            ? "Análisis encolado. El procesamiento comenzó en segundo plano."
            : "Reintento encolado. El análisis continuará en segundo plano.",
        );
        if (mode === "retry") {
          navigate(`/analysis/${analysisId}`);
        }
      }

      await queryClient.invalidateQueries({ queryKey: ["analyses"] });
      await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "status"] });
    } catch (requestError) {
      if (isAxiosError(requestError)) {
        const message = requestError.response?.data?.error?.message;
        if (typeof message === "string") {
          addToast("error", message);
          return;
        }
      }
      addToast("error", mode === "start" ? "No se pudo iniciar el análisis" : "No se pudo reintentar el análisis");
    } finally {
      setRetryingAnalysisId(null);
    }
  };

  const handleStartAnalysis = async (analysisId: string) => {
    await handleStartOrRetryAnalysis(analysisId, "start");
  };

  const handleRetryAnalysis = async (analysisId: string) => {
    await handleStartOrRetryAnalysis(analysisId, "retry");
  };

  const handleOpenDelete = (item: AnalysisListItem) => {
    setDeleteModalState({
      id: item.id,
      label: item.analysis_name ?? item.primary_document_name ?? `Análisis ${item.id.slice(0, 8)}`,
      isErrorAnalysis: item.status.toLowerCase() === "error",
    });
  };

  const handleConfirmDelete = async () => {
    if (!deleteModalState) {
      return;
    }

    try {
      await deleteMutation.mutateAsync(deleteModalState.id);
      setDeleteModalState(null);
      addToast(
        "success",
        deleteModalState.isErrorAnalysis
          ? "El análisis con error se eliminó definitivamente."
          : "El análisis se eliminó del historial.",
      );
      await queryClient.invalidateQueries({ queryKey: ["analyses"] });
    } catch (requestError) {
      if (isAxiosError(requestError)) {
        const message = requestError.response?.data?.error?.message;
        if (typeof message === "string") {
          addToast("error", message);
          return;
        }
      }
      addToast("error", "No se pudo eliminar el análisis");
    }
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
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[28px] font-bold leading-[1.15] tracking-[-0.015em] text-cedi-navy">Licitaciones</h1>
          <p className="mt-1.5 text-sm text-cedi-navy-68">Estado del pipeline por unidad de negocio.</p>
        </div>
        <div className="max-w-full">
          <DateRangeFilter
            preset={datePreset}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onPresetChange={setDatePreset}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
          />
        </div>
      </header>

      <section
        aria-label="Indicadores"
        className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]"
      >
        {kpis.map((kpi) => (
          <KpiCard
            key={kpi.label}
            label={kpi.label}
            value={kpi.value}
            dotColorClass={kpi.dotClass}
            progressPercent={progressPercent(Number(kpi.value))}
            valueTestId={kpi.testId}
            active={Boolean(kpi.active)}
            showPercent={kpi.label !== "TOTAL"}
            onClick={() => {
              if ("key" in kpi) {
                const next = activeBusinessStatus === kpi.key ? null : kpi.key;
                setActiveBusinessStatus(next);
              }
              if (!("key" in kpi)) {
                kpi.onClick();
              }
              setPage(1);
            }}
          />
        ))}
      </section>

      <ExpiringAlertsSection
        alerts={expiringAlerts}
        onOpenAlert={(alert) => navigate(`/analysis/${alert.analysisId}?tab=timeline`)}
      />

      <section id="listado" className="space-y-3" aria-label="Filtros de listado">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="max-w-[340px] flex-[1_1_220px]">
            <SearchInput value={searchInput} onChange={setSearchInput} />
          </div>

          {businessUnits.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtro de unidad">
              <span className="mr-1 text-[12px] font-bold uppercase tracking-[0.14em] text-cedi-navy-55">Unidad</span>
              {businessUnits.map((unit) => {
                const isActive = businessUnit === unit.business_unit;
                return (
                  <button
                    key={unit.business_unit}
                    type="button"
                    onClick={() => setBusinessUnit(isActive ? "" : unit.business_unit)}
                    className={[
                      "inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap rounded-full border-[1.5px] px-3.5 text-[13px] font-semibold leading-none",
                      isActive
                        ? "border-cedi-navy bg-cedi-navy text-white"
                        : "border-cedi-navy-20 bg-white text-cedi-navy hover:border-cedi-navy-30",
                    ].join(" ")}
                    aria-pressed={isActive}
                  >
                    <span className={["h-2 w-2 rounded-full", getUnitDotClass(unit.business_unit)].join(" ")} aria-hidden="true" />
                    {unit.business_unit}
                    <span className={isActive ? "font-medium text-white/80" : "font-medium text-cedi-navy-55"}>{unit.count}</span>
                  </button>
                );
              })}
            </div>
          ) : null}

          <div className="flex items-center gap-3">
            <span className="text-[13px] text-cedi-navy-68">{tableTotal} de {total} licitaciones</span>
            {hasFiltersApplied ? (
              <button
                type="button"
                className="h-8 rounded-full px-3 text-[13px] font-semibold text-cedi-celeste hover:text-cedi-navy"
                onClick={() => {
                  clearFilters();
                  setActiveBusinessStatus(null);
                }}
              >
                Limpiar filtros
              </button>
            ) : null}
          </div>
        </div>

        {analysesQuery.isLoading ? <p className="text-sm text-gray-600">Cargando historial...</p> : null}
        {analysesQuery.isError ? <p className="text-sm text-error">No se pudo cargar el historial.</p> : null}

        {!analysesQuery.isLoading && !analysesQuery.isError && tableTotal === 0 ? (
          <EmptyState />
        ) : (
          <>
          <AnalysisTable
            items={tableItems}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={setSort}
            onRowClick={handleRowClick}
            onStartAnalysis={handleStartAnalysis}
            onRetryAnalysis={handleRetryAnalysis}
            onDeleteAnalysis={handleOpenDelete}
            retryingAnalysisId={retryingAnalysisId}
            deletingAnalysisId={deleteMutation.isPending ? deleteModalState?.id ?? null : null}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
            <p className="text-sm text-gray-700">Mostrando {rangeStart}-{rangeEnd} de {tableTotal}</p>
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

      {deleteModalState ? (
        <AnalysisDeleteConfirmModal
          analysisName={deleteModalState.label}
          isErrorAnalysis={deleteModalState.isErrorAnalysis}
          isSubmitting={deleteMutation.isPending}
          onCancel={() => setDeleteModalState(null)}
          onConfirm={() => {
            void handleConfirmDelete();
          }}
        />
      ) : null}

      {duplicateModalState ? (
        <DuplicateWarningModal
          duplicates={duplicateModalState.duplicates}
          isSubmitting={startMutation.isPending}
          onCancel={() => setDuplicateModalState(null)}
          onConfirm={(decisions) => {
            void handleStartOrRetryAnalysis(duplicateModalState.analysisId, duplicateModalState.mode, decisions);
          }}
        />
      ) : null}
    </section>
  );
}
