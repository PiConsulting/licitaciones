interface UploadProgressProps {
  uploading: boolean;
}

export function UploadProgress({ uploading }: UploadProgressProps) {
  if (!uploading) {
    return null;
  }

  return (
    <div className="rounded-md border border-primary bg-primary-light p-3 text-sm text-primary" role="status">
      Subiendo archivos y validando en servidor...
    </div>
  );
}
