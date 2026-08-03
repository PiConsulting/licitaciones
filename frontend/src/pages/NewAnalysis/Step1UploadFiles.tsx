import { Button } from "../../components/Button";
import { DropZone } from "../../components/upload/DropZone";
import { FileList } from "../../components/upload/FileList";
import { ValidationAlert } from "../../components/upload/ValidationAlert";
import { useFileUpload } from "../../hooks/useFileUpload";

interface Step1UploadFilesProps {
  onNext: () => void;
}

export function Step1UploadFiles({ onNext }: Step1UploadFilesProps) {
  const { files, messages, canContinue, addFiles, removeFile } = useFileUpload();

  return (
    <section className="space-y-4" aria-label="Paso 1: Subir archivos">
      <DropZone onFilesSelected={addFiles} />
      <ValidationAlert messages={messages} />
      <FileList files={files} onRemove={removeFile} />

      <div className="flex justify-end">
        <Button type="button" onClick={onNext} disabled={!canContinue}>
          Siguiente
        </Button>
      </div>
    </section>
  );
}
