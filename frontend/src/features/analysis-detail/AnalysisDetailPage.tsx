import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { AnalysisProgress } from "../../components/analysis/AnalysisProgress";
import { ReanalyzeModal } from "../../components/analysis/ReanalyzeModal";
import { CATEGORY_NAMES, CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CompleteTrackingConfirmModal } from "../../components/analysis/CompleteTrackingConfirmModal";
import { StartTrackingConfirmModal } from "../../components/analysis/StartTrackingConfirmModal";
import { Button } from "../../components/Button";
import { Tabs, Tab } from "../../components/Tabs";
import { useToast } from "../../components/ToastContainer";
import { useAnalysisStatus } from "../../hooks/useAnalysisStatus";
import { useReanalyzeAnalysis } from "../../hooks/useReanalyzeAnalysis";
import { useStartAnalysisCategories } from "../../hooks/useStartAnalysisCategories";
import type { AnalysisStatusResponse, ReanalyzeRequest } from "../../types/analysis";
import { AnalysisSummaryStrip } from "./AnalysisSummaryStrip";
import { CategoryList } from "./CategoryList";
import { AnalysisDetailHeader } from "./AnalysisDetailHeader";
import { PreviewTab } from "./PreviewTab";
import { TimelineTab } from "./TimelineTab";
import { VersionHistoryTab } from "./VersionHistoryTab";
import { TrackingProgressSummary } from "./components/TrackingProgressSummary";
import { useAnalysisDetail } from "./hooks/useAnalysisDetail";
import {
  useCompleteTracking,
  useCreateTrackingComment,
  useDeleteTrackingComment,
  useStartTracking,
  useUpdateTrackingCategoryStatus,
  useUpdateTrackingComment,
  useUpdateTrackingItemStatus,
} from "./hooks/useTrackingMutations";
import type { Citation, NarrativeSource } from "./types";
import { DocumentSelector } from "../pdf-viewer/DocumentSelector";
import { PDFViewer } from "../pdf-viewer/PDFViewer";

interface AnalysisDetailPageProps {
  analysisId: string;
}

function phase2RedirectKey(analysisId: string): string {
  return `analysis:${analysisId}:redirect_to_categories_on_analyze`;
}

