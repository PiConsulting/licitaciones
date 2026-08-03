import type { UploadedFile } from "../../types/upload";
import { DocumentListItem } from "./DocumentListItem";

interface DocumentListProps {
  files: UploadedFile[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

export function DocumentList({ files, selectedIndex, onSelect }: DocumentListProps) {
  return (
    <div className="space-y-3" aria-label="Lista de documentos para designar principal">
      {files.map((item, index) => (
        <DocumentListItem
          key={item.id}
          item={item}
          selected={selectedIndex === index}
          onSelect={() => onSelect(index)}
        />
      ))}
    </div>
  );
}
