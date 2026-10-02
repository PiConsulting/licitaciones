import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { History } from "lucide-react";

import { AnalysisProgress } from "../../components/analysis/AnalysisProgress";
import { ReanalyzeModal } from "../../components/analysis/ReanalyzeModal";
import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { Tab } from "../../components/Tabs";
import { useToast } from "../../components/ToastContainer";
import { useAnalysisStatus } from "../../hooks/useAnalysisStatus";
import { useReanalyzeAnalysis } from "../../hooks/useReanalyzeAnalysis";
import { useCategoriesDecision } from "../../hooks/useStartAnalysisCategories";
import { getTimelineEvents } from "../../api/timeline";
import { patchAnalysis } from "../../api/analyses";
import type { AnalysisStatusResponse, CategoriesDecision, ReanalyzeRequest } from "../../types/analysis";
import { CategoryList } from "./CategoryList";
import { AnalysisDetailHeader } from "./AnalysisDetailHeader";
import { EstadoTab } from "./EstadoTab";
import { PreviewTab } from "./PreviewTab";
import { TimelineTab } from "./TimelineTab";
import { VersionHistoryTab } from "./VersionHistoryTab";
import { getAnalysisSummary } from "./utils/categoryStats";
import { useAnalysisDetail } from "./hooks/useAnalysisDetail";
import { useBusinessDecisionActions } from "./hooks/useBusinessDecisionActions";
import { businessStateQueryKey } from "./hooks/useBusinessState";
import { useStartTracking } from "./hooks/useTrackingMutations";
import type { AnalysisDetail, Citation, NarrativeSource } from "./types";
import { getPendingActionText, resolveBusinessStatus } from "./utils/businessStatus";
import { PDFViewer } from "../pdf-viewer/PDFViewer";

interface AnalysisDetailPageProps {
  analysisId: string;
}

function phase2RedirectKey(analysisId: string): string {
  return `analysis:${analysisId}:redirect_to_categories_on_analyze`;
}

const DETAIL_SETTLE_MAX_ATTEMPTS = 5;
const DETAIL_SETTLE_RETRY_DELAY_MS = 1200;

function hasPendingCategories(analysis?: AnalysisDetail): boolean {
  if (!analysis) {
    return false;
  }
  return CATEGORY_ORDER.some((categoryId) => {
    const category = analysis.current_version.extracted_data[categoryId];
    if (!category) {
      return true;
    }
    const isPhaseOnePendingEmptyCategory =
      category.extraction_status === "not_found" &&
      category.items.length === 0 &&
      category.confidence === 0 &&
      !category.is_reviewed;
    return category.extraction_status === "not_analyzed" || isPhaseOnePendingEmptyCategory;
  });
}

const DEEP_LINK_TABS = ["preview", "categories", "timeline", "versions", "estado"];

