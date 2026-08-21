import { Button } from "../Button";

interface CompleteTrackingConfirmModalProps {
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CompleteTrackingConfirmModal({
  isSubmitting = false,
  onCancel,
  onConfirm,
}: CompleteTrackingConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Terminar seguimiento</h2>
        <p className="mt-2 text-sm text-gray-600">
          Se guardarán los cambios realizados en categorías, checklist y comentarios. El seguimiento quedará
          finalizado en modo solo lectura.
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Seguir editando
          </Button>
          <Button type="button" onClick={onConfirm} loading={isSubmitting}>
            Confirmar finalización
          </Button>
        </div>
      </div>
    </div>
  );
}
