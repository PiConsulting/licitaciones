import type { ViewerDocument } from "./types";

interface DocumentSelectorProps {
  documents: ViewerDocument[];
  value: string;
  onChange: (documentId: string) => void;
}

export function DocumentSelector({ documents, value, onChange }: DocumentSelectorProps) {
  if (documents.length <= 1) {
    return null;
  }

  return (
    <select
      aria-label="Documento"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-8 max-w-[260px] rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 font-display text-xs font-semibold text-[#003C6B] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0099DB]"
    >
      {documents.map((document) => (
        <option key={document.id} value={document.id}>
          {document.filename}
        </option>
      ))}
    </select>
  );
}
