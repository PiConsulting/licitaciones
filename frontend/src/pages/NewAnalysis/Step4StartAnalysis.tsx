import { isAxiosError } from "axios";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Loader2, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cancelAnalysis } from "../../api/analyses";
import { AnalysisDeleteConfirmModal } from "../../components/analysis/AnalysisDeleteConfirmModal";
import { DuplicateWarningModal } from "../../components/analysis/DuplicateWarningModal";
import { useToast } from "../../components/ToastContainer";
import { useAnalysisStatus } from "../../hooks/useAnalysisStatus";
import { useDeleteAnalysis } from "../../hooks/useDeleteAnalysis";
import { useDocumentUpload } from "../../hooks/useDocumentUpload";
import { useStartAnalysis } from "../../hooks/useStartAnalysis";
import type { AnalysisStatusResponse, DuplicateDecision, DuplicateWarning } from "../../types/analysis";
import type { UploadedFile } from "../../types/upload";

interface Step4StartAnalysisProps {
  files: UploadedFile[];
  primaryIndex: number;
  analysisName?: string;
  businessUnit?: string;
  documentsCount?: number;
  primaryDocumentName?: string | null;
  onBack: () => void;
}

const STAGE_INDEX: Record<string, number> = {
  queued: 0,
  extracting_text: 1,
  indexing: 2,
  analyzing: 3,
  consolidating: 4,
  completed: 4,
};

const STAGE_CEILING: Record<string, number> = {
  queued: 15,
  extracting_text: 36,
  indexing: 56,
  analyzing: 80,
  consolidating: 93,
  completed: 100,
};

