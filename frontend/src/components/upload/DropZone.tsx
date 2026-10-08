import { Upload } from "lucide-react";
import { useDropzone } from "react-dropzone";

import { cn } from "../../utils/cn";

interface DropZoneProps {
  onFilesSelected: (files: File[]) => void;
}

export function DropZone({ onFilesSelected }: DropZoneProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "application/pdf": [".pdf"],
    },
    multiple: true,
    onDrop: (acceptedFiles, fileRejections) => {
      const rejectedFiles = fileRejections.map((entry) => entry.file);
      onFilesSelected([...acceptedFiles, ...rejectedFiles]);
    },
  });

  return (
    <div
      {...getRootProps()}
      data-testid="dropzone"
      className={cn(
        "flex min-h-[220px] w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-[rgba(0,60,107,.3)] bg-white px-6 text-center transition-all duration-150",
        isDragActive && "border-[#0099DB] bg-[#F4F9FC]",
      )}
    >
      <input {...getInputProps()} aria-label="Seleccionar archivos PDF" />
      <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[linear-gradient(145deg,#0099DB,#2F4EF8)] text-white">
        <Upload data-testid="upload-icon" size={22} aria-hidden="true" />
      </span>
      <p className="text-[15px] font-semibold text-[#003C6B]">Arrastrá tu PDF acá o hacé clic para seleccionar</p>
      <p className="text-xs text-[rgba(0,60,107,.55)]">Hasta 10 archivos por análisis · máximo 50 MB por archivo · solo PDF</p>
    </div>
  );
}
