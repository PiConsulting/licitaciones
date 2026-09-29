import { Check, FileText, Loader2, Trash2 } from "lucide-react";

import type { UploadedFile } from "../../types/upload";

interface FileListItemProps {
  item: UploadedFile;
  onRemove: (id: string) => void;
}

export function FileListItem({ item, onRemove }: FileListItemProps) {
  return (
    <li className="flex items-center justify-between gap-4 rounded-xl border border-cedi-navy-12 bg-white px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F4F9FC] text-cedi-celeste" aria-hidden="true">
          <FileText size={18} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-cedi-navy">{item.file.name}</p>
          <p className="mt-0.5 text-xs text-cedi-navy-55">{item.pagesLabel}, {item.sizeMb} MB</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {item.status === "validating" ? (
          <span className="inline-flex items-center gap-2 rounded-full bg-cedi-navy-8 px-2.5 py-1 text-xs font-semibold text-cedi-navy-68" aria-live="polite">
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            Validando…
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#CCFBF1] px-2.5 py-1 text-xs font-semibold text-[#0B6B58]" aria-live="polite">
            <Check size={14} aria-hidden="true" />
            Válido
          </span>
        )}

        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-cedi-navy-55 hover:bg-red-50 hover:text-error"
          aria-label={`Remover ${item.file.name}`}
          onClick={() => onRemove(item.id)}
        >
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
    </li>
  );
}