export function AnalysisDetailPage({ analysisId }: AnalysisDetailPageProps) {
  const query = useAnalysisDetail(analysisId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { addToast } = useToast();
  const categoriesDecisionMutation = useCategoriesDecision();
  const reanalyzeMutation = useReanalyzeAnalysis();
  const startTrackingMutation = useStartTracking();
  const patchAnalysisMutation = useMutation({
    mutationFn: (payload: { monto_estimado: number; moneda: string }) => patchAnalysis(analysisId, payload),
  });

  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedCitations, setSelectedCitations] = useState<Citation[]>([]);
  const [selectedSources, setSelectedSources] = useState<NarrativeSource[]>([]);
  const [showReanalyzeModal, setShowReanalyzeModal] = useState(false);
  const [showPdfViewer, setShowPdfViewer] = useState(true);
  const [statusPollingEnabled, setStatusPollingEnabled] = useState(false);
  const [redirectToCategoriesOnAnalyze, setRedirectToCategoriesOnAnalyze] = useState(
    () => sessionStorage.getItem(phase2RedirectKey(analysisId)) === "1",
  );
  const requestedTab = searchParams.get("tab");
  const initialTab = requestedTab && DEEP_LINK_TABS.includes(requestedTab) ? requestedTab : "preview";
  const [tabsDefaultTab, setTabsDefaultTab] = useState(initialTab);
  const [activeTab, setActiveTab] = useState(initialTab);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);

  useEffect(() => {
    if (redirectToCategoriesOnAnalyze) {
      sessionStorage.setItem(phase2RedirectKey(analysisId), "1");
      return;
    }
    sessionStorage.removeItem(phase2RedirectKey(analysisId));
  }, [analysisId, redirectToCategoriesOnAnalyze]);

  const statusPolling = useAnalysisStatus(analysisId, statusPollingEnabled);
  const timelineQuery = useQuery({
    queryKey: ["timeline", analysisId],
    queryFn: () => getTimelineEvents(analysisId, { includeHidden: true }),
  });

  useEffect(() => {
    if (query.data?.status === "analyzed" && redirectToCategoriesOnAnalyze) {
      setTabsDefaultTab("categories");
      setRedirectToCategoriesOnAnalyze(false);
    }
  }, [query.data?.status, redirectToCategoriesOnAnalyze]);

  useEffect(() => {
    setActiveTab(tabsDefaultTab);
  }, [tabsDefaultTab]);

  useEffect(() => {
    const status = query.data?.status;
    if ((status === "queued" || status === "processing") && !statusPollingEnabled) {
      setStatusPollingEnabled(true);
    }
  }, [query.data?.status, statusPollingEnabled]);

  useEffect(() => {
    if (!query.data) {
      return;
    }
    setSelectedVersionId((current) => current ?? query.data.current_version.id);
  }, [query.data]);

  useEffect(() => {
    const polledStatus = statusPolling.data?.status;
    if (!statusPollingEnabled || !polledStatus) {
      return;
    }

    const isTerminal = ["analyzed", "en_revision", "error", "cancelled", "validated"].includes(
      polledStatus as string,
    );
    if (!isTerminal) {
      return;
    }

    let cancelled = false;
    const shouldRedirectToCategories = polledStatus === "analyzed" && redirectToCategoriesOnAnalyze;
    setRedirectToCategoriesOnAnalyze(false);

    // Espera el refetch antes de apagar el polling para evitar el parpadeo del panel de progreso.
    // Si el backend recién marcó el análisis como "analyzed", el detalle puede tardar unos
    // instantes en reflejar las categorías recién completadas: reintenta hasta que aparezcan
    // o se agote el margen de espera, en vez de quedarse con un conteo desactualizado.
    const waitForDetailToSettle = async () => {
      let result = await query.refetch();
      if (polledStatus === "analyzed") {
        let attempts = 0;
        while (!cancelled && attempts < DETAIL_SETTLE_MAX_ATTEMPTS && hasPendingCategories(result.data)) {
          await new Promise((resolve) => setTimeout(resolve, DETAIL_SETTLE_RETRY_DELAY_MS));
          if (cancelled) {
            return;
          }
          result = await query.refetch();
          attempts += 1;
        }
      }
      if (cancelled) {
        return;
      }
      if (shouldRedirectToCategories) {
        setTabsDefaultTab("categories");
      }
      setStatusPollingEnabled(false);
    };

    void waitForDetailToSettle();

    return () => {
      cancelled = true;
    };
  }, [query, redirectToCategoriesOnAnalyze, statusPolling.data?.status, statusPollingEnabled]);

  const documentsById = useMemo(() => {
    return new Map((query.data?.documents ?? []).map((document) => [document.id, document]));
  }, [query.data?.documents]);

  const canReanalyze =
    (query.data?.status === "en_revision" ||
      query.data?.status === "analyzed" ||
      query.data?.status === "validated" ||
      query.data?.status === "error") &&
    !statusPollingEnabled;
  const canStartTracking =
    !query.data?.tracking && (query.data?.status === "analyzed" || query.data?.status === "validated");
  const hasTracking = Boolean(query.data?.tracking);

  const handleStartTracking = async () => {
    try {
      await startTrackingMutation.mutateAsync({ analysisId });
      addToast("success", "Seguimiento iniciado correctamente.");
      navigate(`/analysis/${analysisId}/checklist`);
    } catch {
      addToast("error", "No se pudo iniciar el seguimiento.");
    }
  };

  useEffect(() => {
    const handleTogglePdf = () => setShowPdfViewer((current) => !current);
    window.addEventListener("analysis-detail:toggle-pdf", handleTogglePdf);
    return () => window.removeEventListener("analysis-detail:toggle-pdf", handleTogglePdf);
  }, []);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("analysis-detail:pdf-visibility", { detail: { visible: showPdfViewer } }));
  }, [showPdfViewer]);

  useEffect(() => {
    const handleOpenReanalyze = () => {
      if (canReanalyze) {
        setShowReanalyzeModal(true);
      }
    };
    window.addEventListener("analysis-detail:open-reanalyze", handleOpenReanalyze);
    return () => window.removeEventListener("analysis-detail:open-reanalyze", handleOpenReanalyze);
  }, [canReanalyze]);

  useEffect(() => {
    const handleOpenChecklist = () => {
      if (hasTracking) {
        navigate(`/analysis/${analysisId}/checklist`);
      } else if (canStartTracking) {
        void handleStartTracking();
      } else {
        addToast("error", "El seguimiento se puede iniciar una vez que el análisis está completado.");
      }
    };
    window.addEventListener("analysis-detail:open-checklist", handleOpenChecklist);
    return () => window.removeEventListener("analysis-detail:open-checklist", handleOpenChecklist);
  }, [hasTracking, canStartTracking, analysisId, navigate, addToast, handleStartTracking]);

  // Calculado con optional chaining (en vez de después de los early-return de abajo) porque
  // alimenta useBusinessDecisionActions, un hook -- no puede llamarse condicionalmente.
  const businessStatus = resolveBusinessStatus(query.data?.business_status);
  const isPendingDecision = businessStatus === "pendiente_decision";
  const isDecisionOpen = businessStatus === "en_analisis" || isPendingDecision;
  const canStartCategories =
    query.data?.status === "en_revision" &&
    !statusPollingEnabled &&
    isDecisionOpen &&
    (query.data?.categories_decision !== "rejected" || isPendingDecision);
  const pendingActionText = getPendingActionText(businessStatus);

  const handleCategoriesDecision = async (decision: CategoriesDecision) => {
    try {
      const response = await categoriesDecisionMutation.mutateAsync({ analysisId, decision });

      queryClient.setQueryData<AnalysisDetail | undefined>(["analysis", analysisId, "detail"], (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          categories_decision: response.decision,
          categories_decision_by_name: response.decision_by_name,
          categories_decision_at: response.decision_at,
          business_status: decision === "approved" ? "en_revision" : "no_aprobada",
        };
      });
      void queryClient.invalidateQueries({ queryKey: businessStateQueryKey(analysisId) });

      if (decision === "approved") {
        const queuedStatus: AnalysisStatusResponse = {
          id: analysisId,
          status: "queued",
          current_stage: "queued",
          progress_percentage: 0,
          stage_progress: "En cola",
        };

        queryClient.setQueryData(["analysis", analysisId, "status"], queuedStatus);
        setRedirectToCategoriesOnAnalyze(true);
        setStatusPollingEnabled(true);
        addToast("success", "Análisis de categorías iniciado.");
      } else {
        addToast("success", "Decisión registrada: no se van a analizar las categorías restantes.");
      }
    } catch {
      addToast(
        "error",
        decision === "approved"
          ? "No se pudo iniciar el análisis de categorías."
          : "No se pudo registrar el rechazo.",
      );
    }
  };

  // Misma logica de aprobar/rechazar que usa EstadoTab (useBusinessDecisionActions), para que
  // el panel de decision de Preview sea exactamente el mismo componente y comportamiento --
  // bug real 2026-09-29: antes cada tab tenia su propio panel con texto distinto.
  const previewDecisionActions = useBusinessDecisionActions({
    analysisId,
    canStartCategories,
    onApproveCategories: () => handleCategoriesDecision("approved"),
    onRejectCategories: () => handleCategoriesDecision("rejected"),
  });

  if (query.isLoading) {
    return <p className="text-sm text-gray-600">Cargando detalle del análisis...</p>;
  }

  if (query.isError) {
    return <p className="text-sm text-error">No se pudo cargar el detalle del análisis.</p>;
  }

  if (!query.data) {
    return <p className="text-sm text-gray-600">No hay datos de análisis disponibles.</p>;
  }

  const versions = query.data.versions && query.data.versions.length > 0
    ? query.data.versions
    : [query.data.current_version];
  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? query.data.current_version;
  const versionViewAnalysis = {
    ...query.data,
    tracking: null,
    current_version: selectedVersion,
  };

  const handleReanalyze = async (payload: ReanalyzeRequest) => {
    try {
      const response = await reanalyzeMutation.mutateAsync({ analysisId, payload });

      const queuedStatus: AnalysisStatusResponse = {
        id: analysisId,
        status: "queued",
        current_stage: "queued",
        progress_percentage: 0,
        stage_progress: "En cola",
        reanalysis_type: response.reanalysis_type,
        reanalysis_categories: response.categories,
        reanalysis_started_at: new Date().toISOString(),
      };

      queryClient.setQueryData(["analysis", analysisId, "status"], queuedStatus);
      setShowReanalyzeModal(false);
      setStatusPollingEnabled(true);
      addToast("success", "Reanálisis encolado correctamente.");
    } catch {
      addToast("error", "No se pudo encolar el reanálisis.");
    }
  };

  const primaryDocument = query.data.documents.find((document) => document.is_primary) ?? query.data.documents[0];
  const activeDocumentId = selectedDocumentId ?? selectedCitation?.document_id ?? primaryDocument?.id;
  const activeDocumentName = activeDocumentId
    ? (documentsById.get(activeDocumentId)?.filename ?? selectedCitation?.document_name ?? "Documento")
    : primaryDocument?.filename;
  const activeCitations = selectedCitations.length > 0 ? selectedCitations : selectedCitation ? [selectedCitation] : [];

  const tabs: Tab[] = [
    {
      id: "preview",
      label: "Preview",
      content: (
        <PreviewTab
          analysis={query.data}
          onViewSource={({ citation, citations, sources }) => {
            setSelectedDocumentId(citation.document_id);
            setSelectedCitation(citation);
            setSelectedCitations(citations);
            setSelectedSources(sources);
            setShowPdfViewer(true);
          }}
          decisionLoading={previewDecisionActions.isPending || categoriesDecisionMutation.isPending}
          onApproveDecision={previewDecisionActions.handleApprove}
          onRejectDecision={previewDecisionActions.handleReject}
          categoriesDecision={isPendingDecision ? null : query.data.categories_decision}
          categoriesDecisionByName={query.data.categories_decision_by_name}
          categoriesDecisionAt={query.data.categories_decision_at}
        />
      ),
    },
    {
      id: "categories",
      label: "Categorías",
      content: (
        <CategoryList
          analysis={query.data}
          onViewSource={({ citation, citations, sources }) => {
            setSelectedDocumentId(citation.document_id);
            setSelectedCitation(citation);
            setSelectedCitations(citations);
            setSelectedSources(sources);
            setShowPdfViewer(true);
          }}
        />
      ),
    },
    {
      id: "timeline",
      label: "Timeline",
      content: (
        <TimelineTab
          analysisId={analysisId}
          onViewSource={(documentId, page, fragment, highlightRegions) => {
            const documentName = documentsById.get(documentId)?.filename ?? "Documento";
            setSelectedDocumentId(documentId);
            setSelectedCitation({
              // Sin highlight_regions (análisis viejo, sin recalcular), el PDFViewer navega a la página pero no resalta texto -- ver `timeline/materializer.py::_compute_highlight_regions`.
              text: fragment ?? "",
              page,
              document_id: documentId,
              document_name: documentName,
            });
            setSelectedCitations([]);
            setSelectedSources(
              highlightRegions && highlightRegions.length > 0
                ? [
                    {
                      id: 0,
                      document_id: documentId,
                      document_name: documentName,
                      page,
                      text: fragment ?? "",
                      highlight_regions: highlightRegions,
                    },
                  ]
                : []
            );
            setShowPdfViewer(true);
          }}
        />
      ),
    },
    {
      id: "versions",
      label: "Versiones",
      content: (
        <div className="flex flex-col gap-4" data-testid="versions-tab-content">
          {selectedVersion.id !== query.data.current_version.id ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[rgba(0,153,219,.3)] bg-[rgba(0,153,219,.08)] px-[18px] py-3.5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[10px] bg-[rgba(0,153,219,.16)] text-[#0099DB]">
                  <History className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-[13.5px] font-semibold text-[#003C6B]">
                    Estás viendo la versión {selectedVersion.version_number}
                  </p>
                  <p className="mt-0.5 text-xs text-[rgba(0,60,107,.6)]">
                    Esta versión es solo de lectura. Los cambios se hacen sobre la versión actual.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedVersionId(query.data.current_version.id)}
                className="inline-flex h-8 flex-shrink-0 items-center whitespace-nowrap rounded-full border-0 bg-[#003C6B] px-3.5 text-[12.5px] font-semibold text-white hover:bg-[#0099DB]"
              >
                Volver a la versión actual
              </button>
            </div>
          ) : null}

          <VersionHistoryTab
            versions={versions}
            currentVersionId={query.data.current_version.id}
            selectedVersionId={selectedVersion.id}
            onSelectVersion={setSelectedVersionId}
          />

          <div className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-5" data-testid="version-detail-panel">
            <p className="mb-3 font-display text-sm font-semibold text-[#003C6B]">
              Vista histórica · Versión {selectedVersion.version_number}
            </p>
            <CategoryList
              analysis={versionViewAnalysis}
              onViewSource={({ citation, citations, sources }) => {
                setSelectedDocumentId(citation.document_id);
                setSelectedCitation(citation);
                setSelectedCitations(citations);
                setSelectedSources(sources);
                setShowPdfViewer(true);
              }}
            />
          </div>
        </div>
      ),
    },
    {
      id: "estado",
      label: "Estado",
      content: (
        <EstadoTab
          analysisId={analysisId}
          businessStatus={query.data.business_status}
          canStartCategories={canStartCategories}
          historyBelow={showPdfViewer}
          categoriesDecisionLoading={categoriesDecisionMutation.isPending}
          onApproveCategories={() => handleCategoriesDecision("approved")}
          onRejectCategories={() => handleCategoriesDecision("rejected")}
        />
      ),
    },
  ];

  const summary = getAnalysisSummary(query.data);
  const previewCategory = query.data.current_version.extracted_data.preview_criterios;
  const previewFound = previewCategory?.items.filter((item) => item.field_state === "extraido").length ?? 0;
  const previewNotFound = previewCategory?.items.filter((item) => item.field_state === "no_encontrado").length ?? 0;
  const previewReview = previewCategory?.items.filter((item) => item.field_state === "en_conflicto").length ?? 0;
  const previewCount = previewFound + previewNotFound + previewReview;

  const timelineEvents = timelineQuery.data ?? [];
  const activeTimelineEvents = timelineEvents.filter((e) => !e.deleted && !e.hidden);
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const completedTimelineCount = activeTimelineEvents.filter(
    (e) => e.event_date !== null && e.event_date < todayIso,
  ).length;
  const nextTimelineEvent = [...activeTimelineEvents]
    .filter((e) => e.event_date !== null && e.event_date >= todayIso)
    .sort((a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime())[0];
  const formatShortDate = (isoDate: string) => {
    const [, month, day] = isoDate.split("-");
    return `${day}/${month}`;
  };
  const timelineHint =
    activeTimelineEvents.length === 0
      ? "Sin hitos cargados todavía"
      : `${activeTimelineEvents.length} hitos · ${completedTimelineCount} cumplidos${
          nextTimelineEvent ? ` · próximo: ${nextTimelineEvent.name} ${formatShortDate(nextTimelineEvent.event_date!)}` : ""
        }`;

  const tabHint =
    activeTab === "preview"
      ? `Objeto + criterios · ${previewFound} encontrados · ${previewNotFound} no encontrados · ${previewReview} a revisar`
      : activeTab === "categories"
        ? `Fase Preview completa · ${summary.extractedCategories}/${summary.totalCategories} categorías extraídas`
        : activeTab === "timeline"
          ? timelineHint
          : activeTab === "estado"
            ? (pendingActionText ?? "Recorrido y resultado de la licitación")
            : "Comparación histórica de versiones";

  const tabCounters: Record<string, string> = {
    preview: String(previewCount),
    categories: `${summary.extractedCategories}/${summary.totalCategories}`,
    timeline: String(activeTimelineEvents.length),
    versions: String(versions.length),
  };

  const activeTabContent = tabs.find((tab) => tab.id === activeTab)?.content ?? tabs[0]?.content;

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div data-testid="detail-summary-panel">
        <AnalysisDetailHeader
          analysis={query.data}
          isEditingPresupuesto={patchAnalysisMutation.isPending}
          onOpenEstado={() => setActiveTab("estado")}
          onEditPresupuesto={async (payload) => {
            try {
              await patchAnalysisMutation.mutateAsync(payload);
              await queryClient.invalidateQueries({ queryKey: ["analysis", analysisId, "detail"] });
              await queryClient.invalidateQueries({ queryKey: ["analyses"] });
              addToast("success", "Presupuesto oficial actualizado manualmente.");
            } catch {
              addToast("error", "No se pudo actualizar el presupuesto oficial.");
              throw new Error("manual_budget_patch_failed");
            }
          }}
          onViewSource={({ citation, citations, sources }) => {
            setSelectedDocumentId(citation.document_id);
            setSelectedCitation(citation);
            setSelectedCitations(citations);
            setSelectedSources(sources);
            setShowPdfViewer(true);
          }}
        />
      </div>

      <div className="flex min-w-0 flex-col gap-6 xl:flex-row">
        <div
          data-testid="analysis-content-panel"
          className={`min-w-0 w-full flex flex-col gap-4 ${
            showPdfViewer ? "xl:w-[60%]" : "xl:w-full"
          }`}
        >
          {statusPollingEnabled ? (
            <div data-testid="categories-progress-panel">
              {statusPolling.data ? (
                <AnalysisProgress analysisId={analysisId} status={statusPolling.data} />
              ) : (
                <div className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-4 py-3">
                  <p className="text-sm text-[rgba(0,60,107,.68)]">Consultando progreso del análisis...</p>
                </div>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav
              aria-label="Tabs"
              className="inline-flex gap-1 rounded-full border border-[rgba(0,60,107,.12)] bg-white p-1"
            >
              {tabs.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    aria-current={isActive ? "page" : undefined}
                    aria-label={tab.label}
                    className={[
                      "inline-flex h-[34px] items-center gap-2 rounded-full px-4 text-[13px] font-semibold transition-colors",
                      isActive
                        ? "bg-[#003C6B] text-white"
                        : "bg-transparent text-[#003C6B] hover:bg-[#F4F9FC]",
                    ].join(" ")}
                  >
                    <span>{tab.label}</span>
                    {tab.id === "estado" ? (
                      pendingActionText ? (
                        <span
                          role="img"
                          aria-label="Acción pendiente"
                          title={pendingActionText}
                          data-testid="estado-pending-dot"
                          className={[
                            "inline-block h-2 w-2 rounded-full",
                            isActive ? "bg-[#7FF3DE]" : "bg-[#A966FF]",
                          ].join(" ")}
                        />
                      ) : null
                    ) : (
                      <span
                        className={[
                          "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold",
                          isActive
                            ? "bg-[rgba(255,255,255,.18)] text-[#7FF3DE]"
                            : "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]",
                        ].join(" ")}
                      >
                        {tabCounters[tab.id] ?? "0"}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>
            <span className="text-[13px] text-[rgba(0,60,107,.68)]">{tabHint}</span>
          </div>

          {activeTabContent}
        </div>

        {showPdfViewer ? (
          <aside
            data-testid="pdf-viewer-panel"
            className="min-w-0 w-full overflow-hidden rounded-2xl border border-[rgba(0,60,107,.12)] bg-white xl:sticky xl:top-4 xl:h-[calc(100vh-2rem)] xl:w-[40%] xl:min-w-[320px]"
          >
            {activeDocumentId ? (
              <PDFViewer
                documentId={activeDocumentId}
                documentName={activeDocumentName ?? "Documento"}
                citations={activeCitations}
                documents={query.data.documents}
                focusCitation={selectedCitation}
                sources={selectedSources}
                onClose={() => setShowPdfViewer(false)}
              />
            ) : (
              <p className="p-4 text-sm text-gray-600">No hay documentos disponibles para este análisis.</p>
            )}
          </aside>
        ) : null}
      </div>

      {showReanalyzeModal ? (
        <ReanalyzeModal
          open={showReanalyzeModal}
          isSubmitting={reanalyzeMutation.isPending}
          onCancel={() => setShowReanalyzeModal(false)}
          onConfirm={handleReanalyze}
        />
      ) : null}
    </section>
  );
}
