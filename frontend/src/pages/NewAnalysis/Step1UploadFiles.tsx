import { ChevronRight } from "lucide-react";

import { DropZone } from "../../components/upload/DropZone";
import { FileList } from "../../components/upload/FileList";
import { ValidationAlert } from "../../components/upload/ValidationAlert";
import { useFileUpload } from "../../hooks/useFileUpload";
import type { UploadedFile } from "../../types/upload";

interface Step1UploadFilesProps {
  onNext: (files: UploadedFile[]) => void;
}

export function Step1UploadFiles({ onNext }: Step1UploadFilesProps) {
  const { files, messages, canContinue, addFiles, removeFile } = useFileUpload();
  const validFiles = files.filter((file) => file.status === "valid").length;

  return (
    <section className="flex flex-col gap-4" aria-label="Paso 1: Subir archivos">
      <DropZone onFilesSelected={addFiles} />
      <ValidationAlert messages={messages} />
      <FileList files={files} onRemove={removeFile} />

      <div className="flex items-center justify-end gap-3">
        <span className="text-[13px] text-[rgba(0,60,107,.55)]">
          {files.length} archivo{files.length === 1 ? "" : "s"} · {validFiles} válido{validFiles === 1 ? "" : "s"}
        </span>
        <button
          type="button"
          onClick={() => onNext(files)}
          disabled={!canContinue}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-full border-0 bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-[26px] text-sm font-semibold text-white transition-colors hover:bg-[#003C6B] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente
          <ChevronRight size={16} strokeWidth={2.5} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
