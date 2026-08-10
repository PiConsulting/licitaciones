import { isAxiosError } from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";

import { AnalysisDeleteConfirmModal } from "../../components/analysis/AnalysisDeleteConfirmModal";
import { DuplicateWarningModal } from "../../components/analysis/DuplicateWarningModal";
import { AnalysisProgress } from "../../components/analysis/AnalysisProgress";
import { Button } from "../../components/Button";
import { useToast } from "../../components/ToastContainer";
import { useAnalysisPolling } from "../../hooks/useAnalysisPolling";
import { useDeleteAnalysis } from "../../hooks/useDeleteAnalysis";
import { useStartAnalysis } from "../../hooks/useStartAnalysis";
import type { AnalysisStatusResponse, DuplicateDecision, DuplicateWarning } from "../../types/analysis";

interface Step4StartAnalysisProps {
  analysisId: string;
  initialDecisions?: DuplicateDecision[];
  onBack: () => void;
}

export function Step4StartAnalysis({ analysisId, initialDecisions = [], onBack }: Step4StartAnalysisProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateWarning[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [analysisName, setAnalysisName] = useState("");

  const startMutation = useStartAnalysis();
  const deleteMutation = useDeleteAnalysis();
  const handleAnalysisCompleted = useCallback(() => {
    addToast("success", "El análisis terminó correctamente.");
  }, [addToast]);

  const polling = useAnalysisPolling(analysisId, pollingEnabled, { onCompleted: handleAnalysisCompleted });
  const canRetryAfterError = polling.data?.status === "error";

  const handleDeleteAnalysis = async () => {
    try {
      await deleteMutation.mutateAsync(analysisId);
      addToast("success", "El análisis con error se eliminó definitivamente.");
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
      addToast("error", "No se pudo eliminar el análisis");
    }
  };

  const startWithDecisions = async (decisions: DuplicateDecision[]) => {
    setError(null);
    const normalizedName = analysisName.trim();
    // Force a fresh polling cycle on every attempt.
    setPollingEnabled(false);
    try {
      const response = await startMutation.mutateAsync({
        analysisId,
        payload: {
          decisions,
          ...(normalizedName ? { analysis_name: normalizedName } : {}),
        },
      });

      if (response.requires_resolution) {
        setDuplicates(response.duplicates);
        setShowModal(true);
        return;
      }

      if (response.redirect_analysis_id) {
        navigate(`/analysis/${response.redirect_analysis_id}`);
        return;
      }

      if (
        response.status === "queued" ||
        response.status === "processing"
      ) {
        const queuedStatus: AnalysisStatusResponse = {
          id: analysisId,
          status: "queued",
          current_stage: "queued",
          progress_percentage: 0,
          stage_progress: "En cola",
        };
        queryClient.setQueryData(["analysis", analysisId, "status"], queuedStatus);

        setShowModal(false);
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
      setError("No se pudo iniciar el análisis");
    }
  };

  return (
    <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-6">
      <h2 className="text-lg font-semibold text-gray-900">Paso 4: Iniciar análisis</h2>
      <p className="text-sm text-gray-600">Confirmá el inicio. Si hay duplicados, vas a poder decidir por cada archivo.</p>

      <div className="space-y-2">
        <label htmlFor="analysis-name" className="text-sm font-medium text-gray-700">
          Nombre del análisis (opcional)
        </label>
        <input
          id="analysis-name"
          type="text"
          maxLength={160}
          value={analysisName}
          onChange={(event) => setAnalysisName(event.target.value)}
          placeholder="Ej: Licitación mantenimiento edilicio 2026"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>

      {polling.isLoading && pollingEnabled ? <p className="text-sm text-gray-600">Consultando estado...</p> : null}
      {polling.error instanceof Error ? <p className="text-sm text-error">{polling.error.message}</p> : null}
      {polling.data ? <AnalysisProgress analysisId={analysisId} status={polling.data} /> : null}

      {error ? <p className="text-sm text-error">{error}</p> : null}

      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={startMutation.isPending || pollingEnabled}>
          Volver
        </Button>
        <div className="flex items-center gap-3">
          {canRetryAfterError ? (
            <button
              type="button"
              aria-label="Eliminar análisis"
              title="Eliminar análisis"
              className="rounded-md border border-gray-200 p-2 text-error transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => setShowDeleteModal(true)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 size={18} aria-hidden="true" />
            </button>
          ) : null}
          <Button
            type="button"
            onClick={() => startWithDecisions(initialDecisions)}
            loading={startMutation.isPending}
            disabled={pollingEnabled && !canRetryAfterError}
          >
            {canRetryAfterError ? "Reintentar análisis" : "Iniciar análisis"}
          </Button>
        </div>
      </div>

      {showModal ? (
        <DuplicateWarningModal
          duplicates={duplicates}
          isSubmitting={startMutation.isPending}
          onCancel={() => setShowModal(false)}
          onConfirm={(decisions) => {
            void startWithDecisions(decisions);
          }}
        />
      ) : null}

      {showDeleteModal ? (
        <AnalysisDeleteConfirmModal
          analysisName={`Análisis ${analysisId.slice(0, 8)}`}
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
