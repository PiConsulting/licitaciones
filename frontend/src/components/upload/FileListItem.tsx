import { Check, FileText, Loader2, Trash2 } from "lucide-react";

import type { UploadedFile } from "../../types/upload";

interface FileListItemProps {
  item: UploadedFile;
  onRemove: (id: string) => void;
}

export function FileListItem({ item, onRemove }: FileListItemProps) {
  return (
    <li className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-white p-3">
      <div className="flex min-w-0 items-center gap-3">
        <FileText size={24} className="shrink-0 text-gray-600" aria-hidden="true" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-gray-900">{item.file.name}</p>
          <p className="text-xs text-gray-500">{item.sizeMb} MB</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {item.status === "validating" ? (
          <span className="inline-flex items-center gap-2 text-sm text-gray-500" aria-live="polite">
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            Validando...
          </span>
        ) : (
          <span className="inline-flex items-center gap-2 text-sm text-green-600" aria-live="polite">
            <Check size={16} className="text-success" aria-hidden="true" />
            ✓ Válido — {item.pagesLabel}, {item.sizeMb} MB
          </span>
        )}

        <button
          type="button"
          className="rounded-md p-2 text-gray-400 hover:bg-gray-50 hover:text-gray-700"
          aria-label={`Remover ${item.file.name}`}
          onClick={() => onRemove(item.id)}
        >
          <Trash2 size={20} aria-hidden="true" />
        </button>
      </div>
    </li>
  );
}
