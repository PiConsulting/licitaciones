import { isAxiosError } from "axios";
import { useState } from "react";

import { DuplicateWarningModal } from "../../components/analysis/DuplicateWarningModal";
import { Button } from "../../components/Button";
import { UploadProgress } from "../../components/upload/UploadProgress";
import { useDocumentUpload } from "../../hooks/useDocumentUpload";
import type { DuplicateDecision, DuplicateWarning } from "../../types/analysis";
import type { DocumentWarning } from "../../types/document";
import type { UploadedFile } from "../../types/upload";

interface Step3ConfirmationProps {
  files: UploadedFile[];
  primaryIndex: number;
  onBack: () => void;
  onContinueToStart: (analysisId: string, initialDecisions: DuplicateDecision[]) => void;
}

export function Step3Confirmation({ files, primaryIndex, onBack, onContinueToStart }: Step3ConfirmationProps) {
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<DocumentWarning[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateWarning[]>([]);
  const [pendingAnalysisId, setPendingAnalysisId] = useState<string | null>(null);

  const { mutateAsync, isPending } = useDocumentUpload();

  const handleStartAnalysis = async () => {
    setError(null);
    try {
      const response = await mutateAsync({
        files: files.map((item) => item.file),
        primaryFileIndex: primaryIndex,
      });
      setWarnings(response.warnings);

      // Se detectan duplicados apenas se sube el archivo (ya está en blob y
      // hasheado en este punto) — no hay que esperar al paso 4 para avisar.
      if (response.requires_resolution) {
        setDuplicates(response.duplicates);
        setPendingAnalysisId(response.id);
        return;
      }

      onContinueToStart(response.id, []);
    } catch (uploadError) {
      if (isAxiosError(uploadError)) {
        const message = uploadError.response?.data?.error?.message;
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
      <h2 className="text-lg font-semibold text-gray-900">Paso 3: Confirmación</h2>
      <p className="text-sm text-gray-600">Revisá y comenzá el análisis de documentos.</p>

      <ul className="space-y-2">
        {files.map((file, index) => (
          <li key={file.id} className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700">
            {file.file.name}
            {index === primaryIndex ? " (Principal)" : ""}
          </li>
        ))}
      </ul>

      <UploadProgress uploading={isPending} />

      {warnings.length > 0 ? (
        <div className="space-y-2">
          {warnings.map((warning) => (
            <p key={warning.filename} className="rounded-md border border-warning bg-warning-light p-3 text-sm text-amber-800">
              {warning.message}
            </p>
          ))}
        </div>
      ) : null}

      {error ? <p className="text-sm text-error">{error}</p> : null}
      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={isPending}>
          Volver
        </Button>
        <Button type="button" onClick={handleStartAnalysis} loading={isPending}>
          Continuar
        </Button>
      </div>

      {pendingAnalysisId && duplicates.length > 0 ? (
        <DuplicateWarningModal
          duplicates={duplicates}
          onCancel={() => {
            setPendingAnalysisId(null);
            setDuplicates([]);
          }}
          onConfirm={(decisions) => {
            onContinueToStart(pendingAnalysisId, decisions);
          }}
        />
      ) : null}
    </section>
  );
}
