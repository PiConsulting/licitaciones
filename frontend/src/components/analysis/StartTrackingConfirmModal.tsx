import { Button } from "../Button";

interface StartTrackingConfirmModalProps {
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function StartTrackingConfirmModal({
  isSubmitting = false,
  onCancel,
  onConfirm,
}: StartTrackingConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Iniciar seguimiento</h2>
        <p className="mt-2 text-sm text-gray-600">
          Se va a activar el seguimiento operativo de esta licitación. Podrás gestionar estados por categoría,
          checklist y comentarios sin modificar la extracción IA original.
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button type="button" onClick={onConfirm} loading={isSubmitting}>
            Iniciar seguimiento
          </Button>
        </div>
      </div>
    </div>
  );
}
