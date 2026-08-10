import { Button } from "../Button";

interface AnalysisDeleteConfirmModalProps {
  analysisName: string;
  isErrorAnalysis: boolean;
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function AnalysisDeleteConfirmModal({
  analysisName,
  isErrorAnalysis,
  isSubmitting = false,
  onCancel,
  onConfirm,
}: AnalysisDeleteConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Confirmar eliminación</h2>
        <p className="mt-2 text-sm text-gray-600">
          {isErrorAnalysis
            ? `Se eliminará definitivamente ${analysisName} de la base de datos y de los recursos asociados.`
            : `Se ocultará ${analysisName} del historial con borrado lógico.`}
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button type="button" variant="danger" onClick={onConfirm} loading={isSubmitting}>
            Eliminar
          </Button>
        </div>
      </div>
    </div>
  );
}