function getStageTitle(stage: AnalysisStatusResponse["current_stage"] | undefined): string {
  switch (stage) {
    case "extracting_text":
      return "Extrayendo texto";
    case "indexing":
      return "Preparando";
    case "analyzing":
      return "Analizando";
    case "consolidating":
    case "completed":
      return "Consolidando";
    case "queued":
    default:
      return "En cola";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function computePreviewCounts(extractedData: AnalysisStatusResponse["extracted_data"]): {
  found: number;
  notFound: number;
  review: number;
} {
  if (!isRecord(extractedData)) {
    return { found: 0, notFound: 0, review: 0 };
  }

  const rawPreview = extractedData.preview_criterios;
  const items = Array.isArray(rawPreview)
    ? rawPreview
    : isRecord(rawPreview) && Array.isArray(rawPreview.items)
      ? rawPreview.items
      : [];

  let found = 0;
  let notFound = 0;
  let review = 0;

  for (const item of items) {
    if (!isRecord(item)) {
      continue;
    }

    const status = String(item.extraction_status ?? "").toLowerCase();
    if (status === "success") {
      found += 1;
      continue;
    }
    if (status === "not_found" || status === "failed") {
      notFound += 1;
      continue;
    }
    if (status === "partial") {
      review += 1;
    }
  }

  return { found, notFound, review };
}

export function Step4StartAnalysis({
  files,
  primaryIndex,
  analysisName,
  businessUnit,
  documentsCount = 0,
  primaryDocumentName = null,
  onBack,
}: Step4StartAnalysisProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const startedRef = useRef(false);

  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateWarning[]>([]);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [displayedProgress, setDisplayedProgress] = useState(0);

  const uploadMutation = useDocumentUpload();
  const startMutation = useStartAnalysis();
  const deleteMutation = useDeleteAnalysis();

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!analysisId) {
        throw new Error("No hay análisis para cancelar");
      }
      return cancelAnalysis(analysisId);
    },
    onSuccess: (response) => {
      if (analysisId) {
        queryClient.setQueryData(["analysis", analysisId, "status"], response);
      }
    },
  });

  const statusQuery = useAnalysisStatus(analysisId ?? "", pollingEnabled && Boolean(analysisId));
  const statusData = statusQuery.data;

  const isDone = statusData?.status === "analyzed" || statusData?.status === "en_revision";
  const isFailed = statusData?.status === "error" || statusData?.status === "cancelled";
  const isRunning = pollingEnabled && !isDone && !isFailed;
  const isUploading = uploadMutation.isPending && !analysisId;

  const actualProgress = Math.max(0, statusData?.progress_percentage ?? 0);
  const currentStage = statusData?.current_stage ?? "queued";
  const stageCeiling = STAGE_CEILING[currentStage] ?? 93;
  const stageIndex = STAGE_INDEX[currentStage] ?? 0;

  const pct = isDone
    ? 100
    : isFailed
      ? Math.max(actualProgress, displayedProgress, 38)
      : Math.max(actualProgress, displayedProgress);
  const activeIdx = stageIndex;

  const previewCounts = useMemo(() => computePreviewCounts(statusData?.extracted_data ?? null), [statusData?.extracted_data]);
  const titleName =
    analysisName && analysisName.trim()
      ? analysisName.trim()
      : analysisId
        ? `Analisis ${analysisId.slice(0, 8)}`
        : "Nuevo analisis";

  const startWithDecisions = async (targetAnalysisId: string, decisions: DuplicateDecision[]) => {
    setError(null);

    try {
      const response = await startMutation.mutateAsync({
        analysisId: targetAnalysisId,
        payload: { decisions },
      });

      if (response.requires_resolution) {
        setDuplicates(response.duplicates);
        setShowDuplicateModal(true);
        return;
      }

      if (response.redirect_analysis_id) {
        navigate(`/analysis/${response.redirect_analysis_id}`);
        return;
      }

      if (response.status === "queued" || response.status === "processing") {
        queryClient.setQueryData(["analysis", targetAnalysisId, "status"], {
          id: targetAnalysisId,
          status: "queued",
          current_stage: "queued",
          progress_percentage: 0,
          stage_progress: "En cola",
        } satisfies AnalysisStatusResponse);
        setShowDuplicateModal(false);
        setPollingEnabled(true);
      }
    } catch (requestError) {
      if (isAxiosError(requestError)) {
        const message = requestError.response?.data?.error?.message;
        if (typeof message === "string") {
          setError(message);
          return;
        }
      }
      setError("No se pudo iniciar el analisis");
    }
  };

  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    const run = async () => {
      setError(null);
      setDisplayedProgress(0);

      try {
        const createResponse = await uploadMutation.mutateAsync({
          files: files.map((item) => item.file),
          primaryFileIndex: primaryIndex,
          analysisName,
          businessUnit,
        });

        setAnalysisId(createResponse.id);

        await startWithDecisions(createResponse.id, []);
      } catch (requestError) {
        if (isAxiosError(requestError)) {
          const message = requestError.response?.data?.error?.message;
          if (typeof message === "string") {
            setError(message);
            return;
          }
        }
        setError("No se pudo crear o iniciar el analisis");
      }
    };

    void run();
  }, [analysisName, businessUnit, files, primaryIndex, uploadMutation]);

  useEffect(() => {
    if (!isRunning) {
      return;
    }

    const timer = window.setInterval(() => {
      setDisplayedProgress((current) => {
        const floor = Math.max(current, actualProgress);
        const capped = Math.min(stageCeiling, floor);

        if (capped >= stageCeiling) {
          return capped;
        }

        const gap = stageCeiling - capped;
        const step = gap > 24 ? 1.4 : gap > 10 ? 0.9 : 0.45;
        return Math.min(stageCeiling, capped + step);
      });
    }, 350);

    return () => {
      window.clearInterval(timer);
    };
  }, [actualProgress, isRunning, stageCeiling]);

  useEffect(() => {
    if (isDone) {
      setDisplayedProgress(100);
      addToast("success", "El analisis termino correctamente.");
    }
  }, [addToast, isDone]);

  const handleDeleteAnalysis = async () => {
    if (!analysisId) {
      return;
    }

    try {
      await deleteMutation.mutateAsync(analysisId);
      addToast("success", "El analisis con error se elimino definitivamente.");
      await queryClient.invalidateQueries({ queryKey: ["analyses"] });
      navigate("/dashboard");
    } catch (requestError) {
      if (isAxiosError(requestError)) {
        const message = requestError.response?.data?.error?.message;
        if (typeof message === "string") {
          addToast("error", message);
          return;
        }
      }
      addToast("error", "No se pudo eliminar el analisis");
    }
  };

  const statusTitle = useMemo(() => {
    if (isDone) {
      return "Analisis terminado";
    }
    if (isFailed) {
      return "El analisis fallo";
    }
    return `${getStageTitle(statusData?.current_stage)}...`;
  }, [isDone, isFailed, statusData?.current_stage]);

  const statusSub = useMemo(() => {
    if (isUploading) {
      return "Subiendo y validando archivos";
    }
    if (isDone) {
      return "Fase Preview completa. Las categorias restantes se inician desde el detalle.";
    }
    if (isFailed) {
      return statusData?.error_message || "Etapa: extrayendo texto.";
    }
    if (statusData?.current_stage === "analyzing") {
      return "Analizando criterios de preview";
    }
    if (statusData?.stage_progress) {
      return statusData.stage_progress;
    }
    return activeIdx === 3 ? "Analizando criterios de preview" : "Procesando en segundo plano";
  }, [activeIdx, isDone, isFailed, isUploading, statusData?.current_stage, statusData?.error_message, statusData?.stage_progress]);

  return (
    <section aria-label="Paso 4: Resultado" className="flex flex-col gap-5">
      <div className="flex flex-col gap-5 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-[14px]">
            <span
              className={[
                "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
                isDone
                  ? "bg-[#7FF3DE] text-[#003C6B]"
                  : isFailed
                    ? "bg-[#FEE2E2] text-[#DC2626]"
                    : "bg-[#F4F9FC] text-[#0099DB]",
              ].join(" ")}
            >
              {isDone ? (
                <Check size={20} strokeWidth={3} aria-hidden="true" />
              ) : isFailed ? (
                <X size={20} strokeWidth={2.5} aria-hidden="true" />
              ) : (
                <Loader2 size={20} className="animate-spin" aria-hidden="true" />
              )}
            </span>
            <div>
              <h2 className="font-display text-[22px] font-bold leading-[1.15] text-[#003C6B]">{statusTitle}</h2>
              <p className="mt-1 text-sm text-[rgba(0,60,107,.68)]">{statusSub}</p>
            </div>
          </div>
          <span
            className={[
              "font-display text-[36px] font-bold leading-none tracking-[-0.03em]",
              isFailed ? "text-[#DC2626]" : "text-[#003C6B]",
            ].join(" ")}
          >
            {Math.max(0, Math.min(100, Math.round(pct)))}%
          </span>
        </div>

        <div className="h-2 overflow-hidden rounded-full bg-[rgba(0,60,107,.1)]">
          <div
            className={[
              "h-full rounded-full transition-[width] duration-500",
              isFailed ? "bg-[#DC2626]" : "bg-[linear-gradient(90deg,#0099DB,#7FF3DE)]",
            ].join(" ")}
            style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
          />
        </div>

        {isRunning ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-[rgba(0,60,107,.55)]">
              Podes cerrar esta pantalla: el analisis sigue en segundo plano y queda en el Historial.
            </span>
            <button
              type="button"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending || !analysisId}
              className="inline-flex h-9 items-center gap-2 rounded-full border-[1.5px] border-[rgba(220,38,38,.4)] bg-white px-4 text-[13px] font-semibold text-[#DC2626] hover:bg-[#FEE2E2] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <X size={14} aria-hidden="true" />
              {cancelMutation.isPending ? "Cancelando..." : "Cancelar analisis"}
            </button>
          </div>
        ) : null}

        {error ? <p className="text-sm text-error">{error}</p> : null}

        {isFailed ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[rgba(220,38,38,.3)] bg-[#FEF2F2] px-4 py-3">
            <span className="text-[13px] text-[#B91C1C]">
              No se pudo extraer texto del anexo: el PDF parece escaneado sin OCR. Podes reintentar o eliminar el analisis.
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  if (analysisId) {
                    void startWithDecisions(analysisId, []);
                  }
                }}
                disabled={startMutation.isPending || !analysisId}
                className="inline-flex h-9 items-center rounded-full bg-[#003C6B] px-4 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                Reintentar
              </button>
              <button
                type="button"
                aria-label="Eliminar analisis"
                onClick={() => setShowDeleteModal(true)}
                disabled={deleteMutation.isPending || !analysisId}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border-[1.5px] border-[rgba(220,38,38,.4)] bg-white text-[#DC2626] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {isDone ? (
        <div className="flex flex-col gap-5 rounded-2xl bg-[#003C6B] p-6 text-white">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#7FF3DE]">Preview listo</span>
              <h3 className="mt-1.5 font-display text-xl font-bold leading-[1.2]">{titleName}</h3>
              <p className="mt-1.5 text-[13px] text-white/75">
                {businessUnit || "Unidad sin definir"}
                {primaryDocumentName ? ` · ${primaryDocumentName}` : ""}
                {documentsCount > 0 ? ` · ${documentsCount} documento${documentsCount === 1 ? "" : "s"}` : ""}
                {" · "}
                10 criterios de preview y Objeto y Alcance extraidos
              </p>
            </div>
            <div className="flex gap-4">
              <div>
                <div className="font-display text-[28px] font-bold leading-none">{previewCounts.found}</div>
                <div className="mt-1 text-[11px] text-white/75">encontrados</div>
              </div>
              <div>
                <div className="font-display text-[28px] font-bold leading-none text-[#7FF3DE]">{previewCounts.notFound}</div>
                <div className="mt-1 text-[11px] text-white/75">no encontrado</div>
              </div>
              <div>
                <div className="font-display text-[28px] font-bold leading-none text-[#A966FF]">{previewCounts.review}</div>
                <div className="mt-1 text-[11px] text-white/75">a revisar</div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <Link
              to={analysisId ? `/analysis/${analysisId}` : "/dashboard"}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-[#003C6B] hover:bg-[#7FF3DE]"
            >
              Ver preview
              <ChevronRight size={14} aria-hidden="true" />
            </Link>
            <Link
              to="/dashboard"
              className="inline-flex h-11 items-center rounded-full border-2 border-white/40 px-[22px] text-sm font-semibold text-white hover:border-white"
            >
              Ir al historial
            </Link>
          </div>
        </div>
      ) : (
        <div className="flex justify-start">
          <button
            type="button"
            onClick={onBack}
            disabled
            className="inline-flex h-11 cursor-not-allowed items-center rounded-full border-2 border-[rgba(0,60,107,.2)] bg-white px-6 text-sm font-semibold text-[#003C6B] opacity-40"
          >
            Volver
          </button>
        </div>
      )}

      {showDuplicateModal && analysisId ? (
        <DuplicateWarningModal
          duplicates={duplicates}
          isSubmitting={startMutation.isPending}
          onCancel={() => setShowDuplicateModal(false)}
          onConfirm={(decisions) => {
            void startWithDecisions(analysisId, decisions);
          }}
        />
      ) : null}

      {showDeleteModal && analysisId ? (
        <AnalysisDeleteConfirmModal
          analysisName={`Analisis ${analysisId.slice(0, 8)}`}
          isErrorAnalysis
          isSubmitting={deleteMutation.isPending}
          onCancel={() => setShowDeleteModal(false)}
          onConfirm={() => {
            void handleDeleteAnalysis();
          }}
        />
      ) : null}
    </section>
  );
}
