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
    // MVP: un solo archivo por análisis (ver types/upload.ts MVP_MAX_FILES).
    // El backend y el resto del wizard siguen soportando multi-archivo.
    multiple: false,
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
        "flex min-h-[240px] w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-6 text-center transition-all duration-150",
        isDragActive && "scale-[1.02] border-solid border-primary bg-primary-light",
      )}
    >
      <input {...getInputProps()} aria-label="Seleccionar archivos PDF" />
      <Upload data-testid="upload-icon" size={28} className="text-gray-600" aria-hidden="true" />
      <p className="text-sm text-gray-600">Arrastrá tu PDF acá o hacé clic para seleccionar</p>
      <p className="text-xs text-gray-500">Un archivo por análisis, máximo 50 MB</p>
    </div>
  );
}