export function AnalysisDetailPage({ analysisId }: AnalysisDetailPageProps) {
  const query = useAnalysisDetail(analysisId);
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const startCategoriesMutation = useStartAnalysisCategories();
  const reanalyzeMutation = useReanalyzeAnalysis();
  const startTrackingMutation = useStartTracking();
  const completeTrackingMutation = useCompleteTracking();
  const updateCategoryMutation = useUpdateTrackingCategoryStatus();
  const updateItemMutation = useUpdateTrackingItemStatus();
  const createCommentMutation = useCreateTrackingComment();
  const updateCommentMutation = useUpdateTrackingComment();
  const deleteCommentMutation = useDeleteTrackingComment();

  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedCitations, setSelectedCitations] = useState<Citation[]>([]);
  const [selectedSources, setSelectedSources] = useState<NarrativeSource[]>([]);
  const [showStartTrackingModal, setShowStartTrackingModal] = useState(false);
  const [showCompleteTrackingModal, setShowCompleteTrackingModal] = useState(false);
  const [showReanalyzeModal, setShowReanalyzeModal] = useState(false);
  const [showPdfViewer, setShowPdfViewer] = useState(true);
  const [statusPollingEnabled, setStatusPollingEnabled] = useState(false);
  const [redirectToCategoriesOnAnalyze, setRedirectToCategoriesOnAnalyze] = useState(
    () => sessionStorage.getItem(phase2RedirectKey(analysisId)) === "1",
  );
  const [tabsDefaultTab, setTabsDefaultTab] = useState("preview");
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);

  useEffect(() => {
    if (redirectToCategoriesOnAnalyze) {
      sessionStorage.setItem(phase2RedirectKey(analysisId), "1");
      return;
    }
    sessionStorage.removeItem(phase2RedirectKey(analysisId));
  }, [analysisId, redirectToCategoriesOnAnalyze]);

  const statusPolling = useAnalysisStatus(analysisId, statusPollingEnabled);

  useEffect(() => {
    if (query.data?.status === "analyzed" && redirectToCategoriesOnAnalyze) {
      setTabsDefaultTab("categories");
      setRedirectToCategoriesOnAnalyze(false);
    }
  }, [query.data?.status, redirectToCategoriesOnAnalyze]);

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

    const isTerminal =
      polledStatus === "analyzed" ||
      polledStatus === "en_revision" ||
      polledStatus === "error" ||
      polledStatus === "cancelled" ||
      polledStatus === "validated";
    if (!isTerminal) {
      return;
    }

    let cancelled = false;
    const shouldRedirectToCategories = polledStatus === "analyzed" && redirectToCategoriesOnAnalyze;
    setRedirectToCategoriesOnAnalyze(false);

    // Se espera a que termine el refetch del detalle antes de apagar el
    // polling: si se desmonta el panel de progreso (gateado por
    // `statusPollingEnabled`) antes de que llegue la data nueva, el usuario ve
    // un parpadeo (el panel desaparece y, un instante después, el resto de la
    // página vuelve a moverse cuando el detalle finalmente llega).
    void query.refetch().then(() => {
      if (cancelled) {
        return;
      }
      if (shouldRedirectToCategories) {
        setTabsDefaultTab("categories");
      }
      setStatusPollingEnabled(false);
    });

    return () => {
      cancelled = true;
    };
  }, [query, redirectToCategoriesOnAnalyze, statusPolling.data?.status, statusPollingEnabled]);

  const documentsById = useMemo(() => {
    return new Map((query.data?.documents ?? []).map((document) => [document.id, document]));
  }, [query.data?.documents]);

  if (query.isLoading) {
    return <p className="text-sm text-gray-600">Cargando detalle del análisis...</p>;
  }

  if (query.isError) {
    return <p className="text-sm text-error">No se pudo cargar el detalle del análisis.</p>;
  }

  if (!query.data) {
    return <p className="text-sm text-gray-600">No hay datos de análisis disponibles.</p>;
  }

  const canStartCategories = query.data.status === "en_revision" && !statusPollingEnabled;
  const canReanalyze =
    (query.data.status === "en_revision" ||
      query.data.status === "analyzed" ||
      query.data.status === "validated" ||
      query.data.status === "error") &&
    !statusPollingEnabled;
  const versions = query.data.versions && query.data.versions.length > 0
    ? query.data.versions
    : [query.data.current_version];
  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? query.data.current_version;
  const versionViewAnalysis = {
    ...query.data,
    tracking: null,
    current_version: selectedVersion,
  };

  // Categorías que fase 1 (Preview) todavía no corrió -- se muestran entre
  // paréntesis en el aviso de "Iniciar análisis de categorías" para que quede
  // claro que NO es todo el checklist de nuevo, sólo lo que falta.
  const remainingCategoryNames = CATEGORY_ORDER.filter((categoryId) => {
    const category = query.data?.current_version.extracted_data[categoryId];
    return !category || category.extraction_status === "not_analyzed";
  }).map((categoryId) => CATEGORY_NAMES[categoryId]);

  const handleStartCategories = async () => {
    try {
      await startCategoriesMutation.mutateAsync({ analysisId });

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
    } catch {
      addToast("error", "No se pudo iniciar el análisis de categorías.");
    }
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

  const canStartTracking =
    (!query.data.tracking && (query.data.status === "analyzed" || query.data.status === "validated")) ||
    query.data.tracking?.status === "completed";
  const isResumeTracking = query.data.tracking?.status === "completed";
  const isTrackingActive = query.data.tracking?.status === "active";

  // Tabs configuration
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
        />
      ),
    },
    {
      id: "categories",
      label: "Categorías",
      content: (
        <>
          {query.data.tracking?.status === "active" ? <TrackingProgressSummary tracking={query.data.tracking} /> : null}
          <AnalysisSummaryStrip analysis={query.data} />
          <CategoryList
            analysis={query.data}
            onViewSource={({ citation, citations, sources }) => {
              setSelectedDocumentId(citation.document_id);
              setSelectedCitation(citation);
              setSelectedCitations(citations);
              setSelectedSources(sources);
              setShowPdfViewer(true);
            }}
            trackingActionLoading={updateCategoryMutation.isPending || createCommentMutation.isPending}
            onChangeTrackingStatus={(categoryKey, status) => {
              void updateCategoryMutation
                .mutateAsync({ analysisId, categoryKey, status })
                .then(() => addToast("success", "Estado de categoría actualizado."))
                .catch(() => addToast("error", "No se pudo actualizar el estado de la categoría."));
            }}
            onChangeTrackingItemStatus={(categoryKey, trackingItemId, status) => {
              void updateItemMutation.mutateAsync({ analysisId, categoryKey, trackingItemId, status });
            }}
            onCreateTrackingComment={async ({ categoryKey, content }) => {
              await createCommentMutation.mutateAsync({ analysisId, categoryKey, content });
              addToast("success", "Comentario guardado.");
            }}
            onUpdateTrackingComment={async ({ categoryKey, commentId, content }) => {
              await updateCommentMutation.mutateAsync({ analysisId, categoryKey, commentId, content });
              addToast("success", "Comentario actualizado.");
            }}
            onDeleteTrackingComment={async ({ categoryKey, commentId }) => {
              await deleteCommentMutation.mutateAsync({ analysisId, categoryKey, commentId });
              addToast("success", "Comentario eliminado.");
            }}
          />
        </>
      ),
    },
    {
      id: "timeline",
      label: "Timeline",
      content: (
        <TimelineTab
          analysisId={analysisId}
          onViewSource={(documentId, page, fragment) => {
            setSelectedDocumentId(documentId);
            setSelectedCitation({
              // `fragment` es el `source_fragment` del evento/plazo (el texto
              // del pliego del que salió) -- sin esto el PDFViewer navega a
              // la página pero no tiene qué texto buscar para resaltar.
              text: fragment ?? "",
              page,
              document_id: documentId,
              document_name: documentsById.get(documentId)?.filename ?? "Documento",
            });
            setSelectedCitations([]);
            setSelectedSources([]);
            setShowPdfViewer(true);
          }}
        />
      ),
    },
    {
      id: "versions",
      label: "Versiones",
      content: (
        <div className="space-y-4" data-testid="versions-tab-content">
          <VersionHistoryTab
            versions={versions}
            currentVersionId={query.data.current_version.id}
            selectedVersionId={selectedVersion.id}
            onSelectVersion={setSelectedVersionId}
          />

          <div className="rounded-md border border-slate-200 bg-slate-50 p-4" data-testid="version-detail-panel">
            <p className="mb-3 text-sm font-semibold text-gray-900">Vista histórica - Versión {selectedVersion.version_number}</p>
            <AnalysisSummaryStrip analysis={versionViewAnalysis} />
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
  ];

  const handleStartTracking = async () => {
    try {
      await startTrackingMutation.mutateAsync({ analysisId });
      addToast("success", isResumeTracking ? "Seguimiento reanudado correctamente." : "Seguimiento iniciado correctamente.");
      setShowStartTrackingModal(false);
    } catch {
      addToast("error", "No se pudo iniciar el seguimiento.");
    }
  };

  const handleCompleteTracking = async () => {
    try {
      await completeTrackingMutation.mutateAsync({ analysisId });
      addToast("success", "Seguimiento finalizado. La vista queda en modo solo lectura.");
      setShowCompleteTrackingModal(false);
    } catch {
      addToast("error", "No se pudo finalizar el seguimiento.");
    }
  };

  return (
    <section className="flex min-w-0 flex-col gap-6">
      <div data-testid="detail-summary-panel" className="-mx-6 -mt-6 border-b border-gray-200 bg-surface px-6 pt-6 pb-4">
        <AnalysisDetailHeader
          analysis={query.data}
          rightActions={
            canReanalyze ? (
              <div className="rounded-md border border-blue-200 bg-blue-50 p-3" data-testid="reanalyze-panel">
                <p className="text-sm text-blue-900">
                  ¿Querés refrescar resultados sin perder historial? Cada reanálisis crea una versión nueva y mantiene
                  intactas las anteriores.
                </p>
                <div className="mt-3">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => setShowReanalyzeModal(true)}
                    disabled={reanalyzeMutation.isPending}
                  >
                    Reanalizar
                  </Button>
                </div>
              </div>
            ) : null
          }
        />
      </div>

      {query.data.documents.length > 1 && activeDocumentId && (
        <div className="rounded-md border border-gray-200 bg-white px-4 py-3" data-testid="attachments-selector-panel">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Archivos adjuntos</p>
          <DocumentSelector
            documents={query.data.documents}
            value={activeDocumentId}
            onChange={(documentId) => setSelectedDocumentId(documentId)}
          />
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-6 xl:flex-row">
        <div
          data-testid="analysis-content-panel"
          className={`min-w-0 w-full rounded-md border border-gray-200 bg-white p-5 ${
            showPdfViewer ? "xl:w-[60%] 2xl:w-[55%]" : "xl:w-full"
          }`}
        >
          {statusPollingEnabled ? (
            <div className="mb-4 rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="categories-progress-panel">
              {statusPolling.data ? (
                <AnalysisProgress analysisId={analysisId} status={statusPolling.data} />
              ) : (
                <p className="text-sm text-gray-600">Consultando progreso del análisis...</p>
              )}
            </div>
          ) : null}

          {canStartCategories ? (
            <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3" data-testid="start-categories-panel">
              <p className="text-sm text-amber-900">
                La fase Preview está completa. Podés iniciar el análisis de las categorías restantes
                {remainingCategoryNames.length > 0 ? ` (${remainingCategoryNames.join(", ")})` : ""} para completar
                el checklist.
              </p>
              <div className="mt-3">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    void handleStartCategories();
                  }}
                  loading={startCategoriesMutation.isPending}
                >
                  Iniciar análisis de categorías restantes
                </Button>
              </div>
            </div>
          ) : null}

          <Tabs
            key={`analysis-tabs-${tabsDefaultTab}`}
            tabs={tabs}
            defaultTab={tabsDefaultTab}
          />
        </div>

        {showPdfViewer ? (
          <aside
            data-testid="pdf-viewer-panel"
            className="min-w-0 w-full rounded-md border border-gray-200 bg-white p-2 text-sm text-gray-600 xl:sticky xl:top-4 xl:h-[calc(100vh-2rem)] xl:w-[40%] 2xl:w-[45%]"
          >
            {activeDocumentId ? (
              <PDFViewer
                documentId={activeDocumentId}
                documentName={activeDocumentName ?? "Documento"}
                citations={activeCitations}
                documents={query.data.documents}
                showDocumentSelector={false}
                focusCitation={selectedCitation}
                sources={selectedSources}
                onClose={() => setShowPdfViewer(false)}
              />
            ) : (
              <p className="p-4">No hay documentos disponibles para este análisis.</p>
            )}
          </aside>
        ) : null}
      </div>

      {!showPdfViewer ? (
        <div className="fixed right-5 bottom-5 z-40 flex flex-col items-end gap-2">
          {canStartTracking ? (
            <Button
              type="button"
              size="sm"
              className="rounded-full px-3 shadow-lg"
              loading={startTrackingMutation.isPending}
              onClick={() => setShowStartTrackingModal(true)}
            >
              {isResumeTracking ? "Abrir seguimiento" : "Iniciar seguimiento"}
            </Button>
          ) : null}
          {isTrackingActive ? (
            <Button
              type="button"
              size="sm"
              className="rounded-full px-3 shadow-lg"
              onClick={() => setShowCompleteTrackingModal(true)}
            >
              Terminar seguimiento
            </Button>
          ) : null}
          <button
            type="button"
            className="rounded-full border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-700 shadow-lg hover:border-primary hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            onClick={() => setShowPdfViewer(true)}
          >
            Mostrar PDF
          </button>
        </div>
      ) : canStartTracking || isTrackingActive ? (
        <div className="fixed right-5 bottom-5 z-40 flex flex-col items-end gap-2">
          {canStartTracking ? (
            <Button
              type="button"
              size="sm"
              className="rounded-full px-3 shadow-lg"
              loading={startTrackingMutation.isPending}
              onClick={() => setShowStartTrackingModal(true)}
            >
              {isResumeTracking ? "Abrir seguimiento" : "Iniciar seguimiento"}
            </Button>
          ) : null}
          {isTrackingActive ? (
            <Button
              type="button"
              size="sm"
              className="rounded-full px-3 shadow-lg"
              onClick={() => setShowCompleteTrackingModal(true)}
            >
              Terminar seguimiento
            </Button>
          ) : null}
        </div>
      ) : null}

      {showStartTrackingModal ? (
        <StartTrackingConfirmModal
          isSubmitting={startTrackingMutation.isPending}
          onCancel={() => setShowStartTrackingModal(false)}
          onConfirm={() => {
            void handleStartTracking();
          }}
        />
      ) : null}

      {showCompleteTrackingModal ? (
        <CompleteTrackingConfirmModal
          isSubmitting={completeTrackingMutation.isPending}
          onCancel={() => setShowCompleteTrackingModal(false)}
          onConfirm={() => {
            void handleCompleteTracking();
          }}
        />
      ) : null}

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
