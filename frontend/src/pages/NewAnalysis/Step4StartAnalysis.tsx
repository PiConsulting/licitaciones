import { isAxiosError } from "axios";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { DuplicateWarningModal } from "../../components/analysis/DuplicateWarningModal";
import { AnalysisStatusPolling } from "../../components/analysis/AnalysisStatusPolling";
import { Button } from "../../components/Button";
import { useAnalysisPolling } from "../../hooks/useAnalysisPolling";
import { useStartAnalysis } from "../../hooks/useStartAnalysis";
import type { DuplicateDecision, DuplicateWarning } from "../../types/analysis";

interface Step4StartAnalysisProps {
  analysisId: string;
  onBack: () => void;
}

export function Step4StartAnalysis({ analysisId, onBack }: Step4StartAnalysisProps) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateWarning[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(false);

  const startMutation = useStartAnalysis();
  const polling = useAnalysisPolling(analysisId, pollingEnabled);

  const startWithDecisions = async (decisions: DuplicateDecision[]) => {
    setError(null);
    try {
      const response = await startMutation.mutateAsync({
        analysisId,
        payload: { decisions },
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
        response.status === "extracting_text" ||
        response.status === "indexing" ||
        response.status === "analyzing"
      ) {
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

      <p className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">Análisis ID: {analysisId}</p>

      <AnalysisStatusPolling
        statusData={polling.data}
        isLoading={polling.isLoading && pollingEnabled}
        error={polling.error instanceof Error ? polling.error.message : null}
      />

      {error ? <p className="text-sm text-error">{error}</p> : null}

      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={startMutation.isPending || pollingEnabled}>
          Volver
        </Button>
        <Button
          type="button"
          onClick={() => startWithDecisions([])}
          loading={startMutation.isPending}
          disabled={pollingEnabled}
        >
          Iniciar análisis
        </Button>
      </div>

      {showModal ? (
        <DuplicateWarningModal
          duplicates={duplicates}
          onCancel={() => setShowModal(false)}
          onConfirm={(decisions) => {
            void startWithDecisions(decisions);
          }}
        />
      ) : null}
    </section>
  );
}
