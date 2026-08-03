import { isAxiosError } from "axios";
import { useState } from "react";

import { Button } from "../../components/Button";
import { UploadProgress } from "../../components/upload/UploadProgress";
import { useDocumentUpload } from "../../hooks/useDocumentUpload";
import type { DocumentWarning } from "../../types/document";
import type { UploadedFile } from "../../types/upload";

interface Step3ConfirmationProps {
  files: UploadedFile[];
  primaryIndex: number;
  onBack: () => void;
}

export function Step3Confirmation({ files, primaryIndex, onBack }: Step3ConfirmationProps) {
  const [error, setError] = useState<string | null>(null);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<DocumentWarning[]>([]);

  const { mutateAsync, isPending } = useDocumentUpload();

  const handleStartAnalysis = async () => {
    setError(null);
    try {
      const response = await mutateAsync({
        files: files.map((item) => item.file),
        primaryFileIndex: primaryIndex,
      });
      setAnalysisId(response.id);
      setWarnings(response.warnings);
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
      {analysisId ? (
        <p className="text-sm text-green-700">Análisis creado correctamente ({analysisId}) con estado queued.</p>
      ) : null}

      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={isPending}>
          Volver
        </Button>
        <Button type="button" onClick={handleStartAnalysis} loading={isPending}>
          Iniciar análisis
        </Button>
      </div>
    </section>
  );
}
