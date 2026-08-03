import type { UploadedFile } from "../../types/upload";
import { FileListItem } from "./FileListItem";

interface FileListProps {
  files: UploadedFile[];
  onRemove: (id: string) => void;
}

export function FileList({ files, onRemove }: FileListProps) {
  if (files.length === 0) {
    return null;
  }

  return (
    <ul className="space-y-3" aria-label="Archivos seleccionados">
      {files.map((item) => (
        <FileListItem key={item.id} item={item} onRemove={onRemove} />
      ))}
    </ul>
  );
}